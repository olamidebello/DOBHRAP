import copy, uuid, unittest
from unittest.mock import patch
import app, ai_services as service, advanced as a
import tests.test_wallet as fixtures

class AIServiceTests(unittest.TestCase):
 setUp=fixtures.WalletTests.setUp
 tearDown=fixtures.WalletTests.tearDown
 credit=fixtures.WalletTests.credit
 status=fixtures.WalletTests.status
 def enable(self):
  p=copy.deepcopy(service.DEFAULT);p.update(enabled=True,rates_verified=True,model='gpt-4.1')
  with app.connect() as c:service.dispatch('/api/ai-service/admin','POST',{'policy':p,'revision':1},c,self.root,1)
 def quote(self):
  with patch.object(service.settings,'get',return_value='synthetic-key'),app.connect() as c:return service.quote(c,{'prompt':'Synthetic test'})
 def request(self,key=None):
  q=self.quote();return dict(prompt='Synthetic test',consent=True,request_key=key or str(uuid.uuid4()),quote_revision=q['revision'],maximum_cents=q['maximum_cents'])
 def call(self,body,provider=None,user=None):
  response={'id':'resp_test','model':'gpt-4.1-2025-04-14','status':'completed','usage':{'input_tokens':100,'output_tokens':10,'input_tokens_details':{'cached_tokens':0}},'output':[{'type':'message','content':[{'type':'output_text','text':'Synthetic answer <script>'}]}]}
  with patch.object(service.settings,'get',return_value='synthetic-key'),patch.object(a,'request_json',return_value=provider or response) as api,app.connect() as c:
   result=service.chat(c,body,user or self.user,1)
   return result,api.call_count
 def test_exact_cost_plus_cached_tokens_and_rounding(self):
  r=service.money({'input_tokens':1000000,'output_tokens':1000000,'input_tokens_details':{'cached_tokens':250000}},service.DEFAULT)
  self.assertEqual(r['provider_cost_usd'],'9.625');self.assertEqual(r['retail_before_rounding_usd'],'12.51250');self.assertEqual(r['charged_cents'],1252)
  with self.assertRaises(a.ServiceError):service.money({'input_tokens':1,'output_tokens':1,'input_tokens_details':{'cached_tokens':2}},service.DEFAULT)
 def test_default_disabled_and_unverified_rates_cannot_enable(self):
  with app.connect() as c:
   with self.assertRaises(a.ServiceError):service.quote(c,{'prompt':'test'})
   p=copy.deepcopy(service.DEFAULT);p.update(enabled=True,model='gpt-4.1')
   with self.assertRaises(a.ServiceError):service.clean({'policy':p})
 def test_success_releases_hold_encrypts_data_and_retry_is_idempotent(self):
  self.enable();self.credit();body=self.request();r,calls=self.call(body)
  self.assertEqual(r['state'],'completed');self.assertEqual(r['charged'],1);self.assertEqual(calls,1)
  self.assertEqual(self.status()['balances'][0]['balance'],999)
  again,calls=self.call(body);self.assertEqual(again['id'],r['id']);self.assertEqual(calls,0)
  with app.connect() as c:
   raw=c.execute('SELECT payload FROM ai_service_requests').fetchone()[0];self.assertNotIn('Synthetic',raw)
   self.assertEqual(c.execute("SELECT count(*) FROM wallet_entries WHERE kind='ai_hold'").fetchone()[0],1)
   own=service.dispatch('/api/ai-service/status','GET',{},c,self.root,1);self.assertEqual(own['requests'],[])
  with self.assertRaises(a.ServiceError):self.call(dict(body,prompt='Changed prompt'))
 def test_balance_stale_quote_and_viewer_block_before_provider(self):
  self.enable();body=self.request()
  for user,b in [(self.user,body),(self.root,dict(body,quote_revision=0)),({'id':2,'role':'viewer'},body)]:
   with patch.object(a,'request_json') as provider:
    with self.assertRaises(a.ServiceError):self.call(b,user=user)
    provider.assert_not_called()
  with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM ai_service_requests').fetchone()[0],0)
 def test_unknown_usage_held_no_retry_and_admin_refund(self):
  self.enable();self.credit();body=self.request();r,calls=self.call(body,{'status':'completed'})
  self.assertEqual(r['state'],'reconcile');balance=self.status()['balances'][0]['balance'];self.assertLess(balance,1000)
  again,calls=self.call(body);self.assertEqual(calls,0);self.assertEqual(again['state'],'reconcile')
  with app.connect() as c:
   with self.assertRaises(a.ServiceError):service.dispatch('/api/ai-service/admin','POST',{'action':'refund','id':r['id'],'reason':'Confirmed no useful billable output'},c,self.user,1)
  with app.connect() as c:service.dispatch('/api/ai-service/admin','POST',{'action':'refund','id':r['id'],'reason':'Confirmed no useful billable output'},c,self.root,1)
  self.assertEqual(self.status()['balances'][0]['balance'],1000)
  again,calls=self.call(body);self.assertEqual(again['state'],'refunded');self.assertEqual(calls,0)
 def test_wallet_release_restores_only_held_withdrawable_allocation(self):
  import cashout
  self.enable();self.credit()
  with app.connect() as c:cashout.authorize(c,{'owner':2,'currency':'USD','amount':'10','reason':'Synthetic funded balance','request_key':str(uuid.uuid4())},self.root)
  r,_=self.call(self.request());self.assertEqual(r['charged'],1)
  with app.connect() as c:self.assertEqual(c.execute("SELECT available FROM cashout_funds WHERE owner=2 AND currency='USD'").fetchone()[0],999)
 def test_quote_does_not_debit_and_policy_conflicts(self):
  self.enable();self.credit();q=self.quote();self.assertGreater(q['maximum_cents'],0);self.assertEqual(self.status()['balances'][0]['balance'],1000)
  with app.connect() as c:
   with self.assertRaises(a.ServiceError):service.dispatch('/api/ai-service/admin','POST',{'policy':dict(service.DEFAULT),'revision':1},c,self.root,1)
