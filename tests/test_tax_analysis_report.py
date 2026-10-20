import base64, os, tempfile, unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import app, advanced as a, tax_analyst as analyst, tax_analysis_report as report

class UploadReportTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=self.temp.name+'/db'
  self.env=patch.dict(os.environ,{'DOBHRAP_DB_BACKEND':'sqlite','DOBHRAP_ADMIN_PASSWORD':'synthetic-password-123','DOBHRAP_ENCRYPTION_KEY':Fernet.generate_key().decode(),'DOBHRAP_ENABLE_TAX_ANALYST':'1','OPENAI_API_KEY':'synthetic-key','TAX_ANALYST_MODEL':'synthetic-model'});self.env.start();app.init();__import__('tests.tax_billing_fixture',fromlist=['grant']).grant();self.user={'id':1,'role':'admin'}
 def tearDown(self):self.env.stop();app.DB=self.old;self.temp.cleanup()
 def call(self,route,body,user=None):
  with app.connect() as c:return analyst.dispatch('/api/tax-analyst/'+route,'POST',body,c,user or self.user)
 def upload(self,**kw):return self.call('upload',{'year':2025,'name':'Synthetic PDF','type':'application/pdf','base64':base64.b64encode(b'%PDF-fixture').decode(),**kw})
 def test_upload_event_requires_consent_and_queues_only_new_document(self):
  old=self.upload()
  with self.assertRaises(a.ServiceError):self.upload(auto_analyze=True,base64=base64.b64encode(b'%PDF-new').decode())
  new=self.upload(auto_analyze=True,consent=True,base64=base64.b64encode(b'%PDF-new').decode())
  with app.connect() as c:
   jobs=c.execute('SELECT * FROM tax_analysis_jobs').fetchall();self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]['document_id'],new['id']);self.assertNotEqual(jobs[0]['document_id'],old['id'])
   self.assertEqual(c.execute('SELECT count(*) FROM tax_analyst_documents').fetchone()[0],2)
  with self.assertRaises(a.ServiceError):self.upload(auto_analyze=True,consent=True,base64=base64.b64encode(b'%PDF-new').decode())
 def test_report_does_not_leak_other_owner_or_original_bytes(self):
  self.upload();result=self.call('analysis-report',{'year':2025},{'id':2,'role':'super_admin'})
  self.assertEqual(result['summary']['documents'],0);self.assertNotIn('base64',str(result));self.assertFalse(result['filing_ready'])
 def test_ai_candidates_are_advisory_and_survive_review(self):
  row=analyst.clean_record({'amount':'200','kind':'expense','description':'Supplies','irs_candidate':'supplies'})
  self.assertEqual(row['irs_candidate'],'supplies');self.assertFalse(row['approved']);self.assertEqual(row['business_percent'],0)
  doc={'id':'d','year':2025,'state':'review','records':[row],'tax_fields':[]}
  r=report.build([doc],2025);entry=r['lines'][0]
  self.assertEqual(entry['form'],'Schedule C');self.assertEqual(entry['status'],'Needs review');self.assertIsNone(entry['draft_amount_cents'])
  row.update(approved=True,business_percent=100,category='business_expense',currency='USD',date='2025-01-01',evidence='page 1 line 3')
  r=report.build([doc],2025);self.assertIn('eligibility pending',r['lines'][0]['status']);self.assertFalse(r['filing_ready']);self.assertIsNone(r['lines'][0]['draft_amount_cents'])
 def test_personal_is_excluded_even_if_ai_suggests_business(self):
  row=analyst.clean_record({'amount':'20','kind':'personal','irs_candidate':'office'})
  r=report.build([{'id':'d','year':2025,'state':'review','records':[row]}],2025)
  self.assertEqual(r['lines'][0]['status'],'Excluded')
 def test_unknown_and_wrong_year_not_treated_as_completed_forms(self):
  row=analyst.clean_record({'amount':'20','irs_candidate':'invented'})
  r=report.build([{'id':'d','year':2026,'state':'review','records':[row]}],2026)
  self.assertEqual(r['lines'][0]['form'],'Manual review');self.assertTrue(any('2026' in w for w in r['warnings']))
 def test_approved_w2_and_unapproved_withholding_distinct(self):
  fields=[{'form':'W-2','box':'1','label':'Wages','value':'20000','currency':'USD','year':2025,'approved':True},{'form':'W-2','box':'2','value':'1000','currency':'USD','year':2025,'approved':False}]
  r=report.build([{'id':'d','year':2025,'state':'review','tax_fields':fields}],2025)
  self.assertEqual(r['lines'][0]['draft_amount_cents'],2000000);self.assertIsNone(r['lines'][1]['draft_amount_cents']);self.assertEqual(r['form_worksheets'][0]['line'],'1a');self.assertEqual(r['form_worksheets'][0]['approved_field_total_cents'],2000000)
 def test_failure_notice_never_echoes_provider_body(self):
  d=self.upload()
  with patch.object(analyst,'extract',side_effect=a.ServiceError('Provider rejected request (HTTP 429); secret synthetic body',502)):
   result=self.call('analyze',{'id':d['id'],'revision':d['revision'],'consent':True})
  self.assertIn('HTTP 429',result['notice']);self.assertNotIn('secret',result['notice'])

 def test_asset_review_points_to_schedule_c_not_form_4562_line_13(self):
  row=analyst.clean_record({'amount':'1000','kind':'expense','irs_candidate':'asset'})
  r=report.build([{'id':'d','year':2025,'state':'review','records':[row]}],2025)
  self.assertEqual(r['form_worksheets'][0]['form'],'Schedule C');self.assertEqual(r['form_worksheets'][0]['line'],'13');self.assertIsNone(r['form_worksheets'][0]['approved_field_total_cents'])

 def test_duplicate_approved_forms_have_no_draft_numeric_totals(self):
  field={'form':'W-2','box':'1','value':'20000','currency':'USD','year':2025,'approved':True}
  docs=[{'id':name,'year':2025,'state':'review','tax_fields':[field]} for name in ('one','two')]
  r=report.build(docs,2025)
  self.assertIsNone(r['form_worksheets'][0]['approved_field_total_cents']);self.assertTrue(any('duplicate approved tax forms' in w for w in r['warnings']))
