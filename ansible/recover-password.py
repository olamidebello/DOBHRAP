"""Root-only recovery for an installed MySQL deployment. Never prints the token."""
import argparse
import os
from pathlib import Path
import sys
import tempfile
import time


def issue_recovery(c, email, output, now=None):
    import password_reset
    import advanced
    email=email.strip().lower()
    if len(email)>254 or '@' not in email or any(ch.isspace() for ch in email):
        raise ValueError('Enter a valid account email')
    c.execute('BEGIN IMMEDIATE')
    user=c.execute('SELECT id FROM users WHERE lower(email)=?',(email,)).fetchone()
    if not user:
        raise ValueError('Account not found; no recovery link created')
    token,digest=password_reset.issue(c,user['id'],int(time.time()) if now is None else now)
    c.execute("UPDATE password_resets SET delivery='server-administrator' WHERE token_hash=?",(digest,))
    advanced.audit(c,user['id'],'Server administrator issued account recovery')
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=output.parent,prefix='.oob-recovery-',delete=False) as file:
            temporary=Path(file.name)
            os.chmod(temporary,0o600)
            file.write(password_reset.link(token)+'\n')
            file.flush();os.fsync(file.fileno())
        c.commit()
        os.replace(temporary,output)
    finally:
        if temporary and temporary.exists():temporary.unlink()


def main():
    if os.geteuid()!=0:raise RuntimeError('Run as root on the hosting server')
    parser=argparse.ArgumentParser();parser.add_argument('--email',required=True);args=parser.parse_args()
    if not Path('/etc/dobhrap-mysql.env').is_file():raise RuntimeError('Active MySQL deployment not found')
    os.environ['DOBHRAP_DB_BACKEND']='mysql'
    os.environ['DOBHRAP_MYSQL_CONFIG']='/etc/dobhrap-mysql.json'
    sys.path.insert(0,'/opt/dobhrap/current')
    import app
    with app.connect() as c:issue_recovery(c,args.email,Path('/root/oob-password-reset-link.txt'))
    print('One-time link saved privately. Expires in 15 minutes; the password is unchanged until the link is used.')


if __name__=='__main__':
    try:main()
    except Exception as error:
        # Avoid SQL values, password hashes or reset tokens in Ansible logs.
        print('Recovery failed (%s). Check the account email and installed MySQL deployment.'%type(error).__name__,file=sys.stderr)
        sys.exit(1)
