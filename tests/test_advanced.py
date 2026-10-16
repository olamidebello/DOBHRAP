import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from datetime import date
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.fernet import Fernet
import app
import advanced as a
import worker
import backup

class BusinessTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();app.DB=self.temp.name+'/test.db'
  self.env=patch.dict(os.environ,{'DOBHRAP_ADMIN_PASSWORD':'testing-password-1234','DOBHRAP_ENCRYPTION_KEY':Fernet.generate_key().decode(),'CHECK_ENV':'sandbox','PLAID_ENV':'sandbox','CHECK_API_KEY':'','PLAID_CLIENT_ID':'','PLAID_SECRET':'','DOBHRAP_ENABLE_LIVE_PAYROLL':'0','EFILE_GATEWAY_URL':'','EFILE_GATEWAY_TOKEN':'','DOBHRAP_ENABLE_EFILE_TRANSMISSION':'0'})
  self.env.start();app.init();self.user={'id':1,'role':'admin'};self.other={'id':2,'role':'admin'}
 def tearDown(self):self.env.stop();self.temp.cleanup()
 def call(self,path,body=None,user=None):
  with app.connect() as c:return a.dispatch('/api/advanced/'+path,'POST' if body is not None else 'GET',body or {},c,user or self.user,app.post_journal)
 def workflow(self,kind,payload):return self.call('workflows',{'kind':kind,'payload':payload})['id']
 def queue(self,w):
  self.call('workflow/action',{'id':w,'action':'submit'})
  self.call('workflow/action',{'id':w,'action':'approve'},self.other)
 def payroll(self):return {'company':'com_demo','period_start':'2026-10-01','period_end':'2026-10-07','payday':'2026-10-16','items':[{'employee':'emp_demo','earnings':[{'workplace':'wrk_demo','type':'hourly','amount':'800.00','hours':40}]}]}
 def test_tax_bracket_boundary(self):
  r=a.estimate_tax({'year':2026,'filing_status':'single','ordinary_income':'28500'})
  self.assertEqual(r['taxable_income_cents'],1240000);self.assertEqual(r['ordinary_income_tax_cents'],124000)
  self.assertEqual(a.estimate_tax({'year':2026,'filing_status':'single','ordinary_income':'50000'})['ordinary_income_tax_cents'],382000)
 def test_tax_rejects_wrong_year_nonfinite_and_negative(self):
  for year,amount in [(2025,'1'),(2026,'NaN'),(2026,'-1')]:
   with self.assertRaises(a.ServiceError):a.estimate_tax({'year':year,'filing_status':'single','ordinary_income':amount})
 def test_reject_self_approval_and_replay(self):
  w=self.workflow('payroll_create',self.payroll());self.call('workflow/action',{'id':w,'action':'submit'})
  with self.assertRaises(a.ServiceError):self.call('workflow/action',{'id':w,'action':'approve'})
  self.call('workflow/action',{'id':w,'action':'approve'},self.other)
  with self.assertRaises(a.ServiceError):self.call('workflow/action',{'id':w,'action':'approve'},self.other)
  self.assertEqual(len(self.call('jobs')),1)
 def test_duplicate_payroll_request_is_rejected(self):
  self.workflow('payroll_create',self.payroll())
  with self.assertRaises(a.ServiceError):self.workflow('payroll_create',self.payroll())
 def test_non_admin_cannot_read_provider_data(self):
  for role in ('editor','viewer'):
   with self.assertRaises(a.ServiceError):self.call('jobs',user={'id':3,'role':role})
 def test_workflow_payload_encrypted(self):
  w=self.workflow('payroll_create',self.payroll())
  with app.connect() as c:
   raw=c.execute('SELECT payload FROM workflows WHERE id=?',(w,)).fetchone()[0]
   self.assertNotIn('emp_demo',raw);self.assertEqual(a.unseal(raw)['company'],'com_demo')
 def test_csv_reimport_and_posting_idempotency(self):
  data={'account_id':'checking','csv':'external_id,date,name,amount,currency\nref-1,2026-10-15,Supplies,12.50,USD'}
  self.assertEqual(self.call('bank/import',data)['imported'],1);self.assertEqual(self.call('bank/import',data)['imported'],0)
  tx=self.call('bank/transactions')[0];post={'transaction_id':tx['id'],'category_account':'5000'}
  self.call('bank/post',post)
  with self.assertRaises(a.ServiceError):self.call('bank/post',post)
  with app.connect() as c:self.assertEqual(c.execute('SELECT sum(debit)-sum(credit) FROM lines').fetchone()[0],0)
 def test_bank_sync_pages_modifications_and_removals(self):
  with app.connect() as c:c.execute('INSERT INTO bank_items(id,owner,environment,secret) VALUES(?,?,?,?)',('item1',1,'sandbox',a.seal({'access_token':'secret-token'})))
  tx={'transaction_id':'tx1','account_id':'acc1','date':'2026-10-15','name':'Coffee','amount':5,'iso_currency_code':'USD'}
  pages=[{'added':[tx],'next_cursor':'c1','has_more':True},{'modified':[{**tx,'amount':6}],'removed':[{'transaction_id':'tx1'}],'next_cursor':'c2','has_more':False}]
  with patch.object(a,'plaid',side_effect=pages):self.assertEqual(self.call('bank/sync',{'item_id':'item1'})['pages'],2)
  row=self.call('bank/transactions')[0];self.assertEqual(row['amount_cents'],600);self.assertEqual(row['removed'],1)
  with app.connect() as c:self.assertEqual(c.execute('SELECT cursor FROM bank_items').fetchone()[0],'c2')
 def test_sync_error_preserves_cursor_and_records(self):
  with app.connect() as c:c.execute('INSERT INTO bank_items(id,owner,environment,secret) VALUES(?,?,?,?)',('item1',1,'sandbox',a.seal({'access_token':'secret-token'})))
  with patch.object(a,'plaid',side_effect=[{'added':[],'next_cursor':'c1','has_more':True},a.ServiceError('Network unavailable',502)]):
   with self.assertRaises(a.ServiceError):self.call('bank/sync',{'item_id':'item1'})
  with app.connect() as c:self.assertEqual(c.execute('SELECT cursor FROM bank_items').fetchone()[0],'')
 def test_provider_payroll_preview_and_release(self):
  w=self.workflow('payroll_create',self.payroll());self.queue(w)
  preview={'id':'pay_demo','status':'draft','preview':{'status':'succeeded','started_at':'2026-10-16T00:00:00Z'},'net_pay':'700.00'}
  with patch.object(a,'check_api',side_effect=[{'id':'pay_demo'},preview]) as provider:
   self.assertTrue(worker.execute());self.assertEqual(provider.call_args_list[0].kwargs['idempotency_key'].split('-')[-1],'create')
  job=self.call('jobs')[0];self.assertEqual(job['state'],'preview_ready')
  release=self.workflow('payroll_release',{'job_id':job['id']});self.queue(release)
  with patch.object(a,'check_api',side_effect=[preview,{'id':'pay_demo','status':'pending'}]):worker.execute()
  self.assertEqual(self.call('jobs')[0]['state'],'submitted')
 def test_changed_provider_preview_blocks_release(self):
  w=self.workflow('payroll_create',self.payroll());self.queue(w)
  preview={'id':'pay_demo','status':'draft','preview':{'status':'succeeded','started_at':'old'}}
  with patch.object(a,'check_api',side_effect=[{'id':'pay_demo'},preview]):worker.execute()
  release=self.workflow('payroll_release',{'job_id':self.call('jobs')[0]['id']});self.queue(release)
  with patch.object(a,'check_api',return_value={**preview,'preview':{'status':'succeeded','started_at':'new'}}) as provider:worker.execute();self.assertEqual(provider.call_count,1)
  self.assertEqual(self.call('jobs')[0]['state'],'blocked')
 def test_uncertain_mutation_is_not_retried(self):
  w=self.workflow('payroll_create',self.payroll());self.queue(w)
  with patch.object(a,'check_api',side_effect=a.ServiceError('Timeout',502)) as provider:
   worker.execute();worker.execute();self.assertEqual(provider.call_count,1)
  self.assertEqual(self.call('jobs')[0]['state'],'uncertain')
 def test_live_payroll_requires_explicit_flag(self):
  with patch.dict(os.environ,{'CHECK_ENV':'production','CHECK_API_KEY':'test'}),patch.object(a,'request_json') as http:
   with self.assertRaises(a.ServiceError):a.check_api('/payrolls',{})
   http.assert_not_called()
 def test_efile_authorization_required(self):
  with self.assertRaises(a.ServiceError):self.workflow('efile_submit',{'provider_return_id':'return1','signature_authorization_id':'sign1','form':'1040','tax_year':2026,'consent_confirmed':False})
 def test_efile_submission_and_acknowledgement(self):
  w=self.workflow('efile_submit',{'provider_return_id':'return1','signature_authorization_id':'sign1','form':'1040','tax_year':2026,'consent_confirmed':True});self.queue(w)
  with patch.object(a,'efile_api',return_value={'id':'filing1','status':'received'}) as http:
   worker.execute();self.assertTrue(http.call_args.kwargs['transmit'])
  job=self.call('jobs')[0];self.assertEqual(job['state'],'submitted')
  with patch.object(a,'efile_api',return_value={'id':'filing1','status':'accepted','authority_submission_id':'test-ack'}):
   self.assertEqual(self.call('jobs/refresh',{'id':job['id']})['provider']['status'],'accepted')
 def test_source_edit_stops_posting(self):
  with app.connect() as c:rid=c.execute('INSERT INTO records(module,data) VALUES(?,?)',('invoices',json.dumps({'name':'Sale','amount':'20.00'}))).lastrowid
  w=self.workflow('invoice_post',{'record_id':rid});self.queue(w)
  with app.connect() as c:c.execute('UPDATE records SET data=? WHERE id=?',(json.dumps({'name':'Changed','amount':'50.00'}),rid))
  worker.execute();self.assertEqual(self.call('jobs')[0]['state'],'blocked')
  with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM journals').fetchone()[0],0)
 def test_recurring_occurrence_exactly_once(self):
  self.call('schedules',{'module':'tasks','payload':{'name':'Reminder'},'next_date':'2026-10-01','interval_days':30})
  with app.connect() as c:worker.recurring(c,date(2026,10,16));worker.recurring(c,date(2026,10,16))
  with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0],1)
 def test_backup_can_be_read(self):
  with patch.dict(os.environ,{'DOBHRAP_DB':app.DB,'DOBHRAP_BACKUP_DIR':self.temp.name+'/backups'}):backup.backup()
  files=list(Path(self.temp.name+'/backups').glob('*.sqlite3'));self.assertEqual(len(files),1)
  with a.sqlite3.connect(files[0]) as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
 def test_http_auth_csrf_and_new_routes(self):
  import threading,urllib.request,urllib.error,http.cookiejar
  server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
  base='http://127.0.0.1:'+str(server.server_port);token=''
  def request(path,data=None,csrf=True):
   headers={'Content-Type':'application/json'}
   if csrf:headers['X-CSRF-Token']=token
   return json.load(opener.open(urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)))
  try:
   with self.assertRaises(urllib.error.HTTPError) as err:request('/api/advanced/status')
   self.assertEqual(err.exception.code,401)
   token=request('/api/login',{'email':os.environ.get('DOBHRAP_ADMIN_EMAIL','admin@example.com'),'password':'testing-password-1234'})['csrf']
   self.assertEqual(request('/api/advanced/status')['payroll']['environment'],'sandbox')
   with self.assertRaises(urllib.error.HTTPError) as err:request('/api/advanced/tax/estimate',{'year':2026,'filing_status':'single','ordinary_income':'50000'},False)
   self.assertEqual(err.exception.code,403)
   self.assertEqual(request('/api/advanced/tax/estimate',{'year':2026,'filing_status':'single','ordinary_income':'50000'})['ordinary_income_tax_cents'],382000)
   with opener.open(base+'/advanced.js') as response:self.assertIn(b'showAdvanced',response.read())
   request('/api/users',{'email':'editor-test@example.com','password':'editor-password-1234','role':'editor'})
   request('/api/logout',{});token=request('/api/login',{'email':'editor-test@example.com','password':'editor-password-1234'})['csrf']
   with self.assertRaises(urllib.error.HTTPError) as err:request('/api/advanced/jobs')
   self.assertEqual(err.exception.code,403)
  finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
