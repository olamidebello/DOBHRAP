"""Remove an exact domain from competing active nginx server_name directives."""
import datetime
from pathlib import Path
import re
import shutil
import subprocess
import sys


def without_domain(text, domain):
    # Tokenize directives so inline blocks, quoted names and comments are safe.
    token_pattern = r"\#[^\n]*|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s{};#]+|[{};]"
    tokens = [m for m in re.finditer(token_pattern, text) if not m.group().startswith('#')]
    edits = []
    start = True
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if start and token.group() == 'server_name':
            end = index + 1
            while end < len(tokens) and tokens[end].group() not in (';', '{', '}'):
                end += 1
            if end < len(tokens) and tokens[end].group() == ';':
                names = tokens[index + 1:end]
                if any(name.group().strip('\"\'') == domain for name in names):
                    kept = [name.group() for name in names if name.group().strip('\"\'') != domain]
                    edits.append((token.start(), tokens[end].end(), 'server_name ' + ' '.join(kept or ['retired-oob.invalid']) + ';'))
                index = end
        start = tokens[index].group() in (';', '{', '}')
        index += 1
    for left, right, value in reversed(edits):
        text = text[:left] + value + text[right:]
    return text



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
