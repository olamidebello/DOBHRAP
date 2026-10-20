import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import app
import password_reset as recovery
import provider_settings as settings
from cryptography.fernet import Fernet

spec=importlib.util.spec_from_file_location('smtp_setup',Path(__file__).resolve().parents[1]/'ansible/configure-smtp.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)


class SMTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=self.temp.name+'/test.db'
        self.env=patch.dict(os.environ,{'DOBHRAP_DB_BACKEND':'sqlite',
            'DOBHRAP_ADMIN_PASSWORD':'smtp-test-owner-password',
            'DOBHRAP_ENCRYPTION_KEY':Fernet.generate_key().decode()})
        self.env.start();app.init()
        self.config={'HOST':'smtp.example.com','PORT':587,'USERNAME':'owner@example.com',
                     'PASSWORD':'test-provider-secret','FROM':'owner@example.com','SECURITY':'starttls'}
    def tearDown(self):
        self.env.stop();app.DB=self.old;self.temp.cleanup()
    def test_starttls_before_auth_and_no_message_on_check(self):
        client=MagicMock();client.__enter__.return_value=client;client.noop.return_value=(250,b'OK')
        with patch.object(recovery.smtplib,'SMTP',return_value=client):
            result=recovery.check_mail_connection(self.config)
        self.assertTrue(result['ok']);client.send_message.assert_not_called()
        methods=[call[0] for call in client.method_calls]
        self.assertLess(methods.index('starttls'),methods.index('login'))
        self.assertTrue(client.starttls.call_args.kwargs['context'].check_hostname)
    def test_implicit_tls_and_failure_closes_connection(self):
        client=MagicMock()
        with patch.object(recovery.smtplib,'SMTP_SSL',return_value=client) as tls:
            recovery.smtp_connection({**self.config,'PORT':465,'SECURITY':'tls'})
        self.assertTrue(tls.call_args.kwargs['context'].check_hostname)
        client.starttls.assert_not_called()
        client.login.side_effect=RuntimeError('private server response')
        with patch.object(recovery.smtplib,'SMTP',return_value=client):
            with self.assertRaises(RuntimeError):recovery.smtp_connection(self.config)
        client.close.assert_called_once()
    def test_setup_encrypts_and_preserves_saved_secret_on_blank(self):
        supplied={'SMTP_'+key:str(value) for key,value in self.config.items()}
        with patch.object(recovery,'check_mail_connection',return_value={'ok':True,'message':'Verified'}):
            setup.configure(app,supplied)
            setup.configure(app,{'SMTP_PASSWORD':''})
        self.assertEqual(settings.get('SMTP_PASSWORD'),self.config['PASSWORD'])
        with app.connect() as c:
            row=c.execute("SELECT value FROM provider_settings WHERE key='SMTP_PASSWORD'").fetchone()
            self.assertNotIn(self.config['PASSWORD'],row[0])
            snapshot=settings.snapshot(c)
            self.assertNotIn('value',snapshot['settings']['SMTP_PASSWORD'])
    def test_failed_verification_preserves_existing_configuration(self):
        supplied={'SMTP_'+key:str(value) for key,value in self.config.items()}
        with patch.object(recovery,'check_mail_connection',return_value={'ok':True,'message':'Verified'}):setup.configure(app,supplied)
        with patch.object(recovery,'check_mail_connection',side_effect=OSError('private failure')):
            with self.assertRaises(OSError):setup.configure(app,{'SMTP_PASSWORD':'replacement'})
        self.assertEqual(settings.get('SMTP_PASSWORD'),self.config['PASSWORD'])
    def test_gui_smtp_check_uses_saved_settings(self):
        with patch.object(recovery,'check_mail_connection',return_value={'ok':True,'message':'Verified'}) as check:
            with app.connect() as c:
                user=dict(c.execute('SELECT * FROM users').fetchone());user['role']='super_admin'
                result=settings.dispatch('/api/provider-settings','POST',c=c,user=user,
                    body={'action':'test','provider':'smtp','confirm_password':'smtp-test-owner-password'})
                self.assertTrue(result['ok']);check.assert_called_once()
                self.assertEqual(c.execute("SELECT ok FROM provider_checks WHERE provider='smtp'").fetchone()[0],1)
