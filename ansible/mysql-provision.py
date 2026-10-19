"""Provision dedicated MySQL container credentials; values never printed."""
import argparse
import json
import os
from pathlib import Path
import secrets
import time
import uuid
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


def main():
    mode=argparse.ArgumentParser();mode.add_argument('action',choices=['prepare','configure']);args=mode.parse_args()
    if args.action=='prepare':
        if not ROOT_ENV.exists():private(ROOT_ENV,'MYSQL_ROOT_PASSWORD='+secrets.token_hex(32)+'\nMYSQL_ROOT_HOST=%\n')
        return
    password=dict(line.split('=',1) for line in ROOT_ENV.read_text().splitlines())['MYSQL_ROOT_PASSWORD']
    for attempt in range(90):
        try:
            c=pymysql.connect(host='127.0.0.1',port=PORT,user='root',password=password,autocommit=True)
            break
        except pymysql.err.OperationalError:time.sleep(2)
    else:raise RuntimeError('Dedicated MySQL server did not become ready')
    with c:
        if APP_CONFIG.exists():raise RuntimeError('MySQL config already exists; inspect previous migration before retrying')
        app_password=secrets.token_hex(32)
        with c.cursor() as cursor:
            cursor.execute('CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s',('dobhrap_app','%',app_password))
            cursor.execute('ALTER USER %s@%s IDENTIFIED BY %s',('dobhrap_app','%',app_password))
            cursor.execute('GRANT ALL PRIVILEGES ON `dobhrap\\_%%`.* TO %s@%s',('dobhrap_app','%'))
        private(APP_CONFIG,json.dumps(dict(host='127.0.0.1',port=PORT,user='dobhrap_app',password=app_password,prefix='dobhrap_m'+uuid.uuid4().hex[:12]))+'\n','dobhrap-app')

if __name__=='__main__':main()
