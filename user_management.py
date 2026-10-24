"""Platform administrator account lifecycle; financial/audit records are retained."""
import hmac,re,secrets,time,uuid
import advanced as a

def initialize(c):
 columns={r[1] for r in c.execute('PRAGMA table_info(users)')}
 for name,definition in [('account_status',"TEXT NOT NULL DEFAULT 'active'"),('account_revision','INTEGER NOT NULL DEFAULT 1'),('display_name',"TEXT NOT NULL DEFAULT ''")]:
  if name not in columns:c.execute('ALTER TABLE users ADD COLUMN '+name+' '+definition)

def dispatch(path,method,body,c,user):
 if path!='/api/platform/users':return None
 if user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
 if method=='GET':return listing(c,{})
 if method!='POST':raise a.ServiceError('POST required',405)
 if body.get('action')=='list':return listing(c,body)
 import app,password_reset
 c.execute('BEGIN IMMEDIATE');password_reset.throttle(c,'user-admin:'+str(user['id']),20,int(time.time()))
 actor=c.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone();password=body.get('confirm_password','')
 if actor['role']!='super_admin' or actor['account_status']!='active':raise a.ServiceError('Active super administrator required',403)
 if not isinstance(password,str) or not 14<=len(password)<=1024 or not hmac.compare_digest(actor['hash'],app.password(password,actor['salt'])):
  c.commit();raise a.ServiceError('Confirm your current administrator password',403)
 target=c.execute('SELECT * FROM users WHERE id=?',(body.get('id'),)).fetchone()
 if not target:raise a.ServiceError('User not found',404)
 if target['account_revision']!=body.get('revision'):raise a.ServiceError('User changed; reload before saving',409)
 action=body.get('action')
 if action not in ('edit','suspend','activate','delete'):raise a.ServiceError('Choose edit, suspend, activate or delete')
 if target['account_status']=='deleted':raise a.ServiceError('Deleted login cannot be modified',409)
 role=body.get('role',target['role']) if action=='edit' else target['role'];state='suspended' if action=='suspend' else 'active' if action=='activate' else 'deleted' if action=='delete' else target['account_status']
 if role not in ('admin','editor','viewer','super_admin') or (role=='super_admin' and target['tenant_id']!=1):raise a.ServiceError('Super administrators must belong to the platform workspace')
 if target['id']==user['id'] and state!='active':raise a.ServiceError('You cannot suspend or delete your own administrator login')
 if target['role']=='super_admin' and target['account_status']=='active' and (role!='super_admin' or state!='active'):
  if c.execute("SELECT count(*) FROM users WHERE role='super_admin' AND account_status='active'").fetchone()[0]<=1:raise a.ServiceError('Keep at least one active super administrator',409)
 email=target['email'];name=target['display_name']
 if action=='edit':
  email=str(body.get('email','')).strip().lower();name=str(body.get('display_name','')).strip()
  if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',email) or len(email)>254 or len(name)>150:raise a.ServiceError('Enter a valid email and name up to 150 characters')
  other=c.execute('SELECT id FROM users WHERE lower(email)=? AND id<>?',(email,target['id'])).fetchone()
  if other:raise a.ServiceError('Another account uses that email',409)
 if action=='delete':
  if body.get('confirm_email')!=target['email']:raise a.ServiceError('Type the user email to confirm account deletion')
  email='deleted-'+uuid.uuid4().hex+'@deleted.invalid';name='';role='viewer';salt=secrets.token_hex(16);c.execute('UPDATE users SET salt=?,hash=? WHERE id=?',(salt,app.password(secrets.token_urlsafe(48),salt),target['id']))
 c.execute('UPDATE users SET email=?,display_name=?,role=?,account_status=?,account_revision=account_revision+1 WHERE id=?',(email,name,role,state,target['id']))
 c.execute('DELETE FROM sessions WHERE user_id=?',(target['id'],));c.execute('UPDATE password_resets SET used=1 WHERE user_id=?',(target['id'],))
 if state!='active':
  c.execute("UPDATE communications_accounts SET state='suspended' WHERE owner=?",(target['id'],));c.execute("UPDATE communications_outbox SET state='cancelled',updated=? WHERE owner=? AND state='queued'",(int(time.time()),target['id']))
 a.audit(c,user['id'],'Registered user '+action+' id '+str(target['id']));return {'ok':True,'notice':'User updated; sessions and reset links revoked. Deletion removes the login identity and retains financial/audit records. Independent SIP/mail credentials must also be managed in their provider.'}

def listing(c,body):
 q=str(body.get('query','')).strip();state=body.get('state','all')
 try:page=int(body.get('page',0))
 except (ValueError,TypeError):raise a.ServiceError('Invalid page') from None
 if len(q)>200 or state not in ('all','active','suspended','deleted') or not 0<=page<=10000:raise a.ServiceError('Invalid search filters')
 where=' WHERE (u.email LIKE ? OR u.display_name LIKE ? OR t.name LIKE ?)';args=['%'+q+'%']*3
 if state!='all':where+=' AND u.account_status=?';args.append(state)
 total=c.execute('SELECT count(*) FROM users u JOIN tenants t ON t.id=u.tenant_id'+where,args).fetchone()[0]
 rows=c.execute('SELECT u.id,u.email,u.display_name,u.role,u.tenant_id,u.account_status,u.account_revision,t.name AS workspace,t.status AS workspace_status FROM users u JOIN tenants t ON t.id=u.tenant_id'+where+' ORDER BY u.id LIMIT 100 OFFSET ?',args+[page*100]).fetchall()
 return {'users':[dict(r) for r in rows],'total':total,'page':page,'page_size':100}
