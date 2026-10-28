"""Restore exact OOB hostname on all active listener address groups."""
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import time

DOMAIN='olamideolatayobello.com'
DEST=Path('/etc/nginx/conf.d/00-oob-hardfix.conf')
ROOT=Path('/var/log/oob-hardfix')

def run(args):return subprocess.run(args,check=True,capture_output=True,text=True,timeout=30).stdout

def listeners(dump):
 result={'80':set(), '443':set()}
 for address,port in re.findall(r'\blisten\s+(\[[0-9a-fA-F:]+\]|[0-9]+(?:\.[0-9]+){3}):(80|443)\b',dump):
  ipaddress.ip_address(address.strip('[]'))
  
  if address!='0.0.0.0':result[port].add(address)
 return result

CLEANUP="""self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil((async()=>{
for(const key of await caches.keys())await caches.delete(key);
await self.registration.unregister();
for(const client of await self.clients.matchAll({type:'window'}))client.navigate(client.url);
})()));
"""
def configuration(port, addresses):
 cert='/etc/letsencrypt/live/'+DOMAIN
 clear=CLEANUP.replace('\\','\\\\').replace("'","\\'").replace('\n','\\n')
 text='# Managed OOB domain routing; preserves other hostnames\n'
 for network in ('80','443'):
  tls=' ssl' if network=='443' else ''
  text+='server {\n listen '+network+tls+';\n'
  # Explicit IP listeners outrank wildcard groups even with the same Host/SNI.
  for address in sorted(addresses[network]):text+=' listen '+address+':'+network+tls+';\n'
  text+=' server_name '+DOMAIN+';\n'
  if network=='80':text+=' return 301 https://'+DOMAIN+'$request_uri;\n}\n';continue
  text+=' ssl_certificate '+cert+'/fullchain.pem;\n ssl_certificate_key '+cert+'/privkey.pem;\n'
  text+=' client_max_body_size 25m;\n add_header Cache-Control "no-store" always;\n'
  for path in ('/sw.js','/service-worker.js'):
   text+=" location = "+path+" { default_type application/javascript; return 200 '"+clear+"'; }\n"
  text+=' location / { proxy_pass http://127.0.0.1:'+str(port)+';\n proxy_set_header Host $host;\n proxy_set_header X-Real-IP $remote_addr;\n proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n proxy_set_header X-Forwarded-Proto $scheme;\n }\n}\n'
 return text

def verify(address=None):
 base=['curl','--noproxy','*','-fsS','--max-time','10']
 if address:base+=['--resolve',DOMAIN+':443:'+address]
 body=run(base+['https://'+DOMAIN+'/'])
 if '<title>Olamide Olatayo Bello | Business Suite</title>' not in body or '<title>OlamidePanel' in body:raise ValueError('Root HTML is not the business suite')
 identity=json.loads(run(base+['https://'+DOMAIN+'/api/identity']))
 if identity.get('application')!='oob-business-suite':raise ValueError('Wrong API identity')
 setup=json.loads(run(base+['https://'+DOMAIN+'/api/setup/status']))
 if setup.get('required') is not False:raise ValueError('Existing business setup not found')


def wait_for_verification(address=None, attempts=12):
 # Nginx reload is asynchronous: old workers can briefly serve the old certificate.
 # Each attempt keeps certificate and application identity validation enabled.
 for attempt in range(attempts):
  try:
   verify(address)
   return
  except (subprocess.SubprocessError, ValueError):
   if attempt+1==attempts:raise
   time.sleep(1)

def main():
 ROOT.mkdir(mode=0o700,parents=True,exist_ok=True);backup=ROOT/str(time.time_ns());backup.mkdir(mode=0o700)
 report={'verified':False,'backup':str(backup)};originals={};existed=DEST.exists();old=DEST.read_text() if existed else None;started=False
 try:
  port=int(Path('/etc/oob-business.port').read_text().strip())
  if not 1024<port<65536:raise ValueError('Invalid dedicated port')
  if json.loads(run(['curl','--noproxy','*','-fsS','--max-time','10','http://127.0.0.1:'+str(port)+'/api/identity'])).get('application')!='oob-business-suite':raise ValueError('Private application mismatch')
  dump=run(['nginx','-T']);(backup/'nginx-before.txt').write_text(dump)
  if DEST.is_symlink():raise ValueError('Refuse managed configuration symlink')
  if existed and not old.startswith('# Managed OOB domain routing;'):raise ValueError('Managed path belongs to unrelated configuration')
  spec=importlib.util.spec_from_file_location('retire',Path(__file__).with_name('retire-domain.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  started=True
  for name in re.findall(r'^# configuration file (.+):\s*$',dump,re.M):
   path=Path(name).resolve()
   if not path.is_relative_to('/etc/nginx') or path==DEST:continue
   text=path.read_text();new=module.without_domain(text,DOMAIN)
   if text!=new:
    originals[path]=text;target=backup/str(path).lstrip('/');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text);path.write_text(new)
  DEST.write_text(configuration(port,listeners(dump)));DEST.chmod(0o644)
  after=run(['nginx','-T'])
  if '# configuration file '+str(DEST)+':' not in after:raise ValueError('conf.d is not loaded; configuration not activated')
  run(['nginx','-t']);run(['systemctl','reload','nginx'])
  wait_for_verification('127.0.0.1')
  # Verify each explicit IPv4 group too, not only the wildcard loopback listener.
  for addr in listeners(dump)['443']:
   if ':' not in addr and addr!='0.0.0.0':wait_for_verification(addr)
  report['local_verified']=True
  wait_for_verification();report.update(verified=True,domain=DOMAIN,port=port)
 except Exception as error:
  report['error']=str(error) if isinstance(error,ValueError) else type(error).__name__
  # Keep locally verified repair if only public DNS/network access fails.
  if started and not report.get('local_verified'):
   for path,text in originals.items():path.write_text(text)
   if existed:DEST.write_text(old)
   else:DEST.unlink(missing_ok=True)
   try:run(['nginx','-t']);run(['systemctl','reload','nginx']);report['rolled_back']=True
   except Exception:report['rolled_back']=False
 (ROOT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
 return 0 if report['verified'] else 1
if __name__=='__main__':raise SystemExit(main())
