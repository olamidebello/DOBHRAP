import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import app,registration_otp as otp,advanced as a
import tests.test_tenants as fixtures
class RegistrationOTPTests(unittest.TestCase):
 setUp=fixtures.TenantTests.setUp
 tearDown=fixtures.TenantTests.tearDown
 request=fixtures.TenantTests.request
 login=fixtures.TenantTests.login
 def enable(self):
  with app.connect() as c:c.execute('UPDATE registration_otp_policy SET enabled=1')
 def start(self,phone='+15551234567'):
  with patch.object(otp,'credentials',return_value=('key','secret')),patch.object(otp,'service_sid',return_value='VA'+'a'*32),patch.object(otp,'provider',return_value={'status':'pending'}):return self.request('/api/registration/otp/start',{'phone':phone})
 def test_approved_code_is_required_bound_and_single_use(self):
  self.enable();body={'account_type':'personal','email':'otp@example.com','password':'synthetic-password-123','confirm_password':'synthetic-password-123','phone':'+15551234567'}
  with self.assertRaises(HTTPError) as error:self.request('/api/register',body)
  self.assertEqual(error.exception.code,403);challenge=self.start()['challenge']
  with patch.object(otp,'service_sid',return_value='VA'+'a'*32),patch.object(otp,'provider',return_value={'status':'approved'}):ticket=self.request('/api/registration/otp/check',{'challenge':challenge,'code':'123456'})['ticket']
  with self.assertRaises(HTTPError):self.request('/api/register',dict(body,phone='+15557654321',otp_ticket=ticket))
  self.request('/api/register',dict(body,otp_ticket=ticket))
  with self.assertRaises(HTTPError):self.request('/api/register',dict(body,email='replay@example.com',otp_ticket=ticket))
  with app.connect() as c:
   row=c.execute("SELECT user_id,ticket_hash FROM registration_otp_challenges WHERE id=?",(challenge,)).fetchone();self.assertGreater(row['user_id'],0);self.assertNotEqual(row['ticket_hash'],ticket)
 def test_rate_limit_and_incorrect_code_do_not_approve(self):
  self.enable();challenge=self.start()['challenge']
  with self.assertRaises(HTTPError) as error:self.start()
  self.assertEqual(error.exception.code,429)
  with patch.object(otp,'service_sid',return_value='VA'+'a'*32),patch.object(otp,'provider',return_value={'status':'pending'}):
   with self.assertRaises(HTTPError):self.request('/api/registration/otp/check',{'challenge':challenge,'code':'999999'})
  with app.connect() as c:self.assertEqual(c.execute('SELECT state FROM registration_otp_challenges WHERE id=?',(challenge,)).fetchone()[0],'pending')
 def test_admin_access_and_manual_creation_exemption(self):
  self.enable();root,csrf=self.login('platform@example.com','platform-password-1234')
  result=self.request('/api/platform/users',{'action':'create','workspace_mode':'personal','role':'admin','email':'manual-otp@example.com','password':'synthetic-password-123','password_confirmation':'synthetic-password-123','confirm_password':'platform-password-1234'},root,csrf)
  user,token=self.login('manual-otp@example.com','synthetic-password-123')
  with self.assertRaises(HTTPError) as error:self.request('/api/platform/registration-otp',client=user)
  self.assertEqual(error.exception.code,403)
 def test_provision_reuses_service_and_never_sends_sms(self):
  root,csrf=self.login('platform@example.com','platform-password-1234')
  with patch.object(otp.settings,'get',side_effect=lambda key,default=None:'VA'+'a'*32 if key=='TWILIO_VERIFY_SERVICE_SID' else default),patch.object(otp,'provider',return_value={'sid':'VA'+'a'*32}) as provider:
   self.request('/api/platform/registration-otp',{'action':'provision','confirm_password':'platform-password-1234'},root,csrf);self.assertEqual(provider.call_count,1);self.assertEqual(provider.call_args.args[0],'/v2/Services/VA'+'a'*32);self.assertEqual(len(provider.call_args.args),1)
 def test_provision_creates_key_and_service_and_encrypts_secret(self):
  root,csrf=self.login('platform@example.com','platform-password-1234')
  def saved(key,default=None):
   with app.connect() as c:
    row=c.execute('SELECT value FROM provider_settings WHERE key=?',(key,)).fetchone()
   return otp.a.unseal(row['value'])['value'] if row else default
  with patch.object(otp,'credentials',return_value=('AC'+'b'*32,'synthetic-token')),patch.object(otp.settings,'get',side_effect=saved),patch.object(otp,'provider',side_effect=[{'sid':'SK'+'c'*32,'secret':'synthetic-key-secret'},{'sid':'VA'+'d'*32}]) as provider:
   self.request('/api/platform/registration-otp',{'action':'provision','confirm_password':'platform-password-1234'},root,csrf)
   self.assertEqual(provider.call_count,2);self.assertEqual(provider.call_args_list[1].args[0],'/v2/Services');self.assertEqual(saved('TWILIO_API_KEY_SECRET'),'synthetic-key-secret')
  with app.connect() as c:
   payload=c.execute("SELECT value FROM provider_settings WHERE key='TWILIO_API_KEY_SECRET'").fetchone()[0];self.assertNotIn('synthetic-key-secret',payload)
