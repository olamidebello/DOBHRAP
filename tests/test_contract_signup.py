import unittest
from urllib.error import HTTPError
import app
import tests.test_tenants as fixtures
class ContractSignupTests(unittest.TestCase):
 setUp=fixtures.TenantTests.setUp
 tearDown=fixtures.TenantTests.tearDown
 request=fixtures.TenantTests.request
 login=fixtures.TenantTests.login
 def signup(self,**extra):
  body={'account_type':'government_contracts','service_mode':'contracts_only','company':'Contract Supplier','email':'contracts@example.com','password':'contract-password-1234','confirm_password':'contract-password-1234'}
  body.update(extra);return self.request('/api/register',body)
 def test_signup_and_contracts_only_backend_access(self):
  result=self.signup();client,csrf=self.login('contracts@example.com','contract-password-1234')
  me=self.request('/api/me',client=client);self.assertEqual(me['tenant']['service_mode'],'contracts_only');self.assertEqual(me['modules'],{})
  for path in ('/api/contracting/status','/api/business/profile','/api/business/opportunities','/api/business/proposals','/api/wallet/status','/api/intl/catalog'):
   self.request(path,client=client)
  for path in ('/api/users','/api/customers','/api/communications/status','/api/tax-services/status','/api/market/products','/api/ai-service/status'):
   with self.assertRaises(HTTPError) as error:self.request(path,client=client)
   self.assertEqual(error.exception.code,403)
  self.request('/api/contracting/partners-directory',{},client,csrf)
  self.request('/api/business/profile',{'revision':0,'profile':{'legal_name':'Contract Supplier','naics':'541512'}},client,csrf)
  self.request('/api/contracting/watch',{'enabled':True,'filters':{'naics':'541512'}},client,csrf)
  with app.connect() as c:
   self.assertEqual(c.execute('SELECT count(*) FROM communications_accounts WHERE tenant_id=?',(result['tenant_id'],)).fetchone()[0],0)
  with self.assertRaises(HTTPError) as error:self.request('/api/me',client=client,tenant=1)
  self.assertEqual(error.exception.code,403)
 def test_rejects_conflicting_scope_but_requires_no_business_registration(self):
  with self.assertRaises(HTTPError):self.signup(service_mode='business')
  result=self.signup(company='')
  with app.connect() as c:self.assertEqual(c.execute('SELECT name FROM tenants WHERE id=?',(result['tenant_id'],)).fetchone()[0],'Government contracting account')
 def test_direct_signup_page_is_served(self):
  with self.public.open(self.base+'/contracting-opportunities') as response:
   self.assertEqual(response.status,200);self.assertIn(b'Contracting opportunities only',response.read())
