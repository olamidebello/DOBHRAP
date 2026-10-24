"""Derive private mail provisioning inputs from the installed panel and application."""
import json,os,re,sys
from pathlib import Path
sys.path.insert(0,'/opt/dobhrap/current/ansible')
DOMAIN='olamideolatayobello.com'

def private_json(path):
 p=Path(path)
 if not p.exists():return {}
 if p.is_symlink() or p.stat().st_uid!=0 or p.stat().st_mode&0o077:raise RuntimeError('Mail configuration must be root-only: '+path)
 value=json.loads(p.read_text())
 if not isinstance(value,dict):raise RuntimeError('Mail configuration must be an object')
 return value

def main():
 if os.geteuid()!=0:raise RuntimeError('Run on the application host as root')
 from active_runtime import load_active
 app=load_active('oob-business.service')
 from communications_worker import trusted_module
 db=trusted_module('_dobhrap_panel_mail_db','/opt/olamidepanel/panel/database.py')
 prior=private_json('/etc/olamidepanel/mail-policy.json');bootstrap=private_json('/etc/olamidepanel/mail-bootstrap-policy.json');override=private_json('/etc/dobhrap-panel-mail-overrides.json')
 with db.connect() as c:
  if not c.execute('SELECT name FROM domains WHERE name=?',(DOMAIN,)).fetchone():raise RuntimeError('Add the application domain to OlamidePanel before provisioning its mail')
  requested=override.get('mail_operator_username')
  if requested:operator=c.execute("SELECT username FROM users WHERE username=? AND active=1 AND role IN ('root','super_admin')",(requested,)).fetchone()
  else:operator=c.execute("SELECT username FROM users WHERE active=1 AND role IN ('root','super_admin') ORDER BY id LIMIT 1").fetchone()
  if not operator:raise RuntimeError('An active OlamidePanel root or super administrator is required')
 with app.connect() as c:
  admin=c.execute("SELECT email FROM users WHERE role='super_admin' ORDER BY id LIMIT 1").fetchone()
 host=override.get('mail_hostname') or prior.get('mail_hostname') or bootstrap.get('mail_hostname') or 'mail.olamideolatayobello.com'
 email=override.get('panel_acme_email') or (admin['email'] if admin else '')
 if not re.fullmatch(r'(?:[a-z0-9-]+\.)+[a-z]{2,63}',host) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise RuntimeError('Set valid mail_hostname and panel_acme_email in the private overrides file')
 values=dict(bootstrap,**override)
 values.update(mail_operator_username=operator['username'],mail_hostname=host,panel_acme_email=email,panel_public_ipv4=override.get('panel_public_ipv4',bootstrap.get('panel_public_ipv4','154.16.170.86')),hosting_enable_email=True,mail_target_domains=[DOMAIN],mail_extra_domains=sorted(set(prior.get('mail_extra_domains',[])+prior.get('mail_domains',[])+[DOMAIN])),mail_domains_source=prior.get('mail_domains_source','inventory'),mail_domains=prior.get('mail_domains',[]),mail_selector=prior.get('mail_selector','panel'))
 values.setdefault('mail_dns',{'mode':'manual'});values.setdefault('mail_reverse_dns',{'mode':'manual'});values.setdefault('mail_bootstrap_localparts',['postmaster','abuse','support'])
 target=Path('/etc/dobhrap-panel-mail.json')
 if target.is_symlink():raise RuntimeError('Refuse symlink for private mail inputs')
 import tempfile
 fd,temp=tempfile.mkstemp(dir='/etc',prefix='.dobhrap-mail-')
 try:
  os.fchmod(fd,0o600)
  with os.fdopen(fd,'w') as f:json.dump(values,f)
  os.replace(temp,target)
 finally:
  if os.path.exists(temp):os.unlink(temp)
 print('Private OlamidePanel mail inputs prepared; no credentials printed')
if __name__=='__main__':main()
