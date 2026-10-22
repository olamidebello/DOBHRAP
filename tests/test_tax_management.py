import base64, os, tempfile, unittest, uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from cryptography.fernet import Fernet
import app, advanced as a, tax_analyst as analyst, tax_analyst_billing as billing, tax_analyst_control as control, tax_filing as filing
from tests.tax_billing_fixture import grant

class TaxManagementTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=self.temp.name+'/db'
  self.env=patch.dict(os.environ,{'DOBHRAP_DB_BACKEND':'sqlite','DOBHRAP_ADMIN_PASSWORD':'synthetic-password-123','DOBHRAP_ENCRYPTION_KEY':Fernet.generate_key().decode(),'DOBHRAP_ENABLE_TAX_ANALYST':'1','OPENAI_API_KEY':'synthetic-not-a-key','TAX_ANALYST_MODEL':'synthetic-model'})
  self.env.start();app.init();self.user={'id':1,'tenant_id':1,'role':'admin'};self.root={**self.user,'role':'super_admin'}
 def tearDown(self):self.env.stop();app.DB=self.old;self.temp.cleanup()
 def analyst(self,route,body,user=None):
  with app.connect() as c:return analyst.dispatch('/api/tax-analyst/'+route,'POST',body,c,user or self.user)
 def upload(self,n=1):return self.analyst('upload',{'year':2025,'type':'application/pdf','base64':base64.b64encode(('%PDF-'+str(n)).encode()).decode()})
 def call(self,route,body,user=None):
  with app.connect() as c:return filing.dispatch('/api/tax-filing/'+route,'POST',body,c,user or self.user)
 def admin(self,route,body=None,user=None):
  with app.connect() as c:return control.dispatch('/api/platform/tax-analyst/'+route,'GET' if body is None else 'POST',body or {},c,user or self.root)
 def balance(self,user=None):
  with app.connect() as c:return billing.status(c,1,user or self.user)
 def test_default_price_and_verified_owner_specific_purchase(self):
  self.assertEqual(self.balance()['price_cents'],500)
  with self.assertRaises(a.ServiceError) as error:self.upload()
  self.assertEqual(error.exception.status,402)
  grant(environment='test');grant(state='pending');self.assertEqual(self.balance()['available'],0)
  grant();self.assertEqual(self.balance()['available'],5);self.assertEqual(self.balance({'id':2,'role':'admin'})['available'],0)
 def test_success_consumes_once_and_second_document_cannot_spend_same_session(self):
  grant(count=1);one=self.upload(1);two=self.upload(2)
  with patch.object(analyst,'extract',return_value={'records':[],'tax_fields':[]}) as extract:
   self.assertEqual(self.analyst('analyze',{'id':one['id'],'revision':one['revision'],'consent':True})['state'],'review')
   with self.assertRaises(a.ServiceError) as error:self.analyst('analyze',{'id':two['id'],'revision':two['revision'],'consent':True})
   self.assertEqual(error.exception.status,402);self.assertEqual(extract.call_count,1)
   with app.connect() as c:self.assertEqual(c.execute('SELECT state FROM tax_analyst_documents WHERE id=?',(two['id'],)).fetchone()[0],'uploaded')
  self.assertEqual(self.balance()['available'],0);self.assertEqual(self.balance()['used'],1)
 def test_failure_returns_credit_and_retry_requires_consent(self):
  grant(count=1);doc=self.upload()
  with patch.object(analyst,'extract',side_effect=RuntimeError('synthetic failure')):failed=self.analyst('analyze',{'id':doc['id'],'revision':doc['revision'],'consent':True})
  self.assertEqual(self.balance()['available'],1)
  with app.connect() as c:c.execute('UPDATE tax_analyst_documents SET requested=0 WHERE id=?',(doc['id'],))
  with self.assertRaises(a.ServiceError):self.analyst('retry-analysis',{'id':doc['id'],'revision':failed['revision']})
  self.analyst('retry-analysis',{'id':doc['id'],'revision':failed['revision'],'consent':True})
 def test_concurrent_reservations(self):
  grant(count=1)
  def attempt(_):
   with app.connect() as c:
    try:return bool(billing.reserve(c,self.user,str(uuid.uuid4()),1))
    except a.ServiceError:return False
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
  self.assertEqual(sum(results),1);self.assertEqual(self.balance()['reserved'],1)
 def test_price_authorization_order_snapshot_and_unused_suspend(self):
  order=grant(count=1)[0];self.balance()
  with self.assertRaises(a.ServiceError):self.admin('pricing',user=self.user)
  self.admin('pricing',{'price_cents':750,'active':True,'expected_price_cents':500,'expected_active':True})
  self.assertEqual(self.balance()['price_cents'],750)
  with app.connect() as c:self.assertEqual(c.execute('SELECT amount FROM market_orders WHERE id=?',(order,)).fetchone()[0],500)
  with self.assertRaises(a.ServiceError):self.admin('pricing',{'price_cents':800,'active':True,'expected_price_cents':500,'expected_active':True})
  self.admin('session-action',{'order_id':order,'expected_state':'available'});self.assertEqual(self.balance()['available'],0)
  self.admin('session-action',{'order_id':order,'expected_state':'revoked'});self.assertEqual(self.balance()['available'],1)
  with self.assertRaises(a.ServiceError):self.admin('session-action',{'order_id':order,'expected_state':'used'})
 def test_policy_revision_and_runtime_pause(self):
  settings=self.admin('settings');policy={**settings['policy'],'analysis_enabled':False}
  self.admin('settings',{'revision':settings['revision'],'policy':policy})
  with self.assertRaises(a.ServiceError):self.admin('settings',{'revision':settings['revision'],'policy':policy})
  with self.assertRaises(a.ServiceError):control.validate({**policy,'daily_requests':1000})
  with app.connect() as c:
   with patch.object(analyst,'extract') as extract:self.assertEqual(analyst.process_analysis(c,{1:self.user}),0);extract.assert_not_called()
 def test_return_families_private_encrypted_and_blocked(self):
  for year in (2025,2026):
   for form in ('1040','1065','1120-S','1120'):
    item=self.call('create',{'year':year,'form':form,'name':'Synthetic private taxpayer'})
    self.assertFalse(item['review']['filing_ready']);self.assertTrue(item['review']['blockers'])
    with app.connect() as c:self.assertNotIn('Synthetic private taxpayer',c.execute('SELECT payload FROM tax_filing_cases WHERE id=?',(item['id'],)).fetchone()[0])
    with self.assertRaises(a.ServiceError):self.call('open',{'id':item['id']},{'id':2,'role':'super_admin'})
 def test_regular_se_uses_w2_box3_and_net_profit(self):
  d=filing.clean({'taxpayer_name':'Synthetic','gross_receipts':'50000','expense_supplies':'10000','social_security_wages':'176100','no_special_se_rules':True})
  result=filing.calculation(2025,'1040',d)
  self.assertEqual(result['se_tax_cents'],107126);self.assertEqual(result['half_se_deduction_cents'],53563)
  d['social_security_wages']='0.00';self.assertEqual(filing.calculation(2025,'1040',d)['se_tax_cents'],565182)
 def test_entity_allocation_and_archive_revision(self):
  d=filing.clean({'gross_receipts':'100','expense_other':'200','owners':[{'name':'A','share':'60'},{'name':'B','share':'30'}]})
  r=filing.calculation(2025,'1065',d);self.assertTrue(any('100 percent' in b for b in r['blockers']));self.assertTrue(any('loss' in b for b in r['blockers']))
  item=self.call('create',{'year':2025,'form':'1120','name':'Synthetic'})
  saved=self.call('save',{'id':item['id'],'revision':item['revision'],'data':{**item['data'],'taxpayer_name':'Example LLC'}})
  with self.assertRaises(a.ServiceError):self.call('save',{'id':item['id'],'revision':item['revision'],'data':item['data']})
  archived=self.call('archive',{'id':item['id'],'revision':saved['revision'],'archived':True})
  with self.assertRaises(a.ServiceError):self.call('save',{'id':item['id'],'revision':archived['revision'],'data':saved['data']})
  self.assertEqual(self.call('export',{'id':item['id']})['kind'],'NOT-FOR-FILING')
 def test_admin_queue_metadata_and_cancel(self):
  grant(count=1);self.upload();self.call('create',{'year':2025,'form':'1040','name':'Private name'})
  self.analyst('queue-analysis',{'year':2025,'consent':True})
  overview=self.admin('overview');self.assertNotIn('Private name',str(overview));self.assertNotIn('base64',str(overview));job=overview['workspaces'][0]['jobs'][0]
  self.admin('cancel-job',{'tenant_id':1,'id':job['id']})
  with app.connect() as c:self.assertEqual(c.execute('SELECT state FROM tax_analysis_jobs WHERE id=?',(job['id'],)).fetchone()[0],'cancelled')

