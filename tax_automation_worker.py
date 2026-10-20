"""Bounded, sequential document analysis. Never submits or files a tax return."""
import fcntl
import os
from pathlib import Path
import app


def run():
    lock_path=Path(app.DB).parent/'tax-analysis.lock'
    with lock_path.open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 0
        with app.connect() as catalog:
            tenants=[r['id'] for r in catalog.execute("SELECT id FROM tenants WHERE status='active' ORDER BY id")]
        for tid in tenants:
            with app.connect() as catalog:
                owners={r['id']:dict(r) for r in catalog.execute("SELECT u.* FROM users u JOIN tenants t ON t.id=u.tenant_id WHERE t.status='active' AND u.role!='viewer' AND (u.tenant_id=? OR u.role='super_admin')",(tid,))}
            with app.tenant_connect(tid) as private:
                if app.tax_analyst.process_analysis(private,owners,1):return 1
        return 0


if __name__=='__main__':run()
