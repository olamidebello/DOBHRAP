"""Encrypted platform configuration shared by web and fixed background workers.
Never mutates process environment: concurrent requests cannot inherit another request's keys.
"""
import os
import hmac
import re
import sqlite3
import database
import sys
import json
import time
from urllib.parse import urlsplit

SECRET_FIELDS={'SMTP_PASSWORD','SUPPORT_WEBHOOK_TOKEN','OPENAI_API_KEY','STRIPE_SECRET_KEY','STRIPE_WEBHOOK_SECRET','PAYSTACK_SECRET_KEY','PLAID_CLIENT_ID','PLAID_SECRET','CHECK_API_KEY','EFILE_GATEWAY_TOKEN'}
FIELDS={
 'SMTP_HOST':'text','SMTP_PORT':'port','SMTP_USERNAME':'email_text','SMTP_PASSWORD':'secret','SMTP_FROM':'email','SMTP_SECURITY':['starttls','tls'],
 'SUPPORT_WEBHOOK_TOKEN':'secret',
 'OPENAI_API_KEY':'secret','TAX_ANALYST_MODEL':'text','DOBHRAP_ENABLE_TAX_ANALYST':'bool','TAX_AI_MODEL':'text','DOBHRAP_ENABLE_TAX_AI':'bool','SUPPORT_AI_MODEL':'text','DOBHRAP_ENABLE_SUPPORT_AI':'bool','DOBHRAP_SUPPORT_AUTO_AI':'bool',
 'STRIPE_SECRET_KEY':'secret','STRIPE_WEBHOOK_SECRET':'secret','PAYSTACK_SECRET_KEY':'secret',
 'PAYMENTS_ENV':['test','live'],'DOBHRAP_ENABLE_MARKETPLACE':'bool','DOBHRAP_ENABLE_LIVE_PAYMENTS':'bool',
 'PLAID_CLIENT_ID':'secret','PLAID_SECRET':'secret','PLAID_ENV':['sandbox','production'],'PLAID_REDIRECT_URI':'url',
 'DOBHRAP_ENABLE_LIVE_BANKING':'bool','DOBHRAP_ENABLE_TENANT_BANKING':'bool','DOBHRAP_ENABLE_AUTO_BANK_IMPORT':'bool','DOBHRAP_ENABLE_BANK_STATEMENTS':'bool',
 'CHECK_API_KEY':'secret','CHECK_ENV':['sandbox','production'],'DOBHRAP_ENABLE_LIVE_PAYROLL':'bool',
 'EFILE_GATEWAY_URL':'url','EFILE_GATEWAY_TOKEN':'secret','DOBHRAP_ENABLE_EFILE_TRANSMISSION':'bool',
}

