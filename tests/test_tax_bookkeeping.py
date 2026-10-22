import base64,io,json,unittest,uuid,zipfile
from unittest.mock import patch
from pypdf import PdfWriter
import app,advanced as a,tax_analyst as analyst,tax_analyst_billing as billing
from tests import test_tax_analyst as fixture
from tests.tax_billing_fixture import grant
class BookkeepingTests(unittest.TestCase):
 def setUp(self):
  self.backend=patch.dict(__import__('os').environ,{'DOBHRAP_DB_BACKEND':'sqlite'});self.backend.start();fixture.TaxAnalystTests.setUp(self)
 def tearDown(self):
  fixture.TaxAnalystTests.tearDown(self);self.backend.stop()
 call=fixture.TaxAnalystTests.call
 upload=fixture.TaxAnalystTests.upload
 row=fixture.TaxAnalystTests.row
 save=fixture.TaxAnalystTests.save
 def bk(self,route,body=None,user=None):return self.call('books-'+route,{'year':2026,**(body or {})},user=user)
 def line(self,doc,total='10.00',description='Office paper'):
  data={k:'' for k in analyst.BK_FIELDS['line']};data.update(document_id=doc['id'],date='2026-01-02',description=description,party='Example Supplier',flow='purchase',total=total,tax='0.00',quantity='1',unit_price=total,currency='USD',category='business_expense',evidence='Page 1 line 1')
  return self.bk('save',{'kind':'line','data':data})
 def action(self,route,item,**extra):return self.bk(route,{'id':item['id'],'revision':item['revision'],**extra})
 def test_encryption_ownership_review_and_tax_handoff(self):
  doc=self.upload();line=self.line(doc)
  with app.connect() as c:self.assertNotIn('Office paper',c.execute('SELECT payload FROM tax_bookkeeping_items').fetchone()[0])
  with self.assertRaises(a.ServiceError):self.action('send-to-analyst',line)
  with self.assertRaises(a.ServiceError):self.bk('state',{'id':line['id'],'revision':line['revision'],'state':'reviewed'},user={'id':2,'tenant_id':1,'role':'super_admin'})
  reviewed=self.action('state',line,state='reviewed');self.action('send-to-analyst',reviewed);self.action('send-to-analyst',reviewed)
  records=self.call('list')['documents'][0]['records'];self.assertEqual(len(records),1);self.assertFalse(records[0]['approved']);self.assertEqual(records[0]['business_percent'],0)
  exported=self.bk('export',{'ids':[line['id']]});self.assertEqual(len(exported['items']),1)
  self.assertEqual(self.bk('download-export',{'id':exported['id']})['items'][0]['data']['total'],'10.00')
 def test_atomic_import_duplicate_retry_and_stale_edit(self):
  doc=self.upload();line=self.line(doc);data=line['data']
  imported=self.bk('import',{'kind':'line','rows':[data,data]});self.assertEqual(imported['imported'],0)
  with self.assertRaises(a.ServiceError):self.bk('import',{'kind':'line','rows':[{**data,'description':'New'}, {**data,'date':'2025-01-02'}]})
  self.assertEqual(len(self.bk('overview')['items']),1)
  self.action('state',line,state='reviewed')
  with self.assertRaises(a.ServiceError) as error:self.action('state',line,state='draft')
  self.assertEqual(error.exception.status,409)
 def test_rules_are_previewed_before_manual_application(self):
  line=self.line(self.upload());data={k:'' for k in analyst.BK_FIELDS['rule']};data.update(name='Office coding',match_party='Example',category='business_expense',account_code='5100',project='Office')
  rule=self.bk('save',{'kind':'rule','data':data});rule=self.action('state',rule,state='reviewed')
  suggestions=self.action('preview-rules',line)['suggestions'];self.assertEqual(len(suggestions),1)
  self.assertEqual(next(i for i in self.bk('overview')['items'] if i['id']==line['id'])['data']['account_code'],'')
  applied=self.action('apply-rule',line,rule_id=rule['id']);self.assertEqual(applied['data']['account_code'],'5100');self.assertEqual(applied['state'],'draft')
 def test_matching_exact_currency_amount_and_unmatching(self):
  doc=self.upload();lines=[self.action('state',self.line(doc,'10.00'),state='reviewed'),self.action('state',self.line(doc,'20.00','Ink'),state='reviewed')]
  bank=self.bk('save',{'kind':'bank','data':{'date':'2026-01-03','description':'Purchase paid','total':'30.00','currency':'USD','flow':'debit','reference':'B1'}})
  with self.assertRaises(a.ServiceError):self.action('match',bank,line_ids=[lines[0]['id']])
  matched=self.action('match',bank,line_ids=[i['id'] for i in lines]);self.assertEqual(len(matched['data']['_matched_lines']),2)
  with self.assertRaises(a.ServiceError):self.action('match',bank,line_ids=[i['id'] for i in lines])
  unmatched=self.action('unmatch',matched);self.assertNotIn('_matched_lines',unmatched['data'])
 def test_split_merge_conserve_money_and_preserve_source(self):
  line=self.line(self.upload(),'30.00');result=self.action('transform',line,action='split',parts=[{'description':'Part A','total':'10','tax':'0'},{'description':'Part B','total':'20','tax':'0'}]);parts=result['items']
  self.assertEqual(len(parts),2);self.assertEqual(len(self.bk('overview')['items']),3)
  merged=self.action('transform',parts[0],action='merge',other_ids=[parts[1]['id']]);self.assertEqual(merged['items'][0]['data']['total'],'30.00')
  self.assertEqual(merged['items'][0]['state'],'draft')
 def test_claim_requires_different_assigned_reviewer(self):
  with app.connect() as c:c.execute("INSERT INTO users(id,email,salt,hash,role,tenant_id) VALUES(2,'reviewer@example.com','x','x','admin',1)")
  doc=self.upload();claim=self.bk('save',{'kind':'claim','data':{'date':'2026-01-02','description':'Office expense','total':'10','currency':'USD','purpose':'Paper for business','document_id':doc['id'],'reviewer_id':2}})
  submitted=self.action('state',claim,state='submitted')
  with self.assertRaises(a.ServiceError):self.action('claim-decision',submitted,state='approved',reason='Checked receipt')
  reviewer={'id':2,'tenant_id':1,'role':'admin'};inbox=self.bk('overview',user=reviewer);self.assertEqual(len(inbox['assigned_claims']),1)
  self.assertIn('base64',self.bk('claim-document',{'id':claim['id']},user=reviewer))
  decided=self.bk('claim-decision',{'id':claim['id'],'revision':submitted['revision'],'state':'approved','reason':'Checked original receipt'},user=reviewer);self.assertEqual(decided['state'],'approved')
 def test_diagnostics_refresh_and_critical_cannot_be_dismissed(self):
  doc=self.upload();report=self.call('diagnostics',{'year':2026});self.assertFalse(report['filing_ready']);self.assertFalse(report['transmission_available'])
  warning=next(d for d in report['diagnostics'] if d['severity']=='warning');critical=next(d for d in report['diagnostics'] if d['blocks_filing'])
  self.call('acknowledge-diagnostic',{'year':2026,'diagnostic_id':warning['id'],'notes':'Compared to original document'})
  self.assertEqual(next(d for d in self.call('diagnostics',{'year':2026})['diagnostics'] if d['id']==warning['id'])['review']['status'],'acknowledged')
  with self.assertRaises(a.ServiceError):self.call('acknowledge-diagnostic',{'year':2026,'diagnostic_id':critical['id'],'notes':'Try to suppress'})
  self.call('delete',{'id':doc['id'],'confirm':'DELETE'})
  with self.assertRaises(a.ServiceError):self.call('acknowledge-diagnostic',{'year':2026,'diagnostic_id':warning['id'],'notes':'Old source'})
 def test_bank_quote_counts_pdf_pages_and_reserves_all_or_none(self):
  writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.add_blank_page(width=100,height=100);out=io.BytesIO();writer.write(out)
  body={'type':'application/pdf','base64':base64.b64encode(out.getvalue()).decode(),'processing_mode':'bank','pages':999}
  quote=self.call('quote-upload',body);self.assertEqual((quote['pages'],quote['credits'],quote['additional_credits']),(2,6,1))
  uploaded=self.call('upload',{**body,'year':2026,'quote_revision':quote['rate_revision'],'quote_credits':quote['credits']});self.assertEqual(uploaded['processing']['credits'],6)
  with app.connect() as c:
   with self.assertRaises(a.ServiceError):billing.reserve(c,self.user,uploaded['id'],1,credits=6)
  with app.connect() as c:self.assertEqual(billing.status(c,1,self.user)['available'],5)
  grant(count=1)
  with app.connect() as c:reserved=billing.reserve(c,self.user,uploaded['id'],1,credits=6)
  self.assertEqual(len(reserved),6)
  with app.connect() as c:billing.finish(c,self.user,reserved,False)
  with app.connect() as c:self.assertEqual(billing.status(c,1,self.user)['available'],6)
 def test_free_storage_mode_and_stale_quote_rejected(self):
  body={'year':2026,'type':'application/pdf','base64':base64.b64encode(b'%PDF-free fixture').decode(),'processing_mode':'totals'}
  user={'id':2,'tenant_id':1,'role':'editor'};quote=self.call('quote-upload',body,user=user)
  with self.assertRaises(a.ServiceError):self.call('upload',{**body,'quote_revision':999,'quote_credits':1},user=user)
  uploaded=self.call('upload',{**body,'quote_revision':quote['rate_revision'],'quote_credits':quote['credits']},user=user);self.assertTrue(uploaded['id'])
 def test_office_conversion_is_bounded_and_nonexecuting(self):
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Invoice 25</w:t></w:r></w:p></w:body></w:document>')
  _,_,analysis=analyst.normalized_upload({'type':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','base64':base64.b64encode(out.getvalue()).decode()});self.assertIn('Invoice 25',analysis['analysis_text'])
  with self.assertRaises(a.ServiceError):analyst.normalized_upload({'type':'application/msword','base64':base64.b64encode(b'Legacy Doc').decode()})

 def test_super_admin_module_limits_and_private_usage(self):
  import tax_analyst_control as control
  root={'id':1,'role':'super_admin','tenant_id':1}
  with app.connect() as c:state=control.dispatch('/api/platform/tax-analyst/workbench-settings','GET',{},c,root)
  self.assertNotIn('data',state['workspaces'][0]);self.assertTrue(state['workspaces'][0]['schema_ready'])
  with app.connect() as c:
   with self.assertRaises(a.ServiceError):control.dispatch('/api/platform/tax-analyst/workbench-settings','GET',{},c,self.user)
  policy={**state['policy'],'bookkeeping_enabled':False}
  with app.connect() as c:control.dispatch('/api/platform/tax-analyst/workbench-settings','POST',{'revision':state['revision'],'policy':policy},c,root)
  with self.assertRaises(a.ServiceError):self.line(self.upload())
  with app.connect() as c:
   with self.assertRaises(a.ServiceError):control.dispatch('/api/platform/tax-analyst/workbench-settings','POST',{'revision':state['revision'],'policy':policy},c,root)
 def test_rate_change_preserves_existing_document_quote(self):
  body={'year':2026,'type':'application/pdf','base64':base64.b64encode(b'%PDF-pricing fixture').decode(),'processing_mode':'lines'}
  q=self.call('quote-upload',body);doc=self.call('upload',{**body,'quote_revision':q['rate_revision'],'quote_credits':q['credits']})
  root={'id':1,'role':'super_admin'}
  with app.connect() as c:billing.pricing(c,'POST',{'price_cents':500,'active':True,'expected_price_cents':500,'expected_active':True,'credit_rates':{'totals':1,'lines':4,'supplier':2,'bank_per_page':3},'expected_rates_revision':q['rate_revision']},root)
  self.assertEqual(self.call('quote-upload',body)['credits'],4);self.assertEqual(next(d for d in self.call('list')['documents'] if d['id']==doc['id'])['processing']['credits'],2)
