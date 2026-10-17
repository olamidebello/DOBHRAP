import hashlib, time, unittest, uuid
from unittest.mock import patch
import app, advanced as a, coupons, tax_services
import tests.test_marketplace as fixtures

class CouponTests(unittest.TestCase):
 setUp=fixtures.MarketplaceTests.setUp
 tearDown=fixtures.MarketplaceTests.tearDown
 call=fixtures.MarketplaceTests.call
 def coupon(self,**kw):
  body={'label':'Fixture campaign','code':'FIXTURE-COUPON-2026','service_code':'accounting_support','email':'','expires':int(time.time())+3600,'max_uses':1,'per_user':1,'active':True,**kw}
  return self.cp('manage',body,self.admin)
 def cp(self,route,body=None,user=None):
  with app.connect() as c:return coupons.dispatch('/api/coupons/'+route,'GET' if body is None else 'POST',body or {},c,user or self.buyer,self.tid)
 def redeem(self,code='FIXTURE-COUPON-2026',request=None,product=None):return self.cp('redeem',{'code':code,'request_key':request or str(uuid.uuid4()),'product_id':product or self.product})
 def test_superadmin_management_hash_and_disabled(self):
  with self.assertRaises(a.ServiceError):self.cp('manage')
  created=self.coupon();self.assertEqual(created['code'],'FIXTURE-COUPON-2026');listed=self.cp('manage',user=self.admin);self.assertNotIn('code_hash',listed[0]);self.assertNotIn('code',listed[0]);self.assertEqual(listed[0]['hint'],'2026')
  with app.connect() as c:self.assertEqual(c.execute('SELECT code_hash FROM service_coupons').fetchone()[0],hashlib.sha256(created['code'].encode()).hexdigest())
  self.cp('manage',{'action':'toggle','id':created['id'],'active':False},self.admin)
  with self.assertRaises(a.ServiceError):self.redeem()
 def test_redemption_atomic_and_idempotent_no_gateway_charge(self):
  self.coupon();key=str(uuid.uuid4())
  with patch('marketplace.provider') as provider:
   result=self.redeem(request=key);self.assertEqual(result['state'],'fulfilled');self.assertTrue(self.redeem(request=key)['reused']);provider.assert_not_called()
  with self.assertRaises(a.ServiceError):self.redeem()
  with app.connect() as c:
   self.assertEqual(c.execute('SELECT count(*) FROM coupon_redemptions').fetchone()[0],1);self.assertEqual(c.execute('SELECT amount FROM market_orders').fetchone()[0],0);self.assertEqual(c.execute('SELECT status FROM market_services').fetchone()[0],'active')
 def test_restrictions_expiry_and_owner(self):
  created=self.coupon(email='different@example.com')
  with self.assertRaises(a.ServiceError):self.redeem()
  with app.connect() as c:c.execute("UPDATE service_coupons SET email='',service_code='different'")
  with self.assertRaises(a.ServiceError):self.redeem()
  with app.connect() as c:c.execute("UPDATE service_coupons SET service_code='',expires=1")
  with self.assertRaises(a.ServiceError):self.redeem()
 def test_tax_year_unlock_and_suspension(self):
  with app.connect() as c:c.execute("UPDATE market_products SET service_code='tax_preparation_2026' WHERE id=?",(self.product,))
  self.coupon(service_code='tax_preparation_2026');order=self.redeem()
  with app.connect() as c:
   self.assertTrue(tax_services.paid(c,self.tid,self.buyer['id'],2026));self.assertFalse(tax_services.paid(c,self.tid,self.buyer['id'],2025));self.assertFalse(tax_services.paid(c,self.tid,self.admin['id'],2026))
  self.call('service-action',{'order_id':order['id'],'work_state':'suspended'},self.admin)
  with app.connect() as c:self.assertFalse(tax_services.paid(c,self.tid,self.buyer['id'],2026))
  self.call('service-action',{'order_id':order['id'],'work_state':'in_progress'},self.admin)
  with app.connect() as c:self.assertTrue(tax_services.paid(c,self.tid,self.buyer['id'],2026))
 def test_coupon_cannot_bypass_tax_only_product_scope(self):
  self.coupon()
  with app.connect() as c:
   c.execute("UPDATE tenants SET service_mode='tax_only' WHERE id=?",(self.tid,));tenant=c.execute('SELECT * FROM tenants WHERE id=?',(self.tid,)).fetchone()
   with self.assertRaises(a.ServiceError):tax_services.enforce(c,'/api/coupons/redeem','POST',{'product_id':self.product},tenant,self.buyer)
