"""Fixed-operation root broker for managed email and remote SIP. No paid provisioning."""
import fcntl, importlib.util, json, os, pwd, re, smtplib, ssl, sys, time
from functools import wraps
from email.message import EmailMessage
from pathlib import Path
import advanced as a
import communications as comms


def trusted_module(name,path):
 path=Path(path).resolve()
 for item in (path,*path.parents):
  if str(item)=='/':break
  st=item.stat()
  if st.st_uid!=0 or st.st_mode&0o022:raise RuntimeError('Panel provisioning sources must be root-owned and not writable by other accounts')
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def root_mail_operation(fn):
 @wraps(fn)
 def call(*args,**kwargs):
  previous=os.geteuid()
  try:
   os.seteuid(0)
   return fn(*args,**kwargs)
  finally:os.seteuid(previous)
 return call

@root_mail_operation
def mailbox(c,r,p,instance):
 domain=os.environ.get('COMMS_MAIL_DOMAIN','');host=os.environ.get('COMMS_MAIL_HOST','');actor=os.environ.get('COMMS_MAIL_OPERATOR','')
 if not re.fullmatch(r'(?:[a-z0-9-]+\.)+[a-z]{2,63}',domain) or not re.fullmatch(r'(?:[a-z0-9-]+\.)+[a-z]{2,63}',host) or not actor:raise RuntimeError('Configure approved mail domain, TLS hostname and delegated panel operator in /etc/dobhrap-communications.env')
 address='u'+instance.replace('-','')[:12]+'-'+str(r['owner'])+'@'+domain
 api=trusted_module('_dobhrap_mail_accounts','/opt/olamidepanel/panel/mail_accounts.py');db=trusted_module('_dobhrap_panel_database','/opt/olamidepanel/panel/database.py')
 with db.connect() as con:
  user=con.execute('SELECT id,username,role,active FROM users WHERE username=?',(actor,)).fetchone()
  if not user or not user['active'] or domain not in api.permitted_domains(con,user):raise RuntimeError('Panel operator lacks approved domain delegation')
  previous=con.execute('SELECT id,state FROM mail_requests WHERE address=? AND creator=? ORDER BY id DESC LIMIT 1',(address,user['id'])).fetchone()
  existing=con.execute('SELECT address FROM mail_inventory WHERE address=?',(address,)).fetchone()
  if existing and not previous:raise RuntimeError('Mailbox address already exists without ownership evidence; operator review required')
  if existing and previous and previous['state']=='applied':return 'ready',{'address':address,'login':address,'host':host,'imap_port':993,'smtp_port':587,'tls_required':True,'delivery_verified':False}
  if previous:
   if previous['state'] in ('queued','applying'):return 'awaiting_mail',{'address':address,'host':host}
   raise RuntimeError('Panel mail job needs operator reconciliation: '+previous['state'])
 status,result=api.handle('POST',user,db.connect,{'address':address,'operation':'upsert','password':p['password']})
 if status!=202:raise RuntimeError('Panel mailbox request was not accepted')
 return 'awaiting_mail',{'address':address,'host':host}


def sip(c,r,p,instance):
 import provider_settings as settings
 token=settings.get('SIP_BRIDGE_TOKEN')
 if not token:raise RuntimeError('Save SIP bridge token in Provider provisioning & keys')
 user=c.execute('SELECT email,role FROM users WHERE id=?',(r['owner'],)).fetchone();tenant=c.execute('SELECT name FROM tenants WHERE id=?',(r['tenant_id'],)).fetchone()
 result=a.request_json('https://sip.dobhrap.com/api/integrations/hosted-account',{'instance':instance,'owner':r['owner'],'tenant':r['tenant_id'],'kind':p['account_type'],'role':'admin' if p['account_type']=='organization' and user['role'] in ('admin','super_admin') else 'user','email':user['email'],'name':user['email'],'company':tenant['name'],'password':p['password']},{'Authorization':'Bearer '+token},'POST',timeout=20)
 if result.get('kind')!=p['account_type'] or not result.get('accountId') or result.get('portal')!='https://sip.dobhrap.com/' or result.get('state') not in ('active','awaiting_switch','suspended'):raise RuntimeError('Unrecognized SIP provisioning response')
 return ('ready' if result['state']=='active' else result['state']),result


def save(c,r,p,state):
 c.execute('UPDATE communications_accounts SET state=?,payload=?,attempts=attempts+1,next_attempt=?,updated=? WHERE owner=? AND kind=?',(state,a.seal(p),int(time.time())+60,int(time.time()),r['owner'],r['kind']));c.commit()


