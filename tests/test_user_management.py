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
 def test_edit_revision_and_permanent_deletion(self):
  u=self.setup_user();self.change(u,'edit',email='edited@example.com',display_name='Managed person',role='editor')
  with self.assertRaises(HTTPError) as e:self.change(u,'suspend')
  self.assertEqual(e.exception.code,409)
  u=next(x for x in self.request('/api/platform/users',client=self.root)['users'] if x['id']==u['id']);self.change(u,'delete',confirm_email=u['email'])
  with app.connect() as c:
   row=c.execute('SELECT * FROM users WHERE id=?',(u['id'],)).fetchone();self.assertIsNone(row);self.assertTrue(c.execute('SELECT id FROM tenants WHERE id=?',(u['tenant_id'],)).fetchone())
 def test_admin_password_and_last_admin_protection(self):
  u=self.setup_user()
  with self.assertRaises(HTTPError):self.change(u,'suspend',confirm_password='wrong')
  root=next(x for x in self.request('/api/platform/users',client=self.root)['users'] if x['role']=='super_admin')
  for action,extra in [('suspend',{}),('delete',{'confirm_email':root['email']}),('edit',{'email':root['email'],'role':'viewer'})]:
   with self.assertRaises(HTTPError):self.change(root,action,**extra)
 def test_manual_create_existing_workspace_password_and_queued_services(self):
  self.root,self.token=self.login('platform@example.com','platform-password-1234')
  body={'action':'create','confirm_password':'platform-password-1234','workspace_mode':'existing','tenant_id':1,'display_name':'Manual user','email':'manual@example.com','role':'viewer','password':'manual-password-12345','password_confirmation':'manual-password-12345','account_status':'active'}
  result=self.request('/api/platform/users',body,self.root,self.token);client,csrf=self.login('manual@example.com','manual-password-12345');self.assertEqual(self.request('/api/me',client=client)['role'],'viewer')
  with app.connect() as c:
   u=c.execute('SELECT * FROM users WHERE id=?',(result['id'],)).fetchone();self.assertNotEqual(u['hash'],body['password']);self.assertEqual(c.execute('SELECT count(*) FROM communications_accounts WHERE owner=?',(u['id'],)).fetchone()[0],2)
  with self.assertRaises(HTTPError) as e:self.request('/api/platform/users',body,self.root,self.token)
  self.assertEqual(e.exception.code,409)
 def test_manual_create_new_workspace_and_reject_unsafe_roles(self):
  self.root,self.token=self.login('platform@example.com','platform-password-1234')
  for kind in ('personal','business'):
   body={'action':'create','confirm_password':'platform-password-1234','workspace_mode':kind,'company':'New company','email':kind+'-manual@example.com','role':'admin','password':'manual-password-12345','password_confirmation':'manual-password-12345','account_status':'suspended'}
   r=self.request('/api/platform/users',body,self.root,self.token)
   with app.connect() as c:
    self.assertEqual(c.execute('SELECT service_mode FROM tenants WHERE id=?',(r['tenant_id'],)).fetchone()[0],'tax_only' if kind=='personal' else 'business');self.assertEqual(c.execute('SELECT account_status FROM users WHERE id=?',(r['id'],)).fetchone()[0],'suspended')
   with self.assertRaises(HTTPError):self.login(body['email'],body['password'])
  body.update(email='bad-role@example.com',role='super_admin')
  with self.assertRaises(HTTPError):self.request('/api/platform/users',body,self.root,self.token)
  body.update(workspace_mode='existing',tenant_id=r['tenant_id'])
  with self.assertRaises(HTTPError):self.request('/api/platform/users',body,self.root,self.token)
 def test_manual_creation_rejects_wrong_admin_and_password_mismatch(self):
  self.root,self.token=self.login('platform@example.com','platform-password-1234')
  body={'action':'create','confirm_password':'wrong','workspace_mode':'existing','tenant_id':1,'email':'invalid-create@example.com','role':'viewer','password':'manual-password-12345','password_confirmation':'different'}
  for confirm in ('wrong','platform-password-1234'):
   with self.assertRaises(HTTPError):self.request('/api/platform/users',dict(body,confirm_password=confirm),self.root,self.token)
  with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0],1)

 def test_edit_password_and_profile(self):
  u=self.setup_user();self.change(u,'edit',email='new-login@example.com',display_name='Updated profile',role='editor',phone='+15551234567',job_title='Manager',address='Example address',bio='Profile text',new_password='replacement-password-123',new_password_confirmation='replacement-password-123')
  with self.assertRaises(HTTPError):self.login('managed@example.com')
  self.login('new-login@example.com','replacement-password-123')
  profile=self.request('/api/platform/users',{'action':'profile','id':u['id']},self.root,self.token)['profile'];self.assertEqual(profile['phone'],'+15551234567');self.assertEqual(profile['bio'],'Profile text')
 def test_permanent_removal_deletes_owned_data_and_never_reuses_id(self):
  import advanced as a
  u=self.setup_user()
  with app.connect() as c:c.execute('INSERT INTO platform_user_profiles VALUES(?,?)',(u['id'],a.seal({'phone':'+15551234567'})));c.execute("INSERT INTO wallet_accounts VALUES(?,'USD',100)",(u['id'],))
  with app.tenant_connect(u['tenant_id']) as c:c.execute('INSERT INTO tax_analyst_documents(id,owner,year,payload,size,created) VALUES(?,?,?,?,?,?)',('owned-document',u['id'],2026,a.seal({'private':'tax-data'}),1,0))
  result=self.change(u,'delete',confirm_email=u['email']);self.assertEqual(result['deletion_state'],'completed')
  with app.connect() as c:self.assertIsNone(c.execute('SELECT id FROM users WHERE id=?',(u['id'],)).fetchone());self.assertIsNone(c.execute('SELECT owner FROM wallet_accounts WHERE owner=?',(u['id'],)).fetchone());self.assertTrue(c.execute('SELECT id FROM users WHERE id=1').fetchone())
  with app.tenant_connect(u['tenant_id']) as c:self.assertIsNone(c.execute('SELECT id FROM tax_analyst_documents WHERE owner=?',(u['id'],)).fetchone())
  created=self.request('/api/platform/users',{'action':'create','workspace_mode':'existing','tenant_id':1,'email':'after-delete@example.com','role':'viewer','password':'synthetic-password-123','password_confirmation':'synthetic-password-123','confirm_password':'platform-password-1234'},self.root,self.token);self.assertGreater(created['id'],u['id'])
 def test_user_events_are_admin_only_and_exclude_request_secrets(self):
  u=self.setup_user();self.request('/api/me?password=must-not-log-this',client=self.client)
  with self.assertRaises(HTTPError):self.request('/api/platform/user-events',client=self.client)
  result=self.request('/api/platform/user-events',{},self.root,self.token);self.assertTrue(result['events']);self.assertNotIn('must-not-log-this',json.dumps(result));self.assertNotIn('platform-password-1234',json.dumps(result));self.assertTrue(any(r['actor']==u['id'] for r in result['events']))
