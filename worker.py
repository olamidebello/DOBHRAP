"""One durable job per invocation; systemd timer invokes it every minute.
Uncertain external mutations are never automatically retried.
"""
import json
import time
from datetime import date, timedelta
import app
import advanced as a

def recurring(c, today=None):
    today=today or date.today()
    for row in c.execute('SELECT * FROM schedules WHERE active=1 AND next_date<=?',(today.isoformat(),)).fetchall():
        due=date.fromisoformat(row['next_date'])
        # One occurrence per schedule per invocation; catch up without unbounded bursts.
        inserted=c.execute('INSERT OR IGNORE INTO schedule_occurrences(schedule_id,due_date) VALUES(?,?)',(row['id'],due.isoformat())).rowcount
        if inserted:
            payload=json.loads(row['payload']);payload['name']+=' ['+due.isoformat()+']'
            rid=c.execute('INSERT INTO records(module,data) VALUES(?,?)',(row['module'],json.dumps(payload))).lastrowid
            c.execute('UPDATE schedule_occurrences SET record_id=? WHERE schedule_id=? AND due_date=?',(rid,row['id'],due.isoformat()))
            a.audit(c,0,'recurring record generated '+str(rid))
        c.execute('UPDATE schedules SET next_date=? WHERE id=?',((due+timedelta(days=row['interval_days'])).isoformat(),row['id']))

def execute(connect=app.connect, allow_provider=True):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        recurring(c)
        # A crashed or timed-out mutation must be reconciled in provider console, never blindly retried.
        c.execute("UPDATE jobs SET state='uncertain',error='Worker interrupted; reconcile provider before resubmitting' WHERE state='dispatching' AND started_at<?",(int(time.time())-300,))
        job=c.execute("SELECT j.*,w.kind,w.payload,w.creator FROM jobs j JOIN workflows w ON w.id=j.workflow_id WHERE j.state='queued' ORDER BY j.rowid LIMIT 1").fetchone()
        if not job:return False
        c.execute("UPDATE jobs SET state='dispatching',started_at=? WHERE id=?",(int(time.time()),job['id']))
        c.execute("UPDATE workflows SET state='processing',updated=CURRENT_TIMESTAMP WHERE id=?",(job['workflow_id'],))
        c.commit()
        provider_id=None
        try:
            data=a.unseal(job['payload']);kind=job['kind']
            if not allow_provider and (kind.startswith('payroll_') or kind=='efile_submit'):
                raise a.ServiceError('Provider onboarding unavailable for this workspace',503)
            if kind.startswith('payroll_') and data.get('_environment')!=a.settings.get('CHECK_ENV','sandbox'):
                raise a.ServiceError('Payroll environment changed after approval; create a new workflow',503)
            if kind=='efile_submit' and data.get('_gateway')!=a.settings.get('EFILE_GATEWAY_URL',''):
                raise a.ServiceError('E-file gateway changed after approval; create a new workflow',503)
            data={k:v for k,v in data.items() if not k.startswith('_')}
            if kind=='payroll_create':
                result=a.check_api('/payrolls?include_items=true',data,method='POST',idempotency_key=job['id']+'-create')
                provider_id=a.identifier(result['id'],'pay_')
                # Persist provider ID before preview; a preview failure must not create a second payroll.
                c.execute('UPDATE jobs SET provider_id=?,result=? WHERE id=?',(provider_id,a.seal(result),job['id']));c.commit()
                result=a.check_api('/payrolls/'+provider_id+'/preview?include_items=true')
                state='preview_ready' if result.get('preview',{}).get('status')=='succeeded' else 'preview_pending'
            elif kind=='payroll_release':
                provider_id=a.identifier(data['provider_id'],'pay_')
                c.execute('UPDATE jobs SET provider_id=? WHERE id=?',(provider_id,job['id']));c.commit()
                # Provider timestamp guard ensures the second approver approved the same preview.
                current=a.check_api('/payrolls/'+provider_id+'?include_items=true')
                if current.get('preview',{}).get('status')!='succeeded' or current['preview'].get('started_at')!=data['preview_started_at']:
                    raise a.ServiceError('Payroll preview changed; create a new release approval',503)
                result=a.check_api('/payrolls/'+provider_id+'/approve',{'preview_started_at':data['preview_started_at']},method='POST',idempotency_key=job['id']+'-approve')
                state='submitted'
            elif kind=='efile_submit':
                result=a.efile_api('/submissions',{**data,'idempotency_key':job['id']},method='POST',transmit=True)
                provider_id=a.identifier(result['id']);state='submitted'
                # 'Submitted' never implies IRS acceptance. Refresh obtains provider acknowledgement.
            elif kind in ('invoice_post','bill_post'):
                c.execute('BEGIN IMMEDIATE')
                record=c.execute('SELECT * FROM records WHERE id=?',(data['record_id'],)).fetchone()
                if not record or a.hashlib.sha256(record['data'].encode()).hexdigest()!=data['record_hash']:
                    raise a.ServiceError('Source record changed after approval; posting stopped',409)
                debit,credit=('1100','4000') if kind=='invoice_post' else ('5000','2000')
                amount=data['amount_cents']
                journal=app.post_journal(c,data['name'],[{'account':debit,'debit':amount,'credit':0},{'account':credit,'debit':0,'credit':amount}])
                result={'journal_id':journal};state='completed'
            else:raise a.ServiceError('Unknown job type',503)
            c.execute('UPDATE jobs SET state=?,provider_id=?,result=?,finished_at=? WHERE id=?',
                      (state,provider_id,a.seal(result),int(time.time()),job['id']))
            c.execute('UPDATE workflows SET state=?,updated=CURRENT_TIMESTAMP WHERE id=?',(state,job['workflow_id']))
            a.audit(c,0,'workflow processed '+job['workflow_id']+' '+state)
            c.commit()
        except Exception as exc:
            c.rollback()
            # This may be an ambiguous network outcome. No automatic external mutation retries.
            state='blocked' if isinstance(exc,a.ServiceError) and exc.status in (400,409,503) else 'uncertain'
            message=str(exc) if isinstance(exc,a.ServiceError) else 'Processing interrupted; reconcile provider console'
            c.execute('UPDATE jobs SET state=?,error=?,finished_at=? WHERE id=?',(state,message,int(time.time()),job['id']))
            c.execute('UPDATE workflows SET state=?,updated=CURRENT_TIMESTAMP WHERE id=?',(state,job['workflow_id']))
            a.audit(c,0,'workflow stopped '+job['workflow_id']+' '+state)
    return True

def run_all():
    with app.connect() as catalog:
        tenants=[row['id'] for row in catalog.execute("SELECT id FROM tenants WHERE status='active' ORDER BY id")]
    ai_budget=3
    for tenant_id in tenants:
        execute(lambda tid=tenant_id: app.tenant_connect(tid), allow_provider=tenant_id==1)
        with app.connect() as catalog:
            owners={r['id']:dict(r) for r in catalog.execute("SELECT u.* FROM users u JOIN tenants t ON t.id=u.tenant_id WHERE t.status='active' AND u.role!='viewer' AND (u.tenant_id=? OR u.role='super_admin')",(tenant_id,))}
        if ai_budget>0:
            with app.tenant_connect(tenant_id) as private:ai_budget-=app.tax_preparation.process_suggestions(private,owners,ai_budget)


if __name__=='__main__':
    app.init()
    run_all()
