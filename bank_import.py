"""Consent-based, workspace-isolated bank imports; never uses bank passwords/cookies."""
import base64
import hashlib
import json
import os
import time
import uuid
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
import advanced as a


def initialize(c):
    columns={r[1] for r in c.execute('PRAGMA table_info(bank_items)')}
    for name, definition in [('auto_import','INTEGER NOT NULL DEFAULT 0'),('statements_consent','INTEGER NOT NULL DEFAULT 0'),('last_sync','INTEGER NOT NULL DEFAULT 0'),('next_sync','INTEGER NOT NULL DEFAULT 0'),('sync_error',"TEXT NOT NULL DEFAULT ''")]:
        if name not in columns:c.execute('ALTER TABLE bank_items ADD COLUMN '+name+' '+definition)
    c.executescript('''CREATE TABLE IF NOT EXISTS bank_link_sessions (
      nonce TEXT PRIMARY KEY, owner INTEGER NOT NULL, expires INTEGER NOT NULL,
      item_id TEXT, statements_consent INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS bank_statements (
      id TEXT PRIMARY KEY,item_id TEXT NOT NULL,account_id TEXT NOT NULL,
      month INTEGER NOT NULL,year INTEGER NOT NULL,pdf TEXT NOT NULL,
      imported TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);''')


def allowed(tenant_id):
    return tenant_id==1 or os.environ.get('DOBHRAP_ENABLE_TENANT_BANKING')=='1'


def owned(c,item_id,user):
    row=c.execute('SELECT * FROM bank_items WHERE id=? AND active=1',(item_id,)).fetchone()
    if not row:raise a.ServiceError('Active bank connection not found',404)
    if row['owner']!=user['id'] and user['role']!='super_admin':raise a.ServiceError('Only the connection owner can manage this bank',403)
    if row['environment']!=os.environ.get('PLAID_ENV','sandbox'):raise a.ServiceError('Connection environment mismatch',409)
    return row


