"""Reserved-funds manual cash-out workflow; never initiates a bank transfer."""
import json, time, uuid
import advanced as a
import wallet
from database import MySQLConnection

def initialize(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS cashout_settings(id INTEGER PRIMARY KEY,enabled INTEGER NOT NULL DEFAULT 1);
 INSERT OR IGNORE INTO cashout_settings VALUES(1,1);
 CREATE TABLE IF NOT EXISTS cashout_authorizations(id TEXT PRIMARY KEY,owner INTEGER NOT NULL,currency TEXT NOT NULL,amount INTEGER NOT NULL,actor INTEGER NOT NULL,request_key TEXT NOT NULL,reason TEXT NOT NULL,created INTEGER NOT NULL,UNIQUE(actor,request_key));
 CREATE TABLE IF NOT EXISTS cashout_funds(owner INTEGER NOT NULL,currency TEXT NOT NULL,available INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(owner,currency));
 CREATE TABLE IF NOT EXISTS cashout_requests(id TEXT PRIMARY KEY,owner INTEGER NOT NULL,currency TEXT NOT NULL,amount INTEGER NOT NULL,destination TEXT NOT NULL,state TEXT NOT NULL,request_key TEXT NOT NULL,created INTEGER NOT NULL,updated INTEGER NOT NULL,reference TEXT NOT NULL DEFAULT '',reviewer INTEGER,UNIQUE(owner,request_key));''')

def enabled(c):return bool(c.execute('SELECT enabled FROM cashout_settings WHERE id=1').fetchone()[0])

def rows(c,owner=None):
 where=' WHERE owner=?' if owner is not None else ''
 return [dict(r) for r in c.execute('SELECT id,owner,currency,amount,state,created,updated,reference,reviewer FROM cashout_requests'+where+' ORDER BY created DESC LIMIT 200',() if owner is None else (owner,))]

def status(c,user):
 return {'enabled':enabled(c),'funds':[dict(r) for r in c.execute('SELECT currency,available FROM cashout_funds WHERE owner=?',(user['id'],))],'requests':rows(c,user['id']),'mode':'manual','notice':'Request cash-out of funds explicitly authorized as withdrawable. Funds are held until cancelled, rejected or externally paid. Bank transfers are processed outside this application by the administrator.'}

def authorize(c,body,user):
 if user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
 uid=body.get('owner');code=wallet.currency(body.get('currency','USD'));value=wallet.minor(body.get('amount'),code);reason=str(body.get('reason','')).strip()
 if type(uid) is not int or not 3<=len(reason)<=500:raise a.ServiceError('Select a user and explain the verified funding source')
 key=request_uuid(body.get('request_key'));c.execute('BEGIN IMMEDIATE')
 old=c.execute('SELECT * FROM cashout_authorizations WHERE actor=? AND request_key=?',(user['id'],key)).fetchone()
 marker='Cash-out authorization: '+reason
 if old:
  if old['owner']!=uid or old['currency']!=code or old['reason']!=marker or old['amount']!=value:raise a.ServiceError('Request identifier already used',409)
  return {'ok':True,'reused':True}
 # Lock the spendable balance first; every purchase and hold takes the same lock.
 account=c.execute('SELECT balance FROM wallet_accounts WHERE owner=? AND currency=?'+(' FOR UPDATE' if isinstance(c,MySQLConnection) else ''),(uid,code)).fetchone()
 if not account or account[0]<value:raise a.ServiceError('Insufficient account balance to authorize',402)
 c.execute('INSERT OR IGNORE INTO cashout_funds(owner,currency,available) VALUES(?,?,0)',(uid,code))
 balance=c.execute('SELECT balance FROM wallet_accounts WHERE owner=? AND currency=?',(uid,code)).fetchone()[0]
 if c.execute('UPDATE cashout_funds SET available=available+? WHERE owner=? AND currency=? AND available<=?',(value,uid,code,balance-value)).rowcount!=1:raise a.ServiceError('Amount exceeds unallocated account balance',409)
 c.execute('INSERT INTO cashout_authorizations VALUES(?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),uid,code,value,user['id'],key,marker,int(time.time())))
 # A zero-value ledger annotation never adds spendable money.
 c.execute('INSERT INTO wallet_entries VALUES(?,?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),uid,code,0,'cashout_authorize',None,str(uuid.uuid5(uuid.NAMESPACE_URL,'cashout-authorization/'+str(user['id'])+'/'+key)),user['id'],marker,int(time.time())))
 a.audit(c,user['id'],'Cash-out funds authorized user '+str(uid)+' '+code+' '+str(value))
 return {'ok':True,'reused':False}

def request_uuid(value):
 try:return str(uuid.UUID(str(value)))
 except ValueError:raise a.ServiceError('Use a valid request identifier') from None

def request(c,body,user):
 if user['role']=='viewer':raise a.ServiceError('Read-only accounts cannot cash out',403)
 if not enabled(c):raise a.ServiceError('New cash-out requests are paused',403)
 code=wallet.currency(body.get('currency','USD'));value=wallet.minor(body.get('amount'),code);key=request_uuid(body.get('request_key'))
 destination=body.get('destination')
 if not isinstance(destination,dict) or set(destination)!={'beneficiary','bank','account','routing','country'}:raise a.ServiceError('Complete the payout destination')
 destination={k:str(v).strip() for k,v in destination.items()}
 if any(not v or len(v)>200 or any(ord(ch)<32 for ch in v) for v in destination.values()):raise a.ServiceError('Complete bank details using printable text (maximum 200 characters each)')
 c.execute('BEGIN IMMEDIATE');old=c.execute('SELECT * FROM cashout_requests WHERE owner=? AND request_key=?',(user['id'],key)).fetchone()
 if old:
  if old['currency']!=code or old['amount']!=value or a.unseal(old['destination'])!=destination:raise a.ServiceError('Request identifier already used for different details',409)
  return {'id':old['id'],'state':old['state'],'reused':True}
 if c.execute('UPDATE wallet_accounts SET balance=balance-? WHERE owner=? AND currency=? AND balance>=?',(value,user['id'],code,value)).rowcount!=1:raise a.ServiceError('Insufficient account balance',402)
 if c.execute('UPDATE cashout_funds SET available=available-? WHERE owner=? AND currency=? AND available>=?',(value,user['id'],code,value)).rowcount!=1:raise a.ServiceError('Insufficient withdrawable funds; store credit is not automatically redeemable',402)
 did=str(uuid.uuid4());now=int(time.time())
 c.execute("INSERT INTO cashout_requests(id,owner,currency,amount,destination,state,request_key,created,updated) VALUES(?,?,?,?,?,'pending',?,?,?)",(did,user['id'],code,value,a.seal(destination),key,now,now))
 c.execute('INSERT INTO wallet_entries VALUES(?,?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),user['id'],code,-value,'cashout_hold',did,key,user['id'],'Cash-out funds held',now));a.audit(c,user['id'],'Cash-out request created '+did)
 return {'id':did,'state':'pending','reused':False}

def action(c,body,user,admin=False):
 action=body.get('action');c.execute('BEGIN IMMEDIATE')
 row=c.execute('SELECT * FROM cashout_requests WHERE id=?',(body.get('id'),)).fetchone()
 if not row or (not admin and row['owner']!=user['id']):raise a.ServiceError('Cash-out request not found',404)
 if admin and user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
 expected={'cancel':'pending','approve':'pending','reject':'pending','payment-recorded':'approved'}.get(action)
 if action=='reject' and row['state']=='approved':expected='approved'
 target={'cancel':'cancelled','approve':'approved','reject':'rejected','payment-recorded':'payment_recorded'}.get(action)
 if not expected or (not admin and action!='cancel'):raise a.ServiceError('Invalid cash-out action')
 reference=str(body.get('reference','')).strip()
 if action=='payment-recorded' and (body.get('confirmed_external_payment') is not True or not 3<=len(reference)<=200):raise a.ServiceError('Confirm the completed external bank payment and enter its reference')
 if c.execute('UPDATE cashout_requests SET state=?,updated=?,reviewer=?,reference=? WHERE id=? AND state=?',(target,int(time.time()),user['id'],reference,row['id'],expected)).rowcount!=1:raise a.ServiceError('Request changed or action already completed; reload',409)
 if action in ('cancel','reject'):
  c.execute('UPDATE wallet_accounts SET balance=balance+? WHERE owner=? AND currency=?',(row['amount'],row['owner'],row['currency']))
  c.execute('UPDATE cashout_funds SET available=available+? WHERE owner=? AND currency=?',(row['amount'],row['owner'],row['currency']))
  c.execute('INSERT INTO wallet_entries VALUES(?,?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),row['owner'],row['currency'],row['amount'],'cashout_release',None,str(uuid.uuid5(uuid.NAMESPACE_URL,'cashout-release/'+row['id'])),user['id'],'Cash-out hold released: '+row['id'],int(time.time())))
 a.audit(c,user['id'],'Cash-out '+action+' '+row['id'])
 return {'ok':True,'state':target,'bank_transfer_initiated':False}

def dispatch(path,method,body,c,user):
 if path.startswith('/api/platform/cashout/'):
  if user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
  route=path.rsplit('/',1)[-1]
  if route=='overview' and method=='GET':return {'enabled':enabled(c),'requests':rows(c),'funds':[dict(r) for r in c.execute('SELECT * FROM cashout_funds')]}
  if route=='authorize' and method=='POST':return authorize(c,body,user)
  if route=='settings' and method=='POST':
   if type(body.get('enabled')) is not bool:raise a.ServiceError('Choose cash-out status')
   c.execute('UPDATE cashout_settings SET enabled=? WHERE id=1',(int(body['enabled']),));a.audit(c,user['id'],'Cash-out request availability updated');return {'enabled':body['enabled']}
  if route=='action' and method=='POST':return action(c,body,user,True)
  if route=='destination' and method=='POST':
   row=c.execute('SELECT destination FROM cashout_requests WHERE id=?',(body.get('id'),)).fetchone()
   if not row:raise a.ServiceError('Cash-out request not found',404)
   a.audit(c,user['id'],'Cash-out bank destination viewed '+str(body.get('id')));return {'destination':a.unseal(row['destination'])}
 elif path.startswith('/api/cashout/'):
  route=path.rsplit('/',1)[-1]
  if route=='status' and method=='GET':return status(c,user)
  if route=='request' and method=='POST':return request(c,body,user)
  if route=='action' and method=='POST':return action(c,body,user)
 else:return None
 raise a.ServiceError('Cash-out route not found',404)
