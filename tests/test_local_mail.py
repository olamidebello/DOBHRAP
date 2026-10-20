import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('local_readiness',Path(__file__).resolve().parents[1]/'ansible/local-mail-readiness.py')
readiness=importlib.util.module_from_spec(spec);spec.loader.exec_module(readiness)


class LocalMailTests(unittest.TestCase):
    def test_dkim_public_record_chunks_are_joined(self):
        raw='oob._domainkey IN TXT ( "v=DKIM1; h=sha256; k=rsa; "\n "p=PUBLICKEY" ) ; public only'
        self.assertEqual(readiness.public_record(raw),'v=DKIM1; h=sha256; k=rsa; p=PUBLICKEY')
    def test_missing_public_record_is_not_replaced_with_a_new_key(self):
        with self.assertRaises(ValueError):readiness.public_record('missing')
