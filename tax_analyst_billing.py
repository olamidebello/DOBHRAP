"""One verified live or wallet purchase buys one successful document-analysis session."""
import time
from contextlib import contextmanager
import advanced as a
import wallet

CODE='tax_analyst_session'
PRODUCT='tax-analyst-session'

def initialize(c):
 c.execute('CREATE TABLE IF NOT EXISTS tax_analyst_sessions(order_id TEXT PRIMARY KEY,tenant_id INTEGER NOT NULL,owner INTEGER NOT NULL,state TEXT NOT NULL,document_id TEXT,attempt_revision INTEGER,created INTEGER NOT NULL,updated INTEGER NOT NULL)')
 c.execute('INSERT OR IGNORE INTO market_products VALUES(?,?,?,?,?,?,?)',(PRODUCT,'Tax Analyst — one document session','One session covers one successful PDF or image analysis. Failed extraction keeps the session available for an explicit retry. Saved reports remain accessible.','tax_analyst_session',500,'USD',1))

def sync(c,tid,owner):
 # Test-mode payments, pending orders and browser redirects cannot grant access.
 rows=c.execute("SELECT o.id,o.created FROM market_orders o JOIN market_services s ON s.order_id=o.id WHERE o.owner=? AND o.tenant_id=? AND o.service_code=? AND s.service_code=? AND ((o.environment='live' AND s.environment='live') OR (s.environment='wallet' AND "+wallet.PAID+")) AND o.state='fulfilled' AND s.status='active' AND s.work_state!='suspended' AND o.currency='USD' AND o.amount>=50",(owner,tid,CODE,CODE)).fetchall()
 for r in rows:c.execute("INSERT OR IGNORE INTO tax_analyst_sessions(order_id,tenant_id,owner,state,created,updated) VALUES(?,?,?,'available',?,?)",(r['id'],tid,owner,r['created'],int(time.time())))

def eligible_sql():return " FROM tax_analyst_sessions x JOIN market_orders o ON o.id=x.order_id JOIN market_services s ON s.order_id=x.order_id WHERE x.tenant_id=? AND x.owner=? AND o.state='fulfilled' AND ((o.environment='live' AND s.environment='live') OR (s.environment='wallet' AND "+wallet.PAID+")) AND o.service_code='tax_analyst_session' AND s.service_code='tax_analyst_session' AND s.status='active' AND s.work_state!='suspended'"

def status(c,tid,user):
 sync(c,tid,user['id']);counts={r['state']:r['n'] for r in c.execute('SELECT x.state,count(*) n'+eligible_sql()+' GROUP BY x.state',(tid,user['id']))}
 product=c.execute('SELECT * FROM market_products WHERE id=?',(PRODUCT,)).fetchone()
 return {'price_cents':product['amount'] if product else 500,'currency':'USD','product_id':PRODUCT,'purchase_available':bool(product and product['active']),'available':counts.get('available',0),'reserved':counts.get('reserved',0),'used':counts.get('used',0),'admin_exempt':user['role']=='super_admin','session_definition':'One successfully analyzed document. Failed extraction returns the session for an explicit retry. No automatic retries.','payment_required':user['role']!='super_admin'}

def tid_for(user):return int(user.get('tenant_id',1)) if isinstance(user,dict) else int(user['tenant_id'])

@contextmanager
def catalog_for(tenant_db,user):
 import app
 if tid_for(user)==1:
  yield tenant_db
 else:
  with app.connect() as root:yield root

def require_credit(user):
 if user['role']=='super_admin':return
 import app
 with app.connect() as c:
  s=status(c,tid_for(user),user)
  if not s['available']:raise a.ServiceError('Purchase a Tax Analyst session in the marketplace before uploading or starting analysis',402)

