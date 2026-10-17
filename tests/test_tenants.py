import http.cookiejar
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor
from cryptography.fernet import Fernet
import app
import backup
import worker


class TenantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = app.DB
        app.DB = self.temp.name + '/catalog.db'
        self.env = patch.dict(os.environ, {'DOBHRAP_ADMIN_PASSWORD': 'platform-password-1234',
                              'DOBHRAP_ADMIN_EMAIL': 'platform@example.com',
                              'DOBHRAP_ENCRYPTION_KEY': Fernet.generate_key().decode()})
        self.env.start()
        app.init()
        with app.connect() as c:
            c.execute("UPDATE users SET role='super_admin'")
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.public = build_opener()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        app.DB = self.old_db
        self.env.stop()
        self.temp.cleanup()

    def request(self, path, body=None, client=None, csrf='', tenant=None):
        headers = {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'X-Registration-Request': '1'}
        if tenant is not None:
            headers['X-Tenant-ID'] = str(tenant)
        req = Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with (client or self.public).open(req) as response:
            return json.load(response)

    def register(self, suffix):
        return self.request('/api/register', {'company': 'Company ' + suffix, 'email': suffix + '@example.com',
                            'password': 'workspace-password-123', 'confirm_password': 'workspace-password-123',
                            'role': 'super_admin', 'tenant_id': 1})['tenant_id']

    def login(self, email, password='workspace-password-123'):
        client = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        result = self.request('/api/login', {'email': email, 'password': password}, client=client)
        return client, result['csrf']

    def test_registration_isolation_and_forged_workspace(self):
        a, b = self.register('alpha'), self.register('beta')
        ca, ta = self.login('alpha@example.com')
        cb, tb = self.login('beta@example.com')
        self.assertEqual(self.request('/api/me', client=ca)['role'], 'admin')
        self.request('/api/records/customers', {'name': 'Alpha private'}, ca, ta)
        self.assertEqual(self.request('/api/records/customers', client=cb), [])
        self.assertEqual(len(self.request('/api/records/customers', client=ca)), 1)
        for path in ('/api/records/customers', '/api/users', '/api/reports', '/api/advanced/workflows'):
            with self.assertRaises(HTTPError) as error:
                self.request(path, client=cb, tenant=a)
            self.assertEqual(error.exception.code, 403)
        users = self.request('/api/users', client=cb)
        self.assertEqual([u['email'] for u in users], ['beta@example.com'])
        with self.assertRaises(HTTPError) as error:
            self.request('/api/users', {'email': 'escalated@example.com', 'password': 'workspace-password-123', 'role': 'super_admin'}, cb, tb)
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError) as error:
            self.request('/api/tenants', client=ca)
        self.assertEqual(error.exception.code, 403)

    def test_super_admin_switch_and_suspension_revoke_existing_access(self):
        tid = self.register('customer')
        owner, csrf = self.login('platform@example.com', 'platform-password-1234')
        customer, token = self.login('customer@example.com')
        self.assertEqual(len(self.request('/api/tenants', client=owner)), 2)
        self.assertEqual(self.request('/api/me', client=owner, tenant=tid)['tenant']['id'], tid)
        self.request('/api/tenants', {'action': 'status', 'tenant_id': tid, 'status': 'suspended'}, owner, csrf)
        with self.assertRaises(HTTPError) as error:
            self.request('/api/reports', client=customer)
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError):
            self.login('customer@example.com')
        with patch.object(worker, 'execute') as execute:
            worker.run_all()
            self.assertEqual(execute.call_count, 1)
        self.request('/api/tenants', {'action': 'status', 'tenant_id': tid, 'status': 'active'}, owner, csrf)
        self.assertEqual(self.request('/api/me', client=customer)['tenant']['status'], 'active')

    def test_platform_provider_credentials_are_not_available_to_customers(self):
        self.register('payroll')
        client, csrf = self.login('payroll@example.com')
        with patch.object(app.advanced, 'plaid') as plaid:
            with self.assertRaises(HTTPError) as error:
                self.request('/api/advanced/bank/link-token', {}, client, csrf)
            self.assertEqual(error.exception.code, 503)
            plaid.assert_not_called()
        with self.assertRaises(HTTPError) as error:
            self.request('/api/advanced/workflows', {'kind': 'payroll_create', 'payload': {}}, client, csrf)
        self.assertEqual(error.exception.code, 503)

    def test_backups_include_each_business_database(self):
        tid = self.register('backup')
        with app.tenant_connect(tid) as c:
            c.execute("INSERT INTO records(module,data) VALUES('tasks','{\"name\":\"Tenant task\"}')")
        target = self.temp.name + '/backups'
        with patch.dict(os.environ, {'DOBHRAP_DB': app.DB, 'DOBHRAP_BACKUP_DIR': target}):
            backup.backup()
        copies = list((Path(target) / ('tenant-' + str(tid))).glob('*.sqlite3'))
        self.assertEqual(len(copies), 1)
        with sqlite3.connect(copies[0]) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0], 1)

    def test_dashboard_and_statements_use_posted_workspace_ledger(self):
        tid=self.register('ledger')
        self.register('empty')
        with app.tenant_connect(tid) as c:
            app.post_journal(c,'Capital',[{'account':'1000','debit':50000,'credit':0},{'account':'3000','debit':0,'credit':50000}])
            app.post_journal(c,'Sale',[{'account':'1000','debit':25000,'credit':0},{'account':'4000','debit':0,'credit':25000}])
            app.post_journal(c,'Cost',[{'account':'5000','debit':5000,'credit':0},{'account':'1000','debit':0,'credit':5000}])
        owner,csrf=self.login('ledger@example.com')
        self.request('/api/records/invoices',{'name':'Operational invoice','amount':'123.45','due_date':'2020-01-01'},owner,csrf)
        dashboard=self.request('/api/dashboard',client=owner)
        self.assertEqual(dashboard['ledger']['net_income_cents'],20000)
        self.assertEqual(dashboard['ledger']['cash_cents'],70000)
        self.assertEqual(dashboard['record_totals_cents']['invoices'],12345)
        self.assertEqual(dashboard['attention']['past_due_invoice_records'],1)
        statement=self.request('/api/financial-statements',client=owner)
        self.assertTrue(statement['balanced'])
        self.assertEqual(statement['assets_cents'],70000)
        other,_=self.login('empty@example.com')
        self.assertEqual(self.request('/api/dashboard',client=other)['ledger']['revenue_cents'],0)
        self.assertEqual(self.request('/api/financial-statements',client=other)['assets_cents'],0)

    def test_management_queue_requires_platform_admin_and_fixed_operation(self):
        self.register('ordinary')
        customer,csrf=self.login('ordinary@example.com')
        for path in ('/api/platform/status','/api/platform/jobs'):
            with self.assertRaises(HTTPError) as error:self.request(path,client=customer)
            self.assertEqual(error.exception.code,403)
        owner,token=self.login('platform@example.com','platform-password-1234')
        with self.assertRaises(HTTPError) as error:self.request('/api/platform/jobs',{'kind':'shell','command':'anything'},owner,token)
        self.assertEqual(error.exception.code,400)
        job=self.request('/api/platform/jobs',{'kind':'backup','command':'ignored'},owner,token)
        self.assertEqual(job['state'],'queued')
        with self.assertRaises(HTTPError) as error:self.request('/api/platform/jobs',{'kind':'backup'},owner,token)
        self.assertEqual(error.exception.code,409)
        state=self.request('/api/platform/status',client=owner)
        self.assertEqual(state['jobs'][0]['kind'],'backup')
        self.assertNotIn('command',state['jobs'][0])

    def test_download_pages_and_install_assets_are_public(self):
        for route in ('/downloads','/manifest.webmanifest','/service-worker.js','/workspace.js','/assets/app-icon-192.png'):
            with self.public.open(self.base+route) as response:self.assertEqual(response.status,200)
        with patch.object(app,'mobile_download',return_value={'apk_available':False,'apk_url':None}):
            self.assertFalse(self.request('/api/mobile')['apk_available'])

    def test_duplicate_registration_does_not_allocate_another_workspace(self):
        self.register('unique')
        with self.assertRaises(HTTPError):
            self.register('unique')
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM tenants').fetchone()[0], 2)

    def test_marketplace_http_auth_roles_csrf_and_unsigned_webhook(self):
        with self.assertRaises(HTTPError) as error:self.request('/api/market/orders')
        self.assertEqual(error.exception.code,401)
        self.register('market-buyer')
        client,csrf=self.login('market-buyer@example.com')
        with self.assertRaises(HTTPError) as error:self.request('/api/market/products',{'name':'unauthorized'},client,csrf)
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError) as error:self.request('/api/market/checkout',{},client,'bad-csrf')
        self.assertEqual(error.exception.code,403)
        self.assertEqual(self.request('/api/market/orders',client=client),[])
        with patch.dict(os.environ,{'DOBHRAP_ENABLE_MARKETPLACE':'1','PAYMENTS_ENV':'test','STRIPE_SECRET_KEY':'sk_test_fixture','STRIPE_WEBHOOK_SECRET':'whsec_fixture'}):
            with self.assertRaises(HTTPError) as error:self.request('/api/market/webhooks/stripe',{})
            self.assertEqual(error.exception.code,400)
