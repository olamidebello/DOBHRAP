import os, json, sqlite3, secrets, hashlib, hmac, time, uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
from contextlib import ExitStack
import advanced
import database
import password_reset
import marketplace
import ai_services
import provider_settings
import support
import international
import tax_preparation
import tax_analyst
import tax_analyst_control
import tax_filing
import tax_analyst_billing
import tax_services
import coupons
import wallet
import cashout
import attendance
DB=os.environ.get('DOBHRAP_DB','data/dobhrap.db')
MYSQL_MAINTENANCE=Path('/etc/dobhrap-mysql-maintenance')
def maintenance_active():
 try:return MYSQL_MAINTENANCE.exists()
 except OSError:raise advanced.ServiceError('Unable to check maintenance status. Contact your administrator.',503) from None
MODULES={'customers':['name','email','address'],'vendors':['name','email','address'],'products':['name','sku','price','quantity'],'invoices':['name','customer','amount','due_date'],'bills':['name','vendor','amount','due_date'],'expenses':['name','category','amount','date'],'projects':['name','customer','budget','status'],'employees':['name','email','job','hourly_rate'],'time':['name','employee','hours','date'],'leave':['name','employee','start','end','status'],'recruiting':['name','email','position','status'],'benefits':['name','employee','plan','status'],'performance':['name','employee','goal','status'],'tax_returns':['name','year','filing_status','status'],'tax_documents':['name','return_id','document_type','status'],'tax_income':['name','return_id','income_type','amount'],'tax_deductions':['name','return_id','category','amount'],'bank_review':['name','account','amount','status'],'tasks':['name','assignee','due_date','status']}
MOBILE_CACHE={'expires':0,'result':None}
def mobile_download():
 if MOBILE_CACHE['expires']>time.time():return MOBILE_CACHE['result']
 result={'apk_available':False,'apk_url':None,'build_type':'Android WebView preview (debug signed)','workflow_url':'https://github.com/olamidebello/DOBHRAP/actions/workflows/android-preview.yml'}
 try:
  from urllib.request import Request,urlopen
  with urlopen(Request('https://api.github.com/repos/olamidebello/DOBHRAP/releases/tags/android-preview',headers={'Accept':'application/vnd.github+json','User-Agent':'OOB-Business'}),timeout=3) as response:release=json.loads(response.read(200000))
  for asset in release.get('assets',[]):
   url=asset.get('browser_download_url','')
   if asset.get('name')=='OOB-Business-Android-Preview.apk' and asset.get('size',0)>0 and url.startswith('https://github.com/olamidebello/DOBHRAP/releases/download/android-preview/'):
    result.update(apk_available=True,apk_url=url)
 except Exception:pass
 MOBILE_CACHE.update(expires=time.time()+120,result=result)
 return result

def connect():
 return database.connect(DB)

def password(p,s): return hashlib.scrypt(p.encode(),salt=bytes.fromhex(s),n=16384,r=8,p=1).hex()
def setup_account(c, body):
 c.execute('BEGIN IMMEDIATE')
 if c.execute('SELECT 1 FROM users').fetchone(): raise advanced.ServiceError('Setup has already been completed',409)
 row=c.execute("SELECT value FROM setup_state WHERE key='token_hash'").fetchone()
 supplied=str(body.get('token',''))
 if not row or not hmac.compare_digest(row['value'],hashlib.sha256(supplied.encode()).hexdigest()):
  raise advanced.ServiceError('Invalid setup token',403)
 email=str(body.get('email','')).strip().lower(); p=str(body.get('password',''))
 if len(email)>254 or '@' not in email or any(x.isspace() for x in email): raise ValueError('Enter a valid email')
 if not 14<=len(p)<=1024: raise ValueError('Password must contain 14 to 1024 characters')
 if p!=body.get('confirm_password'): raise ValueError('Passwords do not match')
 salt=secrets.token_hex(16)
 uid=c.execute('INSERT INTO users(email,salt,hash,role) VALUES(?,?,?,?)',(email,salt,password(p,salt),'super_admin')).lastrowid
 c.execute("DELETE FROM setup_state WHERE key='token_hash'")
 c.execute('INSERT INTO audit(user_id,action) VALUES(?,?)',(uid,'Initial super administrator provisioned'))
 return {'ok':True}

