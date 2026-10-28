"""Bounded loading diagnostics and reversible fixes for managed business vhosts."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

DOMAIN = 'olamideolatayobello.com'
FILES = [Path('/etc/nginx/conf.d/00-oob-hardfix.conf'), Path('/etc/nginx/sites-available') / DOMAIN]


def optimize(text):
    # The recovery header was clearing browser caches on every request.
    text = re.sub(r'^\s*add_header\s+Clear-Site-Data\s+[^;]*;\s*$', '', text, flags=re.M)
    if not re.search(r'^\s*gzip\s', text, re.M):
        text = re.sub(r'\bserver\s*\{', 'server {\n gzip on;\n gzip_vary on;\n gzip_min_length 1024;\n gzip_comp_level 4;\n gzip_types text/css application/javascript text/javascript application/json application/manifest+json image/svg+xml;', text)
    return text


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30)


def measure():
    results = []
    for path in ('/', '/contracting.js', '/api/setup/status'):
        result = subprocess.run(['curl', '--silent', '--show-error', '--fail', '--noproxy', '*', '--compressed', '--max-time', '15', '--output', '/dev/null', '--write-out', '%{http_code} %{time_starttransfer} %{time_total} %{size_download}', 'https://' + DOMAIN + path], capture_output=True, text=True, timeout=20)
        results.append({'path': path, 'ok': result.returncode == 0, 'http_ttfb_total_bytes': result.stdout, 'error': result.stderr[:400]})
    return results


def main():
    run('nginx', '-t')
    folder = Path('/var/log/oob-loading') / str(time.time_ns())
    folder.mkdir(parents=True, mode=0o700)
    report = {'before': measure(), 'changed_files': [], 'backup': str(folder)}
    changed = []
    try:
        for index, path in enumerate(FILES):
            if not path.is_file(): continue
            original = path.read_text()
            updated = optimize(original)
            if updated == original: continue
            backup = folder / str(index)
            shutil.copy2(path, backup)
            changed.append((path, backup))
            path.write_text(updated)
            report['changed_files'].append(str(path))
        run('nginx', '-t')
        if changed: run('systemctl', 'reload', 'nginx')
        report['after'] = measure()
        if not all(item['ok'] for item in report['after']):
            raise RuntimeError('HTTPS checks failed; restored original configuration')
        report['status'] = 'applied_and_https_verified'
    except Exception:
        for path, backup in changed: shutil.copy2(backup, path)
        run('nginx', '-t')
        run('systemctl', 'reload', 'nginx')
        report['status'] = 'failed_rolled_back'
        raise
    finally:
        Path('/var/log/oob-loading/report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__': main()