def db_path():return getattr(sys.modules.get('app'),'DB',os.environ.get('DOBHRAP_DB','data/dobhrap.db'))
def initialize(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS provider_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS provider_checks(provider TEXT PRIMARY KEY,ok INTEGER NOT NULL,checked INTEGER NOT NULL,message TEXT NOT NULL,duration_ms INTEGER NOT NULL DEFAULT 0);''')
 if 'duration_ms' not in {row[1] for row in c.execute('PRAGMA table_info(provider_checks)')}:c.execute('ALTER TABLE provider_checks ADD COLUMN duration_ms INTEGER NOT NULL DEFAULT 0')

def get(name,default=None):
 if name not in FIELDS:return os.environ.get(name,default)
 try:
  with database.connect(db_path()) as c:row=c.execute('SELECT value FROM provider_settings WHERE key=?',(name,)).fetchone()
 except sqlite3.OperationalError:return os.environ.get(name,default)
 if not row:return os.environ.get(name,default)
 import advanced as a
 return a.unseal(row[0])['value']

def snapshot(c):
 result={}
 for name,kind in FIELDS.items():
  row=c.execute('SELECT value,updated FROM provider_settings WHERE key=?',(name,)).fetchone()
  if row:
   import advanced as a
   value=a.unseal(row['value'])['value']
  else:value=os.environ.get(name,'')
  result[name]={'configured':bool(value),'source':'GUI' if row else 'server','updated':row['updated'] if row else None}
  if name not in SECRET_FIELDS:result[name]['value']=value
 return {'settings':result,'checks':[dict(r) for r in c.execute('SELECT * FROM provider_checks')],
         'notice':'Blank key fields preserve saved keys. Disable stores an empty override. GUI settings override server environment settings.'}

def validate(name,value):
 import advanced as a
 kind=FIELDS.get(name)
 if kind is None:raise a.ServiceError('Unsupported configuration field')
 if not isinstance(value,str) or len(value)>4096 or '\n' in value or '\r' in value:raise a.ServiceError('Invalid setting value')
 if kind=='port' and value and (not value.isdigit() or not 1<=int(value)<=65535):raise a.ServiceError('Enter a valid SMTP port')
 if kind=='email' and value and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',value):raise a.ServiceError('Enter a valid sender email')
 if kind=='email_text' and len(value)>254:raise a.ServiceError('SMTP username is too long')
 if kind=='bool' and value not in ('0','1'):raise a.ServiceError('Invalid feature switch')
 if isinstance(kind,list) and value not in kind:raise a.ServiceError('Invalid provider environment')
 if kind=='text' and value and not re.fullmatch('[A-Za-z0-9._:-]{1,100}',value):raise a.ServiceError('Invalid model name')
 if kind=='url' and value:
  p=urlsplit(value)
  if p.scheme!='https' or not p.hostname or p.username or p.password or p.fragment:raise a.ServiceError('Provider URLs require HTTPS without credentials')
 if name=='SUPPORT_WEBHOOK_TOKEN' and value and len(value)<32:raise a.ServiceError('Integration token must contain at least 32 characters')
 if name=='OPENAI_API_KEY' and value and not value.startswith('sk-'):raise a.ServiceError('Invalid OpenAI key format')
 if name in ('STRIPE_SECRET_KEY','PAYSTACK_SECRET_KEY') and value and not value.startswith(('sk_test_','sk_live_')):raise a.ServiceError('Invalid payment key format')
 if name=='STRIPE_WEBHOOK_SECRET' and value and not value.startswith('whsec_'):raise a.ServiceError('Invalid Stripe signing secret format')

def check(provider):
 import advanced as a
 import marketplace as m
 if provider=='smtp':
  import password_reset
  return password_reset.check_mail_connection()
 elif provider=='openai':
  key=get('OPENAI_API_KEY','');model=get('SUPPORT_AI_MODEL','') or get('TAX_AI_MODEL','') or get('TAX_ANALYST_MODEL','')
  if not key or not model:raise a.ServiceError('Configure an OpenAI key and model first')
  a.request_json('https://api.openai.com/v1/models/'+a.identifier(model),headers={'Authorization':'Bearer '+key},method='GET')
 elif provider=='stripe':
  result=m.provider('stripe','/balance')
  if result.get('livemode') is not (m.environment()=='live'):raise a.ServiceError('Stripe environment mismatch')
 elif provider=='paystack':
  if m.provider('paystack','/balance').get('status') is not True:raise a.ServiceError('Paystack credentials rejected')
 elif provider=='plaid':a.plaid('/institutions/get',{'country_codes':['US'],'count':1,'offset':0})
 else:raise a.ServiceError('Unsupported connection check')
 return {'ok':True,'message':'Provider accepted credentials. This does not verify webhook delivery or perform a charge.'}

def dispatch(path,method,body,c,user):
 import advanced as a
 if path!='/api/provider-settings':return None
 if user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
 if method=='GET':return snapshot(c)
 import app
 if not hmac.compare_digest(user['hash'],app.password(str(body.get('confirm_password','')),user['salt'])):
  raise a.ServiceError('Confirm your current administrator password',403)
 action=body.get('action')
 if action=='provision_stripe':
  import marketplace as market
  target=market.base_url()+'/api/market/webhooks/stripe'
  listing=market.provider('stripe','/webhook_endpoints?limit=100')
  matches=[item for item in listing.get('data',[]) if item.get('url')==target]
  if listing.get('has_more') or len(matches)>1:raise a.ServiceError('Ambiguous endpoint inventory; reconcile merchant endpoints first',409)
  events={'enabled_events[0]':'checkout.session.completed','enabled_events[1]':'checkout.session.async_payment_succeeded','enabled_events[2]':'checkout.session.expired'}
  if not matches:
   result=market.provider('stripe','/webhook_endpoints',{'url':target,'description':'OOB marketplace payment verification','api_version':'2024-06-20',**events},idempotency='oob-webhook-'+market.environment())
   secret=result.get('secret','')
   if not secret.startswith('whsec_'):raise a.ServiceError('Provider did not return a signing secret',502)
   c.execute('INSERT OR REPLACE INTO provider_settings VALUES(?,?,?)',('STRIPE_WEBHOOK_SECRET',a.seal({'value':secret}),int(time.time())))
   c.commit()  # Persist the one-time provider secret immediately.
  else:
   if not get('STRIPE_WEBHOOK_SECRET',''):raise a.ServiceError('Enter the existing endpoint signing secret before provisioning',409)
   market.provider('stripe','/webhook_endpoints/'+a.identifier(matches[0]['id'],'we_'),{**events,'disabled':'false'})
  a.audit(c,user['id'],'Stripe webhook endpoint provisioned')
  return {'ok':True,'message':'Stripe endpoint configured. Confirm delivery with a signed test checkout event.'}
 if action=='generate_intake_token':
  import secrets
  token=secrets.token_urlsafe(48)
  c.execute('INSERT OR REPLACE INTO provider_settings VALUES(?,?,?)',('SUPPORT_WEBHOOK_TOKEN',a.seal({'value':token}),int(time.time())))
  a.audit(c,user['id'],'Support integration credential rotated')
  return {'ok':True,'token':token,'notice':'New credential shown once. Save it securely. The previous token is invalid.'}
 if action=='profile':
  return {'database_ok':c.execute('PRAGMA quick_check').fetchone()[0]=='ok','active_workspaces':c.execute("SELECT count(*) FROM tenants WHERE status='active'").fetchone()[0],
   'support_queue':c.execute("SELECT count(*) FROM support_jobs WHERE state='queued'").fetchone()[0],
   'payment_queue':c.execute("SELECT count(*) FROM market_orders WHERE state IN ('pending','creating','checkout_error')").fetchone()[0],
   'checks':[dict(r) for r in c.execute('SELECT * FROM provider_checks')],'checked':int(time.time())}
 if action=='save':
  values=body.get('values',{});disable=body.get('disable',[])
  if not isinstance(values,dict) or not isinstance(disable,list):raise a.ServiceError('Invalid settings request')
  effective={name:value for name,value in values.items() if value!='' or name not in SECRET_FIELDS}
  for name in disable:
   if name not in SECRET_FIELDS:raise a.ServiceError('Only provider keys may be disabled')
   effective[name]=''
  for name,value in effective.items():validate(name,value)
  if any(name in ('DOBHRAP_ENABLE_LIVE_PAYMENTS','DOBHRAP_ENABLE_LIVE_BANKING','DOBHRAP_ENABLE_LIVE_PAYROLL','DOBHRAP_ENABLE_EFILE_TRANSMISSION') and value=='1' for name,value in effective.items()) and body.get('confirm_live') is not True:
   raise a.ServiceError('Explicitly confirm live financial operations')
  for name,value in effective.items():c.execute('INSERT OR REPLACE INTO provider_settings VALUES(?,?,?)',(name,a.seal({'value':value}),int(time.time())))
  c.execute('DELETE FROM provider_checks')
  a.audit(c,user['id'],'Provider configuration updated: '+', '.join(sorted(effective)))
  return {'ok':True}
 if action=='test':
  provider=body.get('provider')
  if provider not in ('smtp','openai','stripe','paystack','plaid'):raise a.ServiceError('Unsupported provider')
  started=time.monotonic()
  try:result=check(provider)
  except Exception:result={'ok':False,'message':'Connection check failed. Check credentials, environment, model access and provider status.'}
  c.execute('INSERT OR REPLACE INTO provider_checks VALUES(?,?,?,?,?)',(provider,int(result['ok']),int(time.time()),result['message'],int((time.monotonic()-started)*1000)))
  a.audit(c,user['id'],'Provider connection check '+provider+' '+str(result['ok']))
  return result
 raise a.ServiceError('Unsupported settings action')