BUSINESS_SCHEMA=' CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY,module TEXT,data TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS accounts(code TEXT PRIMARY KEY,name TEXT,type TEXT); CREATE TABLE IF NOT EXISTS journals(id INTEGER PRIMARY KEY,memo TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS lines(id INTEGER PRIMARY KEY,journal_id INTEGER REFERENCES journals(id),account TEXT REFERENCES accounts(code),debit INTEGER,credit INTEGER); CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,user_id INTEGER,action TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);;'
def initialize_business(c):
 c.executescript(BUSINESS_SCHEMA)
 advanced.initialize(c)
 attendance.initialize(c)
 tax_preparation.initialize(c)
 tax_analyst.initialize(c)
 tax_filing.initialize(c)
 for a in [('1000','Cash','asset'),('1100','Accounts receivable','asset'),('2000','Accounts payable','liability'),('3000','Equity','equity'),('4000','Sales','income'),('5000','Operating expense','expense'),('5100','Wages','expense')]: c.execute('INSERT OR IGNORE INTO accounts VALUES(?,?,?)',a)

def tenant_connect(tenant_id):
 tenant_id=int(tenant_id)
 if tenant_id<1: raise ValueError('Invalid workspace')
 path=Path(DB) if tenant_id==1 else Path(DB).parent/'tenants'/('tenant-'+str(tenant_id)+'.db')
 if not database.mysql_enabled() and not path.exists(): raise advanced.ServiceError('Workspace database unavailable',503)
 return database.connect(path,tenant_id=tenant_id)

def register_workspace(c,body):
 c.execute('BEGIN IMMEDIATE')
 if not c.execute('SELECT 1 FROM users').fetchone(): raise advanced.ServiceError('Complete platform setup first',409)
 mode=body.get('service_mode','business')
 if mode not in ('business','tax_only'):raise ValueError('Invalid account type')
 company='Personal tax account' if mode=='tax_only' else str(body.get('company','')).strip();email=str(body.get('email','')).strip().lower();p=str(body.get('password',''))
 if not company or len(company)>150:raise ValueError('Business name is required (maximum 150 characters)')
 if len(email)>254 or '@' not in email or any(x.isspace() for x in email):raise ValueError('Enter a valid email')
 if not 14<=len(p)<=1024 or p!=body.get('confirm_password'):raise ValueError('Use matching passwords of 14 to 1024 characters')
 if c.execute('SELECT 1 FROM users WHERE lower(email)=?',(email,)).fetchone():raise ValueError('An account already uses that email')
 tid=c.execute('INSERT INTO tenants(name,service_mode) VALUES(?,?)',(company,mode)).lastrowid
 if database.mysql_enabled():
  with database.connect(tenant_id=tid,create=True) as tenant:initialize_business(tenant)
 else:
  root=Path(DB).parent/'tenants';root.mkdir(mode=0o700,exist_ok=True)
  target=root/('tenant-'+str(tid)+'.db')
  with sqlite3.connect(target) as tenant:initialize_business(tenant)
  target.chmod(0o600)
 salt=secrets.token_hex(16)
 c.execute('INSERT INTO users(email,salt,hash,role,tenant_id) VALUES(?,?,?,?,?)',(email,salt,password(p,salt),'admin',tid))
 c.execute('INSERT INTO audit(user_id,action) VALUES(0,?)',('Workspace registered '+str(tid),))
 return {'ok':True,'tenant_id':tid}

