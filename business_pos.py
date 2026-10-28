"""Business-only Global POS connection and idempotent opt-in storefront provisioning."""
import base64,json,os,re,secrets,time
from pathlib import Path
import advanced as a

ISSUER='https://olamideolatayobello.com'
ALLOWED={'https://pos.africandroid.com','https://pos.africandroid.world'}
def origin():
 value=os.environ.get('GLOBALPOS_ORIGIN','https://pos.africandroid.com').rstrip('/')
 if value not in ALLOWED:raise a.ServiceError('Configure an approved Global POS origin',503)
 return value

def initialize(c):
 c.execute('CREATE TABLE IF NOT EXISTS business_pos_preferences(tenant_id INTEGER PRIMARY KEY,payload TEXT NOT NULL,state TEXT NOT NULL,updated INTEGER NOT NULL,last_attempt INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT \'\')')

def registration(c,tid,body,mode):
 chosen=body.get('account_type')=='storefront' or body.get('create_storefront') is True
 if not chosen:return
 if mode!='business':raise ValueError('Storefront registration requires a business account')
 country=str(body.get('store_country','')).strip().upper();currency=str(body.get('store_currency','')).strip().upper();zone=str(body.get('store_timezone','')).strip()
 if not re.fullmatch('[A-Z]{2}',country) or not re.fullmatch('[A-Z]{3}',currency):raise ValueError('Choose a two-letter country code and three-letter currency code for the storefront')
 try:
  from zoneinfo import ZoneInfo
  ZoneInfo(zone)
 except (ValueError,KeyError):raise ValueError('Choose a valid store timezone') from None
 prefs={'country':country,'currency':currency,'timezone':zone,'category':'Restaurant' if body.get('store_category')=='restaurant' else 'Retail'}
 c.execute('INSERT INTO business_pos_preferences VALUES(?,?,?,?,?,?)',(tid,a.seal(prefs),'queued',int(time.time()),0,''))

def assertion(user,tenant,nonce,target='merchant',storefront=None,provision=False):
 if not isinstance(nonce,str) or not re.fullmatch('[a-f0-9]{64}',nonce):raise a.ServiceError('Invalid secure connection challenge')
 if target not in ('merchant','pos','restaurant'):raise a.ServiceError('Choose store, retail POS or restaurant POS')
 path=Path(os.environ.get('DOBHRAP_POS_SIGNING_KEY','/etc/dobhrap-pos-signing.key'))
 if not path.is_file():raise a.ServiceError('Store & POS connection is awaiting administrator setup',503)
 from cryptography.hazmat.primitives.serialization import load_pem_private_key
 from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
 private=load_pem_private_key(path.read_bytes(),password=None)
 if not isinstance(private,Ed25519PrivateKey):raise a.ServiceError('Store & POS signing configuration is invalid',503)
 now=int(time.time());claims={'iss':ISSUER,'aud':origin(),'scope':'storefront-provision' if provision else 'store-pos','sub':str(user['id']),'tenant':str(tenant['id']),'role':user['role'],'company':tenant['name'],'email':user['email'],'iat':now,'exp':now+60,'jti':secrets.token_hex(32),'nonce':nonce,'target':target}
 if storefront:claims['storefront']=storefront
 def encode(value):return base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).rstrip(b'=').decode()
 data=encode({'alg':'EdDSA','typ':'JWT'})+'.'+encode(claims);return data+'.'+base64.urlsafe_b64encode(private.sign(data.encode())).rstrip(b'=').decode()

