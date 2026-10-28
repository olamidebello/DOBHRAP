import unittest,json,uuid
from unittest.mock import patch
from urllib.error import HTTPError
import app,advanced as a,business_contracts as business
import tests.test_tenants as fixtures
from tests.contract_source_fixtures import seed_review
class BusinessContractsTests(unittest.TestCase):
 setUp=fixtures.TenantTests.setUp
 tearDown=fixtures.TenantTests.tearDown
 request=fixtures.TenantTests.request
 login=fixtures.TenantTests.login
 register=fixtures.TenantTests.register
 def account(self):
  tid=self.register('contracts');client,csrf=self.login('contracts@example.com');return tid,client,csrf
 def test_profile_encrypts_ein_and_isolates_workspaces(self):
  tid,client,csrf=self.account();p={'legal_name':'Contract business','ein':'12-3456789','cage':'A1B2C','uei':'ABC123DEF456','naics':'541512','contact_email':'contact@example.com','capabilities':'Network support'}
  r=self.request('/api/business/profile',{'profile':p,'revision':0},client,csrf);self.assertEqual(r['profile']['ein'],'***-**6789');self.assertEqual(r['revision'],1)
  with app.connect() as c:self.assertNotIn('123456789',c.execute('SELECT payload FROM business_profiles WHERE tenant_id=?',(tid,)).fetchone()[0])
  self.assertEqual(self.request('/api/business/profile',client=self.login('platform@example.com','platform-password-1234')[0])['profile'],{'ein':''})
  with self.assertRaises(HTTPError) as error:self.request('/api/business/profile',{'profile':p,'revision':0},client,csrf)
  self.assertEqual(error.exception.code,409)
  r=self.request('/api/business/profile',{'profile':dict(p,ein=''),'revision':1},client,csrf);self.assertEqual(r['profile']['ein'],'***-**6789')
 def test_admin_policy_permissions_and_enable_requires_key(self):
  tid,client,csrf=self.account()
  with self.assertRaises(HTTPError) as e:self.request('/api/business/sam-admin',client=client)
  self.assertEqual(e.exception.code,403)
  root,token=self.login('platform@example.com','platform-password-1234')
  with patch.object(business.settings,'get',return_value='key'):
   r=self.request('/api/business/sam-admin',{'revision':1,'enabled':True,'daily_limit':5},root,token);self.assertEqual(r['daily_limit'],5);self.assertTrue(r['enabled']);self.assertNotIn('key',json.dumps(r['usage']))
 def test_search_uses_fixed_api_filters_and_redacts_key_in_snapshots(self):
  tid,client,csrf=self.account();row={'noticeId':'a'*32,'title':'Network support','naicsCode':'541512','responseDeadLine':'2026-12-01','description':'https://bad.example/?api_key=private'}
  with app.connect() as c:c.execute('UPDATE business_sam_policy SET enabled=1,daily_limit=1')
  with patch.object(business.settings,'get',return_value='private-key'),patch.object(a,'request_json',return_value={'opportunitiesData':[row],'totalRecords':1}) as provider:
   r=self.request('/api/business/opportunities',{'naics':'541512'},client,csrf);self.assertEqual(r['opportunities'][0]['url'],'https://sam.gov/opp/'+'a'*32+'/view');self.assertNotIn('private',json.dumps(r));url=provider.call_args.args[0];self.assertTrue(url.startswith('https://api.sam.gov/opportunities/v2/search?'));self.assertIn('ncode=541512',url)
   with app.connect() as c:c.execute('UPDATE business_searches SET updated=0')
   with self.assertRaises(HTTPError) as error:self.request('/api/business/opportunities',{'naics':'541512'},client,csrf)
   self.assertEqual(error.exception.code,429);self.assertEqual(provider.call_count,1)
 def test_proposals_use_owned_sources_and_redacted_ai_prompt(self):
  tid,client,csrf=self.account()
  self.request('/api/business/profile',{'revision':0,'profile':{'legal_name':'Example','ein':'123456789','contact_email':'secret@example.com','capabilities':'Networking'}},client,csrf)
  with app.connect() as c:c.execute('INSERT INTO business_opportunities VALUES(?,?,?,?)',(tid,'a'*32,a.seal({'notice_id':'a'*32,'title':'Network project','url':'https://sam.gov/opp/'+'a'*32+'/view'}),0))
  with app.connect() as c:seed_review(c,tid,c.execute("SELECT id FROM users WHERE email='contracts@example.com'").fetchone()[0])
  r=self.request('/api/business/proposal-create',{'notice_id':'a'*32},client,csrf);prompt=self.request('/api/business/proposal-prompt',{'id':r['id'],'requirements':'Deliver support'},client,csrf)['prompt'];self.assertNotIn('123456789',prompt);self.assertNotIn('secret@example.com',prompt);self.assertIn('Do not invent',prompt)
  root,token=self.login('platform@example.com','platform-password-1234')
  with self.assertRaises(HTTPError):self.request('/api/business/proposal-save',{'id':r['id'],'revision':1,'text':'wrong tenant'},root,token)
  self.request('/api/business/proposal-save',{'id':r['id'],'revision':1,'text':'Reviewed draft','reviewed':True},client,csrf)
  with self.assertRaises(HTTPError) as e:self.request('/api/business/proposal-save',{'id':r['id'],'revision':1,'text':'stale'},client,csrf)
  self.assertEqual(e.exception.code,409)
  self.request('/api/business/proposal-delete',{'id':r['id']},client,csrf);self.assertEqual(self.request('/api/business/proposals',client=client)['proposals'],[])
