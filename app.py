import os, json, sqlite3, secrets, hashlib, hmac, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
from contextlib import ExitStack
import advanced
DB=os.environ.get('DOBHRAP_DB','data/dobhrap.db')
MODULES={'customers':['name','email','address'],'vendors':['name','email','address'],'products':['name','sku','price','quantity'],'invoices':['name','customer','amount','due_date'],'bills':['name','vendor','amount','due_date'],'expenses':['name','category','amount','date'],'projects':['name','customer','budget','status'],'employees':['name','email','job','hourly_rate'],'time':['name','employee','hours','date'],'leave':['name','employee','start','end','status'],'recruiting':['name','email','position','status'],'benefits':['name','employee','plan','status'],'performance':['name','employee','goal','status'],'tax_returns':['name','year','filing_status','status'],'tax_documents':['name','return_id','document_type','status'],'tax_income':['name','return_id','income_type','amount'],'tax_deductions':['name','return_id','category','amount'],'bank_review':['name','account','amount','status'],'tasks':['name','assignee','due_date','status']}
def connect():
 c=sqlite3.connect(DB,timeout=30); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

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
 for a in [('1000','Cash','asset'),('1100','Accounts receivable','asset'),('2000','Accounts payable','liability'),('3000','Equity','equity'),('4000','Sales','income'),('5000','Operating expense','expense'),('5100','Wages','expense')]: c.execute('INSERT OR IGNORE INTO accounts VALUES(?,?,?)',a)

def tenant_connect(tenant_id):
 tenant_id=int(tenant_id)
 if tenant_id<1: raise ValueError('Invalid workspace')
 path=Path(DB) if tenant_id==1 else Path(DB).parent/'tenants'/('tenant-'+str(tenant_id)+'.db')
 if not path.exists(): raise advanced.ServiceError('Workspace database unavailable',503)
 c=sqlite3.connect(path,timeout=30); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

def register_workspace(c,body):
 c.execute('BEGIN IMMEDIATE')
 if not c.execute('SELECT 1 FROM users').fetchone(): raise advanced.ServiceError('Complete platform setup first',409)
 company=str(body.get('company','')).strip();email=str(body.get('email','')).strip().lower();p=str(body.get('password',''))
 if not company or len(company)>150:raise ValueError('Business name is required (maximum 150 characters)')
 if len(email)>254 or '@' not in email or any(x.isspace() for x in email):raise ValueError('Enter a valid email')
 if not 14<=len(p)<=1024 or p!=body.get('confirm_password'):raise ValueError('Use matching passwords of 14 to 1024 characters')
 if c.execute('SELECT 1 FROM users WHERE lower(email)=?',(email,)).fetchone():raise ValueError('An account already uses that email')
 tid=c.execute('INSERT INTO tenants(name) VALUES(?)',(company,)).lastrowid
 root=Path(DB).parent/'tenants';root.mkdir(mode=0o700,exist_ok=True)
 target=root/('tenant-'+str(tid)+'.db')
 with sqlite3.connect(target) as tenant:initialize_business(tenant)
 target.chmod(0o600)
 salt=secrets.token_hex(16)
 c.execute('INSERT INTO users(email,salt,hash,role,tenant_id) VALUES(?,?,?,?,?)',(email,salt,password(p,salt),'admin',tid))
 c.execute('INSERT INTO audit(user_id,action) VALUES(0,?)',('Workspace registered '+str(tid),))
 return {'ok':True,'tenant_id':tid}

def init():
 Path(DB).parent.mkdir(parents=True,exist_ok=True)
 with connect() as c:
  c.executescript("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE,salt TEXT,hash TEXT,role TEXT); CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER,expires INTEGER,csrf TEXT); CREATE TABLE IF NOT EXISTS setup_state(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS tenants(id INTEGER PRIMARY KEY,name TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active',created TEXT DEFAULT CURRENT_TIMESTAMP);")
  if 'tenant_id' not in [row[1] for row in c.execute('PRAGMA table_info(users)')]:c.execute('ALTER TABLE users ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT 1')
  c.execute("INSERT OR IGNORE INTO tenants(id,name) VALUES(1,'Platform workspace')")
  initialize_business(c)
  if not c.execute('SELECT 1 FROM users').fetchone():
   p=os.environ.get('DOBHRAP_ADMIN_PASSWORD',''); email=os.environ.get('DOBHRAP_ADMIN_EMAIL','admin@example.com')
   if p:
    if len(p)<14: raise RuntimeError('Set DOBHRAP_ADMIN_PASSWORD to at least 14 characters')
    s=secrets.token_hex(16); c.execute('INSERT INTO users(email,salt,hash,role) VALUES(?,?,?,?)',(email,s,password(p,s),'admin'))
   else:
    token=os.environ.get('DOBHRAP_SETUP_TOKEN','')
    if len(token)<32: raise RuntimeError('Configure DOBHRAP_SETUP_TOKEN with at least 32 characters for browser setup')
    c.execute("INSERT OR IGNORE INTO setup_state VALUES('token_hash',?)",(hashlib.sha256(token.encode()).hexdigest(),))

