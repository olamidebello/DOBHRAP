"""Use the running web service's backend, never a leftover SQLite catalog."""
import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys


def runtime(service='oob-business.service', proc_root=Path('/proc')):
    if service not in ('oob-business.service', 'dobhrap.service'):
        raise ValueError('Unsupported application service')
    pid = subprocess.check_output(
        ['systemctl', 'show', service, '--property=MainPID', '--value'], text=True
    ).strip()
    if not pid.isdigit() or int(pid) < 1:
        raise RuntimeError('Application service must be running')
    proc = proc_root / pid
    cwd = (proc / 'cwd').resolve(strict=True)
    command = (proc / 'cmdline').read_bytes().split(b'\0')
    if not any(Path(os.fsdecode(arg)).name == 'app.py' for arg in command if arg):
        raise RuntimeError('Service is not the expected application')
    values = {}
    for entry in (proc / 'environ').read_bytes().split(b'\0'):
        key, sep, value = entry.partition(b'=')
        if sep:
            values[os.fsdecode(key)] = os.fsdecode(value)
    backend = values.get('DOBHRAP_DB_BACKEND', 'sqlite')
    if backend not in ('sqlite', 'mysql'):
        raise RuntimeError('Unsupported database backend')
    if backend == 'sqlite':
        db = Path(values.get('DOBHRAP_DB', 'data/dobhrap.db'))
        if not db.is_absolute():
            db = cwd / db
        if not db.is_file() or db.stat().st_size == 0:
            raise RuntimeError('Existing live database is missing; refusing to create one')
        values['DOBHRAP_DB'] = str(db.resolve())
    else:
        config = Path(values.get('DOBHRAP_MYSQL_CONFIG', '/etc/dobhrap-mysql.json'))
        if not config.is_absolute():
            config = cwd / config
        if not config.is_file():
            raise RuntimeError('Live MySQL configuration is missing')
        values['DOBHRAP_MYSQL_CONFIG'] = str(config.resolve())
    values['DOBHRAP_DB_BACKEND'] = backend
    return cwd, values


def load_active(service='oob-business.service', source=None):
    cwd, values = runtime(service)
    # Remove inherited backend overrides before copying the live process settings.
    for key in list(os.environ):
        if key.startswith('DOBHRAP_'):
            del os.environ[key]
    os.environ.update({k: v for k, v in values.items() if k.startswith('DOBHRAP_')})
    os.chdir(cwd)
    sys.path.insert(0, str(Path(source).resolve() if source else cwd))
    app = importlib.import_module('app')
    app.DB = values.get('DOBHRAP_DB', app.DB)
    return app


def maintain(app, action):
    import password_reset
    import database
    with app.connect() as c:
        # Existing accounts are required; do not bootstrap or replace a catalog.
        if not c.execute('SELECT id FROM users LIMIT 1').fetchone():
            raise RuntimeError('No existing accounts in the live backend')
    if action == 'backup':
        import backup
        os.environ['DOBHRAP_BACKUP_DIR'] = '/var/backups/oob-password-repair'
        backup.backup()
    else:
        with app.connect() as c:
            if action == 'migrate':
                password_reset.initialize(c)
            c.execute('SELECT token_hash,user_id,expires,used,created,delivery FROM password_resets LIMIT 1')
            c.execute('SELECT key,count,started FROM password_reset_limits LIMIT 1')
            c.commit()
    return {'backend': 'mysql' if database.mysql_enabled() else 'sqlite', 'action': action, 'ok': True}


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run as root on the hosting server')
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('backup', 'migrate', 'verify'))
    parser.add_argument('--service', default='oob-business.service')
    parser.add_argument('--source')
    args = parser.parse_args()
    print(json.dumps(maintain(load_active(args.service, args.source), args.action)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Live backend maintenance failed (' + type(error).__name__ + '). No credentials are included in this report.', file=sys.stderr)
        sys.exit(1)