def init():
 if not database.mysql_enabled():Path(DB).parent.mkdir(parents=True,exist_ok=True)
 with connect() as c:
  c.executescript("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE,salt TEXT,hash TEXT,role TEXT); CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER,expires INTEGER,csrf TEXT); CREATE TABLE IF NOT EXISTS setup_state(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS tenants(id INTEGER PRIMARY KEY,name TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active',created TEXT DEFAULT CURRENT_TIMESTAMP);")
  password_reset.initialize(c)
  tax_services.initialize(c)
  attendance.initialize_platform(c)
  if 'tenant_id' not in [row[1] for row in c.execute('PRAGMA table_info(users)')]:c.execute('ALTER TABLE users ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT 1')
  c.execute("INSERT OR IGNORE INTO tenants(id,name) VALUES(1,'Platform workspace')")
  c.execute("CREATE TABLE IF NOT EXISTS platform_jobs(id TEXT PRIMARY KEY,kind TEXT NOT NULL,creator INTEGER NOT NULL,state TEXT NOT NULL DEFAULT 'queued',created TEXT DEFAULT CURRENT_TIMESTAMP,finished TEXT,summary TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS platform_state(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
  initialize_business(c)
  marketplace.initialize(c)
  wallet.initialize(c)
  ai_services.initialize(c)
  cashout.initialize(c)
  coupons.initialize(c)
  tax_analyst_billing.initialize(c)
  provider_settings.initialize(c)
  tax_analyst_control.initialize(c)
  support.initialize(c)
  international.initialize(c)
  for tenant in c.execute('SELECT id FROM tenants WHERE id>1').fetchall():
   with tenant_connect(tenant['id']) as tenant_db:initialize_business(tenant_db)
  if not c.execute('SELECT 1 FROM users').fetchone():
   p=os.environ.get('DOBHRAP_ADMIN_PASSWORD',''); email=os.environ.get('DOBHRAP_ADMIN_EMAIL','admin@example.com')
   if p:
    if len(p)<14: raise RuntimeError('Set DOBHRAP_ADMIN_PASSWORD to at least 14 characters')
    s=secrets.token_hex(16); c.execute('INSERT INTO users(email,salt,hash,role) VALUES(?,?,?,?)',(email,s,password(p,s),'admin'))
   else:
    token=os.environ.get('DOBHRAP_SETUP_TOKEN','')
    if len(token)<32: raise RuntimeError('Configure DOBHRAP_SETUP_TOKEN with at least 32 characters for browser setup')
    c.execute("INSERT OR IGNORE INTO setup_state VALUES('token_hash',?)",(hashlib.sha256(token.encode()).hexdigest(),))

WATCHDOG_DB='/var/lib/oob-watchdog/events.db'
def watchdog_report(role):
 if role!='super_admin':raise advanced.ServiceError('Super administrator required',403)
 path=Path(WATCHDOG_DB)
 if not path.exists():return {'installed':False,'events':[],'summary':{},'latest':None}
 try:
  with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5) as c:
   c.row_factory=sqlite3.Row
   events=[dict(r) for r in c.execute('SELECT * FROM watchdog_events ORDER BY id DESC LIMIT 200')]
   for event in events:event['checks']=json.loads(event['checks'])
   since=int(time.time())-86400
   summary={r['action']:r['n'] for r in c.execute('SELECT action,count(*) n FROM watchdog_events WHERE checked_at>=? GROUP BY action',(since,))}
   latest=events[0] if events else None
   return {'installed':True,'events':events,'latest':latest,'summary':summary,
           'stale':not latest or int(time.time())-latest['checked_at']>180,
           'retention_days':90,'history_limit':200,'summary_window_hours':24}
 except (sqlite3.Error,OSError,ValueError):
  raise advanced.ServiceError('Watchdog reports are unavailable; check watchdog installation and reporting permissions',503)

def post_journal(c,memo,lines):
 if len(lines)<2: raise ValueError('At least two journal lines required')
 for l in lines:
  if not isinstance(l.get('debit'),int) or not isinstance(l.get('credit'),int) or min(l['debit'],l['credit'])<0 or (l['debit'] and l['credit']): raise ValueError('Use nonnegative integer cents, debit or credit on each line')
 if sum(l['debit'] for l in lines)!=sum(l['credit'] for l in lines) or not sum(l['debit'] for l in lines): raise ValueError('Journal must balance and total more than zero')
 j=c.execute('INSERT INTO journals(memo) VALUES(?)',(memo,)).lastrowid
 for l in lines: c.execute('INSERT INTO lines(journal_id,account,debit,credit) VALUES(?,?,?,?)',(j,l['account'],l['debit'],l['credit']))
 return j
def financial_statements(c):
 accounts=[dict(row) for row in c.execute('SELECT a.*,coalesce(sum(l.debit),0) debit_cents,coalesce(sum(l.credit),0) credit_cents FROM accounts a LEFT JOIN lines l ON l.account=a.code GROUP BY a.code ORDER BY a.code')]
 for account in accounts:account['balance_cents']=(account['credit_cents']-account['debit_cents']) if account['type'] in ('liability','equity','income') else (account['debit_cents']-account['credit_cents'])
 total=lambda kind:sum(a['balance_cents'] for a in accounts if a['type']==kind)
 net=total('income')-total('expense')
 return {'accounts':accounts,'revenue_cents':total('income'),'expense_cents':total('expense'),'net_income_cents':net,'assets_cents':total('asset'),'liabilities_cents':total('liability'),'equity_cents':total('equity'),'retained_current_earnings_cents':net,'balanced':total('asset')==total('liability')+total('equity')+net,'basis':'Posted journal balances since inception; USD. Current earnings are shown separately from recorded equity.'}

