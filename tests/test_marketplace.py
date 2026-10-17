import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch
import app
import advanced as a
import marketplace as m


class MarketplaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old_db=app.DB;app.DB=self.temp.name+'/catalog.db'
        self.env=patch.dict(os.environ,{'DOBHRAP_ADMIN_PASSWORD':'testing-password-1234','DOBHRAP_ENABLE_MARKETPLACE':'1','PAYMENTS_ENV':'test','DOBHRAP_ENABLE_LIVE_PAYMENTS':'0','STRIPE_SECRET_KEY':'sk_test_fixture','STRIPE_WEBHOOK_SECRET':'whsec_fixture','PAYSTACK_SECRET_KEY':'sk_test_fixture','MARKETPLACE_PUBLIC_URL':'https://olamideolatayobello.com'})
        self.env.start();app.init()
        with app.connect() as c:
            self.tid=app.register_workspace(c,{'company':'Buyer','email':'buyer@example.com','password':'buyer-password-1234','confirm_password':'buyer-password-1234'})['tenant_id']
        self.admin={'id':1,'role':'super_admin','email':'platform@example.com'}
        self.buyer={'id':2,'role':'admin','email':'buyer@example.com'}
        self.product=self.call('products',{'name':'Accounting support','description':'One-time support service','service_code':'accounting_support','amount':2500,'currency':'USD','active':True},self.admin)['id']
    def tearDown(self):
        self.env.stop();app.DB=self.old_db;self.temp.cleanup()
    def call(self,route,body=None,user=None,tid=None):
        with app.connect() as c:
            return m.dispatch('/api/market/'+route,'GET' if body is None else 'POST',body or {},c,user or self.buyer,tid or self.tid)
    def purchase(self,gateway='stripe',request_key=None):
        return self.call('checkout',{'product_id':self.product,'gateway':gateway,'request_key':request_key or str(uuid.uuid4()),'amount':1})
    def paid(self,oid,**overrides):
        return {'id':'cs_test_fixture','payment_status':'paid','amount_total':2500,'currency':'usd','client_reference_id':oid,'metadata':{'order_id':oid},'livemode':False,**overrides}
    def test_checkout_server_price_nonce_and_no_redirect_fulfillment(self):
        request_key=str(uuid.uuid4())
        with patch.object(m,'provider',return_value={'id':'cs_test_fixture','url':'https://checkout.stripe.com/c/test'}) as provider:
            first=self.purchase(request_key=request_key);second=self.purchase(request_key=request_key)
            self.assertEqual(first,second);self.assertEqual(provider.call_count,1)
            self.assertEqual(provider.call_args.args[2]['line_items[0][price_data][unit_amount]'],2500)
            self.assertEqual(provider.call_args.kwargs['idempotency'],first['id'])
        self.assertEqual(self.call('services'),[])
        with patch.object(m,'provider',return_value=self.paid(first['id'],payment_status='unpaid')):
            self.assertEqual(self.call('verify',{'id':first['id']})['state'],'pending')
        self.assertEqual(self.call('services'),[])
    def test_payment_verification_exactly_once_and_isolation(self):
        with patch.object(m,'provider',return_value={'id':'cs_test_fixture','url':'https://checkout.stripe.com/c/test'}):order=self.purchase()
        for changes in ({'amount_total':1},{'currency':'ngn'},{'client_reference_id':'wrong'},{'livemode':True}):
            with patch.object(m,'provider',return_value=self.paid(order['id'],**changes)),self.assertRaises(a.ServiceError):self.call('verify',{'id':order['id']})
        self.assertEqual(self.call('services'),[])
        with self.assertRaises(a.ServiceError):self.call('verify',{'id':order['id']},tid=999)
        with patch.object(m,'provider',return_value=self.paid(order['id'])) as provider:
            self.assertEqual(self.call('verify',{'id':order['id']})['state'],'test_fulfilled')
            self.call('verify',{'id':order['id']});self.assertEqual(provider.call_count,1)
        self.assertEqual(self.call('services')[0]['status'],'test_active')
        self.assertEqual(self.call('services',tid=999),[])
        self.assertEqual(len(self.call('services')),1)
        with self.assertRaises(a.ServiceError):self.call('products',{'action':'archive','id':self.product})
        with self.assertRaises(a.ServiceError):self.call('checkout',{'product_id':self.product,'gateway':'stripe','request_key':str(uuid.uuid4())},user={'id':3,'role':'viewer'})
    def test_stripe_signed_raw_webhook_replay_and_worker(self):
        with patch.object(m,'provider',return_value={'id':'cs_test_fixture','url':'https://checkout.stripe.com/c/test'}):order=self.purchase()
        raw=json.dumps({'id':'evt_fixture','type':'checkout.session.completed','livemode':False,'data':{'object':self.paid(order['id'])}}).encode()
        stamp=str(int(time.time()));signature=hmac.new(b'whsec_fixture',stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest();headers={'Stripe-Signature':'t='+stamp+',v1='+signature}
        with app.connect() as c:
            with self.assertRaises(a.ServiceError):m.webhook(c,'stripe',raw,{})
            with self.assertRaises(a.ServiceError):m.webhook(c,'stripe',raw+b' ',headers)
            m.webhook(c,'stripe',raw,headers);m.webhook(c,'stripe',raw,headers)
            self.assertEqual(c.execute('SELECT count(*) FROM market_events').fetchone()[0],1)
        self.assertEqual(self.call('services'),[])
        with patch.object(m,'provider',return_value=self.paid(order['id'])):m.run_all();m.run_all()
        self.assertEqual(len(self.call('services')),1)
    def test_paystack_reference_amount_signature_and_confirmation(self):
        self.product=self.call('products',{'name':'Office setup','description':'One-time onboarding','service_code':'office_setup','amount':50000,'currency':'NGN','active':True},self.admin)['id']
        with patch.object(m,'provider',side_effect=lambda gateway,path,payload,**kwargs:{'status':True,'data':{'reference':payload['reference'],'authorization_url':'https://checkout.paystack.com/test'}}):order=self.purchase('paystack')
        raw=json.dumps({'event':'charge.success','data':{'reference':order['id']}}).encode();signature=hmac.new(b'sk_test_fixture',raw,hashlib.sha512).hexdigest()
        with app.connect() as c:m.webhook(c,'paystack',raw,{'x-paystack-signature':signature})
        verified={'status':True,'data':{'reference':order['id'],'status':'success','amount':50000,'currency':'NGN','domain':'test'}}
        with patch.object(m,'provider',return_value=verified):m.run_all()
        self.assertEqual(self.call('orders')[0]['state'],'test_fulfilled')
    def test_suspended_tenant_and_network_failure_do_not_activate(self):
        with patch.object(m,'provider',return_value={'id':'cs_test_fixture','url':'https://checkout.stripe.com/c/test'}):order=self.purchase()
        with app.connect() as c:c.execute("UPDATE tenants SET status='suspended' WHERE id=?",(self.tid,))
        with patch.object(m,'provider',return_value=self.paid(order['id'])),self.assertRaises(a.ServiceError):self.call('verify',{'id':order['id']})
        with app.connect() as c:c.execute('UPDATE market_orders SET next_check=0')
        with patch.object(m,'provider',side_effect=a.ServiceError('secret diagnostic')):m.run_all()
        self.assertEqual(self.call('services'),[]);self.assertNotIn('secret diagnostic',self.call('orders')[0]['error'])
    def test_live_disabled_and_bad_checkout_host(self):
        with patch.dict(os.environ,{'PAYMENTS_ENV':'live','STRIPE_SECRET_KEY':'sk_live_fixture'}),self.assertRaises(a.ServiceError):self.purchase()
        with self.assertRaises(a.ServiceError):m.checkout_url('https://checkout.stripe.com.evil.test/path','stripe')
        with patch.object(m,'provider',side_effect=a.ServiceError('private-key')):
            with self.assertRaises(a.ServiceError):self.purchase()
        self.assertNotIn('private-key',self.call('orders')[0]['error'])
