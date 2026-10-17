"""Consistent SQLite online backup; retain 14 days. Encryption key backed up separately."""
import os
from pathlib import Path
import sqlite3
import time
from datetime import datetime, timezone

def backup():
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
if __name__=='__main__':backup()

