import unittest,json
from urllib.error import HTTPError
import app
import tests.test_tenants as fixtures
class UserManagementTests(unittest.TestCase):
 setUp=fixtures.TenantTests.setUp
 tearDown=fixtures.TenantTests.tearDown
 request=fixtures.TenantTests.request
 login=fixtures.TenantTests.login
 register=fixtures.TenantTests.register
 def setup_user(self):
  self.register('managed');self.client,self.csrf=self.login('managed@example.com');self.root,self.token=self.login('platform@example.com','platform-password-1234')
  return next(u for u in self.request('/api/platform/users',client=self.root)['users'] if u['email']=='managed@example.com')
 def change(self,u,action,**kw):return self.request('/api/platform/users',{'id':u['id'],'revision':u['account_revision'],'action':action,'confirm_password':'platform-password-1234',**kw},self.root,self.token)
 def test_global_list_permissions_suspend_reactivate(self):
  u=self.setup_user()
  with self.assertRaises(HTTPError) as e:self.request('/api/platform/users',client=self.client)
  self.assertEqual(e.exception.code,403);self.change(u,'suspend')
  with self.assertRaises(HTTPError):self.request('/api/me',client=self.client)
  with self.assertRaises(HTTPError):self.login('managed@example.com')
  u=next(x for x in self.request('/api/platform/users',client=self.root)['users'] if x['id']==u['id']);self.change(u,'activate');self.login('managed@example.com')
 def test_edit_revision_and_delete_identity_retains_records(self):
  u=self.setup_user();self.change(u,'edit',email='edited@example.com',display_name='Managed person',role='editor')
  with self.assertRaises(HTTPError) as e:self.change(u,'suspend')
  self.assertEqual(e.exception.code,409)
  u=next(x for x in self.request('/api/platform/users',client=self.root)['users'] if x['id']==u['id']);self.change(u,'delete',confirm_email=u['email'])
  with app.connect() as c:
   row=c.execute('SELECT * FROM users WHERE id=?',(u['id'],)).fetchone();self.assertEqual(row['account_status'],'deleted');self.assertNotEqual(row['email'],'edited@example.com');self.assertTrue(c.execute('SELECT id FROM tenants WHERE id=?',(u['tenant_id'],)).fetchone())
 def test_admin_password_and_last_admin_protection(self):
  u=self.setup_user()
  with self.assertRaises(HTTPError):self.change(u,'suspend',confirm_password='wrong')
  root=next(x for x in self.request('/api/platform/users',client=self.root)['users'] if x['role']=='super_admin')
  for action,extra in [('suspend',{}),('delete',{'confirm_email':root['email']}),('edit',{'email':root['email'],'role':'viewer'})]:
   with self.assertRaises(HTTPError):self.change(root,action,**extra)
