"""Provider integrations and durable, two-person financial workflows.
No credentials or bank access tokens are returned through APIs or audit records.
"""
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from cryptography.fernet import Fernet

class ServiceError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message); self.status = status

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None

def request_json(url, payload=None, headers=None, method=None):
    # Configured, server-owned hosts only; no URLs supplied by browser callers.
    if not url.startswith('https://'): raise ServiceError('Provider URL must use HTTPS', 503)
    hdr = {'Content-Type': 'application/json', **(headers or {})}
    req = Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                  headers=hdr, method=method)
    try:
        with build_opener(NoRedirect).open(req, timeout=30) as response:
            raw = response.read(4_000_001)
            if len(raw) > 4_000_000: raise ServiceError('Provider response too large', 502)
            return json.loads(raw)
    except HTTPError as exc:
        # Provider responses can contain private data. Never echo or log the body.
        raise ServiceError('Provider rejected request (HTTP %s); inspect provider console' % exc.code, 502) from None
    except (URLError, TimeoutError, ValueError, OSError):
        raise ServiceError('Provider response unavailable; reconcile before resubmitting', 502) from None

def cipher():
    key = os.environ.get('DOBHRAP_ENCRYPTION_KEY', '')
    if not key: raise ServiceError('Configure the persistent encryption key first', 503)
    try: return Fernet(key.encode())
    except ValueError: raise ServiceError('Invalid encryption key configuration', 503) from None

def seal(data): return cipher().encrypt(json.dumps(data).encode()).decode()
def unseal(data): return json.loads(cipher().decrypt(data.encode()))

