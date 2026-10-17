"""Root-run post-deployment provisioning; output contains no secret values."""
import json
import os
from pathlib import Path
import secrets
import shlex
import sys
import time

if os.geteuid()!=0:raise SystemExit('Run through the root-owned provisioning playbook')
sys.path.insert(0,'/opt/dobhrap/current')
import provider_settings as settings
# Parse systemd EnvironmentFile values as data. Never source it as shell code.
for line in Path('/etc/dobhrap.env').read_text().splitlines():
 key,sep,value=line.partition('=')
 if sep and (key in settings.FIELDS or key in ('DOBHRAP_DB','DOBHRAP_ENCRYPTION_KEY','MARKETPLACE_PUBLIC_URL')):
  parts=shlex.split(value);os.environ[key]=parts[0] if parts else ''
sys.path.insert(0,'/opt/dobhrap/current')
import app
import advanced as a
import provider_settings as settings

with app.connect() as c:
 settings.initialize(c)
 if not c.execute("SELECT 1 FROM provider_settings WHERE key='SUPPORT_WEBHOOK_TOKEN'").fetchone():
  token_path=Path('/etc/oob-support-intake.token')
  if not token_path.exists():
   fd=os.open(token_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(48)+'\n')
  token=token_path.read_text().strip()
  c.execute('INSERT INTO provider_settings VALUES(?,?,?)',('SUPPORT_WEBHOOK_TOKEN',a.seal({'value':token}),int(time.time())))
 c.commit()
 checks=[]
 for provider,field in [('openai','OPENAI_API_KEY'),('stripe','STRIPE_SECRET_KEY'),('paystack','PAYSTACK_SECRET_KEY'),('plaid','PLAID_SECRET')]:
  if not settings.get(field):continue
  started=time.monotonic()
  try:result=settings.check(provider)
  except Exception:result={'ok':False,'message':'Provider check failed. Review credentials, environment and access in the GUI.'}
  elapsed=int((time.monotonic()-started)*1000)
  c.execute('INSERT OR REPLACE INTO provider_checks VALUES(?,?,?,?,?)',(provider,int(result['ok']),int(time.time()),result['message'],elapsed));c.commit()
  checks.append({'provider':provider,'ok':result['ok'],'duration_ms':elapsed})
 report={'api_checks':checks,'checked':int(time.time()),'application_keys_generated':True,
         'provider_keys_must_be_issued_by_provider':True,'configured':{name:item['configured'] for name,item in settings.snapshot(c)['settings'].items()},
         'super_admin_gui':'https://olamideolatayobello.com/','api_diagnostics':'Provider provisioning & keys -> Profile API readiness & queues',
         'support_intake':'https://olamideolatayobello.com/api/support/intake'}
 path=Path('/var/log/oob-provision-readiness.json');fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:json.dump(report,f,indent=2)
 print(json.dumps({'ready':True,'report':str(path),'provider_gui_ready':True,'support_intake_key_generated':True}))
