"""Structured activity metadata. Never records bodies, queries, credentials or file content."""
import re,time,uuid
import advanced as a

def initialize(c):
 c.execute('CREATE TABLE IF NOT EXISTS user_events(id TEXT PRIMARY KEY,actor INTEGER NOT NULL,target INTEGER NOT NULL,tenant_id INTEGER NOT NULL,event TEXT NOT NULL,route TEXT NOT NULL,method TEXT NOT NULL,status INTEGER NOT NULL,created INTEGER NOT NULL)')

def record(app,handler):
 path=handler.path.split('?',1)[0]
 if not path.startswith('/api/') or path=='/api/platform/user-event':return
 # Classify paths rather than recording dynamic IDs or untrusted URL fragments.
 parts=path.split('/');group=parts[2] if len(parts)>2 and re.fullmatch('[a-z-]{1,40}',parts[2]) else 'other'
 route='/api/'+group;event=getattr(handler,'event_name','') or group+'.'+('read' if handler.command=='GET' else 'action')
 if group in ('login','logout','register'):event=group
 with app.connect() as c:
  actor=getattr(handler,'event_actor',0);tid=getattr(handler,'event_tenant',0)
  if actor and not c.execute('SELECT id FROM users WHERE id=?',(actor,)).fetchone():actor=0
  target=getattr(handler,'event_target',0)
  if target and not c.execute('SELECT id FROM users WHERE id=?',(target,)).fetchone():target=0
  c.execute('INSERT INTO user_events VALUES(?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),actor,target,tid,event,route,handler.command,getattr(handler,'event_status',500),int(time.time())))

def dispatch(path,method,body,c,user):
 if path=='/api/platform/user-event':
  if method!='POST':raise a.ServiceError('POST required',405)
  event=body.get('event');page=body.get('page','')
  if event not in ('navigation','button','form') or not isinstance(page,str) or not re.fullmatch('[a-z_]{1,60}',page):raise a.ServiceError('Invalid UI activity metadata')
  import password_reset
  password_reset.throttle(c,'activity:'+str(user['id']),2000,int(time.time()))
  c.execute('INSERT INTO user_events VALUES(?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),user['id'],0,user['tenant_id'],'ui.'+event,'/ui/'+page,'POST',200,int(time.time())))
  return {'ok':True}
 if path!='/api/platform/user-events':return None
 if user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
 if method not in ('GET','POST'):raise a.ServiceError('Read-only activity query',405)
 try:
  page=int(body.get('page',0));actor=int(body.get('actor',0));status=int(body.get('status',0));since=int(body.get('since',0));until=int(body.get('until',0))
 except (ValueError,TypeError):raise a.ServiceError('Invalid activity filters') from None
 if not 0<=page<=10000 or actor<0 or since<0 or until<0 or (status and not 100<=status<=599):raise a.ServiceError('Invalid activity filters')
 filters=[];args=[]
 if actor:filters.append('(actor=? OR target=?)');args.extend([actor,actor])
 for clause,value in [('status=?',status),('created>=?',since),('created<=?',until)]:
  if value:filters.append(clause);args.append(value)
 category=body.get('event','')
 if category:
  if not isinstance(category,str) or not re.fullmatch('[a-z.-]{1,80}',category):raise a.ServiceError('Invalid event category')
  filters.append('event=?');args.append(category)
 where=' WHERE '+' AND '.join(filters) if filters else ''
 total=c.execute('SELECT count(*) FROM user_events'+where,args).fetchone()[0]
 rows=c.execute('SELECT * FROM user_events'+where+' ORDER BY created DESC,id DESC LIMIT 200 OFFSET ?',args+[page*200]).fetchall()
 return {'events':[dict(r) for r in rows],'total':total,'page':page,'page_size':200,'notice':'Application API metadata only. Failed anonymous sign-ins have actor 0. Queries, request bodies and credentials are excluded. External SIP, mailbox and OS events are not collected here.'}
