"""Tenant-isolated workforce clock and employer-reviewed earnings statements."""
import hashlib,hmac,json,math,re,secrets,time,uuid,os
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal,ROUND_HALF_UP
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
import advanced as a

DEFAULT={'enabled':True,'timezone':'America/Chicago','company_name':'','company_address':''}
def ssn_digest(value):
 value=str(value).strip().replace('-','')
 if not re.fullmatch(r'[0-9]{9}',value):raise a.ServiceError('SSN must have nine digits')
 key=os.environ.get('DOBHRAP_ENCRYPTION_KEY','')
 if not key:raise a.ServiceError('Encryption key is required',503)
 return hmac.new(key.encode(),('employee-ssn:'+value).encode(),hashlib.sha256).hexdigest()

def initialize(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS clock_settings(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS clock_workers(id TEXT PRIMARY KEY,code TEXT UNIQUE NOT NULL,payload TEXT NOT NULL,pin_salt TEXT NOT NULL,pin_hash TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
 CREATE TABLE IF NOT EXISTS clock_sites(id TEXT PRIMARY KEY,payload TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
 CREATE TABLE IF NOT EXISTS clock_sessions(token_hash TEXT PRIMARY KEY,worker_id TEXT NOT NULL,csrf TEXT NOT NULL,expires INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS clock_attempts(key TEXT PRIMARY KEY,count INTEGER NOT NULL,started INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS clock_entries(id TEXT PRIMARY KEY,worker_id TEXT NOT NULL,started INTEGER NOT NULL,ended INTEGER,payload TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1);
 CREATE UNIQUE INDEX IF NOT EXISTS clock_one_open ON clock_entries(worker_id) WHERE ended IS NULL;
 CREATE TABLE IF NOT EXISTS clock_actions(request_id TEXT PRIMARY KEY,worker_id TEXT NOT NULL,action TEXT NOT NULL,result TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS clock_changes(id TEXT PRIMARY KEY,entry_id TEXT NOT NULL,actor INTEGER NOT NULL,payload TEXT NOT NULL,created INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS clock_payruns(id TEXT PRIMARY KEY,started INTEGER NOT NULL,ended INTEGER NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL,created INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS clock_statements(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,worker_id TEXT NOT NULL,payload TEXT NOT NULL,UNIQUE(run_id,worker_id));''')
 if 'ssn_hash' not in {r[1] for r in c.execute('PRAGMA table_info(clock_workers)')}:c.execute('ALTER TABLE clock_workers ADD COLUMN ssn_hash TEXT')
 c.execute('CREATE UNIQUE INDEX IF NOT EXISTS clock_ssn_unique ON clock_workers(ssn_hash) WHERE ssn_hash IS NOT NULL')

def initialize_platform(c):
 c.execute('CREATE TABLE IF NOT EXISTS clock_platform(id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL)');c.execute('INSERT OR IGNORE INTO clock_platform VALUES(1,1)')
def config(c):
 r=c.execute('SELECT payload FROM clock_settings WHERE id=1').fetchone();return {**DEFAULT,**(a.unseal(r[0]) if r else {})}
def plain(value,label,limit=150):
 if not isinstance(value,str) or not value.strip() or len(value)>limit or not value.isprintable():raise a.ServiceError('Enter '+label)
 return value.strip()
def money(value):
 try:
  n=Decimal(str(value))
  if not n.is_finite() or n<0 or n>1000000 or n!=n.quantize(Decimal('.01')):raise ValueError()
 except Exception:raise a.ServiceError('Enter a nonnegative USD amount with at most two decimals') from None
 return int(n*100)
def pin_hash(pin,salt):return hashlib.scrypt(str(pin).encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
def worker(c,wid):
 r=c.execute('SELECT * FROM clock_workers WHERE id=?',(wid,)).fetchone()
 if not r:raise a.ServiceError('Worker not found',404)
 return r,a.unseal(r['payload'])
def public_worker(r,p):return {'id':r['id'],'code':r['code'],'active':bool(r['active']),**p}
def qr_invite(tid,code=''):
 import qrcode
 from urllib.parse import urlencode
 url='https://olamideolatayobello.com/employee-clock#'+urlencode({'tenant_id':tid,'employee':code})
 qr=qrcode.QRCode(border=4,error_correction=qrcode.constants.ERROR_CORRECT_M);qr.add_data(url);qr.make(fit=True)
 return {'url':url,'qr_matrix':qr.get_matrix()}
def site_check(p,body,now,tz):
 if p['geofence']:
  try:
   lat=float(body['latitude']);lon=float(body['longitude']);accuracy=float(body['accuracy']);stamp=float(body['location_time'])
   if not all(math.isfinite(x) for x in (lat,lon,accuracy,stamp)) or not -90<=lat<=90 or not -180<=lon<=180 or not 0<=accuracy<=p['max_accuracy_m'] or abs(now-stamp)>120:raise ValueError()
  except (KeyError,ValueError,TypeError):raise a.ServiceError('A fresh, accurate location is required for this site',403) from None
  dlat=math.radians(lat-p['latitude']);dlon=math.radians(lon-p['longitude']);x=math.sin(dlat/2)**2+math.cos(math.radians(lat))*math.cos(math.radians(p['latitude']))*math.sin(dlon/2)**2;distance=6371000*2*math.atan2(math.sqrt(max(0,min(1,x))),math.sqrt(max(0,1-x)))
  if distance+accuracy>p['radius_m']:raise a.ServiceError('You are outside the permitted clock-in area or location is too uncertain',403)
 else:distance=None
 local=datetime.fromtimestamp(now,ZoneInfo(tz));minute=local.hour*60+local.minute;start=p['start_minute'];end=p['end_minute'];day=local.weekday()
 if start!=end:
  if start<end:allowed=day in p['weekdays'] and start<=minute<end
  else:allowed=(day in p['weekdays'] and minute>=start) or ((day-1)%7 in p['weekdays'] and minute<end)
 else:allowed=day in p['weekdays']
 if not allowed:raise a.ServiceError('Clock-in is outside the employer permitted days or hours',403)
 return {'site_id':body['site_id'],'distance_m':None if distance is None else round(distance),'geofence_checked':p['geofence']}
def period(value,weeks,tz):
 try:
  d=date.fromisoformat(value);weeks=int(weeks)
  if d.weekday()!=0 or weeks not in (1,2,3,4):raise ValueError()
  start=int(datetime.combine(d,datetime.min.time(),ZoneInfo(tz)).timestamp());end=int(datetime.combine(d+timedelta(days=7*weeks),datetime.min.time(),ZoneInfo(tz)).timestamp())
 except (ValueError,TypeError):raise a.ServiceError('Select a Monday and one to four whole workweeks') from None
 return start,end

def payroll(c,start,end,only=None):
 settings=config(c);rows=c.execute('SELECT * FROM clock_entries WHERE started<? AND (ended IS NULL OR ended>?) ORDER BY started,id',(end,start)).fetchall();parts={};source=[];blockers=[]
 for r in rows:
  if only and r['worker_id']!=only:continue
  p=a.unseal(r['payload']);source.append([r['id'],r['revision'],r['started'],r['ended'],p])
  if r['ended'] is None:blockers.append('Open shift '+r['id']);continue
  if r['ended']-r['started']>86400:blockers.append('Shift exceeds 24 hours; review '+r['id']);continue
  first=max(start,r['started']);last=min(end,r['ended']);wr,wp=worker(c,r['worker_id'])
  entry=parts.setdefault(wr['id'],{'worker_id':wr['id'],'name':wp['name'],'worker_code':wr['code'],'kind':p['kind'],'seconds':0,'regular_seconds':0,'overtime_seconds':0,'gross_cents':0,'weeks':{},'line_items':[],'_gross':Decimal(0)})
  while first<last:
   local=datetime.fromtimestamp(first,ZoneInfo(settings['timezone']));monday=local.date()-timedelta(days=local.weekday());week=monday.isoformat();boundary=int(datetime.combine(monday+timedelta(days=7),datetime.min.time(),ZoneInfo(settings['timezone'])).timestamp());seconds=min(last,boundary)-first
   w=entry['weeks'].setdefault(week,{'seconds':0,'rate_cents':p['rate_cents'],'kind':p['kind']})
   if w['rate_cents']!=p['rate_cents'] or w['kind']!=p['kind']:blockers.append('Multiple rates or worker classifications in workweek: '+wr['code'])
   threshold=40*3600 if p['kind']=='employee' else 10**12;regular=min(seconds,max(0,threshold-w['seconds']));ot=seconds-regular
   amount=(Decimal(regular)+Decimal(ot)*Decimal('1.5'))*p['rate_cents']/3600
   entry['_gross']+=amount;entry['seconds']+=seconds;entry['regular_seconds']+=regular;entry['overtime_seconds']+=ot;w['seconds']+=seconds
   entry['line_items'].append({'entry_id':r['id'],'week':week,'regular_seconds':regular,'overtime_seconds':ot,'rate_cents':p['rate_cents']});first+=seconds
 for x in parts.values():x['gross_cents']=int(x.pop('_gross').quantize(Decimal('1'),rounding=ROUND_HALF_UP))
 digest=hashlib.sha256(json.dumps({'source':source,'timezone':settings['timezone']},sort_keys=True).encode()).hexdigest()
 return {'started':start,'ended':end,'timezone':settings['timezone'],'workers':list(parts.values()),'blockers':list(dict.fromkeys(blockers)),'digest':digest,'notice':'USD draft earnings only; 40-hour weekly overtime at 1.5 for hourly employees. Contractors use straight time. State daily overtime, special rates, bonuses, benefits and tax withholding are not calculated. Review classification and applicable pay rules.'}

def sync_timesheet(c,eid):
 r=c.execute('SELECT * FROM clock_entries WHERE id=?',(eid,)).fetchone()
 if r['ended'] is None:return
 _,p=worker(c,r['worker_id']);data={'name':p['name'],'employee':r['worker_id'],'hours':str(Decimal(r['ended']-r['started'])/3600),'date':datetime.fromtimestamp(r['started'],ZoneInfo(config(c)['timezone'])).date().isoformat(),'clock_entry_id':eid,'source':'employee_clock'}
 old=c.execute("SELECT id FROM records WHERE module='time' AND json_extract(data,'$.clock_entry_id')=?",(eid,)).fetchone()
 if old:c.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(data),old['id']))
 else:c.execute('INSERT INTO records(module,data) VALUES(?,?)',('time',json.dumps(data)))

def employee(c,body,token,csrf,ip_key,enabled=True):
 if not c.in_transaction:c.execute('BEGIN IMMEDIATE')
 now=int(time.time());action=body.get('action','me');settings=config(c)
 if (not enabled or not settings['enabled']) and action not in ('clock-out','logout'):raise a.ServiceError('Employee clock is suspended; contact your employer',403)
 if action=='login':
  if body.get('_employee_header')!='1':raise a.ServiceError('Use the employee portal',403)
  code=str(body.get('employee_code','')).strip().upper();pin=str(body.get('pin',''))
  if len(code)>30 or len(pin)>128:raise a.ServiceError('Invalid employee ID or PIN',401)
  lookup=ssn_digest(code) if re.fullmatch(r'[0-9]{3}-?[0-9]{2}-?[0-9]{4}',code) else None
  r=c.execute('SELECT * FROM clock_workers WHERE (code=? OR ssn_hash=?) AND active=1',(code,lookup)).fetchone()
  keys=['ip:'+ip_key,'worker:'+r['id'] if r else 'code:'+hashlib.sha256(code.encode()).hexdigest()]
  for key,limit in zip(keys,[30,5]):
   attempt=c.execute('SELECT * FROM clock_attempts WHERE key=?',(key,)).fetchone()
   if attempt and attempt['started']>now-900 and attempt['count']>=limit:raise a.ServiceError('Too many attempts. Try again after 15 minutes or contact your employer',429)
  salt=r['pin_salt'] if r else '00'*16
  valid=hmac.compare_digest(pin_hash(pin,salt),r['pin_hash'] if r else '0'*128)
  if not r or not valid:
   for key in keys:
    old=c.execute('SELECT * FROM clock_attempts WHERE key=?',(key,)).fetchone();count=old['count']+1 if old and old['started']>now-900 else 1;began=old['started'] if old and old['started']>now-900 else now
    c.execute('INSERT OR REPLACE INTO clock_attempts VALUES(?,?,?)',(key,count,began))
   c.commit();raise a.ServiceError('Invalid employee ID or PIN',401)
  c.execute('DELETE FROM clock_attempts WHERE key=?',(keys[1],));c.execute('DELETE FROM clock_sessions WHERE expires<=?',(now,))
  new=secrets.token_urlsafe(32);anti=secrets.token_hex(24);c.execute('INSERT INTO clock_sessions VALUES(?,?,?,?)',(hashlib.sha256(new.encode()).hexdigest(),r['id'],anti,now+8*3600));return {'ok':True,'csrf':anti,'_cookie':new}
 session=c.execute('SELECT * FROM clock_sessions WHERE token_hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),now)).fetchone()
 if not session:raise a.ServiceError('Sign in to the employee clock',401)
 r,p=worker(c,session['worker_id'])
 if not r['active']:raise a.ServiceError('Worker access suspended',403)
 if action!='me' and not hmac.compare_digest(str(csrf),session['csrf']):raise a.ServiceError('Invalid employee request token',403)
 if action=='logout':c.execute('DELETE FROM clock_sessions WHERE token_hash=?',(session['token_hash'],));return {'ok':True,'_cookie':''}
 if action=='change-pin':
  if not hmac.compare_digest(pin_hash(str(body.get('current_pin','')),r['pin_salt']),r['pin_hash']):raise a.ServiceError('Current PIN is incorrect',403)
  new=str(body.get('new_pin',''))
  if not re.fullmatch(r'[0-9]{8,12}',new):raise a.ServiceError('Use an 8 to 12 digit PIN')
  salt=secrets.token_hex(16);c.execute('UPDATE clock_workers SET pin_salt=?,pin_hash=? WHERE id=?',(salt,pin_hash(new,salt),r['id']));c.execute('DELETE FROM clock_sessions WHERE worker_id=?',(r['id'],));return {'ok':True,'_cookie':''}
 if action=='eligibility':
  site=c.execute('SELECT * FROM clock_sites WHERE id=? AND active=1',(body.get('site_id'),)).fetchone()
  if not site:return {'allowed':False,'reason':'Select an active work site'}
  try:site_check(a.unseal(site['payload']),body,now,settings['timezone'])
  except a.ServiceError as error:return {'allowed':False,'reason':str(error)}
  return {'allowed':True,'reason':'Location and schedule checks passed'}
 if action in ('clock-in','clock-out'):
  key=str(body.get('request_id',''))
  if not re.fullmatch(r'[A-Za-z0-9-]{16,80}',key):raise a.ServiceError('A clock request ID is required')
  prior=c.execute('SELECT * FROM clock_actions WHERE request_id=?',(key,)).fetchone()
  if prior:
   if prior['worker_id']!=r['id'] or prior['action']!=action:raise a.ServiceError('Request ID conflict',409)
   return json.loads(prior['result'])
  opened=c.execute('SELECT * FROM clock_entries WHERE worker_id=? AND ended IS NULL',(r['id'],)).fetchone()
  if action=='clock-in':
   if opened:raise a.ServiceError('Already clocked in',409)
   site=c.execute('SELECT * FROM clock_sites WHERE id=? AND active=1',(body.get('site_id'),)).fetchone()
   if not site:raise a.ServiceError('Select an active employer site')
   check=site_check(a.unseal(site['payload']),body,now,settings['timezone']);eid=str(uuid.uuid4());payload={**check,'rate_cents':p['rate_cents'],'kind':p['kind']}
   c.execute('INSERT INTO clock_entries(id,worker_id,started,payload) VALUES(?,?,?,?)',(eid,r['id'],now,a.seal(payload)))
  else:
   if not opened:raise a.ServiceError('Not clocked in',409)
   if now<=opened['started']:raise a.ServiceError('Wait a moment before clocking out',409)
   c.execute('UPDATE clock_entries SET ended=?,revision=revision+1 WHERE id=?',(now,opened['id']));eid=opened['id'];sync_timesheet(c,eid)
  result={'ok':True,'entry_id':eid,'clocked_in':action=='clock-in','server_time':now};c.execute('INSERT INTO clock_actions VALUES(?,?,?,?)',(key,r['id'],action,json.dumps(result)));return result
 if action!='me':raise a.ServiceError('Employee action not found',404)
 entries=[dict(x) for x in c.execute('SELECT id,started,ended,revision FROM clock_entries WHERE worker_id=? ORDER BY started DESC LIMIT 100',(r['id'],))]
 sites=[{'id':x['id'],**a.unseal(x['payload'])} for x in c.execute('SELECT * FROM clock_sites WHERE active=1')]
 statements=[{'id':x['id'],**a.unseal(x['payload'])} for x in c.execute('SELECT * FROM clock_statements WHERE worker_id=? ORDER BY rowid DESC LIMIT 50',(r['id'],))]
 today=datetime.fromtimestamp(now,ZoneInfo(settings['timezone'])).date();monday=today-timedelta(days=today.weekday());start,end=period(monday.isoformat(),1,settings['timezone'])
 return {'worker':{'id':r['id'],'code':r['code'],'name':p['name'],'kind':p['kind'],'job':p['job']},'settings':settings,'sites':sites,'entries':entries,'statements':statements,'clocked_in':any(x['ended'] is None for x in entries),'draft_earnings':payroll(c,start,end,r['id']),'csrf':session['csrf'],'server_time':now}

def admin(path,method,body,c,user,tid):
 if not path.startswith('/api/attendance/'):return None
 if user['role'] not in ('admin','super_admin'):raise a.ServiceError('Employer administrator required',403)
 route=path.rsplit('/',1)[1]
 if route=='overview' and method=='GET':
  return {'settings':config(c),'workers':[public_worker(r,a.unseal(r['payload'])) for r in c.execute('SELECT * FROM clock_workers ORDER BY code')],'sites':[{'id':r['id'],'active':bool(r['active']),**a.unseal(r['payload'])} for r in c.execute('SELECT * FROM clock_sites')],'entries':[{**{k:r[k] for k in ('id','worker_id','started','ended','revision')},**a.unseal(r['payload'])} for r in c.execute('SELECT * FROM clock_entries ORDER BY started DESC LIMIT 500')],'runs':[{'id':r['id'],'state':r['state'],'created':r['created'],**a.unseal(r['payload'])} for r in c.execute('SELECT * FROM clock_payruns ORDER BY created DESC LIMIT 50')],'statements':[{'id':r['id'],**a.unseal(r['payload'])} for r in c.execute('SELECT * FROM clock_statements ORDER BY rowid DESC LIMIT 500')]}
 if method!='POST':raise a.ServiceError('Attendance action not found',404)
 if not c.in_transaction:c.execute('BEGIN IMMEDIATE')
 now=int(time.time())
 if route=='settings':
  old=config(c);tz=str(body.get('timezone',''))
  try:ZoneInfo(tz)
  except (ZoneInfoNotFoundError,ValueError):raise a.ServiceError('Select a valid IANA time zone') from None
  if tz!=old['timezone'] and c.execute('SELECT 1 FROM clock_entries').fetchone():raise a.ServiceError('Workweek time zone is fixed after the first clock entry')
  if type(body.get('enabled')) is not bool:raise a.ServiceError('Choose enabled or suspended')
  p={'enabled':body['enabled'],'timezone':tz,'company_name':plain(body.get('company_name'),'company name'),'company_address':plain(body.get('company_address'),'company address',400)}
  c.execute('INSERT OR REPLACE INTO clock_settings VALUES(1,?)',(a.seal(p),));result={'ok':True}
 elif route=='worker':
  wid=body.get('id');old=None
  if wid:old,prior=worker(c,wid)
  p={'name':plain(body.get('name'),'worker full name'),'email':plain(body.get('email'),'worker email',254),'job':plain(body.get('job'),'job / role'),'phone':str(body.get('phone',''))[:40],'kind':body.get('kind'),'rate_cents':money(body.get('hourly_rate'))}
  if p['kind'] not in ('employee','contractor') or '@' not in p['email'] or p['rate_cents']<=0:raise a.ServiceError('Select worker type, a valid email and positive hourly rate')
  if wid:p['ssn_last4']=prior.get('ssn_last4','')
  if body.get('clear_ssn') is True:p['ssn_last4']=''
  if body.get('ssn'):p['ssn_last4']=str(body['ssn']).replace('-','')[-4:]
  if wid:c.execute('UPDATE clock_workers SET payload=? WHERE id=?',(a.seal(p),wid));result={'id':wid,'code':old['code']}
  else:
   if c.execute('SELECT count(*) FROM clock_workers').fetchone()[0]>=500:raise a.ServiceError('Workspace worker limit reached')
   wid=str(uuid.uuid4());code=secrets.token_hex(5).upper();pin=''.join(secrets.choice('0123456789') for _ in range(10));salt=secrets.token_hex(16)
   c.execute('INSERT INTO clock_workers(id,code,payload,pin_salt,pin_hash,active) VALUES(?,?,?,?,?,1)',(wid,code,a.seal(p),salt,pin_hash(pin,salt)));result={'id':wid,'code':code,'initial_pin':pin}
   # Operational employee record uses references only; secrets and biodata stay encrypted.
   c.execute('INSERT INTO records(module,data) VALUES(?,?)',('employees',json.dumps({'name':p['name'],'job':p['job'],'hourly_rate':str(Decimal(p['rate_cents'])/100),'clock_worker_id':wid})))
  if body.get('ssn'):
   digest=ssn_digest(body['ssn'])
   if c.execute('SELECT 1 FROM clock_workers WHERE ssn_hash=? AND id!=?',(digest,wid)).fetchone():raise a.ServiceError('SSN already enrolled in this company',409)
   c.execute('UPDATE clock_workers SET ssn_hash=? WHERE id=?',(digest,wid))
  if body.get('clear_ssn') is True:c.execute('UPDATE clock_workers SET ssn_hash=NULL WHERE id=?',(wid,))
  result.update(qr_invite(tid,result['code']))
 elif route in ('worker-status','reset-pin','invite'):
  r,p=worker(c,body.get('id'))
  if route=='invite':return {'code':r['code'],**qr_invite(tid,r['code'])}
  if route=='worker-status':
   if type(body.get('active')) is not bool:raise a.ServiceError('Choose worker status')
   if not body['active'] and c.execute('SELECT 1 FROM clock_entries WHERE worker_id=? AND ended IS NULL',(r['id'],)).fetchone():raise a.ServiceError('Close or correct the open shift before suspending this worker')
   c.execute('UPDATE clock_workers SET active=? WHERE id=?',(int(body['active']),r['id']));result={'ok':True}
  else:
   pin=''.join(secrets.choice('0123456789') for _ in range(10));salt=secrets.token_hex(16);c.execute('UPDATE clock_workers SET pin_salt=?,pin_hash=? WHERE id=?',(salt,pin_hash(pin,salt),r['id']));c.execute('DELETE FROM clock_attempts WHERE key=?',('worker:'+r['id'],));result={'initial_pin':pin,'code':r['code']}
  c.execute('DELETE FROM clock_sessions WHERE worker_id=?',(r['id'],))
 elif route=='site':
  name=plain(body.get('name'),'site name');geo=body.get('geofence')
  if type(geo) is not bool:raise a.ServiceError('Choose geofence setting')
  try:
   lat=float(body.get('latitude',0));lon=float(body.get('longitude',0));radius=float(body.get('radius_m',200));accuracy=float(body.get('max_accuracy_m',100));start=int(body.get('start_minute',0));end=int(body.get('end_minute',0));days=body.get('weekdays',list(range(7)))
   if not all(math.isfinite(x) for x in (lat,lon,radius,accuracy)) or not -90<=lat<=90 or not -180<=lon<=180 or not 50<=radius<=50000 or not 5<=accuracy<=500 or not 0<=start<1440 or not 0<=end<1440 or not isinstance(days,list) or not days or any(type(d) is not int or not 0<=d<=6 for d in days):raise ValueError()
  except (ValueError,TypeError):raise a.ServiceError('Enter valid coordinates, radius (50–50000m), accuracy (5–500m), weekdays and hours') from None
  p={'name':name,'geofence':geo,'latitude':lat,'longitude':lon,'radius_m':radius,'max_accuracy_m':accuracy,'start_minute':start,'end_minute':end,'weekdays':days};sid=body.get('id') or str(uuid.uuid4())
  c.execute('INSERT INTO clock_sites VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,active=excluded.active',(sid,a.seal(p),int(body.get('active',True))));result={'id':sid}
 elif route=='manual-entry':
  r,p=worker(c,body.get('worker_id'));reason=plain(body.get('reason'),'reason for manual time entry',500)
  try:start=int(body['started']);end=int(body['ended'])
  except (ValueError,TypeError,KeyError):raise a.ServiceError('Enter start and end timestamps') from None
  if not 0<start<end<=now or end-start>86400:raise a.ServiceError('Enter a completed shift of at most 24 hours')
  if c.execute("SELECT 1 FROM clock_payruns WHERE state='published' AND started<? AND ended>?",(end,start)).fetchone():raise a.ServiceError('Published payroll period is locked',409)
  if c.execute('SELECT 1 FROM clock_entries WHERE worker_id=? AND started<? AND coalesce(ended,?)>?',(r['id'],end,now,start)).fetchone():raise a.ServiceError('Shift overlaps an existing entry',409)
  eid=str(uuid.uuid4());c.execute('INSERT INTO clock_entries(id,worker_id,started,ended,payload) VALUES(?,?,?,?,?)',(eid,r['id'],start,end,a.seal({'rate_cents':p['rate_cents'],'kind':p['kind'],'site_id':None,'source':'employer_manual'})))
  c.execute('INSERT INTO clock_changes VALUES(?,?,?,?,?)',(str(uuid.uuid4()),eid,user['id'],a.seal({'old_started':None,'old_ended':None,'new_started':start,'new_ended':end,'reason':reason}),now));sync_timesheet(c,eid);result={'id':eid}
 elif route=='correct':
  r=c.execute('SELECT * FROM clock_entries WHERE id=?',(body.get('id'),)).fetchone()
  if not r:raise a.ServiceError('Time entry not found',404)
  reason=plain(body.get('reason'),'correction reason',500)
  try:start=int(body['started']);end=int(body['ended'])
  except (ValueError,TypeError,KeyError):raise a.ServiceError('Provide corrected start and end timestamps') from None
  if not 0<start<end<=now or end-start>86400:raise a.ServiceError('Correction must be a completed shift of at most 24 hours')
  if c.execute("SELECT 1 FROM clock_payruns WHERE state='published' AND started<? AND ended>?",(max(end,r['ended'] or now),min(start,r['started']))).fetchone():raise a.ServiceError('Published payroll period is locked; retain the record and resolve through an adjustment outside this clock',409)
  if c.execute('SELECT 1 FROM clock_entries WHERE worker_id=? AND id!=? AND started<? AND coalesce(ended,?)>?',(r['worker_id'],r['id'],end,now,start)).fetchone():raise a.ServiceError('Corrected shift overlaps another shift')
  if c.execute('UPDATE clock_entries SET started=?,ended=?,revision=revision+1 WHERE id=? AND revision=?',(start,end,r['id'],body.get('revision'))).rowcount!=1:raise a.ServiceError('Entry changed; refresh first',409)
  c.execute('INSERT INTO clock_changes VALUES(?,?,?,?,?)',(str(uuid.uuid4()),r['id'],user['id'],a.seal({'old_started':r['started'],'old_ended':r['ended'],'new_started':start,'new_ended':end,'reason':reason}),now));sync_timesheet(c,r['id']);result={'ok':True}
 elif route=='history':return [{'id':r['id'],'actor':r['actor'],'created':r['created'],**a.unseal(r['payload'])} for r in c.execute('SELECT * FROM clock_changes WHERE entry_id=? ORDER BY created',(body.get('id'),))]
 elif route=='payrun':
  settings=config(c);start,end=period(body.get('period_start'),body.get('weeks',1),settings['timezone'])
  if c.execute("SELECT 1 FROM clock_payruns WHERE state='published' AND started<? AND ended>?",(end,start)).fetchone():raise a.ServiceError('A published payroll overlaps this period',409)
  data=payroll(c,start,end);rid=str(uuid.uuid4());c.execute('INSERT INTO clock_payruns VALUES(?,?,?,?,?,?)',(rid,start,end,a.seal(data),'draft',now));result={'id':rid,**data}
 elif route=='publish':
  r=c.execute("SELECT * FROM clock_payruns WHERE id=? AND state='draft'",(body.get('id'),)).fetchone()
  if not r:raise a.ServiceError('Draft payroll not found',404)
  if r['ended']>now:raise a.ServiceError('Wait until the whole workweek period ends before publishing')
  p=a.unseal(r['payload']);fresh=payroll(c,r['started'],r['ended'])
  if fresh['blockers'] or fresh['digest']!=p['digest']:raise a.ServiceError('Timesheets changed or have open/long shifts. Resolve issues and generate a new draft',409)
  settings=config(c)
  if not settings['company_name'] or not settings['company_address']:raise a.ServiceError('Save employer name and address first')
  if body.get('verified') is not True:raise a.ServiceError('Confirm reviewed hours, classification, pay rules and independently calculated withholding')
  if c.execute("SELECT 1 FROM clock_payruns WHERE state='published' AND started<? AND ended>?",(r['ended'],r['started'])).fetchone():raise a.ServiceError('Payroll period already published',409)
  deductions=body.get('deductions',{})
  if not isinstance(deductions,dict):raise a.ServiceError('Provide per-worker verified withholding amounts')
  for w in p['workers']:
   raw=deductions.get(w['worker_id'])
   if not isinstance(raw,dict) or any(k not in raw for k in ('federal','state','social_security','medicare','other')):raise a.ServiceError('Provide all verified withholding fields for each worker, including explicit zero amounts')
   values={k:money(raw[k]) for k in ('federal','state','social_security','medicare','other')};total=sum(values.values())
   if total>w['gross_cents']:raise a.ServiceError('Deductions exceed gross earnings')
   statement={**w,'employer':settings['company_name'],'employer_address':settings['company_address'],'period_start':r['started'],'period_end':r['ended'],'timezone':settings['timezone'],'deductions_cents':values,'net_cents':w['gross_cents']-total,'published_at':now,'reviewed_by':user['id'],'status':'employer_reviewed_not_proof_of_payment','notice':'Employer-recorded earnings statement. Withholding supplied by employer; tax calculation, remittance, payment and state-specific paystub certification are not performed by this clock.'}
   c.execute('INSERT INTO clock_statements VALUES(?,?,?,?)',(str(uuid.uuid4()),r['id'],w['worker_id'],a.seal(statement)))
  c.execute("UPDATE clock_payruns SET state='published' WHERE id=?",(r['id'],));result={'ok':True}
 else:raise a.ServiceError('Attendance action not found',404)
 a.audit(c,user['id'],'Attendance '+route);return result
