import unittest
from urllib.error import HTTPError
import app,advanced as a,user_data
import tests.test_tenants as fixtures
class PartnerTests(unittest.TestCase):
 setUp=fixtures.TenantTests.setUp
 tearDown=fixtures.TenantTests.tearDown
 request=fixtures.TenantTests.request
 login=fixtures.TenantTests.login
 register=fixtures.TenantTests.register
 def company(self,name):
  tid=self.register(name);client,csrf=self.login(name+'@example.com')
  self.request('/api/business/profile',{'revision':0,'profile':{'legal_name':name+' Company','naics':'541512','capabilities':'Private profile capability','ein':'123456789','contact_email':'secret@example.com'}},client,csrf)
  return tid,client,csrf
 def call(self,route,body,client,csrf):return self.request('/api/contracting/partners-'+route,body,client,csrf)
 def publish(self,client,csrf,**extra):
  body={'title':'Teaming for federal support','capabilities':'Published network support','seeking':'Staffing partner','naics':'541512','regions':'United States','role':'Teaming partner','state':'published','publish_confirmed':True};body.update(extra)
  return self.call('save',body,client,csrf)
 def test_opt_in_directory_and_closure(self):
  tid,owner,token=self.company('owner');_,viewer,csrf=self.company('viewer')
  with self.assertRaises(HTTPError):self.publish(owner,token,publish_confirmed=False)
  listing=self.publish(owner,token,state='draft')
  self.assertEqual(self.call('directory',{},viewer,csrf)['listings'],[])
  self.publish(owner,token,id=listing['id'])
  data=self.call('directory',{},viewer,csrf);self.assertEqual(len(data['listings']),1)
  rendered=str(data['listings']);self.assertNotIn('secret@example.com',rendered);self.assertNotIn('123456789',rendered);self.assertNotIn('Private profile capability',rendered)
  self.publish(owner,token,id=listing['id'],state='closed',publish_confirmed=False)
  self.assertEqual(self.call('directory',{},viewer,csrf)['listings'],[])
 def test_private_request_acceptance_and_messages(self):
  tid,owner,token=self.company('target');sender_tid,sender,csrf=self.company('sender');_,stranger,foreign=self.company('stranger')
  listing=self.publish(owner,token)
  with self.assertRaises(HTTPError):self.call('request',{'listing_id':listing['id'],'message':'Team with us','confirmed':False},sender,csrf)
  with app.connect() as c:c.execute('INSERT INTO business_opportunities VALUES(?,?,?,?)',(sender_tid,'a'*32,a.seal({'title':'Network bid','url':'https://sam.gov/opp/'+'a'*32+'/view'}),1))
  request=self.call('request',{'listing_id':listing['id'],'message':'Team with us','confirmed':True,'notice_id':'a'*32},sender,csrf);rid=request['id']
  with self.assertRaises(HTTPError):self.call('request',{'listing_id':listing['id'],'message':'Duplicate','confirmed':True},sender,csrf)
  self.assertEqual(self.call('status',{},owner,token)['pending'],1)
  with self.assertRaises(HTTPError):self.call('thread',{'id':rid},stranger,foreign)
  with self.assertRaises(HTTPError):self.call('respond',{'id':rid,'action':'accepted'},sender,csrf)
  with self.assertRaises(HTTPError):self.call('message',{'id':rid,'text':'Not yet accepted'},sender,csrf)
  self.call('respond',{'id':rid,'action':'accepted'},owner,token)
  self.call('message',{'id':rid,'text':'Discuss division of work'},sender,csrf)
  thread=self.call('thread',{'id':rid},owner,token);self.assertEqual(thread['messages'][0]['text'],'Discuss division of work');self.assertEqual(thread['notice']['title'],'Network bid')
  self.call('respond',{'id':rid,'action':'closed'},sender,csrf)
  with self.assertRaises(HTTPError):self.call('message',{'id':rid,'text':'Closed'},owner,token)
 def test_listing_owner_and_same_workspace_guards(self):
  tid,owner,token=self.company('owner');_,other,csrf=self.company('other');listing=self.publish(owner,token)
  with self.assertRaises(HTTPError):self.publish(other,csrf,id=listing['id'])
  with self.assertRaises(HTTPError):self.call('request',{'listing_id':listing['id'],'message':'Self request','confirmed':True},owner,token)
  with app.connect() as c:c.execute("UPDATE users SET role='viewer' WHERE tenant_id=?",(tid,))
  with self.assertRaises(HTTPError):self.publish(owner,token)
 def test_deletion_removes_shared_private_thread_and_listing(self):
  tid,owner,token=self.company('target');_,sender,csrf=self.company('sender');listing=self.publish(owner,token)
  rid=self.call('request',{'listing_id':listing['id'],'message':'Team with us','confirmed':True},sender,csrf)['id']
  self.call('respond',{'id':rid,'action':'accepted'},owner,token);self.call('message',{'id':rid,'text':'Private discussion'},sender,csrf)
  with app.connect() as c:
   uid=c.execute('SELECT id FROM users WHERE tenant_id=?',(tid,)).fetchone()[0];user_data.purge(c,uid)
   self.assertEqual(c.execute('SELECT count(*) FROM contract_partner_requests').fetchone()[0],0);self.assertEqual(c.execute('SELECT count(*) FROM contract_partner_messages').fetchone()[0],0);self.assertEqual(c.execute('SELECT count(*) FROM contract_partner_listings').fetchone()[0],0)
