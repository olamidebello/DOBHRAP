import base64
import json
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch
from cryptography.fernet import Fernet
import app
import advanced as a
import tax_preparation as t
import provider_settings as settings

class TaxPreparationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=self.temp.name+'/db.sqlite'
  self.env=patch.dict(os.environ,{'DOBHRAP_ADMIN_PASSWORD':'test-password-123456','DOBHRAP_ENCRYPTION_KEY':Fernet.generate_key().decode(),'DOBHRAP_ENABLE_TAX_AI':'0'});self.env.start();app.init();self.user={'id':1,'role':'admin'}
 def tearDown(self):self.env.stop();app.DB=self.old;self.temp.cleanup()
 def call(self,route,body=None,user=None):
  with app.connect() as c:return t.dispatch('/api/tax-prep/'+route,'GET' if body is None else 'POST',body or {},c,user or self.user)
 def create(self):return self.call('create',{})
 def save(self,draft,data,**opts):return self.call('save',{'id':draft['id'],'revision':draft['revision'],'data':data,'completed':draft['completed'],**opts})
 def test_private_owner_encryption_mask_and_conflict(self):
  draft=self.create();data=draft['data'];data['personal']={'first_name':'Fixture','last_name':'Person','tax_id':'111-22-3333','birth_date':'1990-01-01'}
  saved=self.save(draft,data);self.assertEqual(saved['data']['personal']['tax_id'],'***-**-3333')
  with app.connect() as c:
   raw=c.execute('SELECT payload FROM tax_drafts').fetchone()[0];self.assertNotIn('111223333',raw);self.assertNotIn('Fixture',raw)
  with self.assertRaises(a.ServiceError):self.call('open',{'id':draft['id']},user={'id':2,'role':'super_admin'})
  with self.assertRaises(a.ServiceError):self.save(draft,data)
  self.save(saved,saved['data'])
 def test_dependent_masks_survive_row_delete_and_reordering(self):
  d=self.create();ids=[str(uuid.uuid4()),str(uuid.uuid4())];data=d['data']
  data['dependents']=[{'_row_id':ids[0],'name':'First','tax_id':'111223333'},{'_row_id':ids[1],'name':'Second','tax_id':'222334444'}]
  d=self.save(d,data);d['data']['dependents']=d['data']['dependents'][1:];d=self.save(d,d['data'])
  self.assertEqual(d['data']['dependents'][0]['tax_id'],'***-**-4444')
  with app.connect() as c:self.assertEqual(a.unseal(c.execute('SELECT payload FROM tax_drafts').fetchone()[0])['data']['dependents'][0]['tax_id'],'222334444')
 def test_validation_and_no_false_filing_status(self):
  d=self.create()
  for section in ({'income':[{'amount':'NaN'}]},{'personal':{'tax_id':'123'}},{'household':{'filing_status':'invented'}},{'dependents':[{'months':'13'}]}):
   with self.assertRaises(a.ServiceError):self.save(d,{**d['data'],**section})
  with self.assertRaises(a.ServiceError):self.save(d,d['data'],reviewed=True)
  self.assertFalse(d['review']['filing_ready'])
 def test_simple_estimate_is_2026_not_refund_and_complex_blocked(self):
  data={s['key']:[] if s.get('repeat') else {} for s in t.STEPS}
  data.update(start={'name':'Fixture','return_type':'personal','assistance':'self_guided'},personal={'first_name':'F','last_name':'P','birth_date':'1990-01-01','tax_id':'111223333','residency':'us_citizen_resident'},spouse={'applies':'no'},address={'line1':'1 Test','city':'City','region':'TX','postal':'75001','country':'US'},household={'filing_status':'single','married':'no','dependent':'no','age65':'no','blind':'no','spouse_itemizes':'no','digital_assets':'no'},deductions={'method':'standard'},credits={f['key']:'no' for f in t.STEP_MAP['credits']['fields'] if f['type']=='select'},income=[{'kind':'w2','payer':'Test','amount':'28500.00','withholding':'1000.00'}])
  completed=[s['key'] for s in t.STEPS[:14]];r=t.review(data,completed)
  self.assertEqual(r['estimate']['ordinary_income_tax_cents'],124000);self.assertNotIn('refund',r);self.assertFalse(r['filing_ready'])
  data['investments']=[{'description':'Stock','proceeds':'100.00','basis':'50.00'}];self.assertIsNone(t.review(data,completed)['estimate'])
 def test_supported_refund_projection_and_charity_cap(self):
  data={s['key']:[] if s.get('repeat') else {} for s in t.STEPS}
  data.update(start={'name':'Fixture','return_type':'personal','assistance':'self_guided'},personal={'first_name':'F','last_name':'P','birth_date':'1990-01-01','tax_id':'111223333','residency':'us_citizen_resident'},spouse={'applies':'no'},address={'line1':'1 Test','city':'City','region':'TX','postal':'75001','country':'US'},household={'filing_status':'single','married':'no','dependent':'no','age65':'no','blind':'no','spouse_itemizes':'no','digital_assets':'no'},deductions={'method':'standard','cash_charity':'1500'},credits={f['key']:'no' for f in t.STEP_MAP['credits']['fields'] if f['type']=='select'},income=[{'kind':'w2','payer':'Test','amount':'50000','withholding':'6000'}],payments={'estimated':'100','extension':'50','prior_credit':'25','prior_agi':'999999'})
  completed=[s['key'] for s in t.STEPS[:14]];confirm={'verified_records':True,'no_other_taxes_or_credits':True,'charity_verified':True}
  r=t.refund_review(data,completed,confirm);self.assertFalse(r['maximum_refund_verified']);self.assertEqual(r['projection']['payments_and_withholding_cents'],617500);self.assertEqual(r['projection']['supported_tax_savings_cents'],12000);self.assertEqual(r['projection']['scenarios'][1]['extra_deduction_cents'],100000);self.assertEqual(r['projection']['estimated_federal_tax_cents'],370000);self.assertEqual(r['projection']['estimated_refund_cents'],247500)
  draft=self.create();saved=self.save(draft,data,completed=completed);computed=self.call('refund-review',{'id':draft['id'],'revision':saved['revision'],**confirm});self.assertIsNotNone(computed['refund_review']['projection'])
  changed=computed['data'];changed['income'][0]['withholding']='5000';edited=self.save(computed,changed);self.assertEqual(edited['refund_review'],{})
  self.assertIsNone(t.refund_review(data,completed,{})['projection']);data['states']=[{'state':'TX'}];self.assertIsNone(t.refund_review(data,completed,confirm)['projection'])
 def test_documents_encrypt_download_delete_and_fake_type(self):
  d=self.create();raw=b'%PDF-1.4 fixture'
  doc=self.call('document',{'id':d['id'],'name':'fixture.pdf','type':'application/pdf','base64':base64.b64encode(raw).decode()})
  with app.connect() as c:self.assertNotIn('PDF-1.4',c.execute('SELECT payload FROM tax_draft_documents').fetchone()[0])
  self.assertEqual(base64.b64decode(self.call('document-download',{'id':d['id'],'document_id':doc['id']})['base64']),raw)
  with self.assertRaises(a.ServiceError):self.call('document',{'id':d['id'],'name':'bad.pdf','type':'application/pdf','base64':base64.b64encode(b'<script>').decode()})
  self.call('document-delete',{'id':d['id'],'document_id':doc['id']})
  self.assertEqual(self.call('open',{'id':d['id']})['documents'],[])
 def test_source_record_preview_approval_hash_and_dedupe(self):
  d=self.create()
  with app.connect() as c:c.execute('INSERT INTO records(module,data) VALUES(?,?)',('tax_income',json.dumps({'name':'Income fixture','income_type':'wages','amount':'100.00'})))
  preview=self.call('record-preview',{'id':d['id']})['items'];item=preview[0]
  with self.assertRaises(a.ServiceError):self.call('record-import',{'id':d['id'],'revision':d['revision'],'items':preview,'consent':False})
  with self.assertRaises(a.ServiceError):self.call('record-import',{'id':d['id'],'revision':d['revision'],'items':[{**item,'hash':'wrong'}],'consent':True})
  d=self.call('record-import',{'id':d['id'],'revision':d['revision'],'items':preview,'consent':True});self.assertEqual(d['imported'],1)
  d=self.save(d,d['data'])
  d=self.call('record-import',{'id':d['id'],'revision':d['revision'],'items':preview,'consent':True});self.assertEqual(d['imported'],0);self.assertEqual(len(d['data']['income']),1)
 def test_ai_redacted_consent_only_and_no_paid_retry(self):
  d=self.create();data=d['data'];data['personal']={'first_name':'SECRET_NAME','tax_id':'111223333','email':'private@example.com'};d=self.save(d,data)
  with patch.dict(os.environ,{'DOBHRAP_ENABLE_TAX_AI':'1','OPENAI_API_KEY':'sk-fixture','TAX_AI_MODEL':'test-model'}):
   with self.assertRaises(a.ServiceError):self.call('ai-review',{'id':d['id'],'revision':d['revision'],'consent':False})
   result={'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'suggestions':[{'topic':'Education','question':'Do you have qualified tuition documentation for review?'}]})}]}]}
   with patch.object(a,'request_json',return_value=result) as provider:
    d=self.call('ai-review',{'id':d['id'],'revision':d['revision'],'consent':True});sent=json.dumps(provider.call_args.args[1]);self.assertNotIn('SECRET_NAME',sent);self.assertNotIn('111223333',sent);self.assertNotIn('private@example.com',sent);self.assertNotIn('tools',provider.call_args.args[1])
   self.assertEqual(d['ai_review']['state'],'completed')
   with self.assertRaises(a.ServiceError):self.call('ai-review',{'id':d['id'],'revision':d['revision'],'consent':True})
 def test_redacted_export_delete_and_viewer_permissions(self):
  d=self.create();data=d['data'];data['personal']={'tax_id':'111223333'};d=self.save(d,data)
  export=self.call('export',{'id':d['id']});self.assertNotIn('111223333',json.dumps(export));self.assertIn('NOT FOR FILING',export['kind'])
  with self.assertRaises(a.ServiceError):self.call('create',{},user={'id':2,'role':'viewer'})
  with self.assertRaises(a.ServiceError):self.call('delete',{'id':d['id']})
  self.call('delete',{'id':d['id'],'confirm':'DELETE'});self.assertEqual(self.call('returns'),[])
