import json,tempfile,threading,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from health_native.__main__ import Handler
from health_native.reader import HealthReader
class ServerTests(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  c.d=Path(tempfile.mkdtemp());(c.d/'index.html').write_text('ok');c.s=ThreadingHTTPServer(('127.0.0.1',0),Handler);c.s.reader=HealthReader([c.d/'missing']);c.s.web_dir=c.d;threading.Thread(target=c.s.serve_forever,daemon=True).start();c.base='http://127.0.0.1:%d'%c.s.server_port
 @classmethod
 def tearDownClass(c):c.s.shutdown()
 def q(self,p,h=None,m='GET'):
  try:return urlopen(Request(self.base+p,headers=h or {},method=m))
  except HTTPError as e:return e
 def test_security(self):
  r=self.q('/api/health');self.assertEqual(r.status,200);self.assertEqual(r.headers['Cache-Control'],'no-store');self.assertEqual(json.loads(r.read())['mode'],'local');self.assertEqual(self.q('/api/health',{'Host':'evil.test'}).status,403);self.assertEqual(self.q('/api/health',{'Origin':'http://evil.test'}).status,403);self.assertEqual(self.q('/api/health',m='POST').status,405)
  self.assertEqual(self.q('/api/health',{'Origin':self.base}).status,200); self.assertEqual(self.q('/api/health',{'Host':'127.0.0.1:1'}).status,403); self.assertEqual(self.q('/%2e%2e/%2e%2e/etc/passwd').status,404)
  self.assertEqual(self.q('/api/health?file=/etc/passwd').status,400)
  self.assertEqual(self.q('/api/health',{'Sec-Fetch-Site':'cross-site'}).status,403)
  self.assertEqual(self.q('/api/health',m='PUT').status,405)
  self.assertIn("Content-Security-Policy", self.q('/').headers)
  self.assertEqual(self.q('/does-not-exist').status,404)
if __name__=='__main__':unittest.main()
