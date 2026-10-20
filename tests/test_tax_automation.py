import base64
import os
import tempfile
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import app
import advanced as a
import tax_analyst as analyst


class TaxAutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=self.temp.name+'/db'
        self.env=patch.dict(os.environ,{'DOBHRAP_DB_BACKEND':'sqlite','DOBHRAP_ADMIN_PASSWORD':'test-owner-password-123',
            'DOBHRAP_ENCRYPTION_KEY':Fernet.generate_key().decode(),'DOBHRAP_ENABLE_TAX_ANALYST':'1',
            'OPENAI_API_KEY':'sk-test-synthetic-not-a-key','TAX_ANALYST_MODEL':'synthetic-model'})
        self.env.start();app.init();self.user={'id':1,'role':'admin'}
    def tearDown(self):self.env.stop();app.DB=self.old;self.temp.cleanup()
    def call(self,route,body,user=None):
        with app.connect() as c:return analyst.dispatch('/api/tax-analyst/'+route,'POST',body,c,user or self.user)
    def upload(self,number):
        return self.call('upload',{'year':2026,'name':'synthetic.pdf','type':'application/pdf',
            'base64':base64.b64encode(('%PDF-1.4 '+str(number)).encode()).decode()})
    def test_consent_required_and_repeated_queue_is_idempotent(self):
        self.upload(1)
        with self.assertRaises(a.ServiceError):self.call('queue-analysis',{'year':2026})
        self.assertEqual(self.call('queue-analysis',{'year':2026,'consent':True})['queued'],1)
        self.assertEqual(self.call('queue-analysis',{'year':2026,'consent':True})['queued'],0)
    def test_processes_one_document_with_unapproved_results(self):
        self.upload(1);self.upload(2);self.call('queue-analysis',{'year':2026,'consent':True})
        with patch.object(analyst,'extract',return_value={'records':[],'tax_fields':[]}) as extract:
            with app.connect() as c:self.assertEqual(analyst.process_analysis(c,{1:self.user},1),1)
            self.assertEqual(extract.call_count,1)
        with app.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM tax_analysis_jobs WHERE state='queued'").fetchone()[0],1)
            self.assertEqual(c.execute("SELECT count(*) FROM tax_analysis_jobs WHERE state='completed'").fetchone()[0],1)
    def test_failure_is_not_automatically_retried(self):
        self.upload(1);self.call('queue-analysis',{'year':2026,'consent':True})
        with patch.object(analyst,'extract',side_effect=RuntimeError('synthetic failure')) as extract:
            with app.connect() as c:
                self.assertEqual(analyst.process_analysis(c,{1:self.user}),1)
                self.assertEqual(analyst.process_analysis(c,{1:self.user}),0)
            self.assertEqual(extract.call_count,1)
        self.assertEqual(self.call('queue-analysis',{'year':2026,'consent':True})['queued'],0)
    def test_cancelled_unstarted_work_can_be_requeued_with_new_consent(self):
        self.upload(1);self.call('queue-analysis',{'year':2026,'consent':True})
        self.call('cancel-analysis',{'year':2026})
        self.assertEqual(self.call('queue-analysis',{'year':2026,'consent':True})['queued'],1)
    def test_cross_owner_cancel_and_summary_do_not_read_other_uploads(self):
        self.upload(1);self.call('queue-analysis',{'year':2026,'consent':True})
        other={'id':2,'role':'super_admin'}
        self.call('cancel-analysis',{'year':2026},other)
        self.assertEqual(self.call('automation-summary',{'year':2026},other)['line_groups'],{})
        with app.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM tax_analysis_jobs WHERE state='queued'").fetchone()[0],1)
    def test_changed_or_suspended_owner_is_cancelled_without_api_call(self):
        self.upload(1);self.call('queue-analysis',{'year':2026,'consent':True})
        with patch.object(analyst,'extract') as extract:
            with app.connect() as c:analyst.process_analysis(c,{})
            extract.assert_not_called()
    def test_w2_target_is_approved_year_specific_and_duplicates_are_flagged(self):
        field={'form':'W-2','box':'2','value':'1234.56','year':2026,'currency':'USD','approved':True}
        doc={'id':'one','year':2026,'state':'review','records':[],'tax_fields':[field]}
        result=analyst.automation_summary([doc],2026)
        self.assertEqual(result['comparison_target_cents'],123456)
        self.assertIn('not a minimum refund',result['notice'])
        self.assertIsNone(analyst.automation_summary([doc,{**doc,'id':'two'}],2026)['comparison_target_cents'])
        self.assertEqual(analyst.automation_summary([doc],2025)['reviewed_w2_box2_cents'],0)
        doc['tax_fields']=[{**field,'approved':False}]
        self.assertIsNone(analyst.automation_summary([doc],2026)['comparison_target_cents'])
