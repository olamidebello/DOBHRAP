import base64
import os
import tempfile
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import app
import advanced as a
import bank_import as b


class BankImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old_db=app.DB;app.DB=self.temp.name+'/catalog.db'
        self.env=patch.dict(os.environ,{'DOBHRAP_ADMIN_PASSWORD':'testing-password-1234','DOBHRAP_ENCRYPTION_KEY':Fernet.generate_key().decode(),'PLAID_ENV':'sandbox','PLAID_CLIENT_ID':'client','PLAID_SECRET':'secret','DOBHRAP_ENABLE_TENANT_BANKING':'1','DOBHRAP_ENABLE_AUTO_BANK_IMPORT':'1','DOBHRAP_ENABLE_BANK_STATEMENTS':'0'})
        self.env.start();app.init();self.user={'id':1,'role':'admin'}
    def tearDown(self):
        app.DB=self.old_db;self.env.stop();self.temp.cleanup()
    def call(self,route,body=None,user=None,tid=1):
        with app.tenant_connect(tid) as c:
            return a.dispatch('/api/advanced/bank/'+route,'GET' if body is None else 'POST',body or {},c,user or self.user,app.post_journal,tenant_id=tid)
    def item(self,auto=1):
        with app.connect() as c:
            c.execute('INSERT INTO bank_items(id,owner,environment,secret,auto_import) VALUES(?,?,?,?,?)',('item1',1,'sandbox',a.seal({'access_token':'private-access-token'}),auto))
    def test_consent_owner_nonce_replay_and_encryption(self):
        with patch.object(a,'plaid',return_value={'link_token':'link'}) as provider:
            with self.assertRaises(a.ServiceError):self.call('link-token',{})
            link=self.call('link-token',{'consent':True})
            self.assertEqual(provider.call_args.args[1]['user']['client_user_id'],'tenant-1-user-1')
        with patch.object(a,'plaid',return_value={'access_token':'private-access-token','item_id':'new-item'}) as provider:
            with self.assertRaises(a.ServiceError):self.call('exchange',{'nonce':link['nonce'],'public_token':'public'},user={'id':2,'role':'admin'})
            provider.assert_not_called()
            with patch.object(b,'sync',side_effect=a.ServiceError('not ready')):
                result=self.call('exchange',{'nonce':link['nonce'],'public_token':'public'})
            self.assertTrue(result['pending'])
            with self.assertRaises(a.ServiceError):self.call('exchange',{'nonce':link['nonce'],'public_token':'public'})
        with app.connect() as c:
            row=c.execute('SELECT * FROM bank_items').fetchone()
            self.assertNotIn('private-access-token',row['secret']);self.assertEqual(row['auto_import'],1)
        self.assertNotIn('secret',str(self.call('items')))
    def test_owner_and_reconnect(self):
        self.item()
        for route,body in [('sync',{}),('automation',{'enabled':False}),('disconnect',{}),('reconnect',{'consent':True})]:
            with self.assertRaises(a.ServiceError) as exc:self.call(route,{'item_id':'item1',**body},user={'id':2,'role':'admin'})
            self.assertEqual(exc.exception.status,403)
        with patch.object(a,'plaid',return_value={'link_token':'update'}) as provider:
            link=self.call('reconnect',{'item_id':'item1','consent':True})
            self.assertNotIn('products',provider.call_args.args[1]);self.assertIn('access_token',provider.call_args.args[1])
        with patch.object(b,'sync',return_value={'changes':0}),patch.object(a,'plaid') as provider:
            self.call('complete-update',{'nonce':link['nonce']});provider.assert_not_called()
    def test_scheduled_import_pause_failure_backoff_and_dedupe(self):
        self.item()
        tx={'transaction_id':'tx1','account_id':'acc1','date':'2026-10-15','name':'Coffee','amount':5,'iso_currency_code':'USD'}
        with patch.object(a,'plaid',return_value={'added':[tx],'next_cursor':'one','has_more':False}) as provider:
            b.run_all();b.run_all();self.assertEqual(provider.call_count,1)
        self.assertEqual(len(self.call('transactions')),1)
        self.call('automation',{'item_id':'item1','enabled':False})
        with patch.object(a,'plaid') as provider:b.run_all();provider.assert_not_called()
        self.call('automation',{'item_id':'item1','enabled':True})
        with patch.object(a,'plaid',side_effect=a.ServiceError('secret provider data')):b.run_all()
        row=self.call('items')[0];self.assertNotIn('secret provider data',row['sync_error']);self.assertGreater(row['next_sync'],row['last_sync'])
        with app.connect() as c:self.assertEqual(c.execute('SELECT cursor FROM bank_items').fetchone()[0],'one')
        with patch.object(a,'plaid',return_value={'added':[tx],'next_cursor':'two'}):self.call('sync',{'item_id':'item1'})
        self.assertEqual(len(self.call('transactions')),1)
    def test_pdf_encrypted_download_and_no_duplicate_fetch(self):
        self.item()
        with app.connect() as c:c.execute('UPDATE bank_items SET statements_consent=1')
        listing={'accounts':[{'account_id':'acc1','statements':[{'statement_id':'statement1','month':9,'year':2026}]}]}
        with patch.dict(os.environ,{'DOBHRAP_ENABLE_BANK_STATEMENTS':'1'}),patch.object(a,'plaid',return_value=listing),patch.object(b,'pdf_download',return_value=b'%PDF-private') as download:
            with app.connect() as c:
                row=c.execute('SELECT * FROM bank_items').fetchone();self.assertEqual(b.import_statements(c,row),1);self.assertEqual(b.import_statements(c,row),0)
            self.assertEqual(download.call_count,1)
        self.assertEqual(base64.b64decode(self.call('statement-download',{'id':'statement1'})['base64']),b'%PDF-private')
        with app.connect() as c:self.assertNotIn('PDF-private',c.execute('SELECT pdf FROM bank_statements').fetchone()[0])
    def test_tenant_opt_in_and_nonce_isolation(self):
        with app.connect() as c:
            tid=app.register_workspace(c,{'company':'Separate','email':'separate@example.com','password':'workspace-password-123','confirm_password':'workspace-password-123'})['tenant_id']
        with patch.object(a,'plaid',return_value={'link_token':'link'}):link=self.call('link-token',{'consent':True})
        with self.assertRaises(a.ServiceError):self.call('exchange',{'nonce':link['nonce'],'public_token':'public'},tid=tid)
        self.assertEqual(self.call('items',tid=tid),[])
        with patch.dict(os.environ,{'DOBHRAP_ENABLE_TENANT_BANKING':'0'}),patch.object(a,'plaid') as provider:
            with self.assertRaises(a.ServiceError):self.call('link-token',{'consent':True},tid=tid)
            provider.assert_not_called()
