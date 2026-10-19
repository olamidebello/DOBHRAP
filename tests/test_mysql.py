"""Real MySQL integration tests. Set OOB_TEST_MYSQL_CONFIG to opt in.
Requires an isolated MySQL 8.0.16+ server and credentials with schema privileges.
Every test uses a fresh random schema prefix; never uses the production prefix.
"""
import gzip
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid
import app
import database
import backup
import advanced
import mysql_migrate
from cryptography.fernet import Fernet


@unittest.skipUnless(os.environ.get('OOB_TEST_MYSQL_CONFIG'), 'isolated MySQL server required')
class MySQLTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        cfg = json.loads(Path(os.environ['OOB_TEST_MYSQL_CONFIG']).read_text())
        cfg['prefix'] = 'dobhrap_test_' + uuid.uuid4().hex[:12]
        self.cfg = Path(self.temp.name) / 'mysql.json'
        self.cfg.write_text(json.dumps(cfg))
        self.old_db = app.DB
        app.DB = self.temp.name + '/source.db'
        self.env = patch.dict(os.environ, DOBHRAP_DB_BACKEND='mysql', DOBHRAP_MYSQL_CONFIG=str(self.cfg), DOBHRAP_ADMIN_PASSWORD='platform-password-1234', DOBHRAP_ADMIN_EMAIL='owner@example.com', DOBHRAP_ENCRYPTION_KEY=Fernet.generate_key().decode())
        self.env.start()
        with database.connect(create=True):pass
        app.init()

    def tearDown(self):
        with database.connect() as c:
            names = [r['SCHEMA_NAME'] for r in c._query('SELECT SCHEMA_NAME FROM information_schema.SCHEMATA') if r['SCHEMA_NAME'].startswith(json.loads(self.cfg.read_text())['prefix']+'_')]
            for name in names:c._query('DROP DATABASE `' + name + '`')
        self.env.stop()
        app.DB = self.old_db
        self.temp.cleanup()

    def test_ledger_constraints_and_rollback(self):
        with app.connect() as c:
            app.post_journal(c,'Sale',[dict(account='1000',debit=500,credit=0),dict(account='4000',debit=0,credit=500)])
            self.assertEqual(app.financial_statements(c)['net_income_cents'],500)
            self.assertEqual(app.dashboard(c,'admin')['ledger']['cash_cents'],500)
        with self.assertRaises(sqlite3.IntegrityError):
            with app.connect() as c:
                c.execute("INSERT INTO journals(memo) VALUES('rollback')")
                c.execute("INSERT INTO lines(journal_id,account) VALUES(1,'missing')")
        with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM journals').fetchone()[0],1)

    def test_settings_upsert_ignore_and_parameter_safety(self):
        with app.connect() as c:
            c.execute('INSERT OR REPLACE INTO platform_state VALUES(?,?)',('key','contains ? and % and \'quoted\''))
            c.execute('INSERT OR REPLACE INTO platform_state VALUES(?,?)',('key','updated'))
            self.assertEqual(c.execute('SELECT value FROM platform_state WHERE key=?',('key',)).fetchone()[0],'updated')
            self.assertEqual(c.execute('INSERT OR IGNORE INTO accounts VALUES(?,?,?)',('1000','Cash','asset')).rowcount,0)
            c.execute('INSERT INTO market_plan_terms VALUES(?,?) ON CONFLICT(product_id) DO UPDATE SET days=excluded.days',('plan',30))
            c.execute('INSERT INTO market_plan_terms VALUES(?,?) ON CONFLICT(product_id) DO UPDATE SET days=excluded.days',('plan',60))
            self.assertEqual(c.execute('SELECT days FROM market_plan_terms').fetchone()[0],60)
            self.assertEqual(c.execute('UPDATE market_plan_terms SET days=? WHERE product_id=?',(60,'plan')).rowcount,1)
            self.assertEqual(c.execute('UPDATE market_plan_terms SET days=? WHERE product_id=?',(60,'absent')).rowcount,0)
            with self.assertRaises(sqlite3.IntegrityError):c.execute('INSERT OR IGNORE INTO tenants(name) VALUES(NULL)')

    def test_workspace_creation_isolation_and_queue_order(self):
        with app.connect() as c:
            tid=app.register_workspace(c,dict(company='Other',email='other@example.com',password='other-password-1234',confirm_password='other-password-1234'))['tenant_id']
        with app.tenant_connect(tid) as c:
            c.execute('INSERT INTO records(module,data) VALUES(?,?)',('customers',json.dumps({'name':'private'})))
            c.execute('INSERT INTO records(module,data) VALUES(?,?)',('time',json.dumps({'clock_entry_id':'test'})))
            self.assertIsNotNone(c.execute("SELECT id FROM records WHERE json_extract(data,'$.clock_entry_id')=?",('test',)).fetchone())
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0],0)
            c.execute("INSERT INTO platform_jobs(id,kind,creator) VALUES('z','verify',1)")
            c.execute("INSERT INTO platform_jobs(id,kind,creator) VALUES('a','verify',1)")
            self.assertEqual(c.execute('SELECT id FROM platform_jobs ORDER BY rowid').fetchone()[0],'z')

    def test_partial_unique_indexes(self):
        with app.connect() as c:
            values=('first','worker',1,None,'encrypted')
            c.execute('INSERT INTO clock_entries(id,worker_id,started,ended,payload) VALUES(?,?,?,?,?)',values)
            with self.assertRaises(sqlite3.IntegrityError):c.execute('INSERT INTO clock_entries(id,worker_id,started,ended,payload) VALUES(?,?,?,?,?)',('second',*values[1:]))
            c.execute('UPDATE clock_entries SET ended=2 WHERE id=?',('first',))
            c.execute('INSERT INTO clock_entries(id,worker_id,started,ended,payload) VALUES(?,?,?,?,?)',('second',*values[1:]))

    def test_backup_and_restore(self):
        with patch.dict(os.environ,DOBHRAP_BACKUP_DIR=self.temp.name):target=backup.backup()
        sql=gzip.open(target,'rt').read()
        self.assertIn('CREATE TABLE',sql)
        self.assertIn('INSERT INTO `users`',sql)
        self.assertNotIn('_open_worker`) VALUES',sql)
        import pymysql
        options=json.loads(self.cfg.read_text())
        c=pymysql.connect(host=options['host'],port=options['port'],user=options['user'],password=options['password'],client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS,autocommit=True)
        with c:
            with c.cursor() as cursor:
                cursor.execute('DROP DATABASE `'+database.schema_name()+'`')
                cursor.execute(sql)
                while cursor.nextset():pass
        with app.connect() as c:self.assertEqual(c.execute('SELECT email FROM users').fetchone()[0],'owner@example.com')

    def test_verified_migration_with_tenants(self):
        # Build a realistic SQLite source, keeping encryption and credential hashes.
        with patch.dict(os.environ,DOBHRAP_DB_BACKEND='sqlite'):
            app.init()
            with app.connect() as c:
                c.execute("UPDATE users SET role='super_admin'"); c.commit()
                tid=app.register_workspace(c,dict(company='Migrated',email='migrated@example.com',password='tenant-password-1234',confirm_password='tenant-password-1234'))['tenant_id']
                app.post_journal(c,'Sale',[dict(account='1000',debit=123,credit=0),dict(account='4000',debit=0,credit=123)])
            with app.tenant_connect(tid) as c:c.execute('INSERT INTO records(module,data) VALUES(?,?)',('customers','{"name":"Keep me"}'))
        with app.connect() as c:
            # Drop only this test's empty initial schema to test a fresh target.
            c._query('DROP DATABASE `'+database.schema_name()+'`')
        result=mysql_migrate.migrate(app.DB,self.temp.name)
        self.assertTrue(result['verified'])
        app.init()
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0],2)
            self.assertEqual(app.financial_statements(c)['net_income_cents'],123)
        with app.tenant_connect(tid) as c:self.assertEqual(c.execute('SELECT data FROM records').fetchone()[0],'{"name":"Keep me"}')
        with self.assertRaisesRegex(RuntimeError,'not empty'):mysql_migrate.migrate(app.DB,self.temp.name)

    def test_http_login_and_idempotent_record_update(self):
        import threading
        import http.cookiejar
        from urllib.request import Request, build_opener, HTTPCookieProcessor
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        client=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def request(path,body=None,csrf=''):
            req=Request('http://127.0.0.1:%d'%server.server_port+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
            with client.open(req) as response:return json.load(response)
        try:
            csrf=request('/api/login',dict(email='owner@example.com',password='platform-password-1234'))['csrf']
            self.assertEqual(request('/api/me')['email'],'owner@example.com')
            record=request('/api/records/customers',{'name':'Customer'},csrf)
            request('/api/records/customers',{'id':record['id'],'name':'Customer'},csrf)
            request('/api/records/customers',{'id':record['id'],'name':'Customer'},csrf)
            self.assertEqual(request('/api/records/customers')[0]['name'],'Customer')
            self.assertEqual(request('/api/dashboard')['ledger']['net_income_cents'],0)
            from urllib.error import HTTPError
            gate=Path(self.temp.name)/'maintenance';gate.touch()
            with patch.object(app,'MYSQL_MAINTENANCE',gate):
                with self.assertRaises(HTTPError) as error:request('/api/records/customers',{'name':'Blocked'},csrf)
                self.assertEqual(error.exception.code,503)
            self.assertEqual(len(request('/api/records/customers')),1)
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_provisioned_account_can_only_use_application_schemas(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('mysql_provision',Path(__file__).resolve().parents[1]/'ansible/mysql-provision.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        options=json.loads(self.cfg.read_text())
        if options['user']!='root':self.skipTest('Root-only provisioning test; runtime tests use the application account')
        module.PORT=options['port']
        module.ROOT_ENV=Path(self.temp.name)/'root.env'
        module.ROOT_ENV.write_text('MYSQL_ROOT_PASSWORD='+options['password']+'\n')
        module.APP_CONFIG=Path(self.temp.name)/'provisioned.json'
        original_private=module.private
        with patch.object(module,'private',side_effect=lambda p,c,g=None:original_private(p,c)), patch('sys.argv',['mysql-provision.py','configure']):module.main()
        with patch.dict(os.environ,DOBHRAP_MYSQL_CONFIG=str(module.APP_CONFIG)):
            with database.connect(create=True) as c:
                app.initialize_business(c)
                c.execute('INSERT INTO records(module,data) VALUES(?,?)',('customers','{}'))
                with self.assertRaises(sqlite3.OperationalError):c._query('CREATE DATABASE `unrelated_application`')
                c._query('DROP DATABASE `'+database.schema_name()+'`')
        before=module.APP_CONFIG.read_bytes()
        with patch('sys.argv',['mysql-provision.py','configure']):module.main()
        self.assertEqual(module.APP_CONFIG.read_bytes(),before)

    def test_password_reset_on_mysql_revokes_sessions(self):
        import password_reset as recovery
        import time
        with app.connect() as c:
            user=c.execute('SELECT * FROM users LIMIT 1').fetchone()
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)',('recovery-session',user['id'],int(time.time())+3600,'csrf'));c.commit()
            result=recovery.authenticated(c,user,dict(current_password='platform-password-1234',email='owner@example.com'),admin=True);c.commit()
            token=result['reset_url'].split('#token=')[1]
            recovery.finish(c,dict(token=token,password='recovered-password-1234',confirm_password='recovered-password-1234'),'test');c.commit()
            self.assertEqual(c.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
            updated=c.execute('SELECT * FROM users LIMIT 1').fetchone()
            self.assertEqual(updated['hash'],app.password('recovered-password-1234',updated['salt']))
            with self.assertRaises(advanced.ServiceError):recovery.finish(c,dict(token=token),'test')
