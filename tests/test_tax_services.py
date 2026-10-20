import unittest, uuid
from urllib.error import HTTPError
import app, tax_services
import tests.test_tenants as fixtures

class TaxServiceTests(unittest.TestCase):
 setUp=fixtures.TenantTests.setUp
 tearDown=fixtures.TenantTests.tearDown
 request=fixtures.TenantTests.request
 login=fixtures.TenantTests.login
 def account(self):
  body={'service_mode':'tax_only','email':'tax@example.com','password':'workspace-password-123','confirm_password':'workspace-password-123'}
  tid=self.request('/api/register',body)['tenant_id'];client,csrf=self.login('tax@example.com');return tid,client,csrf
 def test_personal_registration_and_backend_scope(self):
  tid,client,csrf=self.account();me=self.request('/api/me',client=client);self.assertEqual(me['tenant']['service_mode'],'tax_only');self.assertEqual(me['modules'],{})
  for path in ('/api/records/customers','/api/dashboard','/api/users','/api/advanced/workflows','/api/financial-statements'):
   with self.assertRaises(HTTPError) as e:self.request(path,client=client)
   self.assertEqual(e.exception.code,403)
  self.assertEqual(self.request('/api/tax-analyst/list',client=client)['documents'],[])
  for path,body in (('/api/tax-prep/create',{}),('/api/tax-analyst/compile',{'year':2026,'confirm':True})):
   with self.assertRaises(HTTPError) as e:self.request(path,body,client,csrf)
   self.assertEqual(e.exception.code,402)
  self.assertEqual(self.request('/api/tax-services/status',client=client)['paid_years'],[])
  root,token=self.login('platform@example.com','platform-password-1234')
  self.assertTrue(self.request('/api/me',client=root,tenant=tid)['modules'])
  self.assertEqual(len(self.request('/api/tenants',client=root)),2)
 def test_live_verified_year_specific_payment_only(self):
  tid,client,csrf=self.account()
  with app.connect() as c:
   uid=c.execute('SELECT id FROM users WHERE tenant_id=?',(tid,)).fetchone()[0];oid=str(uuid.uuid4())
   c.execute("INSERT INTO market_orders(id,tenant_id,owner,product_id,name,service_code,amount,currency,gateway,environment,request_key,state,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(oid,tid,uid,'tax','Tax prep','tax_preparation_2026',1000,'USD','stripe','test',str(uuid.uuid4()),'test_fulfilled',0))
   c.execute('INSERT INTO market_services(order_id,tenant_id,service_code,name,environment,status,activated) VALUES(?,?,?,?,?,?,?)',(oid,tid,'tax_preparation_2026','Tax prep','test','test_active',0))
   self.assertFalse(tax_services.paid(c,tid,uid,2026));c.execute("UPDATE market_orders SET environment='live',state='pending'");c.execute("UPDATE market_services SET environment='live',status='active'");self.assertFalse(tax_services.paid(c,tid,uid,2026));c.execute("UPDATE market_orders SET state='fulfilled'");self.assertTrue(tax_services.paid(c,tid,uid,2026));self.assertFalse(tax_services.paid(c,tid,uid,2025));self.assertFalse(tax_services.paid(c,tid,uid+1,2026))
  draft=self.request('/api/tax-prep/create',{},client,csrf);self.assertEqual(draft['year'],2026)
  self.assertEqual(self.request('/api/tax-services/status',client=client)['paid_years'],[2026])
 def test_tax_only_catalog_and_checkout_restriction(self):
  tid,client,csrf=self.account()
  with app.connect() as c:
   for pid,code in [('tax','tax_preparation_2026'),('business','hosting')]:c.execute('INSERT INTO market_products VALUES(?,?,?,?,?,?,?)',(pid,pid,'fixture',code,1000,'USD',1))
  self.assertEqual({p['id'] for p in self.request('/api/market/products',client=client)},{'tax','tax-analyst-session'})
  with self.assertRaises(HTTPError) as e:self.request('/api/market/checkout',{'product_id':'business','gateway':'stripe','request_key':str(uuid.uuid4())},client,csrf)
  self.assertEqual(e.exception.code,403)