def dashboard(c, role):
 counts={row['module']:row['count'] for row in c.execute('SELECT module,count(*) count FROM records GROUP BY module')}
 totals={module:0 for module in ('invoices','bills','expenses')}
 overdue=0;pending_leave=0;open_tasks=0
 today=time.strftime('%Y-%m-%d')
 for row in c.execute("SELECT module,data FROM records WHERE module IN ('invoices','bills','expenses','leave','tasks')"):
  data=json.loads(row['data']);module=row['module']
  if module in totals:
   try:totals[module]+=advanced.cents(data.get('amount','0'))
   except advanced.ServiceError:pass
  if module=='invoices' and data.get('due_date') and data['due_date']<today:overdue+=1
  if module=='leave' and data.get('status','').lower() in ('','pending','requested'):pending_leave+=1
  if module=='tasks' and data.get('status','').lower() not in ('done','complete','completed','cancelled'):open_tasks+=1
 balances={row['type']:row['balance'] for row in c.execute('SELECT a.type,coalesce(sum(l.debit-l.credit),0) balance FROM accounts a LEFT JOIN lines l ON l.account=a.code GROUP BY a.type')}
 revenue=-balances.get('income',0);expenses=balances.get('expense',0)
 trend=[dict(row) for row in c.execute("SELECT substr(j.created,1,7) month,sum(CASE WHEN a.type='income' THEN l.credit-l.debit ELSE 0 END) revenue_cents,sum(CASE WHEN a.type='expense' THEN l.debit-l.credit ELSE 0 END) expense_cents FROM journals j JOIN lines l ON l.journal_id=j.id JOIN accounts a ON a.code=l.account WHERE j.created>=date('now','start of month','-5 months') GROUP BY substr(j.created,1,7) ORDER BY month")]
 result={'counts':counts,'record_totals_cents':totals,'ledger':{'revenue_cents':revenue,'expense_cents':expenses,'net_income_cents':revenue-expenses,'cash_cents':c.execute("SELECT coalesce(sum(debit-credit),0) FROM lines WHERE account='1000'").fetchone()[0]},'attention':{'past_due_invoice_records':overdue,'pending_leave':pending_leave,'open_tasks':open_tasks},'trend':trend,'recent_activity':[dict(row) for row in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 8')],'generated_at':time.strftime('%Y-%m-%d %H:%M:%S UTC',time.gmtime())}
 if role in ('admin','super_admin'):
  result['workflow_counts']={row['state']:row['count'] for row in c.execute('SELECT state,count(*) count FROM workflows GROUP BY state')}
  result['job_counts']={row['state']:row['count'] for row in c.execute('SELECT state,count(*) count FROM jobs GROUP BY state')}
 return result

class Handler(BaseHTTPRequestHandler):
 def reply(self,status,data,cookie=None):
  b=json.dumps(data).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
  if cookie:self.send_header('Set-Cookie',cookie)
  self.end_headers(); self.wfile.write(b)
 def do_GET(self): self.handle_request()
 def do_POST(self): self.handle_request()
 def handle_request(self):
  try:
   if self.command!='GET' and maintenance_active():raise advanced.ServiceError('Database migration in progress. Please try again shortly.',503)
   path=self.path.split('?')[0]; body={}
   if self.command=='GET' and path in ('/','/setup','/setup/','/register','/register/','/tax-services','/tax-services/','/downloads','/downloads/','/tax-record-upload','/employee-clock','/forgot-password','/reset-password'):
    b=Path(__file__).with_name('index.html').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.plaid.com; connect-src 'self' https://*.plaid.com; frame-src https://*.plaid.com; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"); self.end_headers(); self.wfile.write(b); return
   if self.command=='GET' and path in ('/assets/oob-logo.png','/assets/app-icon-192.png','/assets/app-icon-512.png'):
    b=Path(__file__).with_name('assets').joinpath(path.rsplit('/',1)[1]).read_bytes(); self.send_response(200); self.send_header('Content-Type','image/png'); self.send_header('Content-Length',str(len(b))); self.send_header('Cache-Control','public, max-age=3600'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(b); return
   if self.command=='GET' and path in ('/advanced.js','/workspace.js','/support-ui.js','/international.js','/tax-preparation.js','/tax-analyst.js','/tax-management.js','/ai-services.js','/wallet.js','/cashout.js','/attendance.js','/password-reset.js'):
    b=Path(__file__).with_name(path.lstrip('/')).read_bytes(); self.send_response(200); self.send_header('Content-Type','text/javascript'); self.end_headers(); self.wfile.write(b); return
   if self.command=='GET' and path in ('/manifest.webmanifest','/service-worker.js'):
    b=Path(__file__).with_name(path.lstrip('/')).read_bytes();self.send_response(200);self.send_header('Content-Type','application/manifest+json' if path.endswith('webmanifest') else 'text/javascript');self.send_header('Cache-Control','no-cache');self.end_headers();self.wfile.write(b);return
   if self.command=='GET' and path=='/api/tax-years':self.reply(200,tax_preparation.year_catalog());return
   if self.command=='GET' and path=='/api/mobile':self.reply(200,mobile_download());return
   if self.command=='GET' and path=='/api/identity': self.reply(200,{'application':'oob-business-suite','version':2}); return
   if path=='/health': self.reply(200,{'status':'ok'}); return
   if self.command=='GET' and path=='/api/intl/catalog':self.reply(200,international.catalogs());return
   if self.command=='GET' and path=='/api/market/health':
    self.reply(200,{'marketplace':marketplace.enabled(),'environment':provider_settings.get('PAYMENTS_ENV','test')});return
   if path in ('/api/market/webhooks/stripe','/api/market/webhooks/paystack') and self.command=='POST':
    size=int(self.headers.get('Content-Length',0))
    if not 0<size<=256000:self.reply(413,{'error':'Webhook too large'});return
    raw=self.rfile.read(size)
    with connect() as payment_db:
     result=marketplace.webhook(payment_db,path.rsplit('/',1)[1],raw,self.headers)
     payment_db.commit()
    self.reply(200,result);return
   if self.command=='POST':
    size=int(self.headers.get('Content-Length',0))
    if not 0<=size<=(3_000_000 if path in ('/api/tax-prep/document','/api/tax-analyst/upload','/api/tax-analyst/quote-upload','/api/tax-record-upload') else 1_000_000 if path=='/api/tax-analyst/save' else 100000): self.reply(413,{'error':'Request too large'}); return
    body=json.loads(self.rfile.read(size) or b'{}')
    if not isinstance(body,dict):raise ValueError('Expected a JSON object')
   with ExitStack() as stack:
    c=stack.enter_context(connect())
    if path=='/api/employee-clock' and self.command=='POST':
     tid=int(body.get('tenant_id',0));tenant=c.execute('SELECT * FROM tenants WHERE id=?',(tid,)).fetchone()
     if not tenant or tenant['status']!='active' or tenant['service_mode']=='tax_only':raise advanced.ServiceError('Employee portal unavailable',403)
     private=stack.enter_context(tenant_connect(tid));cookies=SimpleCookie(self.headers.get('Cookie',''));token=cookies['employee_session'].value if 'employee_session' in cookies else ''
     enabled=bool(c.execute('SELECT enabled FROM clock_platform WHERE id=1').fetchone()[0])
     result=attendance.employee(private,{**body,'_employee_header':self.headers.get('X-Employee-Request')},token,self.headers.get('X-Employee-CSRF',''),hashlib.sha256(self.client_address[0].encode()).hexdigest(),enabled)
     private.commit();cookie=None
     if '_cookie' in result:
      value=result.pop('_cookie');cookie='employee_session='+value+'; HttpOnly; SameSite=Strict; Path=/'+('; Max-Age=28800' if value else '; Max-Age=0')+('; Secure' if os.environ.get('DOBHRAP_SECURE_COOKIE')=='1' else '')
     self.reply(200,result,cookie);return
    if path=='/api/tax-record-upload' and self.command=='POST':
     tid=int(body.get('tenant_id',0));tenant=c.execute('SELECT status FROM tenants WHERE id=?',(tid,)).fetchone()
     if not tenant or tenant['status']!='active':raise advanced.ServiceError('Upload link unavailable',404)
     private=stack.enter_context(tenant_connect(tid))
     result=tax_preparation.public_client_request(private,body);private.commit();self.reply(200,result);return
    if path=='/api/support/intake' and self.command=='POST':
     result=support.intake(c,body,self.headers);c.commit();self.reply(201,result);return
    if path=='/api/setup/status' and self.command=='GET':
     self.reply(200,{'required':not bool(c.execute('SELECT 1 FROM users').fetchone())}); return
    if path=='/api/setup' and self.command=='POST':
     if self.headers.get('X-Setup-Request')!='1': self.reply(403,{'error':'Use the setup page'}); return
     result=setup_account(c,body); c.commit(); self.reply(201,result); return
    if path=='/api/register' and self.command=='POST':
     if self.headers.get('X-Registration-Request')!='1':self.reply(403,{'error':'Use the registration page'});return
     result=register_workspace(c,body);c.commit();self.reply(201,result);return
    if path in ('/api/password-reset/request','/api/password-reset/complete') and self.command=='POST':
     if self.headers.get('X-Password-Reset-Request')!='1':raise advanced.ServiceError('Use the password recovery form',403)
     result=password_reset.request(c,body,self.client_address[0]) if path.endswith('/request') else password_reset.finish(c,body,self.client_address[0])
     c.commit();self.reply(200,result);return
    if path=='/api/login' and self.command=='POST':
     u=c.execute('SELECT * FROM users WHERE lower(email)=?',(str(body.get('email','')).strip().lower(),)).fetchone()
     if not u or not hmac.compare_digest(u['hash'],password(body.get('password',''),u['salt'])): time.sleep(.5); self.reply(401,{'error':'Invalid credentials'}); return
     tenant=c.execute('SELECT status FROM tenants WHERE id=?',(u['tenant_id'],)).fetchone()
     if not tenant or (tenant['status']!='active' and u['role']!='super_admin'):self.reply(403,{'error':'Workspace is suspended'});return
     token=secrets.token_hex(32); csrf=secrets.token_hex(24); c.execute('DELETE FROM sessions WHERE expires<?',(int(time.time()),)); c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(token,u['id'],int(time.time())+28800,csrf)); self.reply(200,{'csrf':csrf},'session='+token+'; HttpOnly; SameSite=Strict; Path=/'+('; Secure' if os.environ.get('DOBHRAP_SECURE_COOKIE')=='1' else '')); return
    cookies=SimpleCookie(self.headers.get('Cookie','')); token=cookies['session'].value if 'session' in cookies else ''; u=c.execute('SELECT users.*,sessions.csrf FROM users JOIN sessions ON users.id=sessions.user_id WHERE token=? AND expires>?',(token,int(time.time()))).fetchone()
    if not u:self.reply(401,{'error':'Sign in required'}); return
    if self.command=='POST' and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),u['csrf']): self.reply(403,{'error':'Invalid CSRF token'}); return
    if path=='/api/logout' and self.command=='POST': c.execute('DELETE FROM sessions WHERE token=?',(token,)); self.reply(200,{'ok':True},'session=; Max-Age=0; Path=/'); return
    if path in ('/api/password-reset/admin','/api/password/change') and self.command=='POST':
     result=password_reset.authenticated(c,u,body,admin=path.endswith('/admin'));c.commit();self.reply(200,result);return
    intl_result=international.dispatch(path,self.command,body,c,u)
    if intl_result is not None:c.commit();self.reply(200,intl_result);return
    if path.startswith('/api/platform/cashout/'):
     cashout_result=cashout.dispatch(path,self.command,body,c,u);c.commit();self.reply(200,cashout_result);return
    wallet_result=wallet.admin(path,self.command,body,c,u)
    if wallet_result is not None:c.commit();self.reply(200,wallet_result);return
    analyst_control_result=tax_analyst_control.dispatch(path,self.command,body,c,u)
    if analyst_control_result is not None:c.commit();self.reply(200,analyst_control_result);return
    settings_result=provider_settings.dispatch(path,self.command,body,c,u)
    if settings_result is not None:c.commit();self.reply(200,settings_result);return
    if path=='/api/platform/attendance':
     if u['role']!='super_admin':raise advanced.ServiceError('Super administrator required',403)
     if self.command=='POST':
      if type(body.get('enabled')) is not bool:raise advanced.ServiceError('Choose platform attendance status')
      c.execute('UPDATE clock_platform SET enabled=? WHERE id=1',(int(body['enabled']),));advanced.audit(c,u['id'],'Platform attendance status changed');c.commit()
     self.reply(200,{'enabled':bool(c.execute('SELECT enabled FROM clock_platform WHERE id=1').fetchone()[0]),'workspaces':[dict(r) for r in c.execute('SELECT id,name,status,service_mode FROM tenants ORDER BY id')]});return
    if path=='/api/platform/watchdog':
     if self.command!='GET':raise advanced.ServiceError('Read-only endpoint',405)
     self.reply(200,watchdog_report(u['role']));return
    if path in ('/api/platform/status','/api/platform/jobs'):
     if u['role']!='super_admin':self.reply(403,{'error':'Super administrator required'});return
     if self.command=='GET':
      state={row['key']:json.loads(row['value']) for row in c.execute('SELECT * FROM platform_state')}
      jobs=[dict(row) for row in c.execute('SELECT * FROM platform_jobs ORDER BY created DESC,rowid DESC LIMIT 30')]
      self.reply(200,{'state':state,'jobs':jobs});return
     if path!='/api/platform/jobs' or body.get('kind') not in ('verify','backup','deploy','commission'):raise ValueError('Unsupported platform operation')
     c.execute('BEGIN IMMEDIATE')
     if c.execute("SELECT 1 FROM platform_jobs WHERE state IN ('queued','running')").fetchone():raise advanced.ServiceError('A platform operation is already queued or running',409)
     jid=str(uuid.uuid4());c.execute('INSERT INTO platform_jobs(id,kind,creator) VALUES(?,?,?)',(jid,body['kind'],u['id']))
     c.execute('INSERT INTO audit(user_id,action) VALUES(?,?)',(u['id'],'Platform operation queued '+body['kind']+' '+jid));c.commit();self.reply(202,{'id':jid,'state':'queued'});return
    if path=='/api/tenants':
     if u['role']!='super_admin':self.reply(403,{'error':'Super administrator required'});return
     if self.command=='GET':
      self.reply(200,[dict(row) for row in c.execute('SELECT t.*,count(u.id) user_count FROM tenants t LEFT JOIN users u ON u.tenant_id=t.id GROUP BY t.id ORDER BY t.id')]);return
     if body.get('action')=='status':
      tid=int(body['tenant_id']);status=body['status']
      if tid==1 or status not in ('active','suspended'):raise ValueError('Invalid workspace status change')
      if c.execute('UPDATE tenants SET status=? WHERE id=?',(status,tid)).rowcount!=1:raise ValueError('Workspace not found')
      c.execute('INSERT INTO audit(user_id,action) VALUES(?,?)',(u['id'],'Workspace '+str(tid)+' '+status));c.commit();self.reply(200,{'ok':True});return
     result=register_workspace(c,body);c.commit();self.reply(201,result);return
    tenant_id=int(self.headers.get('X-Tenant-ID') or u['tenant_id'])
    if tenant_id!=u['tenant_id'] and u['role']!='super_admin':self.reply(403,{'error':'Workspace access denied'});return
    tenant=c.execute('SELECT * FROM tenants WHERE id=?',(tenant_id,)).fetchone()
    if not tenant:self.reply(404,{'error':'Workspace not found'});return
    if tenant['status']!='active':self.reply(403,{'error':'Workspace is suspended'});return
    cashout_result=cashout.dispatch(path,self.command,body,c,u)
    if cashout_result is not None:c.commit();self.reply(200,cashout_result);return
    ai_result=ai_services.dispatch(path,self.command,body,c,u,tenant_id)
    if ai_result is not None:c.commit();self.reply(200,ai_result);return
    if path=='/api/wallet/status' and self.command=='GET':self.reply(200,wallet.status(c,u));return
    if path=='/api/tax-analyst/billing' and self.command=='GET':
     result=tax_analyst_billing.status(c,tenant_id,u);c.commit();self.reply(200,result);return
    marketplace.refresh_subscriptions(c)
    tax_services.enforce(c,path,self.command,body,tenant,u)
    if path=='/api/tax-services/status' and self.command=='GET':self.reply(200,tax_services.status(c,tenant_id,u));return
    if path=='/api/me': self.reply(200,{'id':u['id'],'email':u['email'],'role':u['role'],'csrf':u['csrf'],'modules':{} if tenant['service_mode']=='tax_only' and u['role']!='super_admin' else MODULES,'tenant':dict(tenant),'preferences':international.preferences(c,u['id'])}); return
    if path=='/api/users':
     if u['role'] not in ('admin','super_admin'):self.reply(403,{'error':'Administrator required'});return
     if self.command=='GET':self.reply(200,[dict(row) for row in c.execute('SELECT id,email,role FROM users WHERE tenant_id=? ORDER BY id',(tenant_id,))]);return
     if not 14<=len(body.get('password',''))<=1024 or body.get('role') not in ('super_admin','admin','editor','viewer'):raise ValueError('Password needs 14 to 1024 characters and valid role')
     if body.get('role')=='super_admin' and (u['role']!='super_admin' or tenant_id!=1):self.reply(403,{'error':'Only the platform super administrator can grant this role in the platform workspace'});return
     email=str(body['email']).strip().lower()
     if '@' not in email or len(email)>254:raise ValueError('Enter a valid email')
     salt=secrets.token_hex(16);c.execute('INSERT INTO users(email,salt,hash,role,tenant_id) VALUES(?,?,?,?,?)',(email,salt,password(body['password'],salt),body['role'],tenant_id))
     c.execute('INSERT INTO audit(user_id,action) VALUES(?,?)',(u['id'],'User created for workspace '+str(tenant_id)));c.commit();self.reply(201,{'ok':True});return
    support_result=support.dispatch(path,self.command,body,c,u,tenant_id)
    if support_result is not None:c.commit();self.reply(200,support_result);return
    coupon_result=coupons.dispatch(path,self.command,body,c,u,tenant_id)
    if coupon_result is not None:c.commit();self.reply(200,coupon_result);return
    result=marketplace.dispatch(path,self.command,body,c,u,tenant_id)
    if result is not None:
     if tenant['service_mode']=='tax_only' and path=='/api/market/products' and self.command=='GET':result=[p for p in result if (__import__('re').fullmatch(r'tax_(preparation|amendment)_\d{4}',p['service_code']) or p['service_code']=='tax_analyst_session')]
     c.commit();self.reply(200,result);return
    c=stack.enter_context(tenant_connect(tenant_id))
    attendance_result=attendance.admin(path,self.command,body,c,u,tenant_id)
    if attendance_result is not None:c.commit();self.reply(200,attendance_result);return
    filing_result=tax_filing.dispatch(path,self.command,body,c,u)
    if filing_result is not None:c.commit();self.reply(200,filing_result);return
    analyst_result=tax_analyst.dispatch(path,self.command,body,c,{**dict(u),'tenant_id':tenant_id})
    if analyst_result is not None:c.commit();self.reply(200,analyst_result);return
    tax_result=tax_preparation.dispatch(path,self.command,{**body,'_tenant_id':tenant_id},c,u)
    if tax_result is not None:c.commit();self.reply(200,tax_result);return
    if path=='/api/financial-statements' and self.command=='GET':self.reply(200,financial_statements(c));return
    if path=='/api/dashboard' and self.command=='GET':self.reply(200,dashboard(c,u['role']));return
    result=advanced.dispatch(path,self.command,body,c,u,post_journal,tenant_id=tenant_id)
    if result is not None:self.reply(200,result);return
    if self.command=='POST' and u['role']=='viewer':self.reply(403,{'error':'Read-only role'});return
    if path=='/api/reports':
     rows=[dict(r) for r in c.execute('SELECT a.*,coalesce(sum(l.debit),0) debit,coalesce(sum(l.credit),0) credit FROM accounts a LEFT JOIN lines l ON l.account=a.code GROUP BY a.code')]; self.reply(200,{'trial_balance':rows,'audit':[dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')]}); return
    elif path=='/api/journals':
     if self.command=='GET':self.reply(200,{'accounts':[dict(r) for r in c.execute('SELECT * FROM accounts')],'journals':[dict(r) for r in c.execute('SELECT * FROM journals ORDER BY id DESC')]}); return
     result={'id':post_journal(c,body['memo'],body['lines'])}
    elif path=='/api/payroll/preview':
     hours=float(body['hours']); rate=float(body['rate'])
     if not 0<=hours<=744 or not 0<=rate<=100000: raise ValueError('Invalid hours or rate')
     result={'gross_cents':round(hours*rate*100),'status':'draft','notice':'Gross pay worksheet only. No withholding, overtime rules, filing or disbursement calculated.'}
    elif path.startswith('/api/records/'):
     module=path.rsplit('/',1)[1]
     if module not in MODULES: self.reply(404,{'error':'Unknown module'}); return
     if self.command=='GET':self.reply(200,[{'id':r['id'],**json.loads(r['data'])} for r in c.execute('SELECT * FROM records WHERE module=? ORDER BY id DESC',(module,))]); return
     data={k:str(body.get(k,''))[:2000] for k in MODULES[module]}
     if not data['name'].strip(): raise ValueError('Name is required')
     for k in ('amount','price','quantity','budget','hours','hourly_rate'):
      if k in data and (not data[k] or float(data[k])<0): raise ValueError(k+' must be nonnegative')
     if body.get('id'):
      c.execute('BEGIN IMMEDIATE')
      if advanced.record_locked(c,module,body['id']):raise advanced.ServiceError('Record is locked by an approved posting workflow',409)
      if c.execute('UPDATE records SET data=? WHERE id=? AND module=?',(json.dumps(data),int(body['id']),module)).rowcount!=1:raise ValueError('Record not found')
      result={'id':body['id']}
     else:result={'id':c.execute('INSERT INTO records(module,data) VALUES(?,?)',(module,json.dumps(data))).lastrowid}
    else:self.reply(404,{'error':'Not found'}); return
    if self.command=='POST': c.execute('INSERT INTO audit(user_id,action) VALUES(?,?)',(u['id'],path+' '+json.dumps(result)))
    self.reply(200,result)
  except sqlite3.OperationalError:
   self.log_error('Database operation failed; check database availability, permissions and migrations')
   self.reply(503,{'error':'The workspace database is temporarily unavailable. Please try again shortly.'})
  except advanced.ServiceError as e:self.reply(e.status,{'error':str(e)})
  except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as e:self.reply(400,{'error':str(e)})
if __name__=='__main__':
 init(); ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('PORT','8080'))),Handler).serve_forever()