from urllib.error import HTTPError
import tests.test_tenants as tenant_fixtures

class TaxManagementHttpTests(unittest.TestCase):
 setUp=tenant_fixtures.TenantTests.setUp
 tearDown=tenant_fixtures.TenantTests.tearDown
 request=tenant_fixtures.TenantTests.request
 login=tenant_fixtures.TenantTests.login
 register=tenant_fixtures.TenantTests.register
 def test_authenticated_admin_rbac_csrf_billing_and_case_isolation(self):
  with self.public.open(self.base+'/tax-management.js') as asset:self.assertIn(b'showTaxAnalystAdmin',asset.read())
  tid=self.register('taxcase');client,csrf=self.login('taxcase@example.com');root,token=self.login('platform@example.com','platform-password-1234')
  with self.assertRaises(HTTPError) as error:self.request('/api/platform/tax-analyst/settings',client=client)
  self.assertEqual(error.exception.code,403)
  settings=self.request('/api/platform/tax-analyst/settings',client=root)
  with self.assertRaises(HTTPError) as error:self.request('/api/platform/tax-analyst/settings',{'revision':settings['revision'],'policy':settings['policy']},root)
  self.assertEqual(error.exception.code,403)
  status=self.request('/api/tax-analyst/billing',client=client);self.assertEqual(status['price_cents'],500);self.assertEqual(status['available'],0)
  doc={'year':2025,'type':'application/pdf','base64':base64.b64encode(b'%PDF-synthetic').decode()}
  with self.assertRaises(HTTPError) as error:self.request('/api/tax-analyst/upload',doc,client,csrf)
  self.assertEqual(error.exception.code,402)
  with app.connect() as c:uid=c.execute('SELECT id FROM users WHERE tenant_id=?',(tid,)).fetchone()[0]
  grant(owner=uid,tenant=tid,count=1)
  self.assertEqual(self.request('/api/tax-analyst/billing',client=client)['available'],1)
  uploaded=self.request('/api/tax-analyst/upload',doc,client,csrf);self.assertTrue(uploaded['id'])
  with patch.dict(os.environ,{'DOBHRAP_ENABLE_TAX_ANALYST':'1','OPENAI_API_KEY':'synthetic','TAX_ANALYST_MODEL':'synthetic'}),patch.object(analyst,'extract',return_value={'records':[],'tax_fields':[]}):
   analyzed=self.request('/api/tax-analyst/analyze',{'id':uploaded['id'],'revision':uploaded['revision'],'consent':True},client,csrf)
  self.assertEqual(analyzed['state'],'review');self.assertEqual(self.request('/api/tax-analyst/billing',client=client)['used'],1)
  case=self.request('/api/tax-filing/create',{'year':2025,'form':'1065','name':'Private entity'},client,csrf)
  opened=self.request('/api/tax-filing/open',{'id':case['id']},client,csrf);self.assertFalse(opened['review']['filing_ready'])
  with self.assertRaises(HTTPError) as error:self.request('/api/tax-filing/open',{'id':case['id']},root,token,tenant=tid)
  self.assertEqual(error.exception.code,404)
 def test_tax_only_catalog_includes_analyst_and_does_not_accept_coupons(self):
  tid=self.request('/api/register',{'service_mode':'tax_only','email':'taxonly@example.com','password':'workspace-password-123','confirm_password':'workspace-password-123'})['tenant_id'];client,csrf=self.login('taxonly@example.com')
  products=self.request('/api/market/products',client=client);self.assertTrue(any(p['id']=='tax-analyst-session' for p in products))
  with self.assertRaises(HTTPError) as error:self.request('/api/coupons/redeem',{'product_id':'tax-analyst-session','code':'SYNTHETIC-COUPON','request_key':str(uuid.uuid4())},client,csrf)
  self.assertEqual(error.exception.code,403)
  with self.assertRaises(HTTPError) as error:self.request('/api/tax-filing/create',{'year':2025,'form':'1040','name':'Draft'},client,csrf)
  self.assertEqual(error.exception.code,402)
