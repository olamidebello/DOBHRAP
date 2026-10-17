"""Local deployment diagnostics. Never emits environment values or credentials."""
import argparse
import datetime
import json
import os
import shlex
from pathlib import Path
import shutil
import socket
import subprocess
from urllib.request import urlopen


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    return result.stdout.strip() if result.returncode == 0 else ''


def probe(port, path):
    try:
        with urlopen('http://127.0.0.1:%d%s' % (port, path), timeout=2) as response:
            return {'status': response.status, 'body': json.loads(response.read(4096))}
    except Exception as exc:
        return {'status': getattr(exc, 'code', 0)}


def owned_ports(pid):
    if not pid or pid == '0':
        return set()
    inodes = set()
    try:
        for fd in Path('/proc/self/fd' if str(pid) == str(os.getpid()) else '/proc/%s/fd' % pid).iterdir():
            try:
                link = fd.readlink().as_posix()
                if link.startswith('socket:['):
                    inodes.add(link[8:-1])
            except OSError:
                pass
    except OSError:
        return set()
    ports = set()
    for table in ('/proc/net/tcp', '/proc/net/tcp6'):
        for line in Path(table).read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] == '0A' and fields[9] in inodes:
                ports.add(int(fields[1].rsplit(':', 1)[1], 16))
    return ports


def select_port(candidates, reusable):
    for port in candidates:
        if port in reusable:
            return port
        with socket.socket() as listener:
            try:
                listener.bind(('127.0.0.1', port))
                return port
            except OSError:
                pass
    raise RuntimeError('No free application port; inspect listeners with ss -ltnp')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repair', action='store_true')
    args = parser.parse_args()
    service = 'oob-business'
    backup = Path('/var/backups/oob-repair') / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    changes = []
    recommendations = []
    # Only touch the dedicated suite units. Never kill a conflicting listener.
    for suffix, script in [('', 'app.py'), ('-worker', 'worker.py'), ('-backup', 'backup.py')]:
        unit = service + suffix + '.service'
        fragment = command('systemctl', 'show', unit, '-p', 'FragmentPath', '--value')
        dropins = command('systemctl', 'show', unit, '-p', 'DropInPaths', '--value').split()
        if fragment:
            if not fragment.startswith('/') or not Path(fragment).is_file():
                raise RuntimeError('Run repair on the Debian hosting server with a working systemd manager')
            text = Path(fragment).read_text()
            if ('/opt/dobhrap/current/' + script) not in text or 'EnvironmentFile=/etc/dobhrap.env' not in text:
                raise RuntimeError('Dedicated unit name already belongs to another application: ' + unit)
        if dropins and not fragment:
            raise RuntimeError('Orphaned dedicated-service overrides require inspection: ' + unit)
        if dropins:
            recommendations.append('Dedicated service has overrides; restore intended command and environment')
        if args.repair:
            for name in dropins:
                source = Path(name)
                if not str(source).startswith(('/etc/systemd/system/', '/run/systemd/system/')):
                    raise RuntimeError('Unexpected vendor override; inspect ' + name)
                destination = backup / source.as_posix().lstrip('/')
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.move(str(source), destination)
                changes.append('Backed up conflicting override for ' + unit)
    pid = command('systemctl', 'show', service + '.service', '-p', 'MainPID', '--value')
    # Reuse a port only when owned by this dedicated unit AND it identifies the suite.
    reusable = {port for port in owned_ports(pid) if probe(port, '/api/identity').get('body', {}).get('application') == 'oob-business-suite'}
    candidates = list(range(18761, 18801))
    saved = Path('/etc/oob-business.port')
    if saved.exists():
        try:
            value = int(saved.read_text().strip())
            if value in candidates:
                candidates.remove(value)
                candidates.insert(0, value)
        except ValueError:
            recommendations.append('Invalid stored port; select a free port')
    port = select_port(candidates, reusable)
    old_health = probe(18081, '/health')
    if old_health['status'] != 200:
        recommendations.append('Original port 18081 does not pass health; use dedicated service on selected free port')
    recommendations.extend([
        'Keep database, encryption key and setup token backups private',
        'Use the same repair playbook for future deployments to retain the selected port',
        'Public API identity, logo and HTTPS must pass before deployment is considered complete',
    ])
    if args.repair:
        mapping = {
            'PLAID_ENV':'plaid_env', 'PLAID_CLIENT_ID':'plaid_client_id',
            'PLAID_SECRET':'plaid_secret', 'PLAID_REDIRECT_URI':'plaid_redirect_uri',
            'DOBHRAP_ENABLE_LIVE_BANKING':'enable_live_banking',
            'CHECK_ENV':'check_env', 'CHECK_API_KEY':'check_api_key',
            'DOBHRAP_ENABLE_LIVE_PAYROLL':'enable_live_payroll',
            'EFILE_GATEWAY_URL':'efile_gateway_url', 'EFILE_GATEWAY_TOKEN':'efile_gateway_token',
            'DOBHRAP_ENABLE_EFILE_TRANSMISSION':'enable_efile_transmission',
        }
        retained = {}
        environment_file = Path('/etc/dobhrap.env')
        if environment_file.exists():
            for line in environment_file.read_text().splitlines():
                key, separator, value = line.partition('=')
                if separator and key in mapping:
                    parts = shlex.split(value)
                    decoded = parts[0] if parts else ''
                    retained[mapping[key]] = decoded == '1' if mapping[key].startswith('enable_') else decoded
        private = Path('/etc/oob-repair-integrations.json')
        fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(retained, stream)
        private.chmod(0o600)
    if args.repair and changes:
        command('systemctl', 'daemon-reload')
    print(json.dumps({'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'verified': False, 'port': port, 'service': service, 'old_health_status': old_health['status'],
                      'changes': changes, 'backup': str(backup) if changes else None,
                      'recommendations': recommendations}))


if __name__ == '__main__':
    main()
