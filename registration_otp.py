"""Twilio Verify signup gate with private credentials, one-use tickets and SMS caps."""
import base64,datetime,hashlib,hmac,json,os,re,secrets,time,uuid
from urllib.request import Request,build_opener
from urllib.parse import urlencode
from urllib.error import HTTPError,URLError
import advanced as a
import provider_settings as settings

def initialize(c):
 c.execute('CREATE TABLE IF NOT EXISTS registration_otp_policy(id INTEGER PRIMARY KEY,revision INTEGER NOT NULL,enabled INTEGER NOT NULL,daily_limit INTEGER NOT NULL,creation_state TEXT NOT NULL)')
 c.execute("INSERT OR IGNORE INTO registration_otp_policy VALUES(1,1,0,50,'idle')")
 c.execute('CREATE TABLE IF NOT EXISTS registration_otp_challenges(id TEXT PRIMARY KEY,phone TEXT NOT NULL,phone_hash TEXT NOT NULL,ticket_hash TEXT NOT NULL,state TEXT NOT NULL,attempts INTEGER NOT NULL,expires INTEGER NOT NULL,created INTEGER NOT NULL,user_id INTEGER NOT NULL DEFAULT 0)')
 c.execute('CREATE TABLE IF NOT EXISTS registration_otp_usage(day TEXT PRIMARY KEY,requests INTEGER NOT NULL)')

def credentials(master=False):
 account=settings.get('TWILIO_ACCOUNT_SID','');token=settings.get('TWILIO_AUTH_TOKEN','');key=settings.get('TWILIO_API_KEY_SID','');secret=settings.get('TWILIO_API_KEY_SECRET','')
 if not master and re.fullmatch(r'SK[0-9a-fA-F]{32}',key) and secret:return key,secret
 if re.fullmatch(r'AC[0-9a-fA-F]{32}',account) and token:return account,token
 raise a.ServiceError('Configure Twilio account credentials or an API key pair',503)

def provider(path,data=None,master=False):
 user,password=credentials(master);root='https://api.twilio.com' if path.startswith('/2010-04-01/') else 'https://verify.twilio.com'
 req=Request(root+path,data=urlencode(data).encode() if data is not None else None,headers={'Authorization':'Basic '+base64.b64encode((user+':'+password).encode()).decode(),'Content-Type':'application/x-www-form-urlencoded'},method='POST' if data is not None else 'GET')
 try:
  with build_opener(a.NoRedirect).open(req,timeout=20) as r:
   raw=r.read(200001)
   if len(raw)>200000:raise ValueError()
   return json.loads(raw)
 except (HTTPError,URLError,OSError,ValueError):raise a.ServiceError('Twilio request failed. Verify credentials, account permissions, balance and Verify logs; no automatic retry was made.',502) from None

def service_sid():
 sid=settings.get('TWILIO_VERIFY_SERVICE_SID','')
 if not re.fullmatch(r'VA[0-9a-fA-F]{32}',sid):raise a.ServiceError('Provision a Twilio Verify service first',503)
 return sid

def save_key(c,key,value):c.execute('INSERT OR REPLACE INTO provider_settings VALUES(?,?,?)',(key,a.seal({'value':value}),int(time.time())))