def post_journal(c,memo,lines):
 if len(lines)<2: raise ValueError('At least two journal lines required')
 for l in lines:
  if not isinstance(l.get('debit'),int) or not isinstance(l.get('credit'),int) or min(l['debit'],l['credit'])<0 or (l['debit'] and l['credit']): raise ValueError('Use nonnegative integer cents, debit or credit on each line')
 if sum(l['debit'] for l in lines)!=sum(l['credit'] for l in lines) or not sum(l['debit'] for l in lines): raise ValueError('Journal must balance and total more than zero')
 j=c.execute('INSERT INTO journals(memo) VALUES(?)',(memo,)).lastrowid
 for l in lines: c.execute('INSERT INTO lines(journal_id,account,debit,credit) VALUES(?,?,?,?)',(j,l['account'],l['debit'],l['credit']))
 return j
class Handler(BaseHTTPRequestHandler):
 def reply(self,status,data,cookie=None):
  b=json.dumps(data).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
  if cookie:self.send_header('Set-Cookie',cookie)
  self.end_headers(); self.wfile.write(b)
 def do_GET(self): self.handle_request()
 def do_POST(self): self.handle_request()
 def handle_request(self):
  try:
   path=self.path.split('?')[0]; body={}
   if self.command=='GET' and path in ('/','/setup','/setup/','/register','/register/'):
    b=Path(__file__).with_name('index.html').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.plaid.com; connect-src 'self' https://*.plaid.com; frame-src https://*.plaid.com; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"); self.end_headers(); self.wfile.write(b); return
   if self.command=='GET' and path=='/assets/oob-logo.png':
    b=Path(__file__).with_name('assets').joinpath('oob-logo.png').read_bytes(); self.send_response(200); self.send_header('Content-Type','image/png'); self.send_header('Content-Length',str(len(b))); self.send_header('Cache-Control','public, max-age=3600'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(b); return
   if self.command=='GET' and path=='/advanced.js':
    b=Path(__file__).with_name('advanced.js').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/javascript'); self.end_headers(); self.wfile.write(b); return
   if self.command=='GET' and path=='/api/identity': self.reply(200,{'application':'oob-business-suite','version':2}); return
   if path=='/health': self.reply(200,{'status':'ok'}); return
   if self.command=='POST':
    size=int(self.headers.get('Content-Length',0))
    if not 0<=size<=100000: self.reply(413,{'error':'Request too large'}); return
    body=json.loads(self.rfile.read(size) or b'{}')
    if not isinstance(body,dict):raise ValueError('Expected a JSON object')
   with ExitStack() as stack:
    c=stack.enter_context(connect())
    if path=='/api/setup/status' and self.command=='GET':
     self.reply(200,{'required':not bool(c.execute('SELECT 1 FROM users').fetchone())}); return
    if path=='/api/setup' and self.command=='POST':
     if self.headers.get('X-Setup-Request')!='1': self.reply(403,{'error':'Use the setup page'}); return
     result=setup_account(c,body); c.commit(); self.reply(201,result); return
    if path=='/api/register' and self.command=='POST':
     if self.headers.get('X-Registration-Request')!='1':self.reply(403,{'error':'Use the registration page'});return
     result=register_workspace(c,body);c.commit();self.reply(201,result);return
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
    if path=='/api/me': self.reply(200,{'email':u['email'],'role':u['role'],'csrf':u['csrf'],'modules':MODULES,'tenant':dict(tenant)}); return
    if path=='/api/users':
     if u['role'] not in ('admin','super_admin'):self.reply(403,{'error':'Administrator required'});return
     if self.command=='GET':self.reply(200,[dict(row) for row in c.execute('SELECT id,email,role FROM users WHERE tenant_id=? ORDER BY id',(tenant_id,))]);return
     if not 14<=len(body.get('password',''))<=1024 or body.get('role') not in ('super_admin','admin','editor','viewer'):raise ValueError('Password needs 14 to 1024 characters and valid role')
     if body.get('role')=='super_admin' and (u['role']!='super_admin' or tenant_id!=1):self.reply(403,{'error':'Only the platform super administrator can grant this role in the platform workspace'});return
     email=str(body['email']).strip().lower()
     if '@' not in email or len(email)>254:raise ValueError('Enter a valid email')
     salt=secrets.token_hex(16);c.execute('INSERT INTO users(email,salt,hash,role,tenant_id) VALUES(?,?,?,?,?)',(email,salt,password(body['password'],salt),body['role'],tenant_id))
     c.execute('INSERT INTO audit(user_id,action) VALUES(?,?)',(u['id'],'User created for workspace '+str(tenant_id)));c.commit();self.reply(201,{'ok':True});return
    c=stack.enter_context(tenant_connect(tenant_id))
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
  except advanced.ServiceError as e:self.reply(e.status,{'error':str(e)})
  except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as e:self.reply(400,{'error':str(e)})
if __name__=='__main__':
 init(); ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('PORT','8080'))),Handler).serve_forever()

