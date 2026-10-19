"""Provision dedicated MySQL container credentials; values never printed."""
import argparse
import json
import os
from pathlib import Path
import secrets
import time
import uuid
import sys
import subprocess
import pymysql

ROOT_ENV=Path('/etc/dobhrap-mysql-container.env')
APP_CONFIG=Path('/etc/dobhrap-mysql.json')
PORT=int(os.environ.get('OOB_MYSQL_PROVISION_PORT','3307'))

def private(path,content,group=None):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(content)
    if group is not None:
        import grp
        os.chown(path,0,grp.getgrnam(group).gr_gid)
        path.chmod(0o640)


def validate_container():
    result=subprocess.run(['docker','container','inspect','dobhrap-mysql'],capture_output=True,text=True,check=True)
    info=json.loads(result.stdout)[0]
    assert info['Config'].get('Labels',{}).get('app')=='dobhrap-mysql', 'Container label mismatch'
    assert info['Config']['Image']=='mysql:8.4', 'Unexpected MySQL image'
    assert any(m.get('Name')=='dobhrap-mysql-data' and m.get('Destination')=='/var/lib/mysql' for m in info['Mounts']), 'Storage mismatch'
    bindings=info['HostConfig']['PortBindings'].get('3306/tcp',[])
    assert bindings==[{'HostIp':'127.0.0.1','HostPort':'3307'}], 'Unexpected port binding'
    print('Existing dedicated container identity verified')


def main():
    mode=argparse.ArgumentParser();mode.add_argument('action',choices=['prepare','configure','validate-container']);args=mode.parse_args()
    if args.action=='validate-container':
        validate_container();return
    if args.action=='prepare':
        if not ROOT_ENV.exists():private(ROOT_ENV,'MYSQL_ROOT_PASSWORD='+secrets.token_hex(32)+'\nMYSQL_ROOT_HOST=%\n')
        return
    password=dict(line.split('=',1) for line in ROOT_ENV.read_text().splitlines())['MYSQL_ROOT_PASSWORD']
    last_code=None
    for attempt in range(90):
        try:
            c=pymysql.connect(host='127.0.0.1',port=PORT,user='root',password=password,autocommit=True)
            break
        except pymysql.err.OperationalError as error:
            last_code=error.args[0]
            if last_code in (1045,1130):
                raise RuntimeError('Root authentication rejected (MySQL code %s); credentials were not changed' % last_code) from None
            time.sleep(2)
    else:raise RuntimeError('MySQL connection unavailable (last code %s); inspect docker logs for startup errors' % last_code)
    with c:
        if APP_CONFIG.exists():
            candidate=json.loads(APP_CONFIG.read_text())
            prefix=candidate['prefix']
            if not __import__('re').fullmatch(r'dobhrap_[a-z0-9_]+',prefix):raise RuntimeError('Unexpected candidate database prefix')
            with pymysql.connect(host='127.0.0.1',port=PORT,user=candidate['user'],password=candidate['password']) as app:
                with app.cursor() as cursor:
                    cursor.execute('SELECT TABLE_SCHEMA FROM information_schema.TABLES')
                    if any(r[0].startswith(prefix+'_') for r in cursor.fetchall()):
                        raise RuntimeError('Candidate already contains tables; preserve data and inspect its previous migration report')
            print('Existing unused candidate credentials verified; resuming')
            return
        app_password=secrets.token_hex(32)
        with c.cursor() as cursor:
            cursor.execute('CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s',('dobhrap_app','%',app_password))
            cursor.execute('ALTER USER %s@%s IDENTIFIED BY %s',('dobhrap_app','%',app_password))
            cursor.execute('GRANT ALL PRIVILEGES ON `dobhrap\\_%%`.* TO %s@%s',('dobhrap_app','%'))
        private(APP_CONFIG,json.dumps(dict(host='127.0.0.1',port=PORT,user='dobhrap_app',password=app_password,prefix='dobhrap_m'+uuid.uuid4().hex[:12]))+'\n','dobhrap-app')

if __name__=='__main__':
    try:
        main()
    except pymysql.err.MySQLError as error:
        print('MySQL provisioning failed: code %s (%s). Credentials are hidden.' % (error.args[0], type(error).__name__),file=sys.stderr)
        sys.exit(1)
    except (RuntimeError,AssertionError) as error:
        print(str(error),file=sys.stderr);sys.exit(1)
    except Exception as error:
        print('MySQL provisioning failed: %s. Credentials are hidden.' % type(error).__name__,file=sys.stderr)
        sys.exit(1)
