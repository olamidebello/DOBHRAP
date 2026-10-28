"""Retryable removal of user-owned records across catalog and workspace databases."""
import time
import advanced as a
OWNED=['contract_partner_listings','contract_partner_messages','contracting_reports','contracting_watches','contracting_alerts','contracting_approvals','ai_service_requests','bank_items','bank_link_sessions','business_proposals','cashout_authorizations','cashout_funds','cashout_requests','communications_accounts','communications_outbox','coupon_redemptions','market_orders','support_tickets','tax_ai_runs','tax_amendments','tax_analysis_jobs','tax_analyst_builds','tax_analyst_cases','tax_analyst_diagnostic_reviews','tax_analyst_documents','tax_analyst_runs','tax_analyst_sessions','tax_bookkeeping_exports','tax_bookkeeping_items','tax_client_notifications','tax_drafts','tax_filing_cases','tax_suggestion_jobs','wallet_accounts','wallet_entries']
CHILDREN={'contract_partner_requests':[('contract_partner_messages','request_id')],'bank_items': [('bank_statements','item_id'),('bank_transactions','item_id'),('bank_link_sessions','item_id')],'market_orders':[('market_events','order_id'),('market_order_terms','order_id'),('market_services','order_id'),('market_subscriptions','order_id'),('coupon_redemptions','order_id'),('tax_analyst_sessions','order_id')],'support_tickets':[('support_jobs','ticket_id'),('support_messages','ticket_id')],'support_messages':[('support_jobs','message_id')],'tax_drafts':[('tax_auto_reviews','return_id'),('tax_draft_documents','return_id'),('tax_client_notifications','return_id'),('tax_suggestion_jobs','return_id'),('tax_client_requests','return_id')],'tax_client_requests':[('tax_client_signatures','request_id')],'workflows':[('jobs','workflow_id')]}

def initialize(c):
 c.execute("CREATE TABLE IF NOT EXISTS user_deletions(owner INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL,state TEXT NOT NULL,updated INTEGER NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT NOT NULL DEFAULT '')")
 c.execute('CREATE TABLE IF NOT EXISTS user_id_sequence(id INTEGER PRIMARY KEY,value INTEGER NOT NULL)')
 c.execute('INSERT OR IGNORE INTO user_id_sequence VALUES(1,0)')
 high=c.execute('SELECT coalesce(max(id),0) FROM users').fetchone()[0]
 c.execute('UPDATE user_id_sequence SET value=CASE WHEN value<? THEN ? ELSE value END WHERE id=1',(high,high))

def allocate(c):
 # Updating first takes the write lock; IDs are never reused after physical deletion.
 c.execute('UPDATE user_id_sequence SET value=value+1 WHERE id=1')
 high=c.execute('SELECT coalesce(max(id),0) FROM users').fetchone()[0]
 value=max(high+1,c.execute('SELECT value FROM user_id_sequence WHERE id=1').fetchone()[0]);c.execute('UPDATE user_id_sequence SET value=? WHERE id=1',(value,));return value

def columns(c,table):return {r[1] for r in c.execute('PRAGMA table_info('+table+')')}

def remove_rows(c,table,column,value):
 cols=columns(c,table)
 if column not in cols:return
 if table in CHILDREN:
  identity='token_hash' if table=='tax_client_requests' else 'id'
  if identity in cols:
   for r in c.execute('SELECT '+identity+' FROM '+table+' WHERE '+column+'=?',(value,)).fetchall():
    for child,fk in CHILDREN[table]:remove_rows(c,child,fk,r[0])
 c.execute('DELETE FROM '+table+' WHERE '+column+'=?',(value,))

