import unittest,uuid
import app,advanced as a,tax_preparation as prep,tax_analyst as analyst
from tests import test_tax_analyst as fixture
class ReviewCaseTests(unittest.TestCase):
 setUp=fixture.TaxAnalystTests.setUp
 tearDown=fixture.TaxAnalystTests.tearDown
 call=fixture.TaxAnalystTests.call
 upload=fixture.TaxAnalystTests.upload
 row=fixture.TaxAnalystTests.row
 save=fixture.TaxAnalystTests.save
 build=fixture.TaxAnalystTests.build
 def test_private_encrypted_revision_and_evidence(self):
  case=self.call('review-case',{'year':2026});self.assertEqual(case['revision'],0)
  data=case['data'];data['notes']='Private interview source';data['areas']={'income':{'status':'reviewed','notes':'Compared printed income forms'}};data['tasks']=[{'id':str(uuid.uuid4()),'text':'Obtain missing 1099','due':'2026-12-01','status':'requested','evidence':'Asked client during interview'}]
  saved=self.call('save-review-case',{'year':2026,'revision':0,'data':data});self.assertEqual(saved['revision'],1);self.assertFalse(saved['filing_ready'])
  with app.connect() as c:self.assertNotIn('Private interview source',c.execute('SELECT payload FROM tax_analyst_cases').fetchone()[0])
  other=self.call('review-case',{'year':2026},user={'id':2,'role':'super_admin'});self.assertEqual(other['revision'],0);self.assertEqual(other['data']['notes'],'')
  with self.assertRaises(a.ServiceError) as error:self.call('save-review-case',{'year':2026,'revision':0,'data':data})
  self.assertEqual(error.exception.status,409)
  with self.assertRaises(a.ServiceError):self.call('review-case',{'year':2026},user={'id':1,'role':'viewer'})
 def test_checklist_and_task_cannot_be_closed_without_evidence(self):
  data={'profile':'personal','areas':{'credits':{'status':'reviewed','notes':''}},'tasks':[]}
  with self.assertRaises(a.ServiceError):self.call('save-review-case',{'year':2026,'revision':0,'data':data})
  data['areas']={};data['tasks']=[{'id':str(uuid.uuid4()),'text':'Form','status':'received','evidence':''}]
  with self.assertRaises(a.ServiceError):self.call('save-review-case',{'year':2026,'revision':0,'data':data})
 def test_reconciliation_and_preparation_snapshot(self):
  d=self.upload();d=self.save(d,[self.row(approved=False,evidence='',kind='unknown',category='unclassified'),self.row(approved=False,evidence='')])
  report=self.call('review-case',{'year':2026});codes={f['code'] for f in report['findings']};self.assertTrue({'coverage','unreviewed','evidence','classification'}<=codes)
  d=self.save(d,[self.row()]);case=self.call('review-case',{'year':2026});data=case['data'];data['notes']='Reconcile investment carryovers';self.call('save-review-case',{'year':2026,'revision':0,'data':data})
  build=self.build();self.assertEqual(build['analyst_review']['data']['notes'],'Reconcile investment carryovers');self.assertTrue(build['analyst_review']['benefit_review']);self.assertTrue(self.build()['reused'])
  with app.connect() as c:
   row,payload=prep.read(c,build['draft_id'],self.user);view=prep.view(c,row,payload)
   self.assertEqual(view['analyst_review']['revision'],1);self.assertFalse(view['review']['filing_ready']);self.assertFalse(view['analyst_review']['benefit_review'][0]['eligibility_confirmed'])
  data['notes']='Updated source review';self.call('save-review-case',{'year':2026,'revision':1,'data':data});self.assertNotEqual(self.build()['id'],build['id'])
 def test_possible_duplicates_do_not_auto_delete(self):
  d=self.upload();self.save(d,[self.row(approved=False),self.row(approved=False)])
  case=self.call('review-case',{'year':2026});self.assertIn('possible_duplicate',{f['code'] for f in case['findings']})
  self.assertEqual(len(self.call('list')['documents'][0]['records']),2)