def admin(c,user,body,method):
 if user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
 if method=='POST' and body.get('action')!='status':
  import app,password_reset
  c.execute('BEGIN IMMEDIATE');password_reset.throttle(c,'otp-admin:'+str(user['id']),10,int(time.time()));actor=c.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone();password=body.get('confirm_password','')
  if not isinstance(password,str) or len(password)>1024 or not hmac.compare_digest(actor['hash'],app.password(password,actor['salt'])):c.commit();raise a.ServiceError('Confirm your administrator password',403)
  if body.get('action')=='save':
   if type(body.get('enabled')) is not bool or type(body.get('daily_limit')) is not int or not 1<=body['daily_limit']<=1000:raise a.ServiceError('Choose an enable switch and daily SMS limit of 1–1000')
   if body['enabled']:credentials();service_sid()
   if c.execute('UPDATE registration_otp_policy SET enabled=?,daily_limit=?,revision=revision+1 WHERE id=1 AND revision=?',(int(body['enabled']),body['daily_limit'],body.get('revision'))).rowcount!=1:raise a.ServiceError('OTP settings changed; reload',409)
  elif body.get('action')=='provision':
   prior=c.execute('SELECT creation_state FROM registration_otp_policy WHERE id=1').fetchone()[0]
   sid=settings.get('TWILIO_VERIFY_SERVICE_SID','')
   if not sid:
    if prior=='creating':raise a.ServiceError('Previous provisioning outcome is uncertain. Check Twilio and save any created API key/service before retrying.',409)
    c.execute("UPDATE registration_otp_policy SET creation_state='creating' WHERE id=1");c.commit()
    if not (settings.get('TWILIO_API_KEY_SID') and settings.get('TWILIO_API_KEY_SECRET')):
     account,_=credentials(master=True);result=provider('/2010-04-01/Accounts/'+account+'/Keys.json',{'FriendlyName':'DOBHRAP registration Verify'},master=True)
     if not re.fullmatch(r'SK[0-9a-fA-F]{32}',str(result.get('sid',''))) or not result.get('secret'):raise a.ServiceError('Unexpected Twilio key response; reconcile in Twilio',502)
     save_key(c,'TWILIO_API_KEY_SID',result['sid']);save_key(c,'TWILIO_API_KEY_SECRET',result['secret']);c.commit()
    result=provider('/v2/Services',{'FriendlyName':'Olamide Business Suite','CodeLength':6})
    if not re.fullmatch(r'VA[0-9a-fA-F]{32}',str(result.get('sid',''))):raise a.ServiceError('Unexpected Verify service response; reconcile in Twilio',502)
    save_key(c,'TWILIO_VERIFY_SERVICE_SID',result['sid'])
   else:provider('/v2/Services/'+service_sid())
   c.execute("UPDATE registration_otp_policy SET creation_state='ready',revision=revision+1 WHERE id=1")
  elif body.get('action')=='reset':
   if body.get('confirmed_reconciled') is not True:raise a.ServiceError('Review existing Twilio resources and confirm reconciliation first')
   c.execute("UPDATE registration_otp_policy SET creation_state='idle',revision=revision+1 WHERE id=1")
  elif body.get('action')=='test':provider('/v2/Services/'+service_sid())
  else:raise a.ServiceError('Unknown OTP administrator action')
  a.audit(c,user['id'],'Registration OTP settings '+str(body.get('action')));c.commit()
 row=dict(c.execute('SELECT * FROM registration_otp_policy WHERE id=1').fetchone());row['enabled']=bool(row['enabled']);row['configured']=bool(settings.get('TWILIO_VERIFY_SERVICE_SID')) and bool((settings.get('TWILIO_API_KEY_SID') and settings.get('TWILIO_API_KEY_SECRET')) or (settings.get('TWILIO_ACCOUNT_SID') and settings.get('TWILIO_AUTH_TOKEN')));row['usage']=[dict(r) for r in c.execute('SELECT * FROM registration_otp_usage ORDER BY day DESC LIMIT 30')];return row