def dispatch(path,method,body,c,user,tid):
 if path not in ('/api/business/pos','/api/business/pos-session','/api/business/pos-provision'):return None
 tenant=c.execute('SELECT * FROM tenants WHERE id=?',(tid,)).fetchone()
 if not tenant or tenant['service_mode']!='business' or tenant['status']!='active':raise a.ServiceError('Store & POS is available to active business accounts only',403)
 if user['tenant_id']!=tid and user['role']!='super_admin':raise a.ServiceError('Workspace access denied',403)
 row=c.execute('SELECT * FROM business_pos_preferences WHERE tenant_id=?',(tid,)).fetchone();prefs=a.unseal(row['payload']) if row else None
 if path=='/api/business/pos' and method=='GET':
  return {'origin':origin(),'connected':Path(os.environ.get('DOBHRAP_POS_SIGNING_KEY','/etc/dobhrap-pos-signing.key')).is_file(),'company':tenant['name'],'storefront':{'state':row['state'],'updated':row['updated'],'error':row['error'],'slug':prefs.get('slug','')} if row else None,'notice':'Open your company’s Store & POS workspace. Your company identity, email and current role are shared with Global POS; your password is never transferred. Connected access expires after 15 minutes. Contract-only and personal tax accounts do not receive store administration.'}
 if method!='POST':raise a.ServiceError('POST required',405)
 if user['role']=='viewer':raise a.ServiceError('Business administrator or editor required',403)
 if path=='/api/business/pos-provision':
  if user['role'] not in ('admin','super_admin') or not row:raise a.ServiceError('No opted-in storefront for this workspace',403)
  if row['last_attempt']>int(time.time())-30:raise a.ServiceError('Please wait before retrying storefront setup',429)
  c.execute("UPDATE business_pos_preferences SET state='queued',error='' WHERE tenant_id=?",(tid,));return {'ok':True,'notice':'Storefront setup queued. Refresh shortly.'}
 return {'assertion':assertion(user,tenant,body.get('nonce'),body.get('target','merchant'),prefs),'origin':origin()}

def process(app,limit=3):
 with app.connect() as c:jobs=[dict(r) for r in c.execute("SELECT p.*,t.name,t.status,t.service_mode FROM business_pos_preferences p JOIN tenants t ON t.id=p.tenant_id WHERE p.state IN ('queued','retry') AND p.last_attempt<? AND t.status='active' AND t.service_mode='business' ORDER BY p.updated LIMIT ?",(int(time.time())-60,limit))]
 for job in jobs:
  with app.connect() as c:
   now=int(time.time())
   if c.execute('UPDATE business_pos_preferences SET last_attempt=? WHERE tenant_id=? AND last_attempt=?',(now,job['tenant_id'],job['last_attempt'])).rowcount!=1:continue
   user=c.execute("SELECT * FROM users WHERE tenant_id=? AND account_status='active' AND role='admin' ORDER BY id LIMIT 1",(job['tenant_id'],)).fetchone();c.commit()
   try:
    if not user:raise a.ServiceError('An active business administrator must complete store setup')
    prefs=a.unseal(job['payload']);nonce=secrets.token_hex(32);token=assertion(user,{'id':job['tenant_id'],'name':job['name']},nonce,storefront=prefs,provision=True)
    result=a.request_json(origin()+'/api/federation/provision',{'assertion':token,'nonce':nonce},method='POST',timeout=15);front=result.get('storefront',{})
    if not re.fullmatch('[a-z0-9-]{1,80}',str(front.get('slug',''))) or result.get('state')!='ready':raise a.ServiceError('Unexpected storefront provisioning response')
    prefs['slug']=front['slug'];prefs['store_id']=front['store_id'];c.execute("UPDATE business_pos_preferences SET payload=?,state='ready',updated=?,error='' WHERE tenant_id=?",(a.seal(prefs),int(time.time()),job['tenant_id']));a.audit(c,user['id'],'Global POS draft storefront provisioned for workspace '+str(job['tenant_id']))
   except Exception:
    c.rollback();c.execute("UPDATE business_pos_preferences SET state='retry',updated=?,error=? WHERE tenant_id=?",(int(time.time()),'Store setup is waiting for the POS connection. Your account and private storefront choice are preserved.',job['tenant_id']))
