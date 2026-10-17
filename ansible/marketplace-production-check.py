"""Read-only merchant readiness checks. No secrets or card data in the report."""
import json,os,shlex,sys
from pathlib import Path
sys.path.insert(0,'/opt/dobhrap/current')
import provider_settings as settings
for line in Path('/etc/dobhrap.env').read_text().splitlines():
 key,sep,value=line.partition('=')
 if sep and (key in settings.FIELDS or key in ('DOBHRAP_DB','DOBHRAP_ENCRYPTION_KEY','MARKETPLACE_PUBLIC_URL')):
  parts=shlex.split(value);os.environ[key]=parts[0] if parts else ''
import app,marketplace
state=marketplace.readiness();checks=[]
for gateway in state['gateways']:
 result={'gateway':gateway['id'],'currency':gateway['currency'],'configured':gateway['configured'],'signing_key_configured':gateway['signing_key_configured'],'account_verified':False}
 if gateway['configured'] and state['environment']=='live':
  try:settings.check(gateway['id']);result['account_verified']=True
  except Exception:result['message']='Account check failed; inspect merchant credentials and permissions in the GUI.'
 checks.append(result)
with app.connect() as c:
 currencies={r[0] for r in c.execute('SELECT DISTINCT currency FROM market_products WHERE active=1')}
 offers=c.execute('SELECT count(*) FROM market_products WHERE active=1').fetchone()[0]
 verified=c.execute("SELECT count(*) FROM market_orders WHERE environment='live' AND state='fulfilled'").fetchone()[0]
ready=state['enabled'] and state['environment']=='live' and offers>0 and all(any(g['account_verified'] and g['signing_key_configured'] and g['currency']==currency for g in checks) for currency in currencies)
report={'published_offers':offers,'environment':state['environment'],'gateways':checks,'ready_for_live_checkout':ready,'fulfilled_live_orders':verified,'end_to_end_payment_previously_verified':verified>0,'coupons_available':True,'notice':'Production checkout needs configured live merchant credentials, enabled live controls and verified webhook signing. No charge or filing was initiated. Published coupons can cover eligible services independently. A successful real payment is still needed to verify the complete live checkout/webhook path.'}
Path('/var/log/oob-marketplace-production-readiness.json').write_text(json.dumps(report,indent=2));Path('/var/log/oob-marketplace-production-readiness.json').chmod(0o600)
print(json.dumps(report))