def purge(c,uid):
 for table,states in [('ai_service_requests',"('reserved','reconcile')"),('tax_analysis_jobs',"('running','processing')"),('tax_suggestion_jobs',"('running','processing')")]:
  if 'owner' in columns(c,table) and c.execute('SELECT 1 FROM '+table+' WHERE owner=? AND state IN '+states,(uid,)).fetchone():raise a.ServiceError('Wait for active provider work or reconcile it before deletion',409)
 remove_rows(c,'contract_partner_requests','sender',uid);remove_rows(c,'contract_partner_requests','recipient',uid)
 remove_rows(c,'support_messages','author',uid);remove_rows(c,'workflows','creator',uid)
 for table in OWNED:remove_rows(c,table,'owner',uid)
 for table in ['sessions','password_resets','user_preferences','platform_user_profiles','registration_otp_challenges']:remove_rows(c,table,'user_id',uid)
 remove_rows(c,'platform_jobs','creator',uid)
 if 'approver' in columns(c,'workflows'):c.execute('UPDATE workflows SET approver=NULL WHERE approver=?',(uid,))
 for table,col in [('wallet_entries','actor'),('cashout_authorizations','actor'),('cashout_requests','reviewer'),('clock_changes','actor')]:
  if col in columns(c,table):c.execute('UPDATE '+table+' SET '+col+'=0 WHERE '+col+'=?',(uid,))
 if 'actor' in columns(c,'user_events'):
  c.execute('UPDATE user_events SET actor=0 WHERE actor=?',(uid,));c.execute('UPDATE user_events SET target=0 WHERE target=?',(uid,))
 if 'user_id' in columns(c,'audit'):c.execute("UPDATE audit SET user_id=0,action='Removed user activity (anonymized)' WHERE user_id=?",(uid,))

def queue(c,target):
 uid=target['id']
 for table,where in [('ai_service_requests',"state IN ('reserved','reconcile')"),('cashout_requests',"state IN ('pending','approved')"),('communications_outbox',"state='sending'")]:
  if c.execute('SELECT 1 FROM '+table+' WHERE owner=? AND '+where,(uid,)).fetchone():raise a.ServiceError('Reconcile active AI, payment or sending operations before permanent deletion',409)
 c.execute("UPDATE users SET account_status='deleting',account_revision=account_revision+1 WHERE id=?",(uid,));c.execute('DELETE FROM sessions WHERE user_id=?',(uid,));c.execute('UPDATE password_resets SET used=1 WHERE user_id=?',(uid,))
 c.execute("INSERT OR REPLACE INTO user_deletions(owner,tenant_id,state,updated) VALUES(?,?,'queued',?)",(uid,target['tenant_id'],int(time.time())))
 c.commit()

def process(app,owner=None):
 with app.connect() as c:
  if owner is None:jobs=c.execute("SELECT * FROM user_deletions WHERE state='queued' OR (state='processing' AND updated<?) ORDER BY updated LIMIT 5",(int(time.time())-600,)).fetchall()
  else:jobs=c.execute("SELECT * FROM user_deletions WHERE owner=? AND state='queued'",(owner,)).fetchall()
 for job in jobs:
  with app.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   changed=c.execute("UPDATE user_deletions SET state='processing',updated=?,attempts=attempts+1 WHERE owner=? AND (state='queued' OR (state='processing' AND updated<?))",(int(time.time()),job['owner'],int(time.time())-600)).rowcount;c.commit()
  if not changed:continue
  try:
   if job['tenant_id']!=1:
    with app.tenant_connect(job['tenant_id']) as private:purge(private,job['owner'])
   with app.connect() as c:
    c.execute('BEGIN IMMEDIATE');purge(c,job['owner']);c.execute('DELETE FROM users WHERE id=?',(job['owner'],));c.execute("UPDATE user_deletions SET state='completed',updated=? WHERE owner=?",(int(time.time()),job['owner']));a.audit(c,0,'Permanent user deletion completed for internal id '+str(job['owner']))
  except Exception as error:
   with app.connect() as c:c.execute("UPDATE user_deletions SET state='queued',updated=?,last_error=? WHERE owner=?",(int(time.time()),type(error).__name__,job['owner']))
