"""Consistent SQLite online backup; retain 14 days. Encryption key backed up separately."""
import os
from pathlib import Path
import sqlite3
import database
import time
from datetime import datetime, timezone

def backup():
    if database.mysql_enabled():
        return mysql_backup()
    source=Path(os.environ.get('DOBHRAP_DB','data/dobhrap.db'))
    if not source.exists(): return
    target=Path(os.environ.get('DOBHRAP_BACKUP_DIR','/var/backups/dobhrap'))
    target.mkdir(parents=True,exist_ok=True,mode=0o700)
    sources=[(source,target)]
    for tenant in (source.parent/'tenants').glob('tenant-*.db'):
        directory=target/tenant.stem;directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        sources.append((tenant,directory))
    for source,target in sources:
        snapshot(source,target)

def snapshot(source,target):
    name='dobhrap-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite3'
    destination=target/name
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:src.backup(dst)
    for file in target.glob('dobhrap-*.sqlite3'):
        if file.stat().st_mtime<time.time()-14*86400:file.unlink()
def mysql_backup():
    """One InnoDB snapshot across all workspace schemas; no credentials in argv."""
    import gzip
    target=Path(os.environ.get('DOBHRAP_BACKUP_DIR','/var/backups/dobhrap'))
    target.mkdir(parents=True,exist_ok=True,mode=0o700)
    destination=target/('dobhrap-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.mysql.sql.gz')
    temporary=destination.with_suffix('.partial')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'wb') as raw, gzip.open(raw,'wt',encoding='utf-8') as output, database.connect() as db:
            prefix=database.config().get('prefix','dobhrap')
            schemas=[r['SCHEMA_NAME'] for r in db._query('SELECT SCHEMA_NAME FROM information_schema.SCHEMATA') if r['SCHEMA_NAME'].startswith(prefix+'_')]
            db._query('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            db._query('START TRANSACTION WITH CONSISTENT SNAPSHOT')
            output.write('SET FOREIGN_KEY_CHECKS=0;\n')
            for schema in sorted(schemas):
                if not __import__('re').fullmatch(r'[a-z0-9_]+',schema):raise RuntimeError('Invalid schema')
                output.write('CREATE DATABASE IF NOT EXISTS `'+schema+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;\nUSE `'+schema+'`;\n')
                with db.raw.cursor() as c:
                    c.execute('SHOW TABLES FROM `'+schema+'`')
                    tables=[next(iter(r.values())) for r in c.fetchall()]
                for table in tables:
                    with db.raw.cursor() as c:
                        c.execute('SHOW CREATE TABLE `'+schema+'`.`'+table+'`')
                        output.write(c.fetchone()['Create Table']+';\n')
                        c.execute('SELECT * FROM `'+schema+'`.`'+table+'`')
                        for row in c:
                            # Generated index columns are recomputed during restore.
                            row={k:v for k,v in row.items() if k!='_open_worker'}
                            output.write('INSERT INTO `'+table+'` ('+','.join('`'+k+'`' for k in row)+') VALUES ('+','.join(db.raw.escape(v) for v in row.values())+');\n')
            output.write('SET FOREIGN_KEY_CHECKS=1;\n')
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    for file in target.glob('dobhrap-*.mysql.sql.gz'):
        if file.stat().st_mtime<time.time()-14*86400:file.unlink()
    return destination

if __name__=='__main__':backup()

