import os, tempfile, unittest, uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from cryptography.fernet import Fernet
import app, advanced as a, marketplace as market, wallet, tax_services, tax_analyst_billing as billing
import tests.test_tenants as fixtures
from urllib.error import HTTPError

class WalletTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=self.temp.name+'/db'
  self.env=patch.dict(os.environ,{'DOBHRAP_DB_BACKEND':'sqlite','DOBHRAP_ADMIN_PASSWORD':'synthetic-password-123','DOBHRAP_ENCRYPTION_KEY':Fernet.generate_key().decode(),'DOBHRAP_ENABLE_MARKETPLACE':'1'});self.env.start();app.init();self.root={'id':1,'role':'super_admin'};self.user={'id':2,'role':'editor'}
  with app.connect() as c:c.execute("INSERT INTO users(id,email,salt,hash,role,tenant_id) VALUES(2,'synthetic@example.com','x','x','editor',1)")
 def tearDown(self):self.env.stop();app.DB=self.old;self.temp.cleanup()
 def credit(self,amount='10.00',code='USD',key=None,user=None):
  with app.connect() as c:return wallet.credit(c,{'owner':2,'currency':code,'amount':amount,'reason':'Synthetic account credit','request_key':key or str(uuid.uuid4())},user or self.root)
 def buy(self,pid='tax-analyst-session',key=None):
  with app.connect() as c:return market.dispatch('/api/market/checkout','POST',{'gateway':'wallet','product_id':pid,'amount':1,'request_key':key or str(uuid.uuid4())},c,self.user,1)
 def status(self,user=None):
  with app.connect() as c:return wallet.status(c,user or self.user)
 def test_admin_credit_is_audited_idempotent_and_private(self):
  key=str(uuid.uuid4());first=self.credit(key=key);self.assertFalse(first['reused']);self.assertTrue(self.credit(key=key)['reused'])
  self.assertEqual(self.status()['balances'][0]['balance'],1000);self.assertEqual(self.status(self.root)['balances'][0]['balance'],0)
  with app.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM wallet_entries WHERE kind='credit'").fetchone()[0],1);self.assertTrue(c.execute("SELECT 1 FROM audit WHERE action LIKE 'Wallet manual credit %'").fetchone())
  with self.assertRaises(a.ServiceError):self.credit(user=self.user)
  with self.assertRaises(a.ServiceError):self.credit(amount='20',key=key)
 def test_full_balance_payment_uses_server_price_and_grants_analyst_once(self):
  self.credit();key=str(uuid.uuid4());order=self.buy(key=key);self.assertEqual(order['state'],'fulfilled');self.assertTrue(self.buy(key=key)['reused'])
  self.assertEqual(self.status()['balances'][0]['balance'],500)
  with app.connect() as c:self.assertEqual(billing.status(c,1,self.user)['available'],1);self.assertEqual(c.execute('SELECT amount FROM market_orders WHERE id=?',(order['id'],)).fetchone()[0],500)
 def test_currency_matching_and_precision(self):
  with self.assertRaises(a.ServiceError):self.credit(amount='1.001')
  self.credit(code='NGN')
  with self.assertRaises(a.ServiceError) as error:self.buy()
  self.assertEqual(error.exception.status,402);self.assertEqual(self.status()['balances'][0]['balance'],1000)
 def test_concurrent_purchases_do_not_overdraw(self):
  self.credit(amount='5')
  def attempt(_):
   try:return self.buy()['state']=='fulfilled'
   except a.ServiceError:return False
  with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(attempt,range(2)))
  self.assertEqual(sum(result),1);self.assertEqual(self.status()['balances'][0]['balance'],0)
 def test_preparation_plan_fulfillment_and_rollback(self):
  self.credit()
  with app.connect() as c:
   c.execute("INSERT INTO market_products VALUES('prep','Prep','Synthetic','tax_preparation_2025',300,'USD',1)")
   c.execute("INSERT INTO market_products VALUES('plan','Plan','Synthetic','hosting',400,'USD',1)")
   c.execute("INSERT INTO market_plan_terms VALUES('plan',30)")
  prep=self.buy('prep');order=self.buy('plan')
  with app.connect() as c:self.assertTrue(tax_services.paid(c,1,2,2025));self.assertTrue(c.execute('SELECT 1 FROM market_subscriptions WHERE order_id=?',(order['id'],)).fetchone())
  with app.connect() as c:
   market.dispatch('/api/market/service-action','POST',{'order_id':prep['id'],'work_state':'completed'},c,self.root,1)
   self.assertTrue(tax_services.paid(c,1,2,2025))
  self.assertEqual(self.status()['balances'][0]['balance'],300)
  with patch.object(market,'snapshot_terms',side_effect=RuntimeError('Synthetic rollback')):
   with self.assertRaises(RuntimeError):self.buy('prep')
  self.assertEqual(self.status()['balances'][0]['balance'],300)
 def test_fake_wallet_order_without_ledger_does_not_unlock(self):
  from tests.tax_billing_fixture import grant
  oid=grant(owner=2,count=1)[0]
  with app.connect() as c:
   c.execute("UPDATE market_orders SET gateway='wallet',environment='wallet' WHERE id=?",(oid,));c.execute("UPDATE market_services SET environment='wallet' WHERE order_id=?",(oid,))
   self.assertEqual(billing.status(c,1,self.user)['available'],0)
 def test_closed_store_and_readonly_blocked_without_spend(self):
  self.credit()
  with app.connect() as c:c.execute('UPDATE market_store SET open=0')
  with self.assertRaises(a.ServiceError):self.buy()
  self.assertEqual(self.status()['balances'][0]['balance'],1000)
  with app.connect() as c:
   c.execute('UPDATE market_store SET open=1');c.commit()
   with self.assertRaises(a.ServiceError):market.dispatch('/api/market/checkout','POST',{'gateway':'wallet','product_id':'tax-analyst-session','request_key':str(uuid.uuid4())},c,{**self.user,'role':'viewer'},1)

