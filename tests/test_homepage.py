import unittest
from urllib.request import Request
from urllib.error import HTTPError
import tests.test_tenants as fixtures
class HomepageTests(unittest.TestCase):
 setUp=fixtures.TenantTests.setUp
 tearDown=fixtures.TenantTests.tearDown
 def test_homepage_and_account_routes(self):
  with self.public.open(self.base+'/') as response:
   page=response.read().decode();self.assertIn('Your next move.',page);self.assertIn('href="/login"',page);self.assertIn('/contracting-opportunities',page);self.assertIn('<video controls',page);self.assertIn('sample data',page);self.assertEqual(response.headers['Cache-Control'],'no-store')
  for path in ('/login','/workspace','/contracting-opportunities','/register','/tax-services'):
   with self.public.open(self.base+path) as response:self.assertIn(b'id="content"',response.read())
 def test_demo_can_be_streamed_and_seeked(self):
  url=self.base+'/assets/platform-demo.mp4'
  with self.public.open(Request(url,headers={'Range':'bytes=0-99'})) as response:
   data=response.read();self.assertEqual(response.status,206);self.assertEqual(len(data),100);self.assertIn(b'ftyp',data);self.assertTrue(response.headers['Content-Range'].startswith('bytes 0-99/'));self.assertEqual(response.headers['Content-Type'],'video/mp4')
  with self.public.open(Request(url,headers={'Range':'bytes=-20'})) as response:self.assertEqual(len(response.read()),20)
  with self.assertRaises(HTTPError) as error:self.public.open(Request(url,headers={'Range':'bytes=999999999-'}))
  self.assertEqual(error.exception.code,416)
  with self.public.open(self.base+'/assets/platform-demo.vtt') as response:self.assertTrue(response.read().startswith(b'WEBVTT'))
