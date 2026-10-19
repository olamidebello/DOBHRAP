import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app

spec=importlib.util.spec_from_file_location('server_recovery',Path(__file__).resolve().parents[1]/'ansible/recover-password.py')
recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)

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