def public(path,method,body,c,ip):
 if not path.startswith('/api/registration/otp/'):return None
 policy=c.execute('SELECT * FROM registration_otp_policy WHERE id=1').fetchone();route=path.rsplit('/',1)[-1]
 if route=='status' and method=='GET':return {'required':bool(policy['enabled'])}
 if method!='POST':raise a.ServiceError('POST required',405)
 if not policy['enabled']:raise a.ServiceError('Registration OTP is not enabled',409)
 if route=='start':
  phone=body.get('phone','')
  if not isinstance(phone,str) or not re.fullmatch(r'\+[1-9]\d{7,14}',phone):raise a.ServiceError('Enter an international phone number, for example +15551234567')
  sid=service_sid();credentials();now=int(time.time());hashed=hmac.new(os.environ.get('DOBHRAP_ENCRYPTION_KEY','').encode(),phone.encode(),hashlib.sha256).hexdigest()
  import password_reset
  c.execute('BEGIN IMMEDIATE');password_reset.throttle(c,'otp-ip:'+hashlib.sha256(ip.encode()).hexdigest(),10,now)
  if c.execute('SELECT count(*) FROM registration_otp_challenges WHERE phone_hash=? AND created>?',(hashed,now-3600)).fetchone()[0]>=3:raise a.ServiceError('Wait before requesting another code for this phone',429)
  if c.execute('SELECT 1 FROM registration_otp_challenges WHERE phone_hash=? AND created>?',(hashed,now-60)).fetchone():raise a.ServiceError('Wait at least 60 seconds before resending',429)
  day=datetime.datetime.now(datetime.timezone.utc).date().isoformat();c.execute('INSERT OR IGNORE INTO registration_otp_usage VALUES(?,0)',(day,))
  if c.execute('UPDATE registration_otp_usage SET requests=requests+1 WHERE day=? AND requests<?',(day,policy['daily_limit'])).rowcount!=1:raise a.ServiceError('Daily verification SMS limit reached',429)
  challenge=str(uuid.uuid4());c.execute("INSERT INTO registration_otp_challenges(id,phone,phone_hash,ticket_hash,state,attempts,expires,created) VALUES(?,?,?,?,?,0,?,?)",(challenge,a.seal({'phone':phone}),hashed,'','sending',now+600,now));c.commit()
  r=provider('/v2/Services/'+sid+'/Verifications',{'To':phone,'Channel':'sms'})
  if r.get('status')!='pending':raise a.ServiceError('Twilio did not acknowledge the SMS request',502)
  c.execute("UPDATE registration_otp_challenges SET state='pending' WHERE id=?",(challenge,));return {'challenge':challenge,'notice':'Code requested. Delivery and provider charges are controlled by Twilio.'}
 if route=='check':
  code=body.get('code','')
  if not isinstance(code,str) or not re.fullmatch(r'\d{4,10}',code):raise a.ServiceError('Enter the verification code')
  c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM registration_otp_challenges WHERE id=?',(body.get('challenge'),)).fetchone()
  if not row or row['state']!='pending' or row['expires']<int(time.time()) or row['attempts']>=5:raise a.ServiceError('Code expired or unavailable; request a new code',409)
  c.execute('UPDATE registration_otp_challenges SET attempts=attempts+1 WHERE id=?',(row['id'],));c.commit();phone=a.unseal(row['phone'])['phone'];r=provider('/v2/Services/'+service_sid()+'/VerificationCheck',{'To':phone,'Code':code})
  if r.get('status')!='approved':raise a.ServiceError('Incorrect verification code',400)
  ticket=secrets.token_urlsafe(36)
  if c.execute("UPDATE registration_otp_challenges SET state='verified',ticket_hash=? WHERE id=? AND state='pending'",(hashlib.sha256(ticket.encode()).hexdigest(),row['id'])).rowcount!=1:raise a.ServiceError('Verification changed; request a new code',409)
  return {'ticket':ticket,'notice':'Phone verified. Complete account creation within ten minutes of the code request.'}
 raise a.ServiceError('Unknown OTP route',404)

def consume(c,body):
 if not c.execute('SELECT enabled FROM registration_otp_policy WHERE id=1').fetchone()[0]:return None
 ticket=body.get('otp_ticket','');phone=body.get('phone','')
 if not isinstance(ticket,str) or not 32<=len(ticket)<=128:raise a.ServiceError('Verify your phone before creating an account',403)
 row=c.execute("SELECT * FROM registration_otp_challenges WHERE ticket_hash=? AND state='verified' AND expires>?",(hashlib.sha256(ticket.encode()).hexdigest(),int(time.time()))).fetchone()
 if not row or a.unseal(row['phone'])['phone']!=phone:raise a.ServiceError('Phone verification is missing or expired',403)
 if c.execute("UPDATE registration_otp_challenges SET state='used' WHERE id=? AND state='verified'",(row['id'],)).rowcount!=1:raise a.ServiceError('Phone verification was already used',409)
 return phone
