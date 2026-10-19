import os,tempfile,time,unittest,json
from unittest.mock import patch
from datetime import datetime,timezone
from cryptography.fernet import Fernet
import app,attendance as t,advanced as a

class AttendanceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=self.temp.name+'/db.sqlite';self.env=patch.dict(os.environ,{'DOBHRAP_ADMIN_PASSWORD':'test-password-123456','DOBHRAP_ENCRYPTION_KEY':Fernet.generate_key().decode()});self.env.start();app.init();self.user={'id':1,'role':'admin'}
 def tearDown(self):self.env.stop();app.DB=self.old;self.temp.cleanup()
 def admin(self,route,b=None,user=None):
  with app.connect() as c:return t.admin('/api/attendance/'+route,'GET' if b is None else 'POST',b or {},c,user or self.user,1)
 def create(self,**opts):return self.admin('worker',{'name':'Worker Fixture','email':'fixture@example.test','job':'Developer','kind':'employee','hourly_rate':'20',**opts})
 def site(self,**opts):return self.admin('site',{'name':'Office','geofence':False,**opts})
 def employee(self,b,token='',csrf='',at=None,enabled=True):
  with patch.object(t.time,'time',return_value=at or time.time()):
   with app.connect() as c:return t.employee(c,{**b,'_employee_header':'1'},token,csrf,'test-ip',enabled)
 def login(self,w,**opts):return self.employee({'action':'login','employee_code':w['code'],'pin':w['initial_pin'],**opts})
 def test_employee_auth_privacy_isolation_and_pin(self):
  w=self.create(ssn='123-45-6789');other=self.create(name='Other');s=self.login(w,employee_code='123456789');token=s['_cookie'];anti=s['csrf'];data=self.employee({'action':'me'},token)
  self.assertEqual(data['worker']['id'],w['id']);self.assertEqual(data['entries'],[]);self.assertNotIn('pin',json.dumps(data));self.assertNotIn('123456789',json.dumps(data));self.assertNotIn('Other',json.dumps(data))
  with app.connect() as c:
   raw=json.dumps([dict(r) for r in c.execute('SELECT * FROM clock_workers')]);self.assertNotIn('123456789',raw);self.assertNotIn(w['initial_pin'],raw)
  with self.assertRaises(a.ServiceError):self.employee({'action':'logout'},token,'bad')
  self.employee({'action':'change-pin','current_pin':w['initial_pin'],'new_pin':'1234567890'},token,anti)
  with self.assertRaises(a.ServiceError):self.employee({'action':'me'},token)
 def test_rate_limit_persists_failure(self):
  w=self.create()
  for i in range(5):
   with self.assertRaises(a.ServiceError) as e:self.login(w,pin='bad')
   self.assertEqual(e.exception.status,401)
  with self.assertRaises(a.ServiceError) as e:self.login(w)
  self.assertEqual(e.exception.status,429)
  self.admin('reset-pin',{'id':w['id']})
 def test_clock_idempotency_server_time_timesheet_and_logout(self):
  w=self.create();site=self.site();s=self.login(w);token=s['_cookie'];anti=s['csrf'];now=int(time.time());body={'action':'clock-in','site_id':site['id'],'request_id':'clock-in-request-001','started':1}
  first=self.employee(body,token,anti,now);second=self.employee(body,token,anti,now);self.assertEqual(first,second)
  with self.assertRaises(a.ServiceError):self.employee({**body,'request_id':'clock-in-request-002'},token,anti,now)
  self.employee({'action':'clock-out','request_id':'clock-out-request-001'},token,anti,now+3600)
  with app.connect() as c:
   r=c.execute('SELECT * FROM clock_entries').fetchone();self.assertEqual(r['started'],now);self.assertEqual(r['ended']-r['started'],3600);self.assertEqual(json.loads(c.execute("SELECT data FROM records WHERE module='time'").fetchone()[0])['hours'],'1')
  self.employee({'action':'logout'},token,anti)
  with self.assertRaises(a.ServiceError):self.employee({'action':'me'},token)
 def test_geofence_schedule_and_clockout_always_available(self):
  w=self.create();site=self.site(geofence=True,latitude=32,longitude=-96,radius_m=200,max_accuracy_m=100);s=self.login(w);token=s['_cookie'];anti=s['csrf'];now=int(time.time());body={'action':'clock-in','site_id':site['id'],'request_id':'geo-request-000001'}
  for geo in ({},{'latitude':35,'longitude':-96,'accuracy':10,'location_time':now},{'latitude':32,'longitude':-96,'accuracy':500,'location_time':now},{'latitude':32,'longitude':-96,'accuracy':10,'location_time':now-1000}):
   with self.assertRaises(a.ServiceError):self.employee({**body,**geo},token,anti,now)
  self.employee({**body,'latitude':32,'longitude':-96,'accuracy':10,'location_time':now},token,anti,now)
  self.employee({'action':'clock-out','request_id':'geo-request-out01'},token,anti,now+60,enabled=False)
  with self.assertRaises(a.ServiceError):t.site_check({'geofence':False,'start_minute':60,'end_minute':120,'weekdays':[0]}, {'site_id':'x'},int(datetime(2026,10,18,12,tzinfo=timezone.utc).timestamp()),'UTC')
 def historical(self,w,hours,kind='employee'):
  start=int(datetime(2026,10,5,tzinfo=timezone.utc).timestamp())
  with app.connect() as c:
   for i,h in enumerate(hours):c.execute('INSERT INTO clock_entries(id,worker_id,started,ended,payload) VALUES(?,?,?,?,?)',('entry-'+str(i),w['id'],start+i*86400,start+i*86400+h*3600,a.seal({'rate_cents':2000,'kind':kind,'site_id':'test'})))
  return start
 def test_payroll_overtime_publishing_deductions_lock(self):
  self.admin('settings',{'company_name':'Employer','company_address':'123 Test','timezone':'UTC','enabled':True});w=self.create();start=self.historical(w,[8,8,8,8,10]);r=self.admin('payrun',{'period_start':'2026-10-05','weeks':1});self.assertEqual(r['workers'][0]['gross_cents'],86000);self.assertEqual(r['workers'][0]['overtime_seconds'],7200)
  b={'id':r['id'],'verified':True,'deductions':{w['id']:{'federal':'100','state':'0','social_security':'0','medicare':'0','other':'0'}}};self.admin('publish',b)
  data=self.admin('overview');self.assertEqual(data['statements'][0]['net_cents'],76000)
  entry=data['entries'][0]
  with self.assertRaises(a.ServiceError):self.admin('correct',{'id':entry['id'],'revision':entry['revision'],'started':entry['started'],'ended':entry['ended']-10,'reason':'Adjust'})
  with self.assertRaises(a.ServiceError):self.admin('payrun',{'period_start':'2026-10-05'})
 def test_payroll_changed_draft_and_contractor(self):
  self.admin('settings',{'company_name':'Employer','company_address':'123 Test','timezone':'UTC','enabled':True});w=self.create(kind='contractor');self.historical(w,[8,8,8,8,10],kind='contractor');r=self.admin('payrun',{'period_start':'2026-10-05'});self.assertEqual(r['workers'][0]['gross_cents'],84000)
  entry=self.admin('overview')['entries'][0];self.admin('correct',{'id':entry['id'],'revision':entry['revision'],'started':entry['started'],'ended':entry['ended']-3600,'reason':'Verified correction'})
  with self.assertRaises(a.ServiceError):self.admin('publish',{'id':r['id'],'verified':True,'deductions':{}})
  hist=self.admin('history',{'id':entry['id']});self.assertEqual(hist[0]['old_ended'],entry['ended'])
 def test_role_and_tenant_boundary(self):
  for role in ('viewer','editor'):
   with self.assertRaises(a.ServiceError):self.admin('overview',user={'id':2,'role':role})
  w=self.create();target=self.temp.name+'/other.db'
  import sqlite3
  with sqlite3.connect(target) as c:
   c.row_factory=sqlite3.Row;app.initialize_business(c)
   with self.assertRaises(a.ServiceError):t.worker(c,w['id'])
 def test_shift_correction_missing_clockout(self):
  w=self.create();site=self.site();s=self.login(w);now=int(time.time());result=self.employee({'action':'clock-in','site_id':site['id'],'request_id':'missing-out-000001'},s['_cookie'],s['csrf'],now-3600)
  self.admin('correct',{'id':result['entry_id'],'revision':1,'started':now-3600,'ended':now-1,'reason':'Employee reported forgotten clock-out'})
  with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM clock_changes').fetchone()[0],1)
 def test_http_employee_cookie_csrf_and_platform_controls(self):
  import threading,http.client
  server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   w=self.create();site=self.site();port=server.server_address[1]
   def req(path,body=None,headers=None):
    client=http.client.HTTPConnection('127.0.0.1',port);h={'Content-Type':'application/json',**(headers or {})};client.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),h);response=client.getresponse();result=(response.status,dict(response.getheaders()),response.read());client.close();return result
   self.assertEqual(req('/employee-clock')[0],200);self.assertEqual(req('/attendance.js')[0],200)
   b={'tenant_id':1,'action':'login','employee_code':w['code'],'pin':w['initial_pin']}
   self.assertEqual(req('/api/employee-clock',b)[0],403)
   status,h,raw=req('/api/employee-clock',b,{'X-Employee-Request':'1'});self.assertEqual(status,200);self.assertIn('HttpOnly',h['Set-Cookie']);self.assertNotIn('_cookie',json.loads(raw));anti=json.loads(raw)['csrf'];cookie=h['Set-Cookie'].split(';')[0]
   self.assertEqual(req('/api/employee-clock',{'tenant_id':1,'action':'me'},{'Cookie':cookie})[0],200)
   self.assertEqual(req('/api/employee-clock',{'tenant_id':1,'action':'clock-in','site_id':site['id'],'request_id':'http-clock-0000001'},{'Cookie':cookie})[0],403)
   self.assertEqual(req('/api/platform/attendance')[0],401)
   with app.connect() as c:c.execute('UPDATE clock_platform SET enabled=0')
   self.assertEqual(req('/api/employee-clock',b,{'X-Employee-Request':'1'})[0],403)
  finally:server.shutdown();server.server_close();thread.join()
 def test_manual_shift_no_overlap_and_ssn_removal(self):
  w=self.create(ssn='123456789');now=int(time.time());entry=self.admin('manual-entry',{'worker_id':w['id'],'started':now-3600,'ended':now-1,'reason':'Verified off-site work'})
  with self.assertRaises(a.ServiceError):self.admin('manual-entry',{'worker_id':w['id'],'started':now-1800,'ended':now-1,'reason':'Duplicate'})
  self.admin('worker',{'id':w['id'],'name':'Worker Fixture','email':'fixture@example.test','job':'Developer','kind':'employee','hourly_rate':'20','clear_ssn':True})
  with app.connect() as c:self.assertIsNone(c.execute('SELECT ssn_hash FROM clock_workers WHERE id=?',(w['id'],)).fetchone()[0])
