import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app

spec=importlib.util.spec_from_file_location('server_recovery',Path(__file__).resolve().parents[1]/'ansible/recover-password.py')
recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)
spec=importlib.util.spec_from_file_location('active_runtime',Path(__file__).resolve().parents[1]/'ansible/active_runtime.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)

class ServerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=self.temp.name+'/test.db'
        self.env=patch.dict(os.environ,DOBHRAP_DB_BACKEND='sqlite',DOBHRAP_ADMIN_EMAIL='owner@example.com',DOBHRAP_ADMIN_PASSWORD='original-password-1234');self.env.start();app.init()
    def tearDown(self):self.env.stop();app.DB=self.old;self.temp.cleanup()
    def test_private_link_preserves_password_and_can_complete_recovery(self):
        import password_reset
        output=Path(self.temp.name)/'link.txt'
        with app.connect() as c:
            before=dict(c.execute('SELECT * FROM users').fetchone())
            recovery.issue_recovery(c,'OWNER@example.com',output)
            after=dict(c.execute('SELECT * FROM users').fetchone())
            self.assertEqual(before,after)
            self.assertEqual(output.stat().st_mode&0o777,0o600)
            token=output.read_text().strip().split('#token=')[1]
            self.assertNotIn(token,c.execute('SELECT token_hash FROM password_resets').fetchone()[0])
            password_reset.finish(c,dict(token=token,password='recovered-password-1234',confirm_password='recovered-password-1234'),'test');c.commit()
            user=c.execute('SELECT * FROM users').fetchone()
            self.assertEqual(user['hash'],app.password('recovered-password-1234',user['salt']))
    def test_unknown_account_does_not_create_link(self):
        output=Path(self.temp.name)/'link.txt'
        with app.connect() as c:
            with self.assertRaises(ValueError):recovery.issue_recovery(c,'missing@example.com',output)
            self.assertFalse(output.exists())
            self.assertEqual(c.execute('SELECT count(*) FROM password_resets').fetchone()[0],0)

    def test_missing_tables_repaired_idempotently_without_changing_accounts(self):
        with app.connect() as c:
            before=dict(c.execute('SELECT * FROM users').fetchone())
            c.execute('DROP TABLE password_resets')
            c.execute('DROP TABLE password_reset_limits')
        for _ in range(2):
            self.assertEqual(runtime.maintain(app,'migrate')['backend'],'sqlite')
        self.assertTrue(runtime.maintain(app,'verify')['ok'])
        with app.connect() as c:
            self.assertEqual(before,dict(c.execute('SELECT * FROM users').fetchone()))

    def fake_process(self, environment):
        root=Path(self.temp.name)/'proc';process=root/'123';process.mkdir(parents=True)
        (process/'cwd').symlink_to(self.temp.name,target_is_directory=True)
        (process/'cmdline').write_bytes(b'python\0/opt/dobhrap/current/app.py\0')
        (process/'environ').write_bytes(b'\0'.join((k+'='+v).encode() for k,v in environment.items()))
        return root

    def test_live_mysql_takes_precedence_over_leftover_sqlite_path(self):
        config=Path(self.temp.name)/'mysql.json';config.write_text('{}')
        root=self.fake_process({'DOBHRAP_DB_BACKEND':'mysql','DOBHRAP_MYSQL_CONFIG':str(config),'DOBHRAP_DB':'/missing/stale.db'})
        with patch.object(runtime.subprocess,'check_output',return_value='123\n'):
            _,env=runtime.runtime(proc_root=root)
        self.assertEqual(env['DOBHRAP_DB_BACKEND'],'mysql')

    def test_missing_live_sqlite_database_is_never_created(self):
        root=self.fake_process({'DOBHRAP_DB':'missing.db'})
        with patch.object(runtime.subprocess,'check_output',return_value='123\n'):
            with self.assertRaises(RuntimeError):runtime.runtime(proc_root=root)
        self.assertFalse((Path(self.temp.name)/'missing.db').exists())
    def test_live_provider_environment_is_preserved_without_stale_local_keys(self):
        import sys
        original_cwd=Path.cwd();original_path=list(sys.path)
        try:
            with patch.dict(os.environ,{'OPENAI_API_KEY':'synthetic-stale','TAX_ANALYST_MODEL':'stale'}):
                with patch.object(runtime,'runtime',return_value=(Path(self.temp.name),{
                    'DOBHRAP_DB':app.DB,'DOBHRAP_DB_BACKEND':'sqlite',
                    'OPENAI_API_KEY':'synthetic-live','TAX_AI_MODEL':'synthetic-document-model'})):
                    runtime.load_active()
                self.assertEqual(os.environ['OPENAI_API_KEY'],'synthetic-live')
                self.assertEqual(os.environ['TAX_AI_MODEL'],'synthetic-document-model')
                self.assertNotIn('TAX_ANALYST_MODEL',os.environ)
        finally:
            os.chdir(original_cwd);sys.path[:]=original_path

