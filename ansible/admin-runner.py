"""Root-owned, fixed-operation broker; never accepts commands or paths from the web."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import uuid

DB = '/var/lib/dobhrap/dobhrap.db'
SOURCE = Path('/opt/oob-control')


def run(argv, log, timeout=180):
    subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout,
                   cwd=str(SOURCE))


def main():
    if os.geteuid() != 0:
        raise RuntimeError('The management broker must run as its root-owned systemd service')
    if not Path(DB).exists():
        return
    with sqlite3.connect(DB, timeout=30) as c:
        c.row_factory = sqlite3.Row
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='platform_jobs'").fetchone():
            return
        services = {}
        for name in ('oob-business.service','oob-business-worker.timer','oob-business-backup.timer'):
            result = subprocess.run(['systemctl','is-active',name], capture_output=True, text=True, timeout=15)
            services[name] = result.stdout.strip()
        state = {'checked_at':datetime.now(timezone.utc).isoformat(), 'services':services,
                 'deployment_source_ready':(SOURCE/'ansible/repair-oob.yml').exists()}
        c.execute("INSERT OR REPLACE INTO platform_state VALUES('readiness',?)",(json.dumps(state),))
        c.commit()
        c.execute('BEGIN IMMEDIATE')
        c.execute("UPDATE platform_jobs SET state='uncertain',finished=CURRENT_TIMESTAMP,summary='Previous runner interrupted; inspect root logs before repeating' WHERE state='running'")
        job = c.execute("SELECT p.*,u.role FROM platform_jobs p JOIN users u ON u.id=p.creator WHERE p.state='queued' ORDER BY p.rowid LIMIT 1").fetchone()
        if not job:
            return
        try:
            job_id = str(uuid.UUID(job['id']))
            if job_id != job['id'] or job['role'] != 'super_admin' or job['kind'] not in ('verify','backup','deploy','commission'):
                raise ValueError('Rejected management job')
        except ValueError:
            c.execute("UPDATE platform_jobs SET state='rejected',summary='Invalid management job' WHERE id=?",(job['id'],))
            return
        c.execute("UPDATE platform_jobs SET state='running' WHERE id=?",(job_id,))
        c.commit()
        directory=Path('/var/log/oob-admin');directory.mkdir(mode=0o700,exist_ok=True)
        fd=os.open(directory/(job_id+'.log'),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        status='completed'
        summary='Operation completed successfully'
        try:
            with os.fdopen(fd,'w') as log:
                if job['kind'] in ('deploy','commission'):
                    run(['ansible-playbook','-i','dobhrap,','-c','local',str(SOURCE/'ansible/repair-oob.yml')],log,1200)
                elif job['kind']=='backup':
                    run(['runuser','-u','dobhrap-app','--','/opt/dobhrap/current/venv/bin/python','/opt/dobhrap/current/backup.py'],log)
                else:
                    run(['nginx','-t'],log)
                    for name in services:
                        run(['systemctl','is-active',name],log)
                    run(['systemd-analyze','verify','/etc/systemd/system/oob-business.service','/etc/systemd/system/oob-business-worker.timer','/etc/systemd/system/oob-business-backup.timer'],log)
                    result=subprocess.run(['curl','--fail','--silent','--show-error','--noproxy','*','--resolve','olamideolatayobello.com:443:127.0.0.1','https://olamideolatayobello.com/api/identity'],capture_output=True,text=True,check=True,timeout=30)
                    if json.loads(result.stdout).get('application')!='oob-business-suite':
                        raise ValueError('Application identity did not match')
        except Exception:
            status='failed'
            summary='Operation failed; server administrator can inspect /var/log/oob-admin/'+job_id+'.log'
        c.execute('UPDATE platform_jobs SET state=?,finished=CURRENT_TIMESTAMP,summary=? WHERE id=?',(status,summary,job_id))
        c.commit()


if __name__=='__main__':
    main()
