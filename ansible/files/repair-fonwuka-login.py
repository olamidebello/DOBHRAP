"""One-time, restart-safe repair of the explicitly approved duplicate accounts."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import time


def repair(app, backup_dir):
    import user_data
    import advanced
    if os.environ.get('DOBHRAP_DB_BACKEND', 'sqlite') != 'sqlite':
        raise RuntimeError('This targeted repair requires the confirmed SQLite deployment')
    with app.connect() as c:
        keep = c.execute('SELECT * FROM users WHERE id=4').fetchone()
        old = c.execute('SELECT * FROM users WHERE id=2').fetchone()
        if not keep or keep['email'].lower() not in ('fonwuka1@gmail.com', 'fonwuka@gmail.com') or keep['account_status'] != 'active':
            raise RuntimeError('Account 4 does not match the approved active account')
        tenant = c.execute('SELECT status FROM tenants WHERE id=?', (keep['tenant_id'],)).fetchone()
        if not tenant or tenant['status'] != 'active':
            raise RuntimeError('Account 4 workspace is not active')
        if old and (old['email'].lower() != 'fonwuka@gmail.com' or old['account_status'] not in ('suspended', 'deleting') or old['role'] == 'super_admin'):
            raise RuntimeError('Account 2 does not match the approved suspended duplicate')
        if not old and keep['email'] == 'fonwuka@gmail.com':
            return {'changed': False, 'status': 'already_repaired', 'user_id': 4}
        salt, password_hash = keep['salt'], keep['hash']
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / ('before-login-repair-' + str(time.time_ns()) + '.db')
        with sqlite3.connect(backup) as destination:
            c.backup(destination)
        backup.chmod(0o600)
        if old:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT * FROM users WHERE id=2').fetchone()
            if old['account_status'] == 'suspended':
                user_data.queue(c, old)
            c.commit()
    if old:
        user_data.process(app, 2)
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM users WHERE id=2').fetchone():
            raise RuntimeError('Duplicate removal is pending; email unchanged. Resolve active work before rerunning')
        keep = c.execute('SELECT * FROM users WHERE id=4').fetchone()
        if not keep or keep['salt'] != salt or keep['hash'] != password_hash or keep['account_status'] != 'active' or keep['email'].lower() not in ('fonwuka1@gmail.com', 'fonwuka@gmail.com'):
            raise RuntimeError('Account 4 changed during repair; refusing overwrite')
        c.execute("UPDATE users SET email='fonwuka@gmail.com',account_revision=account_revision+1 WHERE id=4")
        c.execute('DELETE FROM sessions WHERE user_id=4')
        c.execute('UPDATE password_resets SET used=1 WHERE user_id=4')
        advanced.audit(c, 0, 'Approved duplicate login repair: removed user 2; retained user 4 and password')
        c.commit()
    return {'changed': True, 'status': 'repaired', 'user_id': 4, 'email': 'fonwuka@gmail.com', 'backup': str(backup)}


if __name__ == '__main__':
    os.umask(0o077)
    sys.path.insert(0, '/opt/dobhrap/current')
    import app
    print(json.dumps(repair(app, Path('/var/backups/dobhrap/login-repair'))))
