"""Audited user store-credit balances and atomic marketplace settlement."""
import re, time, uuid
from decimal import Decimal
from babel.numbers import list_currencies, get_currency_precision
import advanced as a

# Matched against the order, not the current product price. Used by service entitlement checks.
PAID="(o.gateway='wallet' AND o.environment='wallet' AND EXISTS(SELECT 1 FROM wallet_entries w WHERE w.order_id=o.id AND w.owner=o.owner AND w.currency=o.currency AND w.kind='purchase' AND w.amount=-o.amount))"

def initialize(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS wallet_accounts(owner INTEGER NOT NULL,currency TEXT NOT NULL,balance INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(owner,currency));
 CREATE TABLE IF NOT EXISTS wallet_entries(id TEXT PRIMARY KEY,owner INTEGER NOT NULL,currency TEXT NOT NULL,amount INTEGER NOT NULL,kind TEXT NOT NULL,order_id TEXT UNIQUE,request_key TEXT NOT NULL,actor INTEGER NOT NULL,reason TEXT NOT NULL,created INTEGER NOT NULL,UNIQUE(actor,request_key));''')

def currency(value):
 value=str(value or '').upper()
 if value not in list_currencies() or value in ('XTS','XXX'):raise a.ServiceError('Choose a recognized currency')
 return value

def minor(value,code):
 text=str(value)
 if not re.fullmatch(r'\d{1,10}(\.\d{1,4})?',text):raise a.ServiceError('Enter a positive credit amount')
 scaled=Decimal(text)*(10**get_currency_precision(code))
 if scaled!=scaled.to_integral_value() or not 1<=scaled<=100000000000:raise a.ServiceError('Invalid amount or currency precision')
 return int(scaled)

def status(c,user):
 balances=[dict(r) for r in c.execute('SELECT currency,balance FROM wallet_accounts WHERE owner=? ORDER BY currency',(user['id'],))]
 if not balances:balances=[{'currency':'USD','balance':0}]
 return {'balances':balances,'entries':[dict(r) for r in c.execute('SELECT id,currency,amount,kind,order_id,reason,created FROM wallet_entries WHERE owner=? ORDER BY created DESC,id DESC LIMIT 100',(user['id'],))],'notice':'Store credit can pay the full price of any available marketplace purchase in the same currency. No automatic currency conversion or split payment.'}

def credit(c,body,user):
 if user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
 uid=body.get('owner');code=currency(body.get('currency','USD'));amount=minor(body.get('amount'),code);reason=str(body.get('reason','')).strip()
 if type(uid) is not int or not c.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():raise a.ServiceError('Choose an existing user')
 if not 3<=len(reason)<=500:raise a.ServiceError('Enter a credit reason (3–500 characters)')
 try:key=str(uuid.UUID(str(body.get('request_key'))))
 except ValueError:raise a.ServiceError('Use a valid credit request identifier') from None
 c.execute('BEGIN IMMEDIATE')
 old=c.execute('SELECT * FROM wallet_entries WHERE actor=? AND request_key=?',(user['id'],key)).fetchone()
 if old:
  if old['kind']!='credit' or old['owner']!=uid or old['currency']!=code or old['amount']!=amount or old['reason']!=reason:raise a.ServiceError('Request identifier already used for a different transaction',409)
  return {'id':old['id'],'reused':True,'balance':status(c,{'id':uid})['balances']}
 c.execute('INSERT OR IGNORE INTO wallet_accounts(owner,currency,balance) VALUES(?,?,0)',(uid,code))
 if c.execute('UPDATE wallet_accounts SET balance=balance+? WHERE owner=? AND currency=? AND balance<=?',(amount,uid,code,10000000000000-amount)).rowcount!=1:raise a.ServiceError('Account balance limit reached',409)
 eid=str(uuid.uuid4());c.execute('INSERT INTO wallet_entries VALUES(?,?,?,?,?,?,?,?,?,?)',(eid,uid,code,amount,'credit',None,key,user['id'],reason,int(time.time())))
 a.audit(c,user['id'],'Wallet manual credit '+eid+' user '+str(uid)+' '+code+' '+str(amount))
 return {'id':eid,'reused':False,'balance':status(c,{'id':uid})['balances']}

def checkout(c,body,user,tenant_id):
 import marketplace as market
 if user['role']=='viewer':raise a.ServiceError('Read-only accounts cannot purchase',403)
 market.require_open(c)
 if not market.enabled():raise a.ServiceError('Marketplace checkout is disabled',503)
 try:key=str(uuid.UUID(str(body.get('request_key'))))
 except ValueError:raise a.ServiceError('Use a valid purchase request identifier') from None
 c.execute('BEGIN IMMEDIATE')
 old=c.execute('SELECT * FROM market_orders WHERE tenant_id=? AND owner=? AND request_key=?',(tenant_id,user['id'],key)).fetchone()
 if old:
  if old['product_id']!=body.get('product_id') or old['gateway']!='wallet':raise a.ServiceError('Purchase request already belongs to another order',409)
  return {'id':old['id'],'state':old['state'],'reused':True}
 product=c.execute('SELECT * FROM market_products WHERE id=? AND active=1',(body.get('product_id'),)).fetchone()
 if not product:raise a.ServiceError('Offer unavailable',404)
 amount=product['amount'];code=product['currency']
 if type(amount) is not int or amount<=0:raise a.ServiceError('Invalid offer price')
 if c.execute('UPDATE wallet_accounts SET balance=balance-? WHERE owner=? AND currency=? AND balance>=?',(amount,user['id'],code,amount)).rowcount!=1:raise a.ServiceError('Insufficient '+code+' account balance',402)
 oid=str(uuid.uuid4());now=int(time.time())
 c.execute('INSERT INTO market_orders(id,tenant_id,owner,product_id,name,service_code,amount,currency,gateway,environment,request_key,state,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(oid,tenant_id,user['id'],product['id'],product['name'],product['service_code'],amount,code,'wallet','wallet',key,'fulfilled',now))
 c.execute('INSERT INTO wallet_entries VALUES(?,?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),user['id'],code,-amount,'purchase',oid,key,user['id'],'Marketplace purchase: '+product['name'],now))
 market.snapshot_terms(c,oid,product['id'])
 c.execute('INSERT INTO market_services(order_id,tenant_id,service_code,name,environment,status,activated) VALUES(?,?,?,?,?,?,?)',(oid,tenant_id,product['service_code'],product['name'],'wallet','active',now));market.activate_subscription(c,oid)
 a.audit(c,user['id'],'Wallet purchase settled '+oid)
 return {'id':oid,'state':'fulfilled','reused':False}

def admin(path,method,body,c,user):
 if not path.startswith('/api/platform/wallet/'):return None
 if user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
 route=path.rsplit('/',1)[-1]
 if route=='credit' and method=='POST':return credit(c,body,user)
 if route=='overview' and method=='GET':return {'users':[dict(r) for r in c.execute('SELECT u.id,u.email,u.role,u.tenant_id,t.name workspace FROM users u JOIN tenants t ON t.id=u.tenant_id ORDER BY u.email')],'balances':[dict(r) for r in c.execute('SELECT owner,currency,balance FROM wallet_accounts ORDER BY owner,currency')],'entries':[dict(r) for r in c.execute('SELECT * FROM wallet_entries ORDER BY created DESC,id DESC LIMIT 200')]}
 raise a.ServiceError('Wallet route not found',404)
