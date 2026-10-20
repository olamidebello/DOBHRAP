"""Platform analyst controls. No provider keys or taxpayer document contents in admin listings."""
import json, time
import advanced as a

DEFAULTS={'analysis_enabled':True,'uploads_enabled':True,'queue_enabled':True,'worker_enabled':True,'returns_enabled':True,'daily_requests':100,'document_limit':100,'max_file_bytes':2000000,'years':[2025,2026],'return_types':['1040','1065','1120-S','1120']}

def initialize(c):
 c.execute('CREATE TABLE IF NOT EXISTS tax_analyst_controls(id INTEGER PRIMARY KEY,payload TEXT NOT NULL,revision INTEGER NOT NULL,updated INTEGER NOT NULL,updated_by INTEGER NOT NULL)')
 c.execute('INSERT OR IGNORE INTO tax_analyst_controls VALUES(1,?,1,?,0)',(json.dumps(DEFAULTS),int(time.time())))

def read(c=None):
 if c is None:
  import app
  with app.connect() as catalog:return read(catalog)
 row=c.execute('SELECT * FROM tax_analyst_controls WHERE id=1').fetchone()
 return {'policy':{**DEFAULTS,**json.loads(row['payload'])},'revision':row['revision'],'updated':row['updated']} if row else {'policy':dict(DEFAULTS),'revision':0,'updated':0}

def policy():return read()['policy']

def validate(raw):
 if not isinstance(raw,dict) or set(raw)!=set(DEFAULTS):raise a.ServiceError('Supply all analyst policy fields')
 clean={}
 for key in ('analysis_enabled','uploads_enabled','queue_enabled','worker_enabled','returns_enabled'):
  if type(raw[key]) is not bool:raise a.ServiceError('Choose '+key)
  clean[key]=raw[key]
 for key,lo,hi in [('daily_requests',1,100),('document_limit',1,100),('max_file_bytes',1024,2000000)]:
  value=raw[key]
  if type(value) is not int or not lo<=value<=hi:raise a.ServiceError('Invalid '+key)
  clean[key]=value
 for key in ('years','return_types'):
  value=raw[key]
  if not isinstance(value,list) or not value or any(type(v) is not type(DEFAULTS[key][0]) or v not in DEFAULTS[key] for v in value) or len(set(value))!=len(value):raise a.ServiceError('Select supported '+key)
  clean[key]=value
 return clean

def dispatch(path,method,body,c,user):
 if not path.startswith('/api/platform/tax-analyst/'):return None
 if user['role']!='super_admin':raise a.ServiceError('Super administrator required',403)
 import app, tax_filing, provider_settings
 route=path.rsplit('/',1)[-1]
 if route=='pricing':return __import__('tax_analyst_billing').pricing(c,method,body,user)
 if route=='session-action' and method=='POST':return __import__('tax_analyst_billing').session_action(c,body,user)
 if route=='settings':
  if method=='POST':
   clean=validate(body.get('policy'));c.execute('BEGIN IMMEDIATE')
   if c.execute('UPDATE tax_analyst_controls SET payload=?,revision=revision+1,updated=?,updated_by=? WHERE id=1 AND revision=?',(json.dumps(clean),int(time.time()),user['id'],body.get('revision'))).rowcount!=1:raise a.ServiceError('Policy changed; reload controls',409)
   a.audit(c,user['id'],'Tax analyst policy updated')
  elif method!='GET':raise a.ServiceError('Unsupported method',405)
  return {**read(c),'catalog':tax_filing.catalog(),'provider':{'key_configured':bool(provider_settings.get('OPENAI_API_KEY')),'model':provider_settings.get('TAX_ANALYST_MODEL') or provider_settings.get('TAX_AI_MODEL'),'analysis_enabled':provider_settings.get('DOBHRAP_ENABLE_TAX_ANALYST')=='1'},'resources':tax_filing.resource_status()}
 if route=='overview' and method=='GET':
  workspaces=[]
  for t in c.execute('SELECT id,name,status FROM tenants ORDER BY id').fetchall():
   try:
    with app.tenant_connect(t['id']) as private:
     jobs=[dict(r) for r in private.execute('SELECT id,document_id,owner,state,requested,started,finished FROM tax_analysis_jobs ORDER BY requested DESC LIMIT 100')]
     states={r['state']:r['n'] for r in private.execute('SELECT state,count(*) n FROM tax_analysis_jobs GROUP BY state')}
     cases=[dict(r) for r in private.execute('SELECT year,form,state,count(*) n FROM tax_filing_cases GROUP BY year,form,state')]
     workspaces.append({**dict(t),'jobs':jobs,'counts':states,'returns':cases})
   except Exception:workspaces.append({**dict(t),'unavailable':True,'jobs':[],'counts':{},'returns':[]})
  return {'workspaces':workspaces,'audit':[dict(r) for r in c.execute("SELECT user_id,action,created FROM audit WHERE action LIKE 'Tax analyst %' ORDER BY id DESC LIMIT 100")]}
 if route=='cancel-job' and method=='POST':
  tid=body.get('tenant_id')
  if type(tid) is not int or not c.execute('SELECT 1 FROM tenants WHERE id=?',(tid,)).fetchone():raise a.ServiceError('Choose a workspace')
  with app.tenant_connect(tid) as private:
   if private.execute("UPDATE tax_analysis_jobs SET state='cancelled',finished=? WHERE id=? AND state='queued'",(int(time.time()),body.get('id'))).rowcount!=1:raise a.ServiceError('Job already running or no longer queued',409)
  a.audit(c,user['id'],'Tax analyst queued job cancelled in workspace '+str(tid))
  return {'ok':True}
 raise a.ServiceError('Analyst control route not found',404)
