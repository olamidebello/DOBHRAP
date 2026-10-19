import hashlib
import os
import tempfile
import time
import unittest
from unittest.mock import patch
import app
import password_reset as r

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=app.DB;app.DB=self.temp.name+'/test.db'
        self.env=patch.dict(os.environ,DOBHRAP_DB_BACKEND='sqlite',DOBHRAP_ADMIN_PASSWORD='initial-password-123',DOBHRAP_ADMIN_EMAIL='owner@example.com');self.env.start();app.init()
        with app.connect() as c:
            c.execute("UPDATE users SET role='super_admin'")
            self.user=dict(c.execute('SELECT * FROM users').fetchone())
        self.mail=patch.object(r,'mail_config',return_value={});self.mail.start()
    def tearDown(self):self.mail.stop();self.env.stop();app.DB=self.old;self.temp.cleanup()
    def test_single_use_hash_only_and_session_revocation(self):
        with app.connect() as c:
            c.execute("INSERT INTO sessions VALUES('session',1,9999999999,'csrf')")
            token,digest=r.issue(c,1,int(time.time()));c.commit()
            self.assertNotEqual(digest,token)
            self.assertEqual(c.execute('SELECT token_hash FROM password_resets').fetchone()[0],hashlib.sha256(token.encode()).hexdigest())
            r.finish(c,dict(token=token,password='new-password-12345',confirm_password='new-password-12345'),'ip');c.commit()
            self.assertEqual(c.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
            user=c.execute('SELECT * FROM users').fetchone()
            self.assertEqual(user['hash'],app.password('new-password-12345',user['salt']))
            with self.assertRaises(app.advanced.ServiceError):r.finish(c,dict(token=token),'ip')
    def test_expired_and_mismatched_passwords_rejected(self):
        with app.connect() as c:
            token,_=r.issue(c,1,int(time.time())-1000);c.commit()
            with self.assertRaises(app.advanced.ServiceError):r.finish(c,dict(token=token),'ip')
            token,_=r.issue(c,1,int(time.time()));c.commit()
            with self.assertRaises(app.advanced.ServiceError):r.finish(c,dict(token=token,password='long-new-password',confirm_password='different'),'ip')
    def test_unknown_email_has_same_response_and_rate_limit(self):
        with patch.object(r,'send_email') as send:
            with app.connect() as c:
                known=r.request(c,dict(email='owner@example.com'),'ip');c.commit()
                unknown=r.request(c,dict(email='missing@example.com'),'ip');c.commit()
                self.assertEqual(known,unknown);self.assertEqual(send.call_count,1)
                for _ in range(2):r.request(c,dict(email='owner@example.com'),'ip');c.commit()
                with self.assertRaises(app.advanced.ServiceError) as error:r.request(c,dict(email='owner@example.com'),'ip')
                self.assertEqual(error.exception.status,429)
    def test_admin_scope_and_current_password(self):
        with app.connect() as c:
            with self.assertRaises(app.advanced.ServiceError):r.authenticated(c,self.user,dict(current_password='wrong',email='owner@example.com'),True)
            result=r.authenticated(c,self.user,dict(current_password='initial-password-123',email='owner@example.com'),True)
            self.assertIn('/reset-password#token=',result['reset_url'])
            c.commit()
            forged={**self.user,'role':'admin','tenant_id':2}
            with self.assertRaises(app.advanced.ServiceError):r.authenticated(c,forged,dict(current_password='initial-password-123',email='owner@example.com'),True)
    def test_delivery_failure_revokes_token(self):
        with patch.object(r,'send_email',side_effect=OSError('private provider failure')):
            with app.connect() as c:
                result=r.request(c,dict(email='owner@example.com'),'ip');c.commit()
                row=c.execute('SELECT used,delivery FROM password_resets').fetchone()
                self.assertEqual((row['used'],row['delivery']),(1,'failed'))
                self.assertEqual(result['message'],r.GENERIC)
    def test_http_admin_and_public_completion_are_connected(self):
        import http.cookiejar,json,threading
        from urllib.request import Request,build_opener,HTTPCookieProcessor
        from urllib.error import HTTPError
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        client=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def call(path,data=None,headers=None):
            req=Request('http://127.0.0.1:%d'%server.server_port+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
            with client.open(req) as response:return json.load(response)
        try:
            csrf=call('/api/login',dict(email='owner@example.com',password='initial-password-123'))['csrf']
            with client.open('http://127.0.0.1:%d/forgot-password'%server.server_port) as response:self.assertIn(b'password-reset.js',response.read())
            result=call('/api/password-reset/admin',dict(email='owner@example.com',current_password='initial-password-123'),{'X-CSRF-Token':csrf})
            token=result['reset_url'].split('#token=')[1]
            body=dict(token=token,password='http-recovered-12345',confirm_password='http-recovered-12345')
            with self.assertRaises(HTTPError) as error:call('/api/password-reset/complete',body)
            self.assertEqual(error.exception.code,403)
            self.assertTrue(call('/api/password-reset/complete',body,{'X-Password-Reset-Request':'1'})['ok'])
            with self.assertRaises(HTTPError) as error:call('/api/me')
            self.assertEqual(error.exception.code,401)
            self.assertIn('csrf',call('/api/login',dict(email='owner@example.com',password='http-recovered-12345')))
        finally:server.shutdown();server.server_close();thread.join()
