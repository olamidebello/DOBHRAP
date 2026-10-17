import base64, json, os, tempfile, unittest, uuid
from unittest.mock import patch
from cryptography.fernet import Fernet
import app, advanced as a, tax_analyst as t, tax_preparation as prep

class TaxAnalystTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=self.tmp.name+'/db.sqlite';self.user={'id':1,'role':'admin'}
  self.env=patch.dict(os.environ,{'DOBHRAP_ADMIN_PASSWORD':'test-password-123456','DOBHRAP_ENCRYPTION_KEY':Fernet.generate_key().decode(),'DOBHRAP_ENABLE_TAX_ANALYST':'0'});self.env.start();app.init()
 def tearDown(self):self.env.stop();app.DB=self.old;self.tmp.cleanup()
 def call(self,route,body=None,user=None):
  with app.connect() as c:return t.dispatch('/api/tax-analyst/'+route,'GET' if body is None else 'POST',body or {},c,user or self.user)
 def upload(self,y=2026,data=b'%PDF-1.4 analyst fixture'):
  return self.call('upload',{'year':y,'type':'application/pdf','name':'Private fixture.pdf','base64':base64.b64encode(data).decode()})
 def row(self,**kw):return {'id':str(uuid.uuid4()),'date':'2026-02-01','description':'Fixture transaction','amount':'125.50','currency':'USD','kind':'income','category':'interest','business_percent':0,'approved':True,'evidence':'Page 1','notes':'',**kw}
 def save(self,d,rows):return self.call('save',{'id':d['id'],'revision':d['revision'],'records':rows})
 def build(self,y=2026):return self.call('compile',{'year':y,'confirm':True})
 def test_private_encrypted_upload_and_duplicates(self):
  d=self.upload()
  with app.connect() as c:
   raw=c.execute('SELECT payload FROM tax_analyst_documents').fetchone()[0];self.assertNotIn('Private fixture',raw);self.assertNotIn(base64.b64encode(b'%PDF-1.4 analyst fixture').decode(),raw)
  self.assertNotIn('base64',d)
  with self.assertRaises(a.ServiceError):self.upload()
  with self.assertRaises(a.ServiceError):self.call('download',{'id':d['id']},user={'id':2,'role':'super_admin'})
  with self.assertRaises(a.ServiceError):self.call('list',user={'id':1,'role':'viewer'})
 def test_validation_revision(self):
  d=self.upload();self.save(d,[self.row()])
  with self.assertRaises(a.ServiceError):self.save(d,[])
  for row in (self.row(amount='NaN'),self.row(date='2026-02-30'),self.row(kind='deductible'),self.row(business_percent=101)):
   with self.assertRaises(a.ServiceError):t.clean_record(row)
 def test_compile_idempotent_and_handoff(self):
  d=self.upload();self.save(d,[self.row(),self.row(description='Supplies',kind='expense',category='business_expense',amount='100',business_percent=50)])
  b=self.build();self.assertEqual(b['totals']['business_expense_intake_cents'],5000);self.assertIsNotNone(b['draft_id']);self.assertTrue(self.build()['reused'])
  with app.connect() as c:
   r,p=prep.read(c,b['draft_id'],self.user);self.assertEqual(p['data']['income'][0]['amount'],'125.50');self.assertEqual(p['data']['businesses'][0]['expenses'],'50.00');self.assertFalse(prep.view(c,r,p)['review']['filing_ready']);self.assertEqual(c.execute('SELECT count(*) FROM tax_drafts').fetchone()[0],1)
 def test_compile_checks_approval_year_currency_duplicates(self):
  d=self.upload()
  for rows in ([self.row(approved=False)],[self.row(date='2025-01-01')],[self.row(currency='EUR')],[self.row(category='unclassified')],[self.row(),self.row()]):
   d=self.save(d,rows)
   with self.assertRaises(a.ServiceError):self.build()
  d=self.save(d,[self.row(kind='transfer',category='transfer'),self.row(approved=False)])
  with self.assertRaises(a.ServiceError):self.build()
 def test_other_year_worksheet_and_delete(self):
  d=self.upload(2025);self.save(d,[self.row(date='2025-03-01')]);b=self.build(2025);self.assertIsNotNone(b['draft_id'])
  self.call('delete-build',{'id':b['id'],'confirm':'DELETE'});self.assertFalse(self.call('list')['builds'])
  self.call('delete',{'id':d['id'],'confirm':'DELETE'});self.assertFalse(self.call('list')['documents'])
 def test_ai_consent_validation_and_request_shape(self):
  d=self.upload();args={'id':d['id'],'revision':d['revision']}
  with self.assertRaises(a.ServiceError):self.call('analyze',args)
  with self.assertRaises(a.ServiceError):self.call('analyze',{**args,'consent':True})
  output={'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'records':[self.row(approved=True,business_percent=100)]})}]}]}
  with patch.dict(os.environ,{'DOBHRAP_ENABLE_TAX_ANALYST':'1','OPENAI_API_KEY':'test-key','TAX_ANALYST_MODEL':'test-model'}),patch.object(a,'request_json',return_value=output) as request:
   result=self.call('analyze',{**args,'consent':True});self.assertEqual(result['state'],'review');self.assertFalse(result['records'][0]['approved']);self.assertEqual(result['records'][0]['category'],'unclassified');self.assertEqual(result['records'][0]['business_percent'],0)
   body=request.call_args.args[1];self.assertFalse(body['store']);self.assertEqual(body['input'][0]['content'][1]['type'],'input_file');self.assertNotIn('tools',body)
   with self.assertRaises(a.ServiceError):self.call('analyze',{'id':d['id'],'revision':result['revision'],'consent':True})
 def test_ai_failure_no_partial_records_no_auto_retry(self):
  d=self.upload()
  with patch.dict(os.environ,{'DOBHRAP_ENABLE_TAX_ANALYST':'1','OPENAI_API_KEY':'test-key','TAX_ANALYST_MODEL':'test-model'}),patch.object(a,'request_json',side_effect=RuntimeError('private upstream')) as request:
   r=self.call('analyze',{'id':d['id'],'revision':d['revision'],'consent':True});self.assertEqual(r['state'],'failed');self.assertEqual(r['records'],[]);self.assertNotIn('private upstream',r['notice']);self.assertEqual(request.call_count,1)
   with self.assertRaises(a.ServiceError):self.call('analyze',{'id':d['id'],'revision':r['revision'],'consent':True})
 def test_tax_form_extraction_fields_unapproved(self):
  d=self.upload();field={'form':'W-2','box':'1','label':'Wages','value':'50000.00','currency':'USD','year':2026,'approved':True,'evidence':'Page 1 box 1'}
  output={'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'records':[],'tax_fields':[field]})}]}]}
  with patch.dict(os.environ,{'DOBHRAP_ENABLE_TAX_ANALYST':'1','OPENAI_API_KEY':'test-key','TAX_ANALYST_MODEL':'test-model'}),patch.object(a,'request_json',return_value=output):
   r=self.call('analyze',{'id':d['id'],'revision':d['revision'],'consent':True});self.assertFalse(r['tax_fields'][0]['approved']);self.assertEqual(r['tax_fields'][0]['value'],'50000.00')
  with self.assertRaises(a.ServiceError):self.build()
 def test_verified_tax_boxes_map_and_other_fields_preserved(self):
  d=self.upload();fields=[{'form':'W-2','box':box,'label':'Fixture box','value':value,'currency':'USD','year':2026,'approved':True,'evidence':'Page 1'} for box,value in [('1','50000'),('2','6000')]]
  fields.append({'form':'1098-T','box':'1','label':'Education payment','value':'1000','currency':'USD','year':2026,'approved':True})
  self.call('save',{'id':d['id'],'revision':d['revision'],'records':[],'tax_fields':fields});b=self.build();self.assertEqual(len(b['tax_fields']),3)
  with app.connect() as c:
   _,p=prep.read(c,b['draft_id'],self.user);self.assertEqual(len(p['data']['income']),1);self.assertEqual(p['data']['income'][0]['amount'],'50000.00');self.assertEqual(p['data']['income'][0]['withholding'],'6000.00')
  self.assertTrue(self.build()['reused'])
 def test_identifier_fields_are_rejected(self):
  with self.assertRaises(a.ServiceError):t.clean_tax_fields([{'label':'Taxpayer SSN','value':'111-22-3333','year':2026}])
 def test_wrong_year_and_duplicate_box_rejected(self):
  d=self.upload();field={'form':'W-2','box':'1','value':'1000','currency':'USD','year':2025,'approved':True}
  d=self.call('save',{'id':d['id'],'revision':d['revision'],'records':[],'tax_fields':[field]})
  with self.assertRaises(a.ServiceError):self.build()
  field['year']=2026;self.call('save',{'id':d['id'],'revision':d['revision'],'records':[],'tax_fields':[field,field]})
  with self.assertRaises(a.ServiceError):self.build()
 def test_custom_document_type_and_separate_group_totals(self):
  d=self.call('upload',{'year':2026,'type':'application/pdf','document_type':'Business mileage log','name':'Custom.pdf','base64':base64.b64encode(b'%PDF-1.4 custom').decode()})
  self.assertEqual(d['document_type'],'Business mileage log')
  self.save(d,[self.row(amount='0.10'),self.row(amount='0.20',approved=False)])
  groups=self.call('list')['groups'];self.assertEqual(len(groups),1);self.assertEqual(groups[0]['transaction_totals']['USD / income / approved'],10);self.assertEqual(groups[0]['transaction_totals']['USD / income / unreviewed'],20)
 def test_existing_tenant_migration(self):
  with app.connect() as c:tenant=app.register_workspace(c,{'company':'Fixture tenant','email':'tenant@example.com','password':'test-password-123456','confirm_password':'test-password-123456'})['tenant_id']
  with app.tenant_connect(tenant) as c:c.execute('DROP TABLE tax_analyst_documents')
  app.init()
  with app.tenant_connect(tenant) as c:self.assertIsNotNone(c.execute("SELECT name FROM sqlite_master WHERE name='tax_analyst_documents'").fetchone())
