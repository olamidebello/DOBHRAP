import os
import tempfile
import unittest
from datetime import date,timedelta
from unittest.mock import patch
from cryptography.fernet import Fernet
import app
import advanced as a
import international as i

class InternationalTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=self.temp.name+'/db.sqlite'
  self.env=patch.dict(os.environ,{'DOBHRAP_ADMIN_PASSWORD':'test-password-123456','DOBHRAP_ENCRYPTION_KEY':Fernet.generate_key().decode()});self.env.start();app.init()
  self.user={'id':1,'role':'admin'};self.root={'id':1,'role':'super_admin'}
 def tearDown(self):self.env.stop();app.DB=self.old;self.temp.cleanup()
 def call(self,route,body=None,user=None):
  with app.connect() as c:return i.dispatch('/api/intl/'+route,'GET' if body is None else 'POST',body or {},c,user or self.user)
 def test_catalog_rtl_currency_precision_and_seed_lengths(self):
  cat=i.catalogs();self.assertGreater(len(cat['locales']),1000);self.assertGreater(len(cat['currencies']),250)
  currencies={c['id']:c for c in cat['currencies']};self.assertEqual(currencies['JPY']['digits'],0);self.assertEqual(currencies['KWD']['digits'],3)
  self.assertTrue(next(l for l in cat['locales'] if l['id']=='ar-EG')['direction']=='rtl')
  self.assertTrue(all(len(x)==len(i.PHRASES) for x in i.SEEDS.values()))
 def test_preferences_scoped_and_validated(self):
  pref={'locale':'ar-EG','currency':'NGN','timezone':'Africa/Lagos'}
  self.assertEqual(self.call('preferences',pref),pref)
  self.assertEqual(self.call('preferences',user={'id':2,'role':'viewer'})['locale'],'en-US')
  for changes in ({'locale':'invented'},{'currency':'ZZZ'},{'timezone':'Bad/Zone'}):
   with self.assertRaises(a.ServiceError):self.call('preferences',{**pref,**changes})
 def test_formats_and_english_fallback(self):
  result=self.call('format',{'amount':'1234','currency':'JPY','locale':'en-US'});self.assertNotIn('.00',result['formatted'])
  self.assertIn('1.234',self.call('format',{'amount':'1.234','currency':'KWD','locale':'en-US'})['formatted'])
  with self.assertRaises(a.ServiceError):self.call('format',{'amount':'NaN'})
  self.call('preferences',{'locale':'ar-EG','currency':'USD','timezone':'UTC'})
  self.assertEqual(self.call('bundle')['translations']['Customers'],'العملاء')
  self.call('preferences',{'locale':'ja-JP','currency':'JPY','timezone':'Asia/Tokyo'})
  self.assertNotIn('Customers',self.call('bundle')['translations'])
 def test_admin_translation_update_plain_text_and_delete(self):
  with self.assertRaises(a.ServiceError):self.call('translations',{'locale':'ja-JP','entries':{'Customers':'顧客'}})
  self.call('translations',{'locale':'ja-JP','entries':{'Customers':'顧客'}},self.root)
  self.call('preferences',{'locale':'ja-JP','currency':'JPY','timezone':'UTC'})
  self.assertEqual(self.call('bundle')['translations']['Customers'],'顧客')
  with self.assertRaises(a.ServiceError):self.call('translations',{'locale':'ja-JP','entries':{'Customers':'<script>'}},self.root)
  self.call('translations',{'locale':'ja-JP','entries':{'Customers':''}},self.root)
  self.assertNotIn('Customers',self.call('bundle')['translations'])
 def test_reference_rates_dated_and_never_relabel_ledger(self):
  with app.connect() as c:self.assertEqual(i.convert(c,1234,'EUR')['currency'],'USD')
  values={'currency':'EUR','per_usd':'0.9','as_of':date.today().isoformat(),'source':'Operator reference fixture'}
  with self.assertRaises(a.ServiceError):self.call('rates',values)
  self.call('rates',values,self.root)
  with app.connect() as c:
   estimate=i.convert(c,10000,'EUR');self.assertEqual(estimate['amount'],'90.0');self.assertTrue(estimate['converted'])
  self.call('rates',{**values,'as_of':(date.today()-timedelta(days=8)).isoformat()},self.root)
  with app.connect() as c:self.assertEqual(i.convert(c,10000,'EUR')['currency'],'USD')
  with self.assertRaises(a.ServiceError):self.call('rates',{**values,'per_usd':'-1'},self.root)
  with self.assertRaises(a.ServiceError):self.call('rates',{**values,'as_of':(date.today()+timedelta(days=1)).isoformat()},self.root)
