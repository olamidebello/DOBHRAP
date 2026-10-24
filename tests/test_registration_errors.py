import unittest,json
from unittest.mock import patch
from urllib.error import HTTPError
import app
import tests.test_tenants as fixtures

class RegistrationFailureTests(unittest.TestCase):
 setUp=fixtures.TenantTests.setUp
 tearDown=fixtures.TenantTests.tearDown
 request=fixtures.TenantTests.request
 def body(self):return {'account_type':'personal','email':'registration-error@example.com','password':'synthetic-password-123','confirm_password':'synthetic-password-123'}
 def test_storage_failure_is_json_and_rolls_back_catalog(self):
  with patch.object(app,'initialize_business',side_effect=PermissionError('private-server-path')):
   with self.assertRaises(HTTPError) as error:self.request('/api/register',self.body())
  self.assertEqual(error.exception.code,503);self.assertIn('application/json',error.exception.headers['Content-Type']);data=json.load(error.exception);self.assertIn('storage',data['error']);self.assertNotIn('private-server-path',str(data))
  with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM tenants').fetchone()[0],1);self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0],1)
 def test_unexpected_failure_returns_sanitized_json(self):
  with patch.object(app,'register_workspace',side_effect=RuntimeError('private-provider-secret')):
   with self.assertRaises(HTTPError) as error:self.request('/api/register',self.body())
  self.assertEqual(error.exception.code,500);data=json.load(error.exception);self.assertNotIn('private-provider-secret',str(data));self.assertIn('before submitting',data['error'])
