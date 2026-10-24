"""Durable signup provisioning and owner-scoped phone/email services."""
import hmac, imaplib, json, os, re, secrets, time, uuid
from email import policy as email_policy
from email.parser import BytesParser
import advanced as a
import provider_settings as settings


def initialize(c):
 c.execute('CREATE TABLE IF NOT EXISTS communications_policy(id INTEGER PRIMARY KEY,revision INTEGER NOT NULL,payload TEXT NOT NULL)')
 c.execute('INSERT OR IGNORE INTO communications_policy VALUES(1,1,?)',(json.dumps({'sip_enabled':False,'mail_enabled':False}),))
 c.execute('CREATE TABLE IF NOT EXISTS communications_identity(id INTEGER PRIMARY KEY,value TEXT NOT NULL)')
 c.execute('INSERT OR IGNORE INTO communications_identity VALUES(1,?)',(str(uuid.uuid4()),))
 c.execute('CREATE TABLE IF NOT EXISTS communications_accounts(owner INTEGER NOT NULL,tenant_id INTEGER NOT NULL,kind TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,next_attempt INTEGER NOT NULL DEFAULT 0,updated INTEGER NOT NULL,PRIMARY KEY(owner,kind))')
 c.execute('CREATE TABLE IF NOT EXISTS communications_outbox(id TEXT PRIMARY KEY,owner INTEGER NOT NULL,tenant_id INTEGER NOT NULL,request_key TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,created INTEGER NOT NULL,updated INTEGER NOT NULL,UNIQUE(owner,request_key))')


def policy(c):
 r=c.execute('SELECT * FROM communications_policy WHERE id=1').fetchone();return {'revision':r['revision'],'values':json.loads(r['payload'])}


def enqueue(c,owner,tid,mode):
 # Commit credentials with the signup. Never transfer/reuse the user's platform password.
 for kind in ('sip','mail'):
  # Keep signup available before service commissioning; empty payload contains no secret.

  if c.execute('SELECT 1 FROM communications_accounts WHERE owner=? AND kind=?',(owner,kind)).fetchone():continue
  c.execute('INSERT OR IGNORE INTO communications_accounts(owner,tenant_id,kind,state,payload,updated) VALUES(?,?,?,?,?,?)',(owner,tid,kind,'queued',a.seal({'password':secrets.token_urlsafe(36),'account_type':'personal' if mode=='tax_only' else 'organization'}) if os.environ.get('DOBHRAP_ENCRYPTION_KEY') else '',int(time.time())))


def public(r):
 data=a.unseal(r['payload']) if r['payload'] else {'notice':'Waiting for persistent encryption key and service commissioning'}
 return {k:r[k] for k in ('kind','state','attempts','updated')}|{'details':data.get('details',{}),'notice':data.get('notice','Awaiting configured provisioning worker')}


def owned(c,user,kind):
 r=c.execute('SELECT * FROM communications_accounts WHERE owner=? AND tenant_id=? AND kind=?',(user['id'],user['tenant_id'],kind)).fetchone()
 if not r:raise a.ServiceError('Account provisioning has not been queued',409)
 return r,a.unseal(r['payload'])


def credentials(c,user,body):
 import app
 stored=c.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
 if not isinstance(body.get('password'),str) or len(body['password'])>1024 or not hmac.compare_digest(stored['hash'],app.password(body['password'],stored['salt'])):raise a.ServiceError('Confirm your current platform password',403)
 r,p=owned(c,user,body.get('kind'))
 if r['state'] not in ('ready','awaiting_switch'):raise a.ServiceError('Service account is not ready',409)
 a.audit(c,user['id'],'Communications managed credential revealed '+r['kind'])
 return {'username':p['details'].get('login') or p['details'].get('address'),'password':p['password'],'details':p['details']}


def mail_message(body):
 recipients=body.get('to');subject=body.get('subject');text=body.get('text')
 if not isinstance(recipients,str) or len(recipients)>1000:raise a.ServiceError('Enter up to five recipient email addresses')
 recipients=[v.strip() for v in recipients.split(',')]
 if not 1<=len(recipients)<=5 or any(not re.fullmatch(r'[^\s@<>;,\r\n]+@[^\s@<>;,\r\n]+\.[^\s@<>;,\r\n]+',v) for v in recipients):raise a.ServiceError('Enter valid comma-separated recipient addresses')
 if not isinstance(subject,str) or not 1<=len(subject)<=200 or any(ch in subject for ch in '\r\n\x00') or not isinstance(text,str) or not 1<=len(text.encode())<=64000:raise a.ServiceError('Enter a subject and a plain text message up to 64 KB')
 return {'to':recipients,'subject':subject,'text':text}


