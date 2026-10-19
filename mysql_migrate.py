"""Offline, verified SQLite -> MySQL migration. Never overwrites source files.
Run only while all application and financial worker units are stopped.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
import database


def digest(rows):
    h = hashlib.sha256()
    for row in rows:
        h.update((json.dumps(list(row), ensure_ascii=False, separators=(',', ':')) + '\n').encode())
    return h.hexdigest()


def migrate_file(source, tenant_id, directory):
    if not source.is_file() or source.stat().st_size == 0:
        raise RuntimeError('An existing nonempty source database is required')
    snapshot = directory / ('workspace-%d.sqlite3' % tenant_id)
    fd = os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as original, sqlite3.connect(snapshot) as copied:
        original.backup(copied)
    with sqlite3.connect(snapshot) as src, database.connect(tenant_id=tenant_id, create=True) as dst:
        if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or src.execute('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError('Source database integrity validation failed')
        tables = src.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        if dst._query('SHOW TABLES').fetchone():
            raise RuntimeError('Target schema is not empty; choose a fresh migration prefix')
        for name, sql in tables:
            if not __import__('re').fullmatch(r'[a-z][a-z0-9_]*', name):
                raise RuntimeError('Unsupported table name')
            dst.execute(sql)
        dst._query('SET FOREIGN_KEY_CHECKS=0')
        report = {}
        try:
            for name, _ in tables:
                columns = [r[1] for r in src.execute('PRAGMA table_info("' + name + '")')]
                # Explicitly copy SQLite row order for UUID-keyed job queues.
                dst.columns(name)
                seq = dst._rowids[name]
                names = columns + (['_oob_seq'] if seq == '_oob_seq' else [])
                target = ','.join('`' + n + '`' for n in names)
                placeholders = ','.join(['%s'] * len(names))
                source_columns = ','.join('"' + n + '"' for n in columns)
                cursor = src.execute('SELECT ' + source_columns + (',rowid' if seq == '_oob_seq' else '') + ' FROM "' + name + '" ORDER BY rowid')
                with dst.raw.cursor() as c:
                    while rows := cursor.fetchmany(200):
                        c.executemany('INSERT INTO `' + name + '` (' + target + ') VALUES (' + placeholders + ')', rows)
                expected = digest(src.execute('SELECT ' + source_columns + ' FROM "' + name + '" ORDER BY rowid'))
                # Raw cursor retains original types; normalize MySQL date/time to source strings.
                with dst.raw.cursor() as c:
                    c.execute('SELECT ' + ','.join('`' + n + '`' for n in columns) + ' FROM `' + name + '` ORDER BY `' + seq + '`')
                    actual = digest(tuple(r[n] for n in columns) for r in c)
                if expected != actual:
                    raise RuntimeError('Copied data checksum mismatch: workspace %d table %s' % (tenant_id, name))
                count = src.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0]
                report[name] = {'rows': count, 'sha256': actual}
            for sql, in src.execute("SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"):
                dst.execute(sql)
            dst.commit()
        finally:
            dst._query('SET FOREIGN_KEY_CHECKS=1')
        return report


def migrate(source, backup_dir):
    if not database.mysql_enabled():
        raise RuntimeError('Set DOBHRAP_DB_BACKEND=mysql and a candidate MySQL config')
    source = Path(source).resolve(strict=True)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as c:
        tenants = [r[0] for r in c.execute('SELECT id FROM tenants ORDER BY id')]
    if 1 not in tenants:
        raise RuntimeError('Missing platform workspace')
    sources = {tid: source if tid == 1 else source.parent / 'tenants' / ('tenant-%d.db' % tid) for tid in tenants}
    for p in sources.values():
        if not p.is_file() or p.stat().st_size == 0:
            raise RuntimeError('Registered workspace database missing; migration stopped')
    directory = Path(backup_dir) / datetime.now(timezone.utc).strftime('mysql-migration-%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True, mode=0o700)
    result = {'verified': False, 'workspaces': {}, 'backup_directory': str(directory)}
    for tid, path in sources.items():
        result['workspaces'][str(tid)] = migrate_file(path, tid, directory)
    result['verified'] = True
    path = directory / 'verification.json'
    path.write_text(json.dumps(result, indent=2) + '\n')
    path.chmod(0o600)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--backup-dir', default='/var/backups/dobhrap')
    args = parser.parse_args()
    result = migrate(args.source, args.backup_dir)
    print(json.dumps({'verified': result['verified'], 'workspaces': len(result['workspaces']), 'backup_directory': result['backup_directory']}))
