import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hardfix_routing',ROOT/'ansible/hardfix-routing.py')
repair=importlib.util.module_from_spec(spec);spec.loader.exec_module(repair)

class HardfixOrderingTests(unittest.TestCase):
 def test_recovery_precedes_both_tls_verifications(self):
  import re
  names=re.findall(r'^    - name: (.+)$',(ROOT/'ansible/deploy.yml').read_text(),re.M)
  recovery=names.index('Repair exact-host listener precedence before local and public TLS verification')
  self.assertLess(recovery,names.index('Verify local HTTPS with the correct hostname and certificate'))
  self.assertLess(recovery,names.index('Verify public database-backed startup API'))
 def test_reload_settling_retries_without_disabling_certificate_checks(self):
  with patch.object(repair,'verify',side_effect=[subprocess.CalledProcessError(60,['curl']),None]) as verify,patch.object(repair.time,'sleep'):
   repair.wait_for_verification('127.0.0.1',attempts=2)
  self.assertEqual(verify.call_count,2)
 def test_persistent_mismatch_still_fails(self):
  with patch.object(repair,'verify',side_effect=ValueError('Wrong application')),patch.object(repair.time,'sleep'):
   with self.assertRaises(ValueError):repair.wait_for_verification('127.0.0.1',attempts=2)
