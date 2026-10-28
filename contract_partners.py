"""Opt-in, authenticated company directory and private nonbinding bid discussions."""
import json,re,time,uuid
import advanced as a
import business_contracts as business


def initialize(c):
 c.execute('CREATE TABLE IF NOT EXISTS contract_partner_listings(id TEXT PRIMARY KEY,owner INTEGER NOT NULL,tenant_id INTEGER NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,updated INTEGER NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS contract_partner_requests(id TEXT PRIMARY KEY,listing_id TEXT NOT NULL,sender INTEGER NOT NULL,sender_tenant INTEGER NOT NULL,recipient INTEGER NOT NULL,recipient_tenant INTEGER NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,updated INTEGER NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS contract_partner_messages(id TEXT PRIMARY KEY,request_id TEXT NOT NULL,owner INTEGER NOT NULL,tenant_id INTEGER NOT NULL,payload TEXT NOT NULL,created INTEGER NOT NULL)')


def text(body,key,maximum,required=False):
 value=body.get(key,'')
 if not isinstance(value,str) or len(value)>maximum or '\x00' in value:raise a.ServiceError('Invalid '+key.replace('_',' '))
 value=value.strip()
 if required and not value:raise a.ServiceError(key.replace('_',' ').title()+' is required')
 return value


def listing_data(row):
 return {'id':row['id'],'state':row['state'],'updated':row['updated'],**a.unseal(row['payload'])}


def request_row(c,rid,user,tid):
 row=c.execute('SELECT * FROM contract_partner_requests WHERE id=?',(rid,)).fetchone()
 if not row or (row['sender'],row['sender_tenant'])!=(user['id'],tid) and (row['recipient'],row['recipient_tenant'])!=(user['id'],tid):raise a.ServiceError('Partnership discussion not found',404)
 return row


