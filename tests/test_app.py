import os,tempfile,unittest,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import app
class LedgerTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); app.DB=self.temp.name+'/test.db'; os.environ['DOBHRAP_ADMIN_PASSWORD']='test-password-long-enough'; app.init()
 def tearDown(self):self.temp.cleanup()
 def test_balanced_posting(self):
  with app.connect() as c:
   app.post_journal(c,'Sale',[{'account':'1000','debit':2500,'credit':0},{'account':'4000','debit':0,'credit':2500}])
   self.assertEqual(c.execute('SELECT sum(debit)-sum(credit) FROM lines').fetchone()[0],0)
 def test_unbalanced_rejected(self):
  with app.connect() as c:
   with self.assertRaises(ValueError):app.post_journal(c,'Invalid',[{'account':'1000','debit':2500,'credit':0},{'account':'4000','debit':0,'credit':2400}])
   self.assertEqual(c.execute('SELECT count(*) FROM journals').fetchone()[0],0)
 def test_negative_rejected(self):
  with app.connect() as c:
   with self.assertRaises(ValueError):app.post_journal(c,'Invalid',[{'account':'1000','debit':-1,'credit':0},{'account':'4000','debit':0,'credit':-1}])
if __name__=='__main__':unittest.main()