class BalanceFirstTests(WalletTests):
 def auto(self,key=None):
  with app.connect() as c:return market.dispatch('/api/market/checkout','POST',{'gateway':'auto','product_id':'tax-analyst-session','request_key':key or str(uuid.uuid4())},c,self.user,1)
 def test_auto_deducts_and_retry_does_not_double_charge(self):
  self.credit();key=str(uuid.uuid4());first=self.auto(key);self.assertEqual(first['state'],'fulfilled');self.auto(key)
  self.assertEqual(self.status()['balances'][0]['balance'],500)
 def test_shortfall_quote_does_not_deduct(self):
  self.credit('2');quote=self.auto();self.assertEqual((quote['total'],quote['balance'],quote['remaining']),(500,200,300))
  self.assertEqual(self.status()['balances'][0]['balance'],200)
 def test_partial_payment_verified_once(self):
  self.credit('2');key=str(uuid.uuid4());buyer={**self.user,'email':'synthetic@example.com'}
  body={'gateway':'stripe','balance_first':True,'product_id':'tax-analyst-session','request_key':key}
  with patch.object(market,'environment',return_value='live'),patch.object(market,'key',return_value='fixture'),patch.object(market,'base_url',return_value='https://example.com'),patch.object(market,'provider',return_value={'id':'cs_fixture','url':'https://checkout.stripe.com/test'}) as provider:
   with app.connect() as c:order=market.dispatch('/api/market/checkout','POST',body,c,buyer,1)
   self.assertEqual(provider.call_args.args[2]['line_items[0][price_data][unit_amount]'],300)
   with app.connect() as c:market.dispatch('/api/market/checkout','POST',body,c,buyer,1)
   self.assertEqual(provider.call_count,1);self.assertEqual(self.status()['balances'][0]['balance'],0)
   payment={'id':'cs_fixture','client_reference_id':order['id'],'metadata':{'order_id':order['id']},'livemode':True,'payment_status':'paid','amount_total':300,'currency':'usd'}
   with patch.object(market,'provider',return_value={**payment,'amount_total':500}):
    with app.connect() as c:
     with self.assertRaises(a.ServiceError):market.verify(c,order['id'])
   with patch.object(market,'provider',return_value=payment):
    with app.connect() as c:self.assertEqual(market.verify(c,order['id'])['state'],'fulfilled')
    with app.connect() as c:market.verify(c,order['id']);self.assertEqual(billing.status(c,1,buyer)['available'],1)
 def test_uncertain_provider_retains_one_contribution(self):
  self.credit('2');body={'gateway':'stripe','balance_first':True,'product_id':'tax-analyst-session','request_key':str(uuid.uuid4())}
  with patch.object(market,'environment',return_value='live'),patch.object(market,'key',return_value='fixture'),patch.object(market,'base_url',return_value='https://example.com'),patch.object(market,'provider',side_effect=RuntimeError('uncertain')):
   with app.connect() as c:
    with self.assertRaises(a.ServiceError):market.checkout(c,body,self.user,1)
  self.assertEqual(self.status()['balances'][0]['balance'],0)
  with app.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM wallet_entries WHERE kind='purchase_partial'").fetchone()[0],1)

class WalletHttpTests(unittest.TestCase):
 setUp=fixtures.TenantTests.setUp
 tearDown=fixtures.TenantTests.tearDown
 request=fixtures.TenantTests.request
 login=fixtures.TenantTests.login
 register=fixtures.TenantTests.register
 def test_admin_credit_user_balance_and_csrf(self):
  self.register('buyer');buyer,csrf=self.login('buyer@example.com');root,token=self.login('platform@example.com','platform-password-1234')
  with app.connect() as c:uid=c.execute("SELECT id FROM users WHERE email='buyer@example.com'").fetchone()[0]
  payload={'owner':uid,'amount':'5.00','currency':'USD','reason':'Synthetic approved credit','request_key':str(uuid.uuid4())}
  for client,csrf_value in ((buyer,csrf),(root,'')):
   with self.assertRaises(HTTPError) as error:self.request('/api/platform/wallet/credit',payload,client,csrf_value)
   self.assertEqual(error.exception.code,403)
  self.request('/api/platform/wallet/credit',payload,root,token)
  self.assertEqual(self.request('/api/wallet/status',client=buyer)['balances'][0]['balance'],500)
  with self.public.open(self.base+'/wallet.js') as resource:self.assertIn(b'showWallet',resource.read())
