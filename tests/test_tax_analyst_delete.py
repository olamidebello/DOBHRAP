import unittest,uuid,time
import app,advanced as a
from tests import test_tax_analyst as fixture
class AnalystDeletionTests(unittest.TestCase):
 setUp=fixture.TaxAnalystTests.setUp
 tearDown=fixture.TaxAnalystTests.tearDown
 call=fixture.TaxAnalystTests.call
 upload=fixture.TaxAnalystTests.upload
 row=fixture.TaxAnalystTests.row
 save=fixture.TaxAnalystTests.save
 build=fixture.TaxAnalystTests.build
 def test_clear_preserves_original_and_snapshots(self):
  d=self.save(self.upload(),[self.row()]);build=self.build()
  cleared=self.call('clear-records',{'id':d['id'],'revision':d['revision'],'confirm':'CLEAR'})
  self.assertEqual(cleared['records'],[]);self.assertEqual(cleared['tax_fields'],[]);self.assertEqual(cleared['revision'],d['revision']+1)
  self.assertTrue(self.call('download',{'id':d['id']})['base64'])
  self.assertEqual(self.call('list')['builds'][0]['id'],build['id'])
  with self.assertRaises(a.ServiceError):self.call('clear-records',{'id':d['id'],'revision':d['revision'],'confirm':'CLEAR'})
 def test_delete_requires_owner_confirmation_and_current_revision(self):
  d=self.upload()
  for payload,owner in (({'id':d['id'],'confirm':'DELETE'},{'id':2,'role':'super_admin'}),({'id':d['id']},self.user),({'id':d['id'],'confirm':'DELETE','revision':999},self.user)):
   with self.assertRaises(a.ServiceError):self.call('delete',payload,user=owner)
  self.assertEqual(len(self.call('list')['documents']),1)
  self.call('delete',{'id':d['id'],'revision':d['revision'],'confirm':'DELETE'})
  with self.assertRaises(a.ServiceError):self.call('download',{'id':d['id']})
 def test_bulk_delete_is_atomic_and_removes_queue(self):
  a1=self.upload(data=b'%PDF-one');a2=self.upload(data=b'%PDF-two')
  with app.connect() as c:c.execute('INSERT INTO tax_analysis_jobs(id,document_id,owner,revision,requested) VALUES(?,?,?,?,?)',(str(uuid.uuid4()),a1['id'],1,1,int(time.time())))
  selected=[{'id':d['id'],'revision':d['revision']} for d in (a1,a2)]
  with self.assertRaises(a.ServiceError):self.call('delete-documents',{'documents':[selected[0],{**selected[1],'revision':999}],'confirm':'DELETE'})
  self.assertEqual(len(self.call('list')['documents']),2)
  result=self.call('delete-documents',{'documents':selected,'confirm':'DELETE'});self.assertEqual(len(result['deleted']),2);self.assertEqual(self.call('list')['documents'],[])
  with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM tax_analysis_jobs').fetchone()[0],0);self.assertEqual(c.execute("SELECT count(*) FROM audit WHERE action LIKE 'Owner deleted tax analyst document %'").fetchone()[0],2)
 def test_running_document_cannot_be_cleared_or_deleted(self):
  d=self.upload()
  with app.connect() as c:c.execute("UPDATE tax_analyst_documents SET state='analyzing' WHERE id=?",(d['id'],))
  for route,body in [('clear-records',{'id':d['id'],'revision':1,'confirm':'CLEAR'}),('delete',{'id':d['id'],'confirm':'DELETE'}),('delete-documents',{'documents':[{'id':d['id'],'revision':1}],'confirm':'DELETE'})]:
   with self.assertRaises(a.ServiceError) as err:self.call(route,body)
   self.assertEqual(err.exception.status,409)
  self.assertEqual(len(self.call('list')['documents']),1)
