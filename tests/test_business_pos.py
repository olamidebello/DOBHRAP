import os,time,tempfile,secrets,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
import app,advanced as a,business_pos
import tests.test_tenants as fixtures
class StorefrontRegistrationTests(unittest.TestCase):
 setUp=fixtures.TenantTests.setUp
 tearDown=fixtures.TenantTests.tearDown
 request=fixtures.TenantTests.request
 login=fixtures.TenantTests.login
 register=fixtures.TenantTests.register
 def test_registration_queue_and_isolation_and_worker_retry(self):
  data=dict(account_type='storefront',service_mode='business',company='Store owner',email='store@example.com',password='workspace-password-123',confirm_password='workspace-password-123',store_country='US',store_currency='USD',store_timezone='UTC')
  tid=self.request('/api/register',data)['tenant_id'];client,csrf=self.login('store@example.com');status=self.request('/api/business/pos',client=client);self.assertEqual(status['storefront']['state'],'queued')
  self.register('other');other,token=self.login('other@example.com')
  with self.assertRaises(HTTPError):self.request('/api/business/pos',client=other,tenant=tid)
  with app.connect() as c:
   row=c.execute('SELECT * FROM business_pos_preferences WHERE tenant_id=?',(tid,)).fetchone();self.assertEqual(a.unseal(row['payload'])['currency'],'USD')
  key=Path(self.temp.name)/'signing';key.write_bytes(Ed25519PrivateKey.generate().private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()))
  with patch.dict(os.environ,DOBHRAP_POS_SIGNING_KEY=str(key)),patch.object(a,'request_json',return_value={'state':'ready','storefront':{'slug':'store-12345678','store_id':'store-1'}}) as remote:
   business_pos.process(app);business_pos.process(app);self.assertEqual(remote.call_count,1)
   session=self.request('/api/business/pos-session',dict(nonce=secrets.token_hex(32),target='merchant'),client,csrf);self.assertEqual(len(session['assertion'].split('.')),3)
  self.assertEqual(self.request('/api/business/pos',client=client)['storefront']['state'],'ready')
 def test_invalid_opt_in_rolls_back_and_personal_access_denied(self):
  data=dict(account_type='storefront',company='Bad store',email='badstore@example.com',password='workspace-password-123',confirm_password='workspace-password-123')
  with self.assertRaises(HTTPError):self.request('/api/register',data)
  with app.connect() as c:self.assertFalse(c.execute("SELECT 1 FROM users WHERE email='badstore@example.com'").fetchone())
  self.request('/api/register',dict(data,account_type='personal',email='personal@example.com'));client,csrf=self.login('personal@example.com')
  with self.assertRaises(HTTPError):self.request('/api/business/pos',client=client)