def cents(value, signed=False):
    try: number = Decimal(str(value))
    except InvalidOperation: raise ServiceError('Invalid monetary amount') from None
    if not number.is_finite() or abs(number) > Decimal('1000000000') or (not signed and number < 0):
        raise ServiceError('Monetary amount outside permitted range')
    return int((number * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def identifier(value, prefix=None):
    value = str(value)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', value) or (prefix and not value.startswith(prefix)):
        raise ServiceError('Invalid provider identifier')
    return value

def audit(c, user, action):
    c.execute('INSERT INTO audit(user_id,action) VALUES(?,?)', (user, action))

def initialize(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS bank_items (
      id TEXT PRIMARY KEY, owner INTEGER NOT NULL, environment TEXT NOT NULL,
      secret TEXT NOT NULL, cursor TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS bank_transactions (
      id TEXT PRIMARY KEY, item_id TEXT NOT NULL, account_id TEXT NOT NULL, date TEXT NOT NULL,
      name TEXT NOT NULL, amount_cents INTEGER NOT NULL, currency TEXT,
      pending INTEGER NOT NULL DEFAULT 0, removed INTEGER NOT NULL DEFAULT 0,
      journal_id INTEGER REFERENCES journals(id), category_account TEXT);
    CREATE TABLE IF NOT EXISTS workflows (
      id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
      creator INTEGER NOT NULL, approver INTEGER, state TEXT NOT NULL DEFAULT 'draft',
      created TEXT DEFAULT CURRENT_TIMESTAMP, updated TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY, workflow_id TEXT UNIQUE REFERENCES workflows(id),
      state TEXT NOT NULL DEFAULT 'queued', provider_id TEXT, result TEXT,
      error TEXT, started_at INTEGER, finished_at INTEGER);
    CREATE TABLE IF NOT EXISTS schedules (
      id TEXT PRIMARY KEY, module TEXT NOT NULL, payload TEXT NOT NULL,
      next_date TEXT NOT NULL, interval_days INTEGER NOT NULL, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS schedule_occurrences (
      schedule_id TEXT NOT NULL, due_date TEXT NOT NULL, record_id INTEGER,
      PRIMARY KEY(schedule_id,due_date));
    ''')
    for a in [('2100', 'Payroll taxes payable', 'liability'), ('2200', 'Wages payable', 'liability')]:
        c.execute('INSERT OR IGNORE INTO accounts VALUES(?,?,?)', a)

def plaid(endpoint, body):
    env = os.environ.get('PLAID_ENV', 'sandbox')
    if env not in ('sandbox', 'production'): raise ServiceError('Invalid Plaid environment', 503)
    if not os.environ.get('PLAID_CLIENT_ID') or not os.environ.get('PLAID_SECRET'):
        raise ServiceError('Plaid credentials are not configured', 503)
    if env == 'production' and os.environ.get('DOBHRAP_ENABLE_LIVE_BANKING') != '1':
        raise ServiceError('Production banking is disabled', 503)
    return request_json('https://' + env + '.plaid.com' + endpoint,
                        {**body, 'client_id': os.environ['PLAID_CLIENT_ID'], 'secret': os.environ['PLAID_SECRET']})

def check_api(endpoint, body=None, method=None, idempotency_key=None):
    env = os.environ.get('CHECK_ENV', 'sandbox')
    if env not in ('sandbox', 'production'): raise ServiceError('Invalid Check environment', 503)
    if env == 'production' and os.environ.get('DOBHRAP_ENABLE_LIVE_PAYROLL') != '1':
        raise ServiceError('Production payroll is disabled', 503)
    if not os.environ.get('CHECK_API_KEY'): raise ServiceError('Check credentials are not configured', 503)
    host = 'sandbox.checkhq.com' if env == 'sandbox' else 'api.checkhq.com'
    headers={'Authorization':'Bearer '+os.environ['CHECK_API_KEY'],'Check-Version':'2025-01-01'}
    if idempotency_key:headers['X-Idempotency-Key']=idempotency_key
    return request_json('https://' + host + endpoint,body,headers,method)

def efile_api(endpoint, body=None, method=None, transmit=False):
    base = os.environ.get('EFILE_GATEWAY_URL', '').rstrip('/')
    if not base or not os.environ.get('EFILE_GATEWAY_TOKEN'):
        raise ServiceError('No authorized e-file gateway configured; direct IRS transmission is not implemented', 503)
    if transmit and os.environ.get('DOBHRAP_ENABLE_EFILE_TRANSMISSION') != '1':
        raise ServiceError('E-file transmission is disabled', 503)
    return request_json(base + endpoint, body, {'Authorization': 'Bearer ' + os.environ['EFILE_GATEWAY_TOKEN']}, method)

# Federal ordinary-income estimates only. Source: IRS Rev. Proc. 2025-32, section 4.01.
BRACKETS = {
 'single': [12400,50400,105700,201775,256225,640600],
 'married_joint': [24800,100800,211400,403550,512450,768700],
 'married_separate': [12400,50400,105700,201775,256225,384350],
 'head_household': [17700,67450,105700,201750,256200,640600],
}
DEDUCTIONS = {'single':16100,'married_joint':32200,'married_separate':16100,'head_household':24150}
def estimate_tax(body):
    if str(body.get('year')) != '2026': raise ServiceError('Only the versioned 2026 estimate is supported')
    status = body.get('filing_status')
    if status not in BRACKETS: raise ServiceError('Unsupported filing status')
    # Keep estimates separate from validated returns and provider filing packages.
    taxable = max(0, cents(body['ordinary_income']) - DEDUCTIONS[status] * 100)
    lower = 0; tax = Decimal(0)
    for upper, rate in zip([x*100 for x in BRACKETS[status]] + [10**15], ['.10','.12','.22','.24','.32','.35','.37']):
        tax += Decimal(max(0, min(taxable, upper) - lower)) * Decimal(rate)
        lower = upper
    result = int(tax.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return {'year':2026,'taxable_income_cents':taxable,'ordinary_income_tax_cents':result,
            'standard_deduction_cents':DEDUCTIONS[status]*100,'status':'estimate_only',
            'source':'https://www.irs.gov/pub/irs-drop/rp-25-32.pdf',
            'exclusions':'Not a return calculation. Excludes credits, capital gains, AMT, self-employment, state/local taxes and special deduction eligibility. Not payroll withholding.'}

def validate_workflow(c, kind, body):
    if kind == 'payroll_create':
        start, end, payday = (date.fromisoformat(body[k]) for k in ('period_start','period_end','payday'))
        if start > end or payday < end: raise ServiceError('Invalid payroll dates')
        identifier(body['company'], 'com_')
        items = body.get('items', [])
        if not isinstance(items,list) or not 1 <= len(items) <= 500: raise ServiceError('Provide 1 to 500 payroll items')
        for item in items:
            identifier(item['employee'], 'emp_')
            earnings = item.get('earnings', [])
            if not earnings or len(earnings)>20: raise ServiceError('Provide earnings per employee')
            for earn in earnings:
                identifier(earn['workplace'], 'wrk_')
                if earn.get('type') not in ('hourly','salary','overtime','bonus'): raise ServiceError('Unsupported earnings type')
                if cents(earn['amount']) <= 0: raise ServiceError('Earnings must be positive')
                if earn['type'] in ('hourly','overtime'):
                    try:h=Decimal(str(earn.get('hours','')))
                    except InvalidOperation:raise ServiceError('Invalid earnings hours') from None
                    if not h.is_finite() or not 0<h<=744: raise ServiceError('Invalid earnings hours')
        # Filter payload to avoid arbitrary bank/funding or correction overrides.
        return {**{k:body[k] for k in ('company','period_start','period_end','payday','items')}, '_environment':os.environ.get('CHECK_ENV','sandbox')}
    if kind == 'payroll_release':
        job = c.execute('SELECT * FROM jobs WHERE id=?', (body['job_id'],)).fetchone()
        if not job or job['state'] != 'preview_ready': raise ServiceError('A successful provider payroll preview is required')
        for row in c.execute("SELECT payload FROM workflows WHERE kind='payroll_release' AND state NOT IN ('rejected','cancelled')"):
            if unseal(row['payload']).get('job_id')==job['id']:raise ServiceError('A release workflow already exists for this payroll preview')
        preview = unseal(job['result'])
        if preview.get('preview',{}).get('status') != 'succeeded': raise ServiceError('Provider calculation has not succeeded')
        if not preview.get('preview',{}).get('started_at'): raise ServiceError('Provider preview timestamp required')
        original=c.execute('SELECT payload FROM workflows WHERE id=?',(job['workflow_id'],)).fetchone()
        return {'_environment':unseal(original['payload'])['_environment'],'job_id':job['id'],'provider_id':job['provider_id'],
                'preview_started_at':preview['preview']['started_at']}
    if kind == 'efile_submit':
        # A provider-prepared, signed package reference is required, never a local estimate.
        for key in ('provider_return_id','signature_authorization_id','form','tax_year'):
            if not str(body.get(key,'')).strip(): raise ServiceError(key+' is required')
        if body.get('consent_confirmed') is not True: raise ServiceError('Taxpayer filing authorization must be confirmed')
        identifier(body['provider_return_id']); identifier(body['signature_authorization_id'])
        if str(body['tax_year']) not in ('2025','2026'): raise ServiceError('Unsupported year')
        if body['form'] not in ('1040','941','940','1120','1065'): raise ServiceError('Unsupported filing form')
        return {**{k:body[k] for k in ('provider_return_id','signature_authorization_id','form','tax_year','consent_confirmed')}, '_gateway':os.environ.get('EFILE_GATEWAY_URL','')}
    if kind in ('invoice_post','bill_post'):
        module = 'invoices' if kind == 'invoice_post' else 'bills'
        row = c.execute('SELECT * FROM records WHERE id=? AND module=?',(body['record_id'],module)).fetchone()
        if not row: raise ServiceError('Transaction record not found')
        data=json.loads(row['data']); amount=cents(data['amount'])
        if not amount: raise ServiceError('Transaction amount must be positive')
        existing=c.execute("SELECT payload FROM workflows WHERE kind=? AND state NOT IN ('rejected','cancelled')",(kind,)).fetchall()
        if any(unseal(x['payload']).get('record_id')==row['id'] for x in existing):raise ServiceError('An active or completed posting already exists')
        return {'record_id':row['id'],'name':data['name'],'amount_cents':amount,
                'record_hash':hashlib.sha256(row['data'].encode()).hexdigest()}
    raise ServiceError('Unsupported workflow kind')

def sync_bank(c, item_id):
    row=c.execute('SELECT * FROM bank_items WHERE id=? AND active=1',(item_id,)).fetchone()
    if not row: raise ServiceError('Bank connection not found')
    if row['environment'] != os.environ.get('PLAID_ENV','sandbox'): raise ServiceError('Connection environment mismatch')
    secret=unseal(row['secret']); cursor=row['cursor']; pages=[]
    # Collect all pages before applying any of the changes or cursor. Failures are safe to retry.
    for _ in range(100):
        result=plaid('/transactions/sync',{'access_token':secret['access_token'],'cursor':cursor,'count':500})
        pages.append(result); cursor=result['next_cursor']
        if not result.get('has_more'): break
    else: raise ServiceError('Sync page limit reached; cursor preserved',502)
    changes=0
    for page in pages:
        for tx in page.get('added',[])+page.get('modified',[]):
            amount=cents(tx['amount'],signed=True)
            old=c.execute('SELECT * FROM bank_transactions WHERE id=?',(tx['transaction_id'],)).fetchone()
            if old and old['journal_id'] and (old['amount_cents']!=amount or old['account_id']!=tx['account_id']):
                raise ServiceError('Posted bank transaction changed at provider; reconcile manually',409)
            c.execute('''INSERT INTO bank_transactions(id,item_id,account_id,date,name,amount_cents,currency,pending)
             VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET date=excluded.date,name=excluded.name,
             amount_cents=excluded.amount_cents,currency=excluded.currency,pending=excluded.pending,removed=0''',
             (tx['transaction_id'],item_id,tx['account_id'],tx['date'],tx.get('name',''),amount,tx.get('iso_currency_code'),int(tx.get('pending',False))))
            changes+=1
        for tx in page.get('removed',[]):
            c.execute('UPDATE bank_transactions SET removed=1 WHERE id=? AND item_id=?',(tx['transaction_id'],item_id)); changes+=1
    # Optimistic cursor lease prevents stale parallel sync results from overwriting newer state.
    if c.execute('UPDATE bank_items SET cursor=? WHERE id=? AND cursor=?',(cursor,item_id,row['cursor'])).rowcount!=1:
        raise ServiceError('Concurrent bank sync; retry',409)
    return {'changes':changes,'pages':len(pages)}

def dispatch(path, method, body, c, user, post_journal):
    if not path.startswith('/api/advanced/'): return None
    if user['role'] not in ('admin','super_admin'): raise ServiceError('Administrator access required for financial operations',403)
    route=path[len('/api/advanced/'):]
    if route=='status' and method=='GET':
        return {'banking':{'provider':'Plaid','environment':os.environ.get('PLAID_ENV','sandbox'),
                'configured':bool(os.environ.get('PLAID_CLIENT_ID') and os.environ.get('PLAID_SECRET')),
                'live_enabled':os.environ.get('DOBHRAP_ENABLE_LIVE_BANKING')=='1'},
                'payroll':{'provider':'Check','environment':os.environ.get('CHECK_ENV','sandbox'),
                'configured':bool(os.environ.get('CHECK_API_KEY')),'live_enabled':os.environ.get('DOBHRAP_ENABLE_LIVE_PAYROLL')=='1'},
                'efile':{'provider':'Custom authorized gateway adapter required','configured':bool(os.environ.get('EFILE_GATEWAY_URL') and os.environ.get('EFILE_GATEWAY_TOKEN')),
                'transmission_enabled':os.environ.get('DOBHRAP_ENABLE_EFILE_TRANSMISSION')=='1'},
                'encryption_configured':bool(os.environ.get('DOBHRAP_ENCRYPTION_KEY'))}
    if route=='tax/estimate' and method=='POST': return estimate_tax(body)
    if route=='bank/items' and method=='GET':
        return [dict(r) for r in c.execute('SELECT id,owner,environment,active FROM bank_items')]
    if route=='bank/transactions' and method=='GET':
        return [dict(r) for r in c.execute('SELECT * FROM bank_transactions ORDER BY date DESC LIMIT 1000')]
    if route=='bank/link-token' and method=='POST':
        cipher()
        opts={'client_name':'DOBHRAP','user':{'client_user_id':str(user['id'])},'products':['transactions'],'country_codes':['US'],'language':'en'}
        if os.environ.get('PLAID_REDIRECT_URI'): opts['redirect_uri']=os.environ['PLAID_REDIRECT_URI']
        return {'link_token':plaid('/link/token/create',opts)['link_token']}
    if route=='bank/exchange' and method=='POST':
        cipher()
        result=plaid('/item/public_token/exchange',{'public_token':body['public_token']})
        c.execute('INSERT INTO bank_items(id,owner,environment,secret) VALUES(?,?,?,?)',
                  (result['item_id'],user['id'],os.environ.get('PLAID_ENV','sandbox'),seal({'access_token':result['access_token']})))
        audit(c,user['id'],'bank connection added'); return {'id':result['item_id']}
    if route=='bank/sync' and method=='POST':
        result=sync_bank(c,body['item_id']); audit(c,user['id'],'bank transactions synchronized'); return result
    if route=='bank/disconnect' and method=='POST':
        row=c.execute('SELECT * FROM bank_items WHERE id=? AND active=1',(body['item_id'],)).fetchone()
        if not row:raise ServiceError('Active bank connection not found')
        if row['environment']!=os.environ.get('PLAID_ENV','sandbox'): raise ServiceError('Connection environment mismatch')
        plaid('/item/remove',unseal(row['secret']))
        c.execute("UPDATE bank_items SET active=0,secret='',cursor='' WHERE id=?",(row['id'],))
        audit(c,user['id'],'bank connection revoked');return {'disconnected':True}
    if route=='bank/import' and method=='POST':
        rows=list(csv.DictReader(io.StringIO(body['csv'])))
        if not rows or len(rows)>500: raise ServiceError('CSV requires 1 to 500 rows')
        count=0
        for r in rows:
            for key in ('external_id','date','name','amount','currency'):
                if not r.get(key): raise ServiceError('CSV missing '+key)
            date.fromisoformat(r['date'])
            key='csv:'+identifier(body['account_id'])+':'+identifier(r['external_id'])
            count+=c.execute('INSERT OR IGNORE INTO bank_transactions(id,item_id,account_id,date,name,amount_cents,currency) VALUES(?,?,?,?,?,?,?)',
                 (key,'csv',body['account_id'],r['date'],r['name'][:500],cents(r['amount'],True),r['currency'])).rowcount
        audit(c,user['id'],'bank CSV import '+str(count));return {'imported':count}
    if route=='bank/post' and method=='POST':
        c.execute('BEGIN IMMEDIATE')
        tx=c.execute('SELECT * FROM bank_transactions WHERE id=?',(body['transaction_id'],)).fetchone()
        if not tx or tx['journal_id'] or tx['pending'] or tx['removed']:raise ServiceError('Only unposted, settled bank transactions may be posted')
        if tx['currency']!='USD':raise ServiceError('Only USD ledger posting is supported')
        account=c.execute('SELECT * FROM accounts WHERE code=?',(body['category_account'],)).fetchone()
        if not account or account['code']=='1000':raise ServiceError('Select a valid non-cash category account')
        n=tx['amount_cents']
        if not n:raise ServiceError('Zero transaction cannot be posted')
        lines=[{'account':account['code'],'debit':max(n,0),'credit':max(-n,0)},
               {'account':'1000','debit':max(-n,0),'credit':max(n,0)}]
        journal=post_journal(c,'Bank: '+tx['name'],lines)
        c.execute('UPDATE bank_transactions SET journal_id=?,category_account=? WHERE id=?',(journal,account['code'],tx['id']))
        audit(c,user['id'],'bank posting '+str(journal));return {'journal_id':journal}
    if route=='workflows' and method=='GET':
        return [{**dict(r),'payload':unseal(r['payload'])} for r in c.execute('SELECT * FROM workflows ORDER BY created DESC')]
    if route=='workflows' and method=='POST':
        c.execute('BEGIN IMMEDIATE')
        data=validate_workflow(c,body['kind'],body['payload']); key=str(uuid.uuid4())
        if body['kind'] in ('payroll_create','efile_submit'):
            for previous in c.execute("SELECT payload FROM workflows WHERE kind=? AND state NOT IN ('rejected','cancelled','blocked')",(body['kind'],)):
                prior=unseal(previous['payload'])
                duplicate=(prior==data) if body['kind']=='payroll_create' else (prior.get('provider_return_id')==data.get('provider_return_id') and prior.get('_gateway')==data.get('_gateway'))
                if duplicate:raise ServiceError('A workflow already exists for this exact payroll or provider return; inspect its status first',409)
        c.execute('INSERT INTO workflows(id,kind,payload,creator) VALUES(?,?,?,?)',(key,body['kind'],seal(data),user['id']))
        audit(c,user['id'],'workflow created '+key);return {'id':key}
    if route=='workflow/action' and method=='POST':
        # Serialize transition + job creation, including two simultaneous approval requests.
        c.execute('BEGIN IMMEDIATE')
        w=c.execute('SELECT * FROM workflows WHERE id=?',(body['id'],)).fetchone()
        if not w:raise ServiceError('Workflow not found',404)
        action=body['action']; state=w['state']
        if action=='submit' and state=='draft' and w['creator']==user['id']: target='pending_approval'
        elif action in ('approve','reject') and state=='pending_approval' and w['creator']!=user['id']:
            target='queued' if action=='approve' else 'rejected'
            if action=='approve':c.execute('INSERT INTO jobs(id,workflow_id) VALUES(?,?)',(str(uuid.uuid4()),w['id']))
            c.execute('UPDATE workflows SET approver=? WHERE id=?',(user['id'],w['id']))
        elif action=='cancel' and state in ('draft','pending_approval') and w['creator']==user['id']: target='cancelled'
        else:raise ServiceError('Invalid transition or independent second administrator required',409)
        c.execute('UPDATE workflows SET state=?,updated=CURRENT_TIMESTAMP WHERE id=?',(target,w['id']))
        audit(c,user['id'],'workflow '+action+' '+w['id']);return {'state':target}
    if route=='jobs' and method=='GET':
        return [{**dict(r),'result':unseal(r['result']) if r['result'] else None} for r in c.execute('SELECT * FROM jobs ORDER BY rowid DESC')]
    if route=='jobs/refresh' and method=='POST':
        job=c.execute('SELECT j.*,w.kind FROM jobs j JOIN workflows w ON w.id=j.workflow_id WHERE j.id=?',(body['id'],)).fetchone()
        if not job or not job['provider_id']:raise ServiceError('No provider reference available')
        config=unseal(c.execute('SELECT payload FROM workflows WHERE id=?',(job['workflow_id'],)).fetchone()['payload'])
        if job['kind'].startswith('payroll_') and config.get('_environment')!=os.environ.get('CHECK_ENV','sandbox'):raise ServiceError('Provider environment changed',409)
        if job['kind']=='efile_submit' and config.get('_gateway')!=os.environ.get('EFILE_GATEWAY_URL',''):raise ServiceError('Provider gateway changed',409)
        if job['kind'].startswith('payroll_'):
            result=check_api('/payrolls/'+identifier(job['provider_id'])+'?include_items=true')
        elif job['kind']=='efile_submit':result=efile_api('/submissions/'+identifier(job['provider_id']))
        else:raise ServiceError('Internal job needs no provider refresh')
        if job['kind']=='payroll_create' and result.get('preview',{}).get('status')=='succeeded' and result.get('status')=='draft':state='preview_ready'
        else:state='provider_status'
        c.execute('UPDATE jobs SET result=?,state=? WHERE id=?',(seal(result),state,job['id']))
        audit(c,user['id'],'provider status refreshed '+job['id']);return {'state':state,'provider':result}
    if route=='schedules' and method=='GET':
        return [{**dict(r),'payload':json.loads(r['payload'])} for r in c.execute('SELECT * FROM schedules')]
    if route=='schedules' and method=='POST':
        if body['module'] not in ('invoices','bills','tasks'):raise ServiceError('Unsupported recurring record module')
        interval=int(body['interval_days'])
        if not 1<=interval<=366:raise ServiceError('Interval must be 1 to 366 days')
        date.fromisoformat(body['next_date'])
        if not body['payload'].get('name'):raise ServiceError('Record name required')
        key=str(uuid.uuid4());c.execute('INSERT INTO schedules(id,module,payload,next_date,interval_days) VALUES(?,?,?,?,?)',
                 (key,body['module'],json.dumps(body['payload']),body['next_date'],interval))
        audit(c,user['id'],'recurring schedule created '+key);return {'id':key}
    if route=='schedules/disable' and method=='POST':
        c.execute('UPDATE schedules SET active=0 WHERE id=?',(body['id'],));audit(c,user['id'],'recurring schedule disabled');return {'ok':True}
    raise ServiceError('Advanced endpoint not found',404)


def record_locked(c, module, record_id):
    kind={'invoices':'invoice_post','bills':'bill_post'}.get(module)
    if not kind:return False
    for row in c.execute("SELECT payload FROM workflows WHERE kind=? AND state NOT IN ('draft','pending_approval','cancelled','rejected','blocked')",(kind,)):
        if unseal(row['payload']).get('record_id')==int(record_id):return True
    return False

