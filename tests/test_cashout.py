import unittest, uuid, json
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
import app, cashout, advanced as a
import tests.test_wallet as fixtures

class CashoutTests(unittest.TestCase):
 setUp=fixtures.WalletTests.setUp
 tearDown=fixtures.WalletTests.tearDown
 credit=fixtures.WalletTests.credit
 buy=fixtures.WalletTests.buy
 status=fixtures.WalletTests.status
 def authorize(self,amount='10',key=None):
  with app.connect() as c:return cashout.authorize(c,{'owner':2,'currency':'USD','amount':amount,'reason':'Synthetic funded balance','request_key':key or str(uuid.uuid4())},self.root)
 def request(self,key=None,user=None,amount='5'):
  with app.connect() as c:return cashout.request(c,{'currency':'USD','amount':amount,'request_key':key or str(uuid.uuid4()),'destination':{'beneficiary':'Synthetic','bank':'Test bank','account':'123456789','routing':'123456','country':'US'}},user or self.user)
 def action(self,rid,action,user=None,**kwargs):
  with app.connect() as c:return cashout.action(c,{'id':rid,'action':action,**kwargs},user or self.root,admin=(user or self.root)['role']=='super_admin')
 def test_store_credit_is_not_automatically_withdrawable(self):
  self.credit()
  with self.assertRaises(a.ServiceError):self.request()
  self.assertEqual(self.status()['balances'][0]['balance'],1000)
 def test_authorizations_replay_and_same_amount_separate_keys(self):
  self.credit();key=str(uuid.uuid4());self.authorize('5',key);self.assertTrue(self.authorize('5',key)['reused']);self.authorize('5')
  with self.assertRaises(a.ServiceError):self.authorize('1')
  with app.connect() as c:self.assertEqual(cashout.status(c,self.user)['funds'][0]['available'],1000)
 def test_hold_cancel_release_once_and_details_encrypted(self):
  self.credit();self.authorize();key=str(uuid.uuid4());r=self.request(key);self.assertTrue(self.request(key)['reused']);self.assertEqual(self.status()['balances'][0]['balance'],500)
  with app.connect() as c:
   self.assertNotIn('123456789',c.execute('SELECT destination FROM cashout_requests').fetchone()[0]);self.assertNotIn('123456789',json.dumps(cashout.status(c,self.user)))
  with self.assertRaises(a.ServiceError):self.action(r['id'],'cancel',{'id':3,'role':'editor'})
  self.action(r['id'],'cancel',self.user)
  with self.assertRaises(a.ServiceError):self.action(r['id'],'cancel',self.user)
  self.assertEqual(self.status()['balances'][0]['balance'],1000)
 def test_approval_payment_record_and_rejection(self):
  self.credit();self.authorize();r=self.request();self.action(r['id'],'approve')
  with self.assertRaises(a.ServiceError):self.action(r['id'],'payment-recorded',reference='external-123')
  result=self.action(r['id'],'payment-recorded',reference='external-123',confirmed_external_payment=True);self.assertFalse(result['bank_transfer_initiated']);self.assertEqual(self.status()['balances'][0]['balance'],500)
  with self.assertRaises(a.ServiceError):self.action(r['id'],'reject')
  r=self.request();self.action(r['id'],'approve');self.action(r['id'],'reject');self.assertEqual(self.status()['balances'][0]['balance'],500)
 def test_purchase_reduces_withdrawable_allocation(self):
  self.credit();self.authorize('8');self.buy()
  with app.connect() as c:self.assertEqual(cashout.status(c,self.user)['funds'][0]['available'],500)
  self.request();self.assertEqual(self.status()['balances'][0]['balance'],0)
 def test_concurrent_requests_do_not_overdraw(self):
  self.credit('5');self.authorize('5')
  def attempt(_):
   try:self.request();return True
   except a.ServiceError:return False
  with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(attempt,range(2))),1)
 def test_purchase_and_hold_compete_for_same_balance(self):
  self.credit('5');self.authorize('5')
  def attempt(action):
   try:(self.buy() if action=='buy' else self.request());return True
   except a.ServiceError:return False
  with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(attempt,['buy','request'])),1)
  self.assertEqual(self.status()['balances'][0]['balance'],0)
 def test_pause_readonly_and_nonadmin(self):
  self.credit();self.authorize()
  with self.assertRaises(a.ServiceError):self.request(user={**self.user,'role':'viewer'})
  with app.connect() as c:
   with self.assertRaises(a.ServiceError):cashout.dispatch('/api/platform/cashout/overview','GET',{},c,self.user)
   c.execute('UPDATE cashout_settings SET enabled=0')
  with self.assertRaises(a.ServiceError):self.request()

class CashoutHttpTests(unittest.TestCase):
 setUp=fixtures.WalletHttpTests.setUp
 tearDown=fixtures.WalletHttpTests.tearDown
 request=fixtures.WalletHttpTests.request
 login=fixtures.WalletHttpTests.login
 register=fixtures.WalletHttpTests.register
 def test_authorization_csrf_and_user_scope(self):
  self.register('buyer');buyer,csrf=self.login('buyer@example.com');root,token=self.login('platform@example.com','platform-password-1234')
  with self.assertRaises(HTTPError) as e:self.request('/api/platform/cashout/overview',client=buyer)
  self.assertEqual(e.exception.code,403)
  with self.assertRaises(HTTPError) as e:self.request('/api/platform/cashout/settings',{'enabled':False},root,'')
  self.assertEqual(e.exception.code,403)
  self.assertEqual(self.request('/api/cashout/status',client=buyer)['requests'],[])
  with self.public.open(self.base+'/cashout.js') as r:self.assertIn(b'showCashout',r.read())
