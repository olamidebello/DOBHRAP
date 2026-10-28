import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('loading', Path(__file__).resolve().parents[1] / 'ansible/files/repair-loading.py')
loading = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loading)
class LoadingTests(unittest.TestCase):
    def test_cache_wipe_removed_and_repeat_stable(self):
        source = '''server {\n add_header Clear-Site-Data '"cache"' always;\n add_header Cache-Control "no-store" always;\n location / { proxy_pass http://127.0.0.1:18762; }\n}'''
        updated = loading.optimize(source)
        self.assertNotIn('Clear-Site-Data', updated)
        self.assertIn('Cache-Control "no-store"', updated)
        self.assertIn('gzip on;', updated)
        self.assertEqual(loading.optimize(updated), updated)
        self.assertIn('proxy_pass http://127.0.0.1:18762', updated)
    def test_existing_compression_preserved(self):
        text = 'server {\n gzip off;\n}'
        self.assertEqual(loading.optimize(text), text)