def run(app):
 with app.connect() as c:
  flags=comms.policy(c)['values'];instance=c.execute('SELECT value FROM communications_identity WHERE id=1').fetchone()[0]
  for user in c.execute("SELECT u.id,u.tenant_id,t.service_mode FROM users u JOIN tenants t ON t.id=u.tenant_id WHERE t.status='active' ORDER BY u.id").fetchall():comms.enqueue(c,user['id'],user['tenant_id'],user['service_mode'])
  c.commit()
  jobs=c.execute("SELECT a.* FROM communications_accounts a JOIN users u ON u.id=a.owner AND u.tenant_id=a.tenant_id JOIN tenants t ON t.id=a.tenant_id WHERE t.status='active' AND a.state IN ('queued','blocked','awaiting_switch','awaiting_mail') AND a.next_attempt<=? ORDER BY a.updated,a.owner LIMIT 10",(int(time.time()),)).fetchall()
  for r in jobs:
   if r['payload']:p=a.unseal(r['payload'])
   else:
    import secrets
    mode=c.execute('SELECT service_mode FROM tenants WHERE id=?',(r['tenant_id'],)).fetchone()[0]
    p={'password':secrets.token_urlsafe(36),'account_type':'personal' if mode=='tax_only' else 'organization'}
    c.execute('UPDATE communications_accounts SET payload=? WHERE owner=? AND kind=?',(a.seal(p),r['owner'],r['kind']));c.commit()

   if not flags[r['kind']+'_enabled']:
    p['notice']='Provisioning disabled by super admin';save(c,r,p,'blocked');continue
   try:
    state,details=(sip if r['kind']=='sip' else mailbox)(c,r,p,instance);p.update(details=details,notice='Service account ready; paid calls, DNS, mail delivery and PBX routes require their separate readiness checks' if state=='ready' else 'Provider accepted account; activation is pending');save(c,r,p,state)
   except Exception as error:
    # No endpoint response bodies, credentials or taxpayer information in worker output.
    p['notice']=str(error)[:300] if isinstance(error,(RuntimeError,a.ServiceError)) else 'Provisioning needs operator review ('+type(error).__name__+'). Check service logs.';save(c,r,p,'attention')
  # A crashed sender may have handed the message to SMTP. Never resend automatically.
  c.execute("UPDATE communications_outbox SET state='uncertain',updated=? WHERE state='sending' AND updated<?",(int(time.time()),int(time.time())-300));c.commit()
  if not flags['mail_enabled']:return
  messages=c.execute("SELECT o.* FROM communications_outbox o JOIN tenants t ON t.id=o.tenant_id JOIN users u ON u.id=o.owner AND u.tenant_id=o.tenant_id WHERE o.state='queued' AND t.status='active' ORDER BY o.created LIMIT 5").fetchall()
  for row in messages:
   try:
    account,p=comms.owned(c,{'id':row['owner'],'tenant_id':row['tenant_id']},'mail')
    if account['state']!='ready':continue
    if c.execute("UPDATE communications_outbox SET state='sending',updated=? WHERE id=? AND state='queued'",(int(time.time()),row['id'])).rowcount!=1:continue
    c.commit();data=a.unseal(row['payload']);msg=EmailMessage();msg['From']=p['details']['address'];msg['To']=', '.join(data['to']);msg['Subject']=data['subject'];msg['Message-ID']='<'+row['id']+'@'+p['details']['address'].split('@')[1]+'>';msg.set_content(data['text'])
    with smtplib.SMTP(p['details']['host'],587,timeout=20) as smtp:
     smtp.ehlo();smtp.starttls(context=ssl.create_default_context());smtp.ehlo();smtp.login(p['details']['address'],p['password']);rejected=smtp.send_message(msg)
    state='partial' if rejected else 'sent'
   except Exception:state='uncertain'
   c.execute('UPDATE communications_outbox SET state=?,updated=? WHERE id=?',(state,int(time.time()),row['id']));a.audit(c,row['owner'],'System email '+state+' '+row['id']);c.commit()


def main():
 if os.geteuid()!=0:raise RuntimeError('Run fixed provisioning broker as root')
 sys.path.insert(0,str(Path(__file__).resolve().parent/'ansible'))
 from active_runtime import load_active
 with open('/run/lock/dobhrap-communications.lock','w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);app=load_active('oob-business.service');account=pwd.getpwnam('dobhrap-app');os.setegid(account.pw_gid);os.seteuid(account.pw_uid);run(app)
if __name__=='__main__':main()
