"""Super-admin issued full-service vouchers; atomic, audited redemption."""
import hashlib, re, secrets, time, uuid
import advanced as a

def initialize(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS service_coupons(id TEXT PRIMARY KEY,label TEXT NOT NULL,code_hash TEXT UNIQUE NOT NULL,hint TEXT NOT NULL,service_code TEXT NOT NULL,active INTEGER NOT NULL,expires INTEGER NOT NULL,max_uses INTEGER NOT NULL,per_user INTEGER NOT NULL,email TEXT NOT NULL,created INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS coupon_redemptions(order_id TEXT PRIMARY KEY,coupon_id TEXT NOT NULL,owner INTEGER NOT NULL,tenant_id INTEGER NOT NULL,created INTEGER NOT NULL);''')

def dispatch(path,method,body,c,user,tenant_id):
 if not path.startswith('/api/coupons/'):return None
 route=path.rsplit('/',1)[-1];admin=user['role']=='super_admin'
 if route=='manage':
  if not admin:raise a.ServiceError('Super administrator required',403)
  if method=='GET':return [dict(r) for r in c.execute('SELECT id,label,hint,service_code,active,expires,max_uses,per_user,email,created,(SELECT count(*) FROM coupon_redemptions r WHERE r.coupon_id=service_coupons.id) uses FROM service_coupons ORDER BY created DESC')]
  if method!='POST':raise a.ServiceError('Coupon route not found',404)
  if body.get('action')=='toggle':
   if type(body.get('active')) is not bool:raise a.ServiceError('Choose active or disabled')
   if c.execute('UPDATE service_coupons SET active=? WHERE id=?',(int(body['active']),body.get('id'))).rowcount!=1:raise a.ServiceError('Coupon not found',404)
   a.audit(c,user['id'],'Coupon state updated '+str(body['id']));return {'ok':True}
  label=str(body.get('label','')).strip();code=str(body.get('code') or ('OOB-'+secrets.token_hex(10))).strip().upper();service=str(body.get('service_code','')).strip();email=str(body.get('email','')).strip().lower()
  expires=body.get('expires');limit=body.get('max_uses');per=body.get('per_user')
  if not label or len(label)>120 or not re.fullmatch('[A-Z0-9-]{8,80}',code):raise a.ServiceError('Enter a label and coupon code of 8–80 letters, digits or hyphens (or leave code blank to generate)')
  if service and not re.fullmatch('[a-z][a-z0-9_]{1,59}',service):raise a.ServiceError('Invalid service code restriction')
  if email and ('@' not in email or len(email)>254):raise a.ServiceError('Invalid email restriction')
  if type(expires) is not int or expires<=int(time.time()) or type(limit) is not int or not 1<=limit<=100000 or type(per) is not int or not 1<=per<=limit:raise a.ServiceError('Choose a future expiry, total limit and per-user limit')
  if type(body.get('active')) is not bool:raise a.ServiceError('Choose whether to activate the coupon')
  cid=str(uuid.uuid4());c.execute('INSERT INTO service_coupons VALUES(?,?,?,?,?,?,?,?,?,?,?)',(cid,label,hashlib.sha256(code.encode()).hexdigest(),code[-4:],service,int(body['active']),expires,limit,per,email,int(time.time())))
  a.audit(c,user['id'],'Full-service coupon created '+cid);return {'id':cid,'code':code,'notice':'Copy this code now. Only its hash and last four characters are stored. Coupon covers the full price of one eligible service per redemption; no cash value, partial discount or change.'}
 if route=='redemptions' and method=='GET':
  if not admin:raise a.ServiceError('Super administrator required',403)
  return [dict(r) for r in c.execute('SELECT r.*,p.label,o.name,o.service_code,o.currency,o.amount FROM coupon_redemptions r JOIN service_coupons p ON p.id=r.coupon_id JOIN market_orders o ON o.id=r.order_id ORDER BY r.created DESC LIMIT 500')]
 if route!='redeem' or method!='POST':raise a.ServiceError('Coupon route not found',404)
 if user['role'] not in ('admin','super_admin'):raise a.ServiceError('Account administrator required to purchase',403)
 import marketplace as market
 offer=c.execute('SELECT service_code FROM market_products WHERE id=?',(body.get('product_id'),)).fetchone()
 if offer and offer['service_code']=='tax_analyst_session':raise a.ServiceError('Tax Analyst sessions require verified live payment; coupons do not apply',403)
 market.require_open(c)
 code=str(body.get('code','')).strip().upper()
 if not re.fullmatch('[A-Z0-9-]{8,80}',code):raise a.ServiceError('Coupon is invalid or unavailable')
 request_key=str(uuid.UUID(str(body.get('request_key',''))));digest=hashlib.sha256(code.encode()).hexdigest();now=int(time.time());c.execute('BEGIN IMMEDIATE')
 coupon=c.execute('SELECT * FROM service_coupons WHERE code_hash=?',(digest,)).fetchone()
 existing=c.execute('SELECT o.*,r.coupon_id FROM market_orders o LEFT JOIN coupon_redemptions r ON r.order_id=o.id WHERE o.tenant_id=? AND o.owner=? AND o.request_key=?',(tenant_id,user['id'],request_key)).fetchone()
 if existing:
  if not coupon or existing['coupon_id']!=coupon['id'] or existing['product_id']!=body.get('product_id'):raise a.ServiceError('Purchase request already used for another order',409)
  return {'id':existing['id'],'state':existing['state'],'reused':True}
 product=c.execute('SELECT * FROM market_products WHERE id=? AND active=1',(body.get('product_id'),)).fetchone()
 if not coupon or not product or not coupon['active'] or coupon['expires']<=now:raise a.ServiceError('Coupon is invalid or unavailable')
 if coupon['service_code'] and coupon['service_code']!=product['service_code']:raise a.ServiceError('Coupon does not cover this service')
 if coupon['email'] and coupon['email']!=user['email'].lower():raise a.ServiceError('Coupon is restricted to another account')
 uses=c.execute('SELECT count(*) FROM coupon_redemptions WHERE coupon_id=?',(coupon['id'],)).fetchone()[0]
 user_uses=c.execute('SELECT count(*) FROM coupon_redemptions WHERE coupon_id=? AND owner=?',(coupon['id'],user['id'])).fetchone()[0]
 if uses>=coupon['max_uses'] or user_uses>=coupon['per_user']:raise a.ServiceError('Coupon redemption limit reached',409)
 order=str(uuid.uuid4());c.execute("INSERT INTO market_orders(id,tenant_id,owner,product_id,name,service_code,amount,currency,gateway,environment,request_key,state,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(order,tenant_id,user['id'],product['id'],product['name'],product['service_code'],0,product['currency'],'coupon','coupon',request_key,'fulfilled',now))
 market.snapshot_terms(c,order,product['id'])
 c.execute('INSERT INTO coupon_redemptions VALUES(?,?,?,?,?)',(order,coupon['id'],user['id'],tenant_id,now))
 c.execute('INSERT INTO market_services(order_id,tenant_id,service_code,name,environment,status,activated) VALUES(?,?,?,?,?,?,?)',(order,tenant_id,product['service_code'],product['name'],'coupon','active',now));a.audit(c,user['id'],'Coupon redeemed for service '+order)
 market.activate_subscription(c,order)
 return {'id':order,'state':'fulfilled','reused':False,'notice':'Service price fully covered by coupon; no gateway charge.'}

