"""Import an existing SAM.gov-issued key privately and test the installed adapter."""
import json,os,re,sys,time
from pathlib import Path
sys.path.insert(0,'/opt/dobhrap/current/ansible')
def main():
 if os.geteuid()!=0:raise RuntimeError('Run as root on the application host')
 from active_runtime import load_active
 app=load_active('oob-business.service')
 import advanced as a,provider_settings as settings
 keyfile=Path('/root/dobhrap-sam-api-key');key=None
 if keyfile.exists():
  if keyfile.is_symlink() or keyfile.stat().st_uid!=0 or keyfile.stat().st_mode&0o077:raise RuntimeError('SAM key file must be root-owned and mode 0600')
  key=keyfile.read_text().strip()
  if not re.fullmatch('[A-Za-z0-9_-]{16,256}',key):raise RuntimeError('Invalid SAM key file format')
 with app.connect() as c:
  if key:c.execute('INSERT OR REPLACE INTO provider_settings VALUES(?,?,?)',('SAM_API_KEY',a.seal({'value':key}),int(time.time())))
 configured=bool(settings.get('SAM_API_KEY'));ready=False
 if configured:
  try:settings.check('sam');ready=True
  except a.ServiceError:pass
 with app.connect() as c:
  c.execute('UPDATE business_sam_policy SET enabled=?,revision=revision+1 WHERE id=1',(int(ready),))
  c.execute('INSERT OR REPLACE INTO provider_checks(provider,ok,checked,message,duration_ms) VALUES(?,?,?,?,0)',('sam',int(ready),int(time.time()),'SAM.gov connection verified' if ready else 'Save a SAM.gov-issued API key and test access in the SAM.gov admin console'))
  a.audit(c,0,'SAM commissioning completed; key configured '+str(configured)+' ready '+str(ready))
 print(json.dumps({'key_configured':configured,'connection_verified':ready,'key_created':False,'notice':'SAM.gov issues the API key in your own Account Details. Existing keys are reused without disclosure.'}))
if __name__=='__main__':main()
