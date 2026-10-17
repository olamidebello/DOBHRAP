import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import app
import advanced as a
import support as s
import provider_settings as p
import marketplace as m

class SupportTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=self.temp.name+'/db.sqlite'
  self.env=patch.dict(os.environ,{'DOBHRAP_ADMIN_PASSWORD':'testing-password-1234','DOBHRAP_ENCRYPTION_KEY':Fernet.generate_key().decode(),'OPENAI_API_KEY':'','DOBHRAP_ENABLE_SUPPORT_AI':'0'})
  self.env.start();app.init()
  with app.connect() as c:
   c.execute("UPDATE users SET role='super_admin'")
   self.root=dict(c.execute('SELECT * FROM users WHERE id=1').fetchone());c.commit()
   self.tid=app.register_workspace(c,{'company':'Support test','email':'support@example.com','password':'support-password-1234','confirm_password':'support-password-1234'})['tenant_id']
  self.user={'id':2,'role':'admin'}
 def tearDown(self):self.env.stop();app.DB=self.old;self.temp.cleanup()
 def config(self,body):
  with app.connect() as c:return p.dispatch('/api/provider-settings','POST',{'confirm_password':'testing-password-1234',**body},c,self.root)
 def call(self,route,body=None,user=None,tid=None):
  with app.connect() as c:return s.dispatch('/api/support/'+route,'GET' if body is None else 'POST',body or {},c,user or self.user,tid or self.tid)
 def ticket(self,consent=False):return self.call('tickets',{'subject':'Banking help','message':'How do I import bank data?','ai_consent':consent})['id']
 def enable(self):self.config({'action':'save','values':{'OPENAI_API_KEY':'sk-proj-test-only-secret-fixture','SUPPORT_AI_MODEL':'test-model','DOBHRAP_ENABLE_SUPPORT_AI':'1'}})
 def test_keys_encrypted_masked_preserved_and_disabled(self):
  self.enable();self.assertEqual(p.get('OPENAI_API_KEY'),'sk-proj-test-only-secret-fixture')
  with app.connect() as c:
   raw=c.execute("SELECT value FROM provider_settings WHERE key='OPENAI_API_KEY'").fetchone()[0]
   snapshot=p.dispatch('/api/provider-settings','GET',{},c,self.root)
  self.assertNotIn('sk-proj-',raw);self.assertNotIn('sk-proj-',json.dumps(snapshot))
  self.config({'action':'save','values':{'OPENAI_API_KEY':''}});self.assertTrue(p.get('OPENAI_API_KEY'))
  self.config({'action':'save','disable':['OPENAI_API_KEY']});self.assertEqual(p.get('OPENAI_API_KEY'),'')
  self.assertEqual(os.environ['OPENAI_API_KEY'],'')
 def test_configuration_auth_validation_and_live_guard(self):
  with app.connect() as c:
   with self.assertRaises(a.ServiceError):p.dispatch('/api/provider-settings','GET',{},c,self.user)
  with self.assertRaises(a.ServiceError):self.config({'action':'save','confirm_password':'wrong','values':{}})
  with self.assertRaises(a.ServiceError):self.config({'action':'save','values':{'PORT':'22'}})
  with self.assertRaises(a.ServiceError):self.config({'action':'save','values':{'DOBHRAP_ENABLE_LIVE_PAYMENTS':'1'}})
  with self.assertRaises(a.ServiceError):self.config({'action':'save','values':{'EFILE_GATEWAY_URL':'http://example.com'}})
  self.config({'action':'save','values':{'DOBHRAP_ENABLE_LIVE_PAYMENTS':'1'},'confirm_live':True})
 def test_connection_check_and_profile_no_secret_echo(self):
  self.enable()
  with patch.object(a,'request_json',return_value={'id':'test-model'}) as request:
   self.assertTrue(self.config({'action':'test','provider':'openai'})['ok'])
   self.assertIn('/models/test-model',request.call_args.args[0])
  profile=self.config({'action':'profile'});self.assertTrue(profile['database_ok']);self.assertIn('duration_ms',profile['checks'][0])
  with patch.object(a,'request_json',side_effect=RuntimeError('secret!')):
   result=self.config({'action':'test','provider':'openai'});self.assertFalse(result['ok']);self.assertNotIn('secret!',str(result))
 def test_ticket_isolation_priority_and_human_escalation(self):
  tid=self.ticket();self.assertEqual(len(self.call('tickets')),1)
  with self.assertRaises(a.ServiceError):self.call('thread',{'id':tid},tid=999)
  with self.assertRaises(a.ServiceError):self.call('thread',{'id':tid},user={'id':3,'role':'viewer'})
  self.call('action',{'id':tid,'action':'escalate'})
  self.assertTrue(self.call('thread',{'id':tid})['ticket']['escalated'])
  self.call('action',{'id':tid,'action':'close'})
  with self.assertRaises(a.ServiceError):self.call('reply',{'id':tid,'message':'Reply'})
 def test_ai_consent_is_required_and_manual_grounded(self):
  self.enable();tid=self.ticket()
  with self.assertRaises(a.ServiceError):self.call('ai',{'id':tid})
  tid=self.ticket(True);self.call('ai',{'id':tid});self.call('ai',{'id':tid})
  with patch.object(a,'request_json',return_value={'output':[{'type':'message','content':[{'type':'output_text','text':'Use Bank connections. See Bank consent and automatic imports.'}]}]}) as provider:
   s.run_all();s.run_all();self.assertEqual(provider.call_count,1)
   payload=provider.call_args.args[1];self.assertFalse(payload['store']);self.assertNotIn('tools',payload);self.assertIn('Bank consent',payload['input'])
  thread=self.call('thread',{'id':tid});self.assertEqual(sum(m['kind']=='ai' for m in thread['messages']),1)
 def test_revoke_and_failure_no_automatic_paid_retry(self):
  self.enable();tid=self.ticket(True);self.call('ai',{'id':tid})
  self.call('action',{'id':tid,'action':'revoke_ai'})
  with patch.object(a,'request_json') as provider:s.run_all();provider.assert_not_called()
  tid=self.ticket(True);self.call('ai',{'id':tid})
  with patch.object(a,'request_json',side_effect=RuntimeError('private credential')) as provider:
   s.run_all();s.run_all();self.assertEqual(provider.call_count,1)
  self.assertEqual(self.call('thread',{'id':tid})['jobs'][0]['state'],'failed')
  self.assertNotIn('private credential',json.dumps(self.call('thread',{'id':tid})))
 def test_intake_token_generated_once_and_suspended_workspace_rejected(self):
  token=self.config({'action':'generate_intake_token'})['token']
  with app.connect() as c:
   self.assertNotIn(token,json.dumps(p.snapshot(c)))
   with self.assertRaises(a.ServiceError):s.intake(c,{'tenant_id':self.tid},{})
   result=s.intake(c,{'tenant_id':self.tid,'subject':'Automation issue','message':'Readiness failed','ai_consent':True},{'Authorization':'Bearer '+token})
  self.assertFalse(self.call('thread',{'id':result['id']})['ticket']['ai_consent'])
  token2=self.config({'action':'generate_intake_token'})['token'];self.assertNotEqual(token,token2)
 def test_stripe_gui_provision_stores_provider_secret(self):
  self.config({'action':'save','values':{'STRIPE_SECRET_KEY':'sk_test_fixture','PAYMENTS_ENV':'test'}})
  with patch.object(m,'provider',side_effect=[{'data':[],'has_more':False},{'id':'we_fixture','secret':'whsec_new_fixture'}]):
   result=self.config({'action':'provision_stripe'})
  self.assertTrue(result['ok']);self.assertNotIn('whsec_',str(result));self.assertEqual(p.get('STRIPE_WEBHOOK_SECRET'),'whsec_new_fixture')
 def test_overdue_escalation_and_manual_search_content(self):
  tid=self.ticket()
  with app.connect() as c:c.execute('UPDATE support_tickets SET updated=? WHERE id=?',(int(time.time())-90000,tid))
  s.run_all();self.assertTrue(self.call('thread',{'id':tid})['ticket']['escalated'])
  self.assertGreater(len(self.call('manual')),8)
