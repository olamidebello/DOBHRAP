import contextlib,importlib.util,io,json,os,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
spec=importlib.util.spec_from_file_location('panel_mail_setup',Path(__file__).resolve().parents[1]/'ansible/prepare-panel-mail.py');setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)
class PanelMailSetupTests(unittest.TestCase):
 def test_inputs_preserve_existing_domains_dns_and_private_credentials(self):
  panel=MagicMock();panel.execute.return_value.fetchone.side_effect=[{'name':setup.DOMAIN},{'username':'existing-admin'}]
  db=MagicMock();db.connect.return_value.__enter__.return_value=panel
  app=MagicMock();app.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'email':'admin@example.com'}
  prior={'mail_hostname':'mail.example.com','mail_extra_domains':['other.example.com'],'mail_domains_source':'panel'};bootstrap={'mail_dns':{'mode':'namecheap','secret':'private-test-secret'}}
  def read(path):return prior if path.endswith('mail-policy.json') else bootstrap if path.endswith('mail-bootstrap-policy.json') else {}
  with tempfile.TemporaryDirectory() as directory:
   fd,path=tempfile.mkstemp(dir=directory);written={}
   def replace(src,dest):written.update(json.loads(Path(src).read_text()))
   with patch.dict(sys.modules,{'active_runtime':types.SimpleNamespace(load_active=lambda service:app)}),patch('communications_worker.trusted_module',return_value=db),patch.object(setup,'private_json',side_effect=read),patch('os.geteuid',return_value=0),patch('tempfile.mkstemp',return_value=(fd,path)),patch('os.replace',side_effect=replace),contextlib.redirect_stdout(io.StringIO()) as out:
    setup.main()
   self.assertEqual(written['mail_target_domains'],[setup.DOMAIN]);self.assertIn('other.example.com',written['mail_extra_domains']);self.assertEqual(written['mail_dns']['secret'],'private-test-secret');self.assertNotIn('private-test-secret',out.getvalue());self.assertEqual(written['mail_operator_username'],'existing-admin')
 def test_private_inputs_refuse_group_readable_files(self):
  with tempfile.NamedTemporaryFile() as f:
   os.chmod(f.name,0o644)
   with self.assertRaises(RuntimeError):setup.private_json(f.name)