def inbox(p):
 d=p['details'];host=d['host']
 with imaplib.IMAP4_SSL(host,993,timeout=15) as client:
  client.login(d['address'],p['password']);status,_=client.select('INBOX',readonly=True)
  if status!='OK':raise a.ServiceError('Inbox unavailable',502)
  status,result=client.uid('search',None,'ALL')
  if status!='OK':raise a.ServiceError('Unable to list inbox',502)
  messages=[]
  for uid in result[0].split()[-20:][::-1]:
   # Bounded preview only; do not mark messages read or render HTML/attachments.
   status,parts=client.uid('fetch',uid,'(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)] BODY.PEEK[TEXT]<0.16384>)')
   raw=b'\n'.join(part[1] for part in parts if isinstance(part,tuple) and isinstance(part[1],bytes))[:20000]
   msg=BytesParser(policy=email_policy.default).parsebytes(raw)
   messages.append({'uid':uid.decode(),'from':str(msg.get('From','')),'subject':str(msg.get('Subject','')),'date':str(msg.get('Date','')),'preview':msg.get_payload(decode=True).decode('utf-8','replace')[:4000] if not msg.is_multipart() and isinstance(msg.get_payload(decode=True),bytes) else 'Multipart message; use your mail client to read attachments.'})
  return {'messages':messages,'notice':'Read-only previews of the latest 20 messages. Use IMAP for full messages and attachments.'}


def dispatch(path,method,body,c,user,tid):
 if not path.startswith('/api/communications/'):return None
 route=path.rsplit('/',1)[-1]
 if route=='admin':
  if user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
  if method=='POST':
   values=body.get('values')
   if not isinstance(values,dict) or set(values)!={'sip_enabled','mail_enabled'} or any(type(v) is not bool for v in values.values()):raise a.ServiceError('Choose mail and SIP provisioning status')
   if c.execute('UPDATE communications_policy SET payload=?,revision=revision+1 WHERE id=1 AND revision=?',(json.dumps(values),body.get('revision'))).rowcount!=1:raise a.ServiceError('Policy changed; reload',409)
   a.audit(c,user['id'],'Communications provisioning policy changed')
  return policy(c)|{'accounts':[dict(r) for r in c.execute('SELECT owner,tenant_id,kind,state,attempts,updated FROM communications_accounts ORDER BY updated DESC LIMIT 200')],'sip_bridge_configured':bool(settings.get('SIP_BRIDGE_TOKEN'))}
 if route=='status' and method=='GET':
  return policy(c)|{'workspace':dict(c.execute('SELECT name,service_mode FROM tenants WHERE id=?',(user['tenant_id'],)).fetchone()),'accounts':[public(r) for r in c.execute('SELECT * FROM communications_accounts WHERE owner=? AND tenant_id=? ORDER BY kind',(user['id'],user['tenant_id']))],'outbox':[dict(r) for r in c.execute('SELECT id,state,created,updated FROM communications_outbox WHERE owner=? AND tenant_id=? ORDER BY created DESC LIMIT 30',(user['id'],user['tenant_id']))],'phone_portal':'https://sip.dobhrap.com/'}
 if method!='POST':raise a.ServiceError('POST required',405)
 if route=='credentials':return credentials(c,user,body)
 if route=='retry':
  if body.get('kind') not in ('sip','mail'):raise a.ServiceError('Choose email or phone')
  c.execute("UPDATE communications_accounts SET next_attempt=0,state='queued' WHERE owner=? AND tenant_id=? AND kind=? AND state NOT IN ('processing','ready')",(user['id'],user['tenant_id'],body['kind']));return {'ok':True}
 if route=='inbox':
  r,p=owned(c,user,'mail')
  if r['state']!='ready':raise a.ServiceError('Mailbox not ready',409)
  try:return inbox(p)
  except (OSError,imaplib.IMAP4.error):raise a.ServiceError('Mail server unavailable; check mailbox settings and TLS readiness',502) from None
 if route=='send':
  if user['role']=='viewer':raise a.ServiceError('Read-only users cannot send messages',403)
  r,p=owned(c,user,'mail')
  if r['state']!='ready':raise a.ServiceError('Mailbox not ready',409)
  data=mail_message(body)
  try:key=str(uuid.UUID(str(body.get('request_key'))))
  except ValueError:raise a.ServiceError('Use a valid message identifier') from None
  c.execute('BEGIN IMMEDIATE');old=c.execute('SELECT * FROM communications_outbox WHERE owner=? AND request_key=?',(user['id'],key)).fetchone()
  if old:
   if a.unseal(old['payload'])!=data:raise a.ServiceError('Message identifier belongs to a different message',409)
   return {'id':old['id'],'state':old['state']}
  if c.execute('SELECT count(*) FROM communications_outbox WHERE owner=? AND created>?',(user['id'],int(time.time())-86400)).fetchone()[0]>=25:raise a.ServiceError('Daily message limit reached',429)
  mid=str(uuid.uuid4());now=int(time.time());c.execute('INSERT INTO communications_outbox VALUES(?,?,?,?,?,?,?,?)',(mid,user['id'],user['tenant_id'],key,'queued',a.seal(data),now,now));a.audit(c,user['id'],'System email queued '+mid);return {'id':mid,'state':'queued'}
 raise a.ServiceError('Unknown communications route',404)
