import io,json,socket,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
import app,advanced as a,contract_details as d
import tests.test_tenants as fixtures
class DocumentTests(unittest.TestCase):
 def test_text_and_office_extraction(self):
  result=d.extract(b'<h1>Scope</h1><script>evil()</script><p>Support</p>','notice.html','text/html')
  self.assertIn('Support',result['text']);self.assertNotIn('evil',result['text'])
  buff=io.BytesIO()
  with zipfile.ZipFile(buff,'w') as z:z.writestr('word/document.xml','<document><p>Provide support</p></document>')
  result=d.extract(buff.getvalue(),'scope.docx','application/octet-stream');self.assertIn('Provide support',result['text'])
 def test_download_rejects_private_and_unapproved_hosts(self):
  for url in ('http://sam.gov/a','https://evil.example/a','https://sam.gov:444/a','https://user:pass@sam.gov/a'):
   with self.assertRaises(ValueError):d.allowed(url)
  with patch.object(socket,'getaddrinfo',return_value=[(None,None,None,None,('127.0.0.1',443))]):
   with self.assertRaises(ValueError):d.fetch('https://sam.gov/file')
 def test_unsupported_file_fails_explicitly(self):
  with self.assertRaises(ValueError):d.extract(b'unsupported','file.exe','application/octet-stream')
class DetailsTests(unittest.TestCase):
 setUp=fixtures.TenantTests.setUp
 tearDown=fixtures.TenantTests.tearDown
 request=fixtures.TenantTests.request
 login=fixtures.TenantTests.login
 register=fixtures.TenantTests.register
 def account(self):
  tid=self.register('details');client,csrf=self.login('details@example.com')
  with app.connect() as c:
   user=dict(c.execute("SELECT * FROM users WHERE email='details@example.com'").fetchone())
   c.execute('INSERT INTO business_opportunities VALUES(?,?,?,?)',(tid,'a'*32,a.seal({'notice_id':'a'*32,'title':'Support','url':'https://sam.gov/opp/'+'a'*32+'/view'}),0))
  return tid,user,client,csrf
 def test_queued_details_and_cross_tenant_denial(self):
  tid,user,client,csrf=self.account()
  r=self.request('/api/contracting/details',{'notice_id':'a'*32},client,csrf);self.assertEqual(r['state'],'queued')
  root,token=self.login('platform@example.com','platform-password-1234')
  with self.assertRaises(HTTPError):self.request('/api/contracting/details',{'notice_id':'a'*32},root,token)
 def test_report_quote_saved_and_used_by_draft(self):
  tid,user,client,csrf=self.account()
  data={'notice':{'title':'Support','noticeId':'a'*32},'description':'Provide network support','attachments':[{'name':'scope.txt','text':'Staff coverage required','complete':True}],'warnings':[]}
  with app.connect() as c:
   c.execute('INSERT INTO contracting_details VALUES(?,?,?,?,?)',(tid,'a'*32,'ready',a.seal(data),1))
   c.execute('INSERT INTO business_profiles VALUES(?,?,?,?)',(tid,1,a.seal({'legal_name':'Example','ein':'secret-ein','contact_email':'private@example.com','capabilities':'Network support'}),1))
   with patch.object(d.ai_services,'quote',return_value={'maximum_cents':2,'revision':1}) as quote:
    q=d.dispatch('details-quote',{'notice_id':'a'*32},c,user,tid)
    for call in quote.call_args_list:self.assertNotIn('secret-ein',call.args[1]['prompt']);self.assertNotIn('private@example.com',call.args[1]['prompt'])
   with self.assertRaises(a.ServiceError):d.dispatch('details-draft',{'notice_id':'a'*32},c,user,tid)
   with patch.object(d.ai_services,'chat',return_value={'state':'completed','id':'test','answer':'Recommended verified staffing plan [REQUIRED]' }):
    for i in range(q['segments']):d.dispatch('details-analyze',{'notice_id':'a'*32,'fingerprint':q['fingerprint'],'segment':i},c,user,tid)
   result=d.dispatch('details-draft',{'notice_id':'a'*32},c,user,tid)
   draft=a.unseal(c.execute('SELECT payload FROM business_proposals WHERE id=?',(result['id'],)).fetchone()[0]);self.assertIn('Recommended verified staffing',draft['text']);self.assertEqual(draft['status'],'draft')
   with self.assertRaises(a.ServiceError):d.dispatch('details-analyze',{'notice_id':'a'*32,'fingerprint':'stale','segment':0},c,user,tid)
 def test_worker_handles_attachment_failure_without_claiming_completeness(self):
  tid,user,client,csrf=self.account();self.request('/api/contracting/details',{'notice_id':'a'*32},client,csrf)
  with app.connect() as c:c.execute('UPDATE business_sam_policy SET enabled=1')
  raw=json.dumps({'opportunitiesData':[{'noticeId':'a'*32,'title':'Support','resourceLinks':['https://sam.gov/test.exe']}]}).encode()
  with patch.object(d.settings,'get',return_value='fake'),patch.object(d,'fetch',side_effect=[(raw,'application/json',''),ValueError('unavailable')]):d.process(app)
  r=self.request('/api/contracting/details',{'notice_id':'a'*32},client,csrf);self.assertEqual(r['state'],'ready');self.assertFalse(r['coverage_complete']);self.assertTrue(r['attachments'][0]['notes'])