def dispatch(route,method,body,c,user,tid):
 owner=user['id'];now=int(time.time())
 if route=='partners-status':
  return {'pending':c.execute("SELECT count(*) FROM contract_partner_requests WHERE recipient=? AND recipient_tenant=? AND state='pending'",(owner,tid)).fetchone()[0]}
 if route=='partners-directory':
  # Deactivated owners/workspaces immediately disappear from the directory.
  rows=c.execute("SELECT p.* FROM contract_partner_listings p JOIN users u ON u.id=p.owner JOIN tenants t ON t.id=p.tenant_id WHERE p.state='published' AND u.account_status='active' AND t.status='active' ORDER BY p.updated DESC LIMIT 200").fetchall()
  query=text(body,'query',200).casefold();listings=[]
  for r in rows:
   data=listing_data(r)
   if not query or query in json.dumps(data,ensure_ascii=False).casefold():listings.append(data|{'mine':r['owner']==owner and r['tenant_id']==tid,'same_workspace':r['tenant_id']==tid})
  mine=[listing_data(r) for r in c.execute('SELECT * FROM contract_partner_listings WHERE owner=? AND tenant_id=? ORDER BY updated DESC LIMIT 20',(owner,tid))]
  requests=[]
  for r in c.execute('SELECT * FROM contract_partner_requests WHERE (sender=? AND sender_tenant=?) OR (recipient=? AND recipient_tenant=?) ORDER BY updated DESC LIMIT 100',(owner,tid,owner,tid)):
   requests.append({'id':r['id'],'state':r['state'],'updated':r['updated'],'incoming':r['recipient']==owner and r['recipient_tenant']==tid,**a.unseal(r['payload'])})
  return {'listings':listings,'mine':mine,'requests':requests,'notice':'Opt-in directory of self-reported companies, latest 200 publications. Verify credentials, eligibility, exclusion status, conflicts and solicitation teaming rules independently. Discussions and acceptance are nonbinding; no bid or agreement is submitted.'}
 if user['role']=='viewer':raise a.ServiceError('Read-only workspace access',403)
 if route=='partners-save':
  if user['role'] not in ('admin','super_admin'):raise a.ServiceError('Business administrator required to publish a company',403)
  pid=body.get('id');previous=c.execute('SELECT * FROM contract_partner_listings WHERE id=?',(pid,)).fetchone() if pid else None
  if pid and (not previous or previous['owner']!=owner or previous['tenant_id']!=tid):raise a.ServiceError('Listing not found',404)
  state=body.get('state','draft')
  if state not in ('draft','published','closed'):raise a.ServiceError('Choose draft, published or closed')
  if state=='published' and body.get('publish_confirmed') is not True:raise a.ServiceError('Confirm you represent this company and authorize directory publication')
  p,_=business.profile(c,tid)
  if not p.get('legal_name'):raise a.ServiceError('Save your legal business name in the business profile first')
  data={'company':p['legal_name'],'title':text(body,'title',150,True),'capabilities':text(body,'capabilities',3000,True),'seeking':text(body,'seeking',2000,True),'regions':text(body,'regions',500),'naics':text(body,'naics',200),'role':text(body,'role',80),'self_reported':True}
  if data['naics'] and any(not re.fullmatch(r'\d{6}',v.strip()) for v in data['naics'].split(',')):raise a.ServiceError('Use comma-separated six-digit NAICS codes')
  if not previous and c.execute('SELECT count(*) FROM contract_partner_listings WHERE owner=? AND tenant_id=?',(owner,tid)).fetchone()[0]>=20:raise a.ServiceError('Close or update an existing listing; maximum 20 per user')
  pid=pid or str(uuid.uuid4())
  c.execute('INSERT OR REPLACE INTO contract_partner_listings VALUES(?,?,?,?,?,?)',(pid,owner,tid,state,a.seal(data),now));a.audit(c,owner,'Partnership listing '+state+' '+pid)
  return {'ok':True,'id':pid}
 if route=='partners-request':
  listing=c.execute("SELECT p.* FROM contract_partner_listings p JOIN users u ON u.id=p.owner JOIN tenants t ON t.id=p.tenant_id WHERE p.id=? AND p.state='published' AND u.account_status='active' AND t.status='active'",(body.get('listing_id'),)).fetchone()
  if not listing:raise a.ServiceError('Published listing not found',404)
  if listing['tenant_id']==tid:raise a.ServiceError('Choose a company outside your workspace')
  if body.get('confirmed') is not True:raise a.ServiceError('Confirm sharing the company name, selected notice and message with this company')
  p,_=business.profile(c,tid)
  if not p.get('legal_name'):raise a.ServiceError('Complete your business profile first')
  c.execute('BEGIN IMMEDIATE')
  if c.execute('SELECT count(*) FROM contract_partner_requests WHERE sender=? AND updated>?',(owner,now-86400)).fetchone()[0]>=10:raise a.ServiceError('Maximum ten new requests per day',429)
  if c.execute("SELECT 1 FROM contract_partner_requests WHERE sender=? AND sender_tenant=? AND listing_id=? AND state IN ('pending','accepted')",(owner,tid,listing['id'])).fetchone():raise a.ServiceError('You already have an open discussion for this listing',409)
  notice=None;nid=body.get('notice_id')
  if nid:
   row=c.execute('SELECT payload FROM business_opportunities WHERE tenant_id=? AND notice_id=?',(tid,nid)).fetchone()
   if not row:raise a.ServiceError('Choose a saved notice in your workspace')
   opp=a.unseal(row[0]);notice={'notice_id':nid,'title':opp['title'],'url':opp['url']}
  data={'sender_company':p['legal_name'],'recipient_company':a.unseal(listing['payload'])['company'],'listing_title':a.unseal(listing['payload'])['title'],'notice':notice,'message':text(body,'message',3000,True)}
  rid=str(uuid.uuid4());c.execute('INSERT INTO contract_partner_requests VALUES(?,?,?,?,?,?,?,?,?)',(rid,listing['id'],owner,tid,listing['owner'],listing['tenant_id'],'pending',a.seal(data),now));a.audit(c,owner,'Private partnership discussion requested '+rid)
  return {'ok':True,'id':rid}
 if route in ('partners-thread','partners-respond','partners-message'):
  row=request_row(c,body.get('id'),user,tid)
  if route=='partners-thread':
   messages=[{'id':r['id'],'mine':r['owner']==owner and r['tenant_id']==tid,'created':r['created'],**a.unseal(r['payload'])} for r in c.execute('SELECT * FROM contract_partner_messages WHERE request_id=? ORDER BY created,id LIMIT 200',(row['id'],))]
   return {'id':row['id'],'state':row['state'],'incoming':row['recipient']==owner and row['recipient_tenant']==tid,**a.unseal(row['payload']),'messages':messages}
  if route=='partners-respond':
   action=body.get('action')
   if action not in ('accepted','declined','closed'):raise a.ServiceError('Choose accept, decline or close')
   if action!='closed' and (row['recipient'],row['recipient_tenant'])!=(owner,tid):raise a.ServiceError('Only the invited company can accept or decline',403)
   if action!='closed' and row['state']!='pending':raise a.ServiceError('This request is no longer pending',409)
   if action=='closed' and row['state'] not in ('pending','accepted'):raise a.ServiceError('This discussion is already closed',409)
   if c.execute('UPDATE contract_partner_requests SET state=?,updated=? WHERE id=? AND state=?',(action,now,row['id'],row['state'])).rowcount!=1:raise a.ServiceError('Discussion changed; refresh',409)
   a.audit(c,owner,'Partnership discussion '+action+' '+row['id']);return {'ok':True}
  if row['state']!='accepted':raise a.ServiceError('Messaging requires an accepted discussion',409)
  other=row['sender'] if row['recipient']==owner else row['recipient'];active=c.execute('SELECT u.account_status,t.status FROM users u JOIN tenants t ON t.id=u.tenant_id WHERE u.id=?',(other,)).fetchone()
  if not active or active[0]!='active' or active[1]!='active':raise a.ServiceError('Partner account is unavailable',409)
  c.execute('BEGIN IMMEDIATE')
  if c.execute('SELECT count(*) FROM contract_partner_messages WHERE request_id=?',(row['id'],)).fetchone()[0]>=200:raise a.ServiceError('Discussion reached its 200-message limit')
  if c.execute('SELECT count(*) FROM contract_partner_messages WHERE owner=? AND created>?',(owner,now-3600)).fetchone()[0]>=30:raise a.ServiceError('Maximum 30 messages per hour',429)
  c.execute('INSERT INTO contract_partner_messages VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),row['id'],owner,tid,a.seal({'text':text(body,'text',5000,True)}),now));c.execute('UPDATE contract_partner_requests SET updated=? WHERE id=?',(now,row['id']));return {'ok':True}
 raise a.ServiceError('Unknown partnership route',404)
