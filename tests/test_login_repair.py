import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('login_repair', Path(__file__).resolve().parents[1] / 'ansible/files/repair-fonwuka-login.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)

class LoginRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'users.db'
        self.app = types.SimpleNamespace(connect=self.connect)
        with self.connect() as c:
            c.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT UNIQUE,account_status TEXT,tenant_id INTEGER,role TEXT,salt TEXT,hash TEXT,account_revision INTEGER); CREATE TABLE tenants(id INTEGER,status TEXT); CREATE TABLE sessions(user_id INTEGER); CREATE TABLE password_resets(user_id INTEGER,used INTEGER); INSERT INTO tenants VALUES(1,'active'); INSERT INTO users VALUES(2,'fonwuka@gmail.com','suspended',1,'viewer','old','old',1); INSERT INTO users VALUES(4,'fonwuka1@gmail.com','active',1,'viewer','salt','hash',1);")
    def tearDown(self):
        self.tmp.cleanup()
    def connect(self):
        c = sqlite3.connect(self.db)
        c.row_factory = sqlite3.Row
        return c
    def run_repair(self, remove=True):
        def process(app, owner):
            if remove:
                with self.connect() as c: c.execute('DELETE FROM users WHERE id=?', (owner,))
        with patch('user_data.queue'), patch('user_data.process', side_effect=process), patch('advanced.audit'):
            return repair.repair(self.app, Path(self.tmp.name) / 'backup')
    def test_preserves_password_and_is_idempotent(self):
        self.assertTrue(self.run_repair()['changed'])
        with self.connect() as c:
            row = c.execute('SELECT * FROM users WHERE id=4').fetchone()
            self.assertEqual((row['email'],row['salt'],row['hash']), ('fonwuka@gmail.com','salt','hash'))
        self.assertFalse(self.run_repair()['changed'])
    def test_pending_deletion_does_not_rename(self):
        with self.assertRaises(RuntimeError): self.run_repair(False)
        with self.connect() as c: self.assertEqual(c.execute('SELECT email FROM users WHERE id=4').fetchone()[0], 'fonwuka1@gmail.com')
    def test_wrong_duplicate_refused_before_backup(self):
        with self.connect() as c: c.execute("UPDATE users SET email='someone@example.com' WHERE id=2")
        with self.assertRaises(RuntimeError): self.run_repair()
        self.assertFalse((Path(self.tmp.name) / 'backup').exists())
