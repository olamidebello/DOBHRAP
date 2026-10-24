"""Root-only local commissioning. Never prints service credentials."""
import json, os, re, sys, time
from pathlib import Path
sys.path.insert(0,'/opt/dobhrap/current/ansible')

def main():
 if os.geteuid()!=0:raise RuntimeError('Run as root on hosting')
 from active_runtime import load_active
 app=load_active('oob-business.service')
 import communications as comms, communications_worker as worker, advanced as a
 token_file=Path('/root/dobhrap-sip-bridge-token');sip_ready=False;mail_ready=False;domain='olamideolatayobello.com';actor='';host=''
 with app.connect() as c:
  if token_file.exists():
   if token_file.is_symlink() or token_file.stat().st_uid!=0 or token_file.stat().st_mode&0o077:raise RuntimeError('Bridge token file must be root-only, mode 0600')
   token=token_file.read_text().strip()
   if not re.fullmatch(r'[0-9a-f]{64}',token):raise RuntimeError('Invalid bridge token format')
   c.execute('INSERT OR REPLACE INTO provider_settings VALUES(?,?,?)',('SIP_BRIDGE_TOKEN',a.seal({'value':token}),int(time.time())));sip_ready=True
  else:
   import provider_settings
   sip_ready=bool(provider_settings.get('SIP_BRIDGE_TOKEN'))
  root_policy=Path('/etc/olamidepanel/mail-policy.json')
  if root_policy.exists():
   if root_policy.is_symlink() or root_policy.stat().st_uid!=0 or root_policy.stat().st_mode&0o022:raise RuntimeError('Mail policy must be root-owned and protected')
   p=json.loads(root_policy.read_text());host=p.get('mail_hostname','')
   if domain in p.get('mail_domains',[])+p.get('mail_extra_domains',[]) and re.fullmatch(r'(?:[a-z0-9-]+\.)+[a-z]{2,63}',host):
    db=worker.trusted_module('_comms_panel_db','/opt/olamidepanel/panel/database.py')
    with db.connect() as panel:
     row=panel.execute('SELECT u.username FROM mail_delegations m JOIN users u ON u.id=m.owner WHERE m.domain=? AND u.active=1',(domain,)).fetchone()
     if row:actor=row['username'];mail_ready=True
  if not re.fullmatch(r'[A-Za-z0-9_.@-]*',actor):raise RuntimeError('Invalid panel operator identifier')
  if host and not re.fullmatch(r'(?:[a-z0-9-]+\.)+[a-z]{2,63}',host):raise RuntimeError('Invalid mail hostname')
  c.execute('UPDATE communications_policy SET payload=?,revision=revision+1 WHERE id=1',(json.dumps({'sip_enabled':sip_ready,'mail_enabled':mail_ready}),));a.audit(c,0,'Communications commissioned: SIP '+str(sip_ready)+' mail '+str(mail_ready));c.commit()
 content='COMMS_MAIL_DOMAIN='+domain+'\nCOMMS_MAIL_HOST='+host+'\nCOMMS_MAIL_OPERATOR='+actor+'\n'
 # These are validated server-owned identifiers, never commands.
 if not re.fullmatch(r'[A-Za-z0-9_.@-]*',actor):raise RuntimeError('Invalid panel operator identifier')
 path=Path('/etc/dobhrap-communications.env')
 if path.is_symlink():raise RuntimeError('Refuse symlink configuration')
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:f.write(content)
 os.chmod(path,0o600)
 print(json.dumps({'sip_enabled':sip_ready,'mail_enabled':mail_ready,'mail_domain':domain,'mail_host':host,'mail_operator_delegated':bool(actor),'paid_calls_enabled':False,'delivery_verified':False}))
if __name__=='__main__':main()
