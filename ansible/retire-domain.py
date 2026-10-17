"""Remove an exact domain from competing active nginx server_name directives."""
import datetime
from pathlib import Path
import re
import shutil
import subprocess
import sys


def without_domain(text, domain):
    def replace(match):
        names = match.group(2).split()
        if domain not in names:
            return match.group(0)
        names = [name for name in names if name != domain]
        return match.group(1) + ' '.join(names or ['retired-oob.invalid']) + ';'
    return re.sub(r'(^[ \t]*server_name\s+)([^;#]+);', replace, text, flags=re.M)


def main():
    domain, managed = sys.argv[1], Path(sys.argv[2]).resolve()
    configuration = subprocess.run(['nginx', '-T'], check=True, capture_output=True, text=True).stdout
    paths = {Path(p).resolve() for p in re.findall(r'^# configuration file (.+):$', configuration, re.M)}
    changes = {}
    for path in paths:
        if path == managed:
            continue
        old = path.read_text()
        new = without_domain(old, domain)
        if old != new:
            changes[path] = (old, new)
    if not changes:
        print('No competing domain entries')
        return
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    backup = Path('/var/backups/dobhrap-nginx') / stamp
    backup.mkdir(parents=True, mode=0o700)
    try:
        for path, (old, new) in changes.items():
            target = backup / str(path).lstrip('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            path.write_text(new)
        subprocess.run(['nginx', '-t'], check=True, capture_output=True)
    except Exception:
        for path, (old, new) in changes.items():
            path.write_text(old)
        raise
    print('Updated %s competing config files; backups: %s' % (len(changes), backup))


if __name__ == '__main__':
    main()