def pdf_download(secret,statement_id):
    # The provider URL is fixed. Never follow redirects or accept a browser-supplied URL.
    env=os.environ.get('PLAID_ENV','sandbox')
    if env not in ('sandbox','production') or (env=='production' and os.environ.get('DOBHRAP_ENABLE_LIVE_BANKING')!='1'):
        raise a.ServiceError('Banking environment is disabled',503)
    payload={**secret,'statement_id':statement_id,'client_id':os.environ['PLAID_CLIENT_ID'],'secret':os.environ['PLAID_SECRET']}
    req=Request('https://'+env+'.plaid.com/statements/download',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    try:
        with build_opener(a.NoRedirect).open(req,timeout=30) as response:
            raw=response.read(10_000_001)
            if len(raw)>10_000_000 or not raw.startswith(b'%PDF-'):raise a.ServiceError('Invalid or oversized bank statement',502)
            checksum=response.headers.get('Plaid-Content-Hash')
            if checksum and checksum.lower()!=hashlib.sha256(raw).hexdigest():raise a.ServiceError('Statement checksum mismatch',502)
            return raw
    except (HTTPError,URLError,TimeoutError,OSError):raise a.ServiceError('Statement download unavailable; reconnect or check provider access',502) from None


def import_statements(c,row):
    if not row['statements_consent'] or os.environ.get('DOBHRAP_ENABLE_BANK_STATEMENTS')!='1':return 0
    secret=a.unseal(row['secret']);listing=a.plaid('/statements/list',secret);count=0
    for account in listing.get('accounts',[]):
        for statement in account.get('statements',[]):
            sid=a.identifier(statement['statement_id'])
            if c.execute('SELECT 1 FROM bank_statements WHERE id=?',(sid,)).fetchone():continue
            raw=pdf_download(secret,sid)
            c.execute('INSERT OR IGNORE INTO bank_statements(id,item_id,account_id,month,year,pdf) VALUES(?,?,?,?,?,?)',
                      (sid,row['id'],account['account_id'],statement['month'],statement['year'],a.seal({'base64':base64.b64encode(raw).decode()})))
            count+=1
            if count>=10:return count  # Bounded catch-up; remaining files arrive on later runs.
    return count


def sync(c,item_id,statements=True):
    result=a.sync_bank(c,item_id)
    c.commit()  # Transactions remain imported even if optional Statements is unavailable.
    row=c.execute('SELECT * FROM bank_items WHERE id=?',(item_id,)).fetchone()
    try:
        result['statements']=import_statements(c,row) if statements else 0
        error=''
    except a.ServiceError:
        result['statements']=0;error='Transactions imported; statements unavailable. Check Statements access and reconnect.'
    now=int(time.time())
    c.execute('UPDATE bank_items SET last_sync=?,next_sync=?,sync_error=? WHERE id=?',(now,now+900,error,item_id))
    return result


def dispatch(route,method,body,c,user,tenant_id):
    if not route.startswith('bank/'):return None
    provider_routes={'bank/link-token','bank/exchange','bank/reconnect','bank/complete-update','bank/automation','bank/sync','bank/disconnect'}
    if route in provider_routes and not allowed(tenant_id):raise a.ServiceError('Provider onboarding is not configured for this workspace',503)
    if route=='bank/items' and method=='GET':
        return [dict(r) for r in c.execute('SELECT id,owner,environment,active,auto_import,statements_consent,last_sync,next_sync,sync_error FROM bank_items')]
    if route=='bank/statements' and method=='GET':
        return [dict(r) for r in c.execute('SELECT id,item_id,account_id,month,year,imported FROM bank_statements ORDER BY year DESC,month DESC LIMIT 1000')]
    if route=='bank/statement-download' and method=='POST':
        row=c.execute('SELECT pdf FROM bank_statements WHERE id=?',(body.get('id'),)).fetchone()
        if not row:raise a.ServiceError('Statement not found',404)
        return a.unseal(row['pdf'])  # Existing session, CSRF and workspace checks apply.
    if route in ('bank/link-token','bank/reconnect') and method=='POST':
        a.cipher()
        if body.get('consent') is not True:raise a.ServiceError('Bank data consent is required')
        row=owned(c,body.get('item_id'),user) if route=='bank/reconnect' else None
        statements=bool(row['statements_consent']) if row else body.get('statements') is True
        if statements and os.environ.get('DOBHRAP_ENABLE_BANK_STATEMENTS')!='1':raise a.ServiceError('Bank PDF statements are not enabled',503)
        opts={'client_name':'OOB Business','user':{'client_user_id':'tenant-'+str(tenant_id)+'-user-'+str(user['id'])},'country_codes':['US'],'language':'en'}
        if row:opts['access_token']=a.unseal(row['secret'])['access_token']
        else:
            opts['products']=['transactions']+(['statements'] if statements else [])
            if statements:opts['statements']={'start_date':(a.date.today()-a.timedelta(days=90)).isoformat(),'end_date':a.date.today().isoformat()}
        if os.environ.get('PLAID_REDIRECT_URI'):opts['redirect_uri']=os.environ['PLAID_REDIRECT_URI']
        token=a.plaid('/link/token/create',opts)['link_token']
        nonce=uuid.uuid4().hex
        c.execute('DELETE FROM bank_link_sessions WHERE expires<?',(int(time.time()),))
        c.execute('INSERT INTO bank_link_sessions VALUES(?,?,?,?,?)',(hashlib.sha256(nonce.encode()).hexdigest(),user['id'],int(time.time())+1800,row['id'] if row else None,int(statements)))
        return {'link_token':token,'nonce':nonce,'update':bool(row)}
    if route in ('bank/exchange','bank/complete-update') and method=='POST':
        nonce=hashlib.sha256(str(body.get('nonce','')).encode()).hexdigest()
        link=c.execute('SELECT * FROM bank_link_sessions WHERE nonce=? AND owner=? AND expires>?',(nonce,user['id'],int(time.time()))).fetchone()
        if not link:raise a.ServiceError('Bank login expired or belongs to another user/workspace. Start again.',403)
        if bool(link['item_id'])!=(route=='bank/complete-update'):raise a.ServiceError('Invalid bank login completion',409)
        if link['item_id']:
            row=owned(c,link['item_id'],user);item_id=row['id']
        else:
            result=a.plaid('/item/public_token/exchange',{'public_token':body['public_token']})
            item_id=result['item_id']
            c.execute('INSERT INTO bank_items(id,owner,environment,secret,auto_import,statements_consent) VALUES(?,?,?,?,1,?)',
                      (item_id,user['id'],os.environ.get('PLAID_ENV','sandbox'),a.seal({'access_token':result['access_token']}),link['statements_consent']))
        c.execute('DELETE FROM bank_link_sessions WHERE nonce=?',(nonce,))
        c.execute("UPDATE bank_items SET next_sync=0,sync_error='' WHERE id=?",(item_id,))
        a.audit(c,user['id'],'bank consent completed; automatic import authorized')
        c.commit()  # Preserve the exchanged token even if first data extraction is still pending.
        try:result=sync(c,item_id)
        except a.ServiceError:
            c.rollback();c.execute('UPDATE bank_items SET sync_error=? WHERE id=?',('Import pending; scheduled retry or reconnect if login is required.',item_id));result={'pending':True}
        return {'id':item_id,**result}
    if route=='bank/automation' and method=='POST':
        row=owned(c,body.get('item_id'),user)
        if not isinstance(body.get('enabled'),bool):raise a.ServiceError('Choose enable or pause')
        c.execute('UPDATE bank_items SET auto_import=?,next_sync=0 WHERE id=?',(int(body['enabled']),row['id']))
        a.audit(c,user['id'],'bank automatic import '+('enabled' if body['enabled'] else 'paused'))
        return {'enabled':body['enabled']}
    if route=='bank/sync' and method=='POST':
        row=owned(c,body.get('item_id'),user);return sync(c,row['id'])
    if route=='bank/disconnect' and method=='POST':
        row=owned(c,body.get('item_id'),user)
        a.plaid('/item/remove',a.unseal(row['secret']))
        c.execute("UPDATE bank_items SET active=0,auto_import=0,secret='',cursor='',sync_error='' WHERE id=?",(row['id'],))
        c.execute('DELETE FROM bank_link_sessions WHERE item_id=?',(row['id'],))
        a.audit(c,user['id'],'bank connection revoked');return {'disconnected':True}
    return None


def run_all():
    import app
    if os.environ.get('DOBHRAP_ENABLE_AUTO_BANK_IMPORT')!='1':return
    with app.connect() as catalog:
        tenants=[r['id'] for r in catalog.execute("SELECT id FROM tenants WHERE status='active' ORDER BY id")]
    for tid in tenants:
        if not allowed(tid):continue
        with app.tenant_connect(tid) as c:
            items=c.execute('SELECT id FROM bank_items WHERE active=1 AND auto_import=1 AND next_sync<=? ORDER BY next_sync LIMIT 20',(int(time.time()),)).fetchall()
        for item in items:
            with app.tenant_connect(tid) as c:
                now=int(time.time())
                # Commit a lease before network I/O. GUI pause/disconnect and overlapping workers are respected.
                claimed=c.execute('UPDATE bank_items SET next_sync=? WHERE id=? AND active=1 AND auto_import=1 AND next_sync<=?',(now+900,item['id'],now)).rowcount
                c.commit()
                if not claimed:continue
                try:sync(c,item['id'])
                except Exception:
                    c.rollback()
                    c.execute('UPDATE bank_items SET next_sync=?,sync_error=? WHERE id=?',(now+3600,'Import unavailable. Reconnect if bank login or consent expired; otherwise check provider access.',item['id']))


if __name__=='__main__':
    import fcntl
    import app
    # Prevent concurrent timer/manual processes; no credentials are printed.
    with open(os.path.join(os.path.dirname(app.DB),'bank-import.lock'),'w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit(0)
        app.init();run_all()
