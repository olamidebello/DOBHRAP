import json, uuid, unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
import app, advanced as a, communications as comms, communications_worker as worker
import tests.test_tenants as fixtures

class CommunicationsTests(unittest.TestCase):
 setUp=fixtures.TenantTests.setUp
 tearDown=fixtures.TenantTests.tearDown
 request=fixtures.TenantTests.request
 login=fixtures.TenantTests.login
 def account(self,kind='personal',email='phone@example.com'):
  self.request('/api/register',{'account_type':kind,'company':'Court example','email':email,'password':'workspace-password-123','confirm_password':'workspace-password-123'})
  client,csrf=self.login(email)
  with app.connect() as c:return dict(c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()),client,csrf
 def ready_mail(self,user):
  with app.connect() as c:
   r,p=comms.owned(c,user,'mail');p['details']={'address':'managed@example.com','login':'managed@example.com','host':'mail.example.com'};worker.save(c,r,p,'ready')
 def test_signup_encrypted_distinct_credentials_and_account_types(self):
  for kind in ('personal','business'):
   user,client,csrf=self.account(kind,kind+'@example.com')
   with app.connect() as c:
    rows=c.execute('SELECT * FROM communications_accounts WHERE owner=?',(user['id'],)).fetchall();self.assertEqual(len(rows),2)
    secrets=[a.unseal(r['payload']) for r in rows];self.assertNotEqual(secrets[0]['password'],secrets[1]['password'])
    self.assertEqual(secrets[0]['account_type'],'personal' if kind=='personal' else 'organization');self.assertNotIn('workspace-password',rows[0]['payload'])
   result=self.request('/api/communications/status',client=client);self.assertEqual(len(result['accounts']),2);self.assertNotIn('password',json.dumps(result))
 def test_credential_reauthentication_and_owner_isolation(self):
  owner,client,csrf=self.account();other,oc,ot=self.account(email='other@example.com');self.ready_mail(owner)
  for body,who,token in [({'kind':'mail','password':'wrong'},client,csrf),({'kind':'mail','password':'workspace-password-123','owner':owner['id']},oc,ot)]:
   with self.assertRaises(HTTPError):self.request('/api/communications/credentials',body,who,token)
  result=self.request('/api/communications/credentials',{'kind':'mail','password':'workspace-password-123'},client,csrf);self.assertEqual(result['username'],'managed@example.com')
  self.assertTrue(result['password']);self.assertEqual(self.request('/api/communications/status',client=oc)['accounts'][0]['state'],'queued')
 def test_admin_policy_permission_and_revision(self):
  user,client,csrf=self.account()
  with self.assertRaises(HTTPError) as error:self.request('/api/communications/admin',client=client)
  self.assertEqual(error.exception.code,403);root,token=self.login('platform@example.com','platform-password-1234')
  state=self.request('/api/communications/admin',client=root);body={'revision':state['revision'],'values':{'sip_enabled':True,'mail_enabled':False}}
  self.request('/api/communications/admin',body,root,token)
  with self.assertRaises(HTTPError) as error:self.request('/api/communications/admin',body,root,token)
  self.assertEqual(error.exception.code,409)
 def test_outbox_idempotency_validation_and_no_browser_send(self):
  user,client,csrf=self.account();self.ready_mail(user);body={'to':'recipient@example.com','subject':'Hello','text':'Test','request_key':str(uuid.uuid4())}
  first=self.request('/api/communications/send',body,client,csrf);second=self.request('/api/communications/send',body,client,csrf);self.assertEqual(first,second);self.assertEqual(first['state'],'queued')
  for changes in ({'text':'different'},{'to':'x@example.com\r\nBcc:bad@example.com'},{'subject':'Header\nInjection'}):
   with self.assertRaises(HTTPError):self.request('/api/communications/send',dict(body,**changes),client,csrf)
  with app.connect() as c:
   row=c.execute('SELECT * FROM communications_outbox').fetchone();self.assertNotIn('recipient@example.com',row['payload']);self.assertEqual(c.execute('SELECT count(*) FROM communications_outbox').fetchone()[0],1)
 def test_worker_disabled_then_pending_then_ready_no_password_rotation(self):
  user,client,csrf=self.account()
  with patch.object(worker,'sip') as sip,patch.object(worker,'mailbox') as mail:
   worker.run(app);sip.assert_not_called();mail.assert_not_called()
   with app.connect() as c:c.execute('UPDATE communications_policy SET payload=?',(json.dumps({'sip_enabled':True,'mail_enabled':False}),));c.execute('UPDATE communications_accounts SET next_attempt=0')
   sip.return_value=('awaiting_switch',{'login':user['email']});worker.run(app);first=sip.call_args.args[2]['password']
   with app.connect() as c:c.execute('UPDATE communications_accounts SET next_attempt=0')
   sip.return_value=('ready',{'login':user['email']});worker.run(app);self.assertEqual(first,sip.call_args.args[2]['password'])
   with app.connect() as c:self.assertEqual(comms.owned(c,user,'sip')[0]['state'],'ready')
 def test_smtp_uncertainty_never_automatically_retries(self):
  user,client,csrf=self.account();self.ready_mail(user)
  self.request('/api/communications/send',{'to':'x@example.com','subject':'Test','text':'hello','request_key':str(uuid.uuid4())},client,csrf)
  with app.connect() as c:c.execute('UPDATE communications_policy SET payload=?',(json.dumps({'sip_enabled':False,'mail_enabled':True}),))
  with patch.object(worker,'mailbox',return_value=('awaiting_mail',{})),patch.object(worker.smtplib,'SMTP',side_effect=OSError('lost after handoff')) as smtp:
   worker.run(app);worker.run(app);self.assertEqual(smtp.call_count,1)
  with app.connect() as c:self.assertEqual(c.execute('SELECT state FROM communications_outbox').fetchone()[0],'uncertain')
 def test_bridge_validates_reply_and_uses_stable_external_identity(self):
  user,client,csrf=self.account('business')
  with app.connect() as c:
   r,p=comms.owned(c,user,'sip')
   with patch('provider_settings.get',return_value='secret'),patch.object(a,'request_json',return_value={'accountId':'remote','kind':'organization','portal':'https://sip.dobhrap.com/','state':'awaiting_switch'}) as request:
    self.assertEqual(worker.sip(c,r,p,'instance')[0],'awaiting_switch');body=request.call_args.args[1];self.assertEqual(body['role'],'admin');self.assertEqual(body['password'],p['password']);self.assertEqual(body['owner'],user['id'])
   with patch('provider_settings.get',return_value='secret'),patch.object(a,'request_json',return_value={'state':'active'}):
    with self.assertRaises(RuntimeError):worker.sip(c,r,p,'instance')
 def test_mail_address_collision_requires_operator_review(self):
  con=MagicMock();con.execute.return_value.fetchone.side_effect=[{'id':4,'active':1},None,{'address':'existing'}]
  db=MagicMock();db.connect.return_value.__enter__.return_value=con;api=MagicMock();api.permitted_domains.return_value=['example.com']
  with patch.dict('os.environ',{'COMMS_MAIL_DOMAIN':'example.com','COMMS_MAIL_HOST':'mail.example.com','COMMS_MAIL_OPERATOR':'operator'}),patch.object(worker,'trusted_module',side_effect=[api,db]):
   with self.assertRaisesRegex(RuntimeError,'ownership evidence'):worker.mailbox.__wrapped__(None,{'owner':1},{'password':'secret'},str(uuid.uuid4()))
  api.handle.assert_not_called()

 def test_uncommissioned_signup_queues_without_unencrypted_credentials(self):
  with patch.dict('os.environ',{'DOBHRAP_ENCRYPTION_KEY':''}):
   user,client,csrf=self.account()
   state=self.request('/api/communications/status',client=client);self.assertEqual(len(state['accounts']),2)
   with app.connect() as c:self.assertEqual(c.execute('SELECT payload FROM communications_accounts WHERE owner=?',(user['id'],)).fetchone()[0],'')
  worker.run(app)
  with app.connect() as c:self.assertTrue(a.unseal(c.execute('SELECT payload FROM communications_accounts WHERE owner=?',(user['id'],)).fetchone()[0])['password'])
