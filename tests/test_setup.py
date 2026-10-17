import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import app


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_db = app.DB
        app.DB = self.temp.name + '/setup.db'
        self.token = 'one-time-server-token-' + 'x' * 32
        self.env = patch.dict(os.environ, {'DOBHRAP_ADMIN_PASSWORD': '', 'DOBHRAP_SETUP_TOKEN': self.token})
        self.env.start()
        app.init()

    def tearDown(self):
        app.DB = self.previous_db
        self.env.stop()
        self.temp.cleanup()

    def payload(self, **changes):
        return dict(token=self.token, email='owner@example.com', password='long-new-password-123', confirm_password='long-new-password-123', **changes)

    def test_first_run_and_irreversible_completion(self):
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0], 0)
            app.setup_account(c, self.payload())
        app.init()
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT role FROM users').fetchone()[0], 'super_admin')
            self.assertEqual(c.execute('SELECT count(*) FROM setup_state').fetchone()[0], 0)
            with self.assertRaises(app.advanced.ServiceError) as error:
                app.setup_account(c, self.payload())
            self.assertEqual(error.exception.status, 409)

    def test_invalid_token_and_password_leave_setup_available(self):
        for key, value in [('token', 'wrong'), ('password', 'short'), ('confirm_password', 'different')]:
            body = self.payload()
            body[key] = value
            with app.connect() as c:
                with self.assertRaises((ValueError, app.advanced.ServiceError)):
                    app.setup_account(c, body)
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0], 0)

    def test_simultaneous_setup_creates_only_one_account(self):
        def create():
            try:
                with app.connect() as c:
                    app.setup_account(c, self.payload())
                return True
            except app.advanced.ServiceError:
                return False
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: create(), range(2)))
        self.assertEqual(sum(results), 1)

    def test_http_setup_and_super_admin_access(self):
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        def request(path, body=None, headers=None):
            return urlopen(Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                   headers={'Content-Type': 'application/json', **(headers or {})}))
        try:
            with request('/api/identity') as response:
                self.assertEqual(json.load(response)['application'], 'oob-business-suite')
            with request('/api/setup/status') as response:
                self.assertTrue(json.load(response)['required'])
            with self.assertRaises(HTTPError) as error:
                request('/api/setup', self.payload())
            self.assertEqual(error.exception.code, 403)
            with request('/api/setup', self.payload(), {'X-Setup-Request': '1'}) as response:
                self.assertEqual(response.status, 201)
            with request('/api/login', {'email': 'owner@example.com', 'password': 'long-new-password-123'}) as response:
                cookie = response.headers['Set-Cookie'].split(';')[0]
                csrf = json.load(response)['csrf']
            with request('/api/users', headers={'Cookie': cookie}) as response:
                self.assertEqual(json.load(response)[0]['role'], 'super_admin')
            with request('/api/advanced/status', headers={'Cookie': cookie}) as response:
                self.assertEqual(response.status, 200)
            with request('/api/setup/status') as response:
                self.assertFalse(json.load(response)['required'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