def reserve(tenant_db,user,did,revision):
 if user['role']=='super_admin':return None
 with catalog_for(tenant_db,user) as c:
  c.execute('BEGIN IMMEDIATE');sync(c,tid_for(user),user['id'])
  row=c.execute('SELECT x.order_id'+eligible_sql()+" AND x.state='available' ORDER BY x.created,x.order_id LIMIT 1",(tid_for(user),user['id'])).fetchone()
  if not row:raise a.ServiceError('A purchased Tax Analyst session is required for this document',402)
  if c.execute("UPDATE tax_analyst_sessions SET state='reserved',document_id=?,attempt_revision=?,updated=? WHERE order_id=? AND state='available'",(did,revision,int(time.time()),row['order_id'])).rowcount!=1:raise a.ServiceError('Session already reserved; reload status',409)
  a.audit(c,user['id'],'Tax analyst session reserved '+row['order_id']);c.commit();return row['order_id']

def finish(tenant_db,user,order,success):
 if not order:return
 with catalog_for(tenant_db,user) as c:
  if success:c.execute("UPDATE tax_analyst_sessions SET state='used',updated=? WHERE order_id=? AND owner=? AND state='reserved'",(int(time.time()),order,user['id']))
  else:c.execute("UPDATE tax_analyst_sessions SET state='available',document_id=NULL,attempt_revision=NULL,updated=? WHERE order_id=? AND owner=? AND state='reserved'",(int(time.time()),order,user['id']))
  a.audit(c,user['id'],'Tax analyst session '+('consumed ' if success else 'returned after failure ')+order);c.commit()

def pricing(c,method,body,user):
 if user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
 if method=='POST':
  price=body.get('price_cents');active=body.get('active')
  if type(price) is not int or not 50<=price<=1000000 or type(active) is not bool:raise a.ServiceError('Choose a USD price from $0.50 to $10,000 and purchase availability')
  # Do not mutate outstanding orders or previously purchased sessions.
  if c.execute('UPDATE market_products SET amount=?,active=? WHERE id=? AND amount=? AND active=?',(price,int(active),PRODUCT,body.get('expected_price_cents'),int(body.get('expected_active',False)))).rowcount!=1:raise a.ServiceError('Price changed; reload pricing',409)
  a.audit(c,user['id'],'Tax analyst session price/availability updated')
 for pair in c.execute("SELECT DISTINCT tenant_id,owner FROM market_orders WHERE service_code='tax_analyst_session' AND environment IN ('live','wallet') AND state='fulfilled' LIMIT 500").fetchall():sync(c,pair['tenant_id'],pair['owner'])
 return {'product':dict(c.execute('SELECT * FROM market_products WHERE id=?',(PRODUCT,)).fetchone()),'sessions':[dict(r) for r in c.execute('SELECT order_id,tenant_id,owner,state,document_id,created,updated FROM tax_analyst_sessions ORDER BY updated DESC LIMIT 200')],'notice':'One successful document analysis per live-paid or wallet-paid session. Test payments and coupons do not grant paid analyst sessions. Super administrators are exempt for platform operations.'}

def session_action(c,body,user):
 if user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
 expected=body.get('expected_state');target={'available':'revoked','revoked':'available'}.get(expected)
 if not target or c.execute('UPDATE tax_analyst_sessions SET state=?,updated=? WHERE order_id=? AND state=?',(target,int(time.time()),body.get('order_id'),expected)).rowcount!=1:raise a.ServiceError('Only unused sessions may be suspended or restored; reload status',409)
 a.audit(c,user['id'],'Tax analyst unused session '+target+' '+str(body.get('order_id')));return {'ok':True}


def release_interrupted(tenant_db,user,did):
 with catalog_for(tenant_db,user) as c:
  c.execute("UPDATE tax_analyst_sessions SET state='available',document_id=NULL,attempt_revision=NULL,updated=? WHERE owner=? AND tenant_id=? AND document_id=? AND state='reserved'",(int(time.time()),user['id'],tid_for(user),did))
  c.commit()
