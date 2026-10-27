import json,time,uuid
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import app,advanced as a,business_contracts as business,contracting
import tests.test_tenants as fixtures

class ContractingTests(unittest.TestCase):
 setUp=fixtures.TenantTests.setUp
 tearDown=fixtures.TenantTests.tearDown
 request=fixtures.TenantTests.request
 login=fixtures.TenantTests.login
 register=fixtures.TenantTests.register
 def account(self):
  tid=self.register('bids');client,csrf=self.login('bids@example.com')
  with app.connect() as c:
   user=dict(c.execute("SELECT * FROM users WHERE email='bids@example.com'").fetchone())
   c.execute('INSERT INTO business_opportunities VALUES(?,?,?,?)',(tid,'a'*32,a.seal({'notice_id':'a'*32,'title':'Network support','url':'https://sam.gov/opp/'+'a'*32+'/view'}),0))
  return tid,user,client,csrf
 def test_watch_owner_and_workspace_isolation(self):
  tid,user,client,csrf=self.account()
  self.request('/api/contracting/watch',{'enabled':True,'filters':{'naics':'541512'}},client,csrf)
  r=self.request('/api/contracting/status',client=client);self.assertTrue(r['watch']['enabled'])
  root,_=self.login('platform@example.com','platform-password-1234')
  self.assertFalse(self.request('/api/contracting/status',client=root)['watch']['enabled'])
  with self.assertRaises(HTTPError):self.request('/api/contracting/watch',{'enabled':True,'filters':{'url':'https://evil.example'}},client,csrf)
 def test_worker_deduplicates_alerts_and_respects_opt_out(self):
  tid,user,client,csrf=self.account()
  self.request('/api/contracting/watch',{'enabled':True,'filters':{'naics':'541512'}},client,csrf)
  opp={'notice_id':'a'*32,'title':'Support','url':'https://sam.gov/opp/'+'a'*32+'/view'}
  with patch.object(business,'search',return_value={'opportunities':[opp]}) as search:
   contracting.process(app);self.assertEqual(search.call_count,1)
   contracting.process(app);self.assertEqual(search.call_count,1)
   with app.connect() as c:c.execute('UPDATE contracting_watches SET last_attempt=0')
   contracting.process(app)
   self.assertEqual(len(self.request('/api/contracting/status',client=client)['alerts']),1)
   self.request('/api/contracting/watch',{'enabled':False,'filters':{}},client,csrf)
   with app.connect() as c:c.execute('UPDATE contracting_watches SET last_attempt=0')
   contracting.process(app);self.assertEqual(search.call_count,2)
 def test_approval_and_submission_require_exact_reviewed_draft(self):
  tid,user,client,csrf=self.account()
  r=self.request('/api/business/proposal-create',{'notice_id':'a'*32},client,csrf)
  with self.assertRaises(HTTPError):self.request('/api/contracting/submission',{'id':r['id'],'revision':1},client,csrf)
  self.request('/api/business/proposal-save',{'id':r['id'],'revision':1,'text':'Verified proposed approach, staffing and pricing','reviewed':True},client,csrf)
  self.request('/api/contracting/approve',{'id':r['id'],'revision':2,'confirmed':True},client,csrf)
  h=self.request('/api/contracting/submission',{'id':r['id'],'revision':2},client,csrf);self.assertTrue(h['url'].startswith('https://sam.gov/opp/'))
  self.request('/api/business/proposal-save',{'id':r['id'],'revision':2,'text':'Changed offer','reviewed':True},client,csrf)
  with self.assertRaises(HTTPError) as error:self.request('/api/contracting/submission',{'id':r['id'],'revision':3},client,csrf)
  self.assertEqual(error.exception.code,409)
 def test_ai_direct_draft_uses_redacted_profile_and_preserves_owner(self):
  tid,user,client,csrf=self.account()
  self.request('/api/business/profile',{'profile':{'legal_name':'Example','naics':'541512','capabilities':'Support','ein':'123456789','contact_email':'private@example.com'},'revision':0},client,csrf)
  r=self.request('/api/business/proposal-create',{'notice_id':'a'*32},client,csrf)
  with app.connect() as c:
   body={'id':r['id'],'revision':1,'requirements':'Support contract','mode':'full','consent':True}
   body['prompt_digest']=contracting.digest(contracting.prompt(c,tid,body,user)[2])
   with patch.object(contracting.ai_services,'chat',return_value={'state':'completed','id':'synthetic','answer':'Proposed support approach'}) as ai:
    result=contracting.dispatch('/api/contracting/generate','POST',body,c,user,tid)
    prompt=ai.call_args.args[1]['prompt'];self.assertNotIn('123456789',prompt);self.assertNotIn('private@example.com',prompt);self.assertTrue(result['saved'])
   c.commit()
  proposals=self.request('/api/business/proposals',client=client)['proposals'];self.assertEqual(proposals[0]['text'],'Proposed support approach');self.assertEqual(proposals[0]['status'],'draft')
 def test_documented_sam_filters_and_misspelled_deadline_field(self):
  tid,user,client,csrf=self.account()
  with app.connect() as c:c.execute('UPDATE business_sam_policy SET enabled=1')
  result={'opportunitiesData':[{'noticeId':'b'*32,'title':'Network support','reponseDeadLine':'2026-12-01'}],'totalRecords':1}
  with patch.object(business.settings,'get',return_value='synthetic-secret'),patch.object(a,'request_json',return_value=result) as api:
   r=self.request('/api/business/opportunities',{'organization':'Navy','state':'TX','psc':'D302','due_from':'2026-11-01','due_to':'2026-12-01','notice_type':'o'},client,csrf)
   url=api.call_args.args[0];self.assertIn('organizationName=Navy',url);self.assertIn('rdlfrom=',url);self.assertIn('ptype=o',url)
   self.assertEqual(r['opportunities'][0]['responseDeadLine'],'2026-12-01')
