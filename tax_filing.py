"""Private federal return workspaces and bounded calculations. Incomplete coverage blocks filing."""
import json, re, time, uuid
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import advanced as a
import tax_analyst_control as controls

FORMS={'1040':{'title':'Individual income tax return','required_forms':['1040'],'conditional_forms':['Schedule 1','Schedule 2','Schedule 3','Schedule A','Schedule B','Schedule C','Schedule D','Schedule E','Schedule SE','Form 4562','Form 8829','Form 8995','Schedule 8812','Form 8863','Form 8962'],'url':'https://www.irs.gov/forms-pubs/about-form-1040'},'1065':{'title':'Partnership return','required_forms':['1065','Schedule K','Schedule K-1 for every partner'],'conditional_forms':['Schedule B','Schedule L','Schedule M-1','Schedule M-2','Form 4562','Schedules K-2 / K-3'],'url':'https://www.irs.gov/forms-pubs/about-form-1065'},'1120-S':{'title':'S corporation return','required_forms':['1120-S','Schedule K','Schedule K-1 for every shareholder'],'conditional_forms':['Schedule B','Schedule L','Schedule M-1','Schedule M-2','Form 4562','Schedules K-2 / K-3'],'url':'https://www.irs.gov/forms-pubs/about-form-1120-s'},'1120':{'title':'Corporation return','required_forms':['1120'],'conditional_forms':['Schedule C','Schedule J','Schedule K','Schedule L','Schedule M-1','Schedule M-2','Form 4562','Form 1125-A','Form 1125-E'],'url':'https://www.irs.gov/forms-pubs/about-form-1120'}}
EXPENSES=['advertising','commissions','contract_labor','insurance','legal_professional','office','rent','repairs','supplies','licenses_taxes','travel','deductible_meals','utilities','wages','other']
MONEY=['wages','social_security_wages','interest','ordinary_dividends','qualified_dividends','withholding','estimated_payments','gross_receipts','returns_allowances','cost_of_goods_sold']+['expense_'+k for k in EXPENSES]
TEXT={'name':150,'taxpayer_name':150,'business_name':150,'business_activity':300,'accounting_method':30,'review_notes':4000}
CHECKS=['records_verified','business_allocation_verified','no_special_se_rules','no_other_income','no_other_deductions_credits','all_partners_reviewed','basis_capital_reviewed','balance_sheet_reviewed']

def catalog():return [{'form':key,**value,'years':[2025,2026],'calculation_support':'Partial individual / Schedule C / regular Schedule SE worksheets' if key=='1040' else 'Entity gross-profit worksheet and owner-allocation intake','official_form_completion':False,'filing_ready':False} for key,value in FORMS.items()]

def resource_status():
 try:
  result=json.loads(Path('/var/lib/oob-tax-forms/status.json').read_text())
  return result if isinstance(result,dict) else {}
 except (OSError,ValueError):return {}

def initialize(c):
 c.execute("CREATE TABLE IF NOT EXISTS tax_filing_cases(id TEXT PRIMARY KEY,owner INTEGER NOT NULL,year INTEGER NOT NULL,form TEXT NOT NULL,payload TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,state TEXT NOT NULL DEFAULT 'draft',created INTEGER NOT NULL,updated INTEGER NOT NULL)")

def amount(raw):
 text=str(raw or '0')
 if not re.fullmatch(r'\d{1,11}(\.\d{1,2})?',text):raise a.ServiceError('Use nonnegative USD amounts with at most two decimals')
 return int(Decimal(text)*100)

def clean(raw):
 if not isinstance(raw,dict) or set(raw)-set(TEXT)-set(MONEY)-set(CHECKS)-{'owners'}:raise a.ServiceError('Unsupported return input')
 data={key:str(raw.get(key,'')).strip()[:limit] for key,limit in TEXT.items()}
 for key in MONEY:data[key]=format(Decimal(amount(raw.get(key)))/100,'.2f')
 for key in CHECKS:
  if type(raw.get(key,False)) is not bool:raise a.ServiceError('Use checkbox answers')
  data[key]=raw.get(key,False)
 owners=raw.get('owners',[])
 if not isinstance(owners,list) or len(owners)>100:raise a.ServiceError('Maximum 100 owners')
 data['owners']=[]
 for owner in owners:
  if not isinstance(owner,dict):raise a.ServiceError('Invalid owner')
  share=str(owner.get('share','0'))
  if not re.fullmatch(r'\d{1,3}(\.\d{1,4})?',share) or not 0<=Decimal(share)<=100:raise a.ServiceError('Owner share must be 0 to 100 percent')
  data['owners'].append({'name':str(owner.get('name',''))[:150],'share':share})
 if amount(data['qualified_dividends'])>amount(data['ordinary_dividends']):raise a.ServiceError('Qualified dividends are a subset of ordinary dividends')
 return data

def cents_rate(value,rate):return int((Decimal(value)*Decimal(rate)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def calculation(year,form,d):
 values={key:amount(d.get(key)) for key in MONEY};expenses=sum(values['expense_'+k] for k in EXPENSES)
 receipts=values['gross_receipts']-values['returns_allowances'];gross_profit=receipts-values['cost_of_goods_sold'];profit=gross_profit-expenses
 blockers=['Official form completion, complete year-specific tax calculations, filing validation and signatures are not implemented for this workspace.']
 if not d.get('records_verified'):blockers.append('Reconcile all records and source documents.')
 if not d.get('taxpayer_name'):blockers.append('Confirm the taxpayer or entity legal name.')
 if values['gross_receipts'] or expenses:
  if not d.get('business_allocation_verified'):blockers.append('Confirm business-purpose allocation and year-specific expense limitations, including already-limited deductible meals.')
 if profit<0:blockers.append('Business loss limitations, basis, at-risk and passive-activity rules require review.')
 worksheets=[{'form':'Schedule C' if form=='1040' else form,'label':'Gross receipts less returns / allowances','amount_cents':receipts},{'form':'Schedule C' if form=='1040' else form,'label':'Gross profit before other income','amount_cents':gross_profit},{'form':'Schedule C' if form=='1040' else form,'label':'Reviewed expense intake (not a certified deduction)','amount_cents':expenses},{'form':'Schedule C' if form=='1040' else form,'label':'Net business worksheet before special adjustments','amount_cents':profit}]
 se_tax=None;deduction=None
 if form=='1040':
  net=max(0,cents_rate(profit,'0.9235'));base={2025:17610000,2026:18450000}[year]
  if d.get('no_special_se_rules'):
   se_tax=0 if net<40000 else cents_rate(min(net,max(0,base-values['social_security_wages'])),'0.124')+cents_rate(net,'0.029')
   deduction=cents_rate(se_tax,'0.5')
   worksheets.extend([{'form':'Schedule SE','label':'Regular-method net earnings worksheet','amount_cents':net},{'form':'Schedule SE','label':'Regular-method SE tax worksheet','amount_cents':se_tax},{'form':'Schedule 1','label':'One-half regular SE tax worksheet','amount_cents':deduction}])
   if values['wages']+net>20000000:blockers.append('Additional Medicare tax / filing status threshold review required.')
  else:blockers.append('Confirm regular self-employment method; clergy, church employees, railroad income, exemptions, multiple-person allocation and optional methods are not covered.')
  blockers+=['Individual filing status, identity, dependents, QBI, deductions, credits, tax-table calculation and other taxes need the complete preparation interview.']
  if year==2026:blockers.append('2026 final forms and year-specific filing validation must be verified before release.')
 else:
  owners=d.get('owners',[])
  if form in ('1065','1120-S'):
   if not owners or sum(Decimal(o['share']) for o in owners)!=100:blockers.append('Owner allocation percentages must total 100 percent.')
   if not d.get('all_partners_reviewed') or not d.get('basis_capital_reviewed'):blockers.append('Review owners, separately stated items, basis/capital accounts and every Schedule K-1.')
   blockers.append('K / K-1, special allocations, shareholder compensation, elections and entity-specific tax calculations are not complete.')
  else:blockers.append('Corporate taxable income, special deductions, NOLs, credits, Schedule J and tax/payment computation require completion.')
  if not d.get('balance_sheet_reviewed'):blockers.append('Complete balance-sheet and book-to-tax reconciliation or establish a valid exception.')
 allocations=[{'name':o['name'],'share':o['share'],'illustrative_profit_share_cents':cents_rate(profit,str(Decimal(o['share'])/100)),'notice':'Arithmetic illustration only; not a K-1 allocation or distributive-share determination.'} for o in d.get('owners',[])]
 return {'worksheets':worksheets,'owner_allocations':allocations,'blockers':list(dict.fromkeys(blockers)),'filing_ready':False,'transmission_available':False,'se_tax_cents':se_tax,'half_se_deduction_cents':deduction,'required_forms':FORMS[form]['required_forms'],'conditional_forms':FORMS[form]['conditional_forms'],'sources':[FORMS[form]['url'],'https://www.irs.gov/instructions/i1040sse','https://www.ssa.gov/oact/cola/cbb.html'],'notice':'Draft preparation calculations, not an official completed return. AI suggestions and owner share arithmetic do not establish eligibility. No minimum refund is guaranteed.'}

def read(c,user,did):
 row=c.execute('SELECT * FROM tax_filing_cases WHERE id=? AND owner=?',(did,user['id'])).fetchone()
 if not row:raise a.ServiceError('Private federal return not found',404)
 return row,a.unseal(row['payload'])

def view(row,payload):
 return {**{k:row[k] for k in ('id','year','form','revision','state','created','updated')},'data':payload['data'],'source_build':payload.get('source_build'),'analyst_review':payload.get('analyst_review',{}),'review':calculation(row['year'],row['form'],payload['data'])}

def dispatch(path,method,body,c,user):
 if not path.startswith('/api/tax-filing/'):return None
 if user['role']=='viewer':raise a.ServiceError('Editor or administrator required',403)
 route=path.rsplit('/',1)[-1];policy=controls.policy()
 if route=='catalog' and method=='GET':return {'catalog':catalog(),'policy':{key:policy[key] for key in ('years','return_types','returns_enabled')},'resources':resource_status()}
 if route=='list' and method=='GET':return [{k:r[k] for k in ('id','year','form','revision','state','created','updated')} for r in c.execute('SELECT * FROM tax_filing_cases WHERE owner=? ORDER BY updated DESC',(user['id'],))]
 if method!='POST':raise a.ServiceError('Unsupported method',405)
 if route=='open':
  r,p=read(c,user,body.get('id'));return view(r,p)
 if route=='create':
  y=body.get('year');form=body.get('form')
  if not policy['returns_enabled'] or y not in policy['years'] or form not in policy['return_types'] or type(y) is not int:raise a.ServiceError('This year or return type is disabled',403)
  if c.execute('SELECT count(*) FROM tax_filing_cases WHERE owner=?',(user['id'],)).fetchone()[0]>=40:raise a.ServiceError('Return workspace limit reached')
  did=str(uuid.uuid4());now=int(time.time());c.execute('INSERT INTO tax_filing_cases(id,owner,year,form,payload,created,updated) VALUES(?,?,?,?,?,?,?)',(did,user['id'],y,form,a.seal({'data':clean({'name':str(body.get('name',''))})}),now,now));a.audit(c,user['id'],'Federal return workspace created '+did)
  r,p=read(c,user,did);return view(r,p)
 r,p=read(c,user,body.get('id'))
 if route=='export':return {'kind':'NOT-FOR-FILING','return':view(r,p),'exported_at':int(time.time())}
 if route=='delete':
  if body.get('confirm')!='DELETE':raise a.ServiceError('Confirm deletion')
  c.execute('DELETE FROM tax_filing_cases WHERE id=? AND owner=?',(r['id'],user['id']));a.audit(c,user['id'],'Federal return workspace deleted '+r['id']);return {'ok':True}
 if not policy['returns_enabled']:raise a.ServiceError('Return editing is paused',403)
 if r['state']=='archived' and route!='archive':raise a.ServiceError('Restore this archived return before editing',409)
 if route=='save':p['data']=clean(body.get('data'))
 elif route=='import-analyst':
  if body.get('confirm') is not True:raise a.ServiceError('Confirm import replaces financial inputs and requires duplicate/business allocation review')
  build=c.execute('SELECT * FROM tax_analyst_builds WHERE id=? AND owner=? AND year=?',(body.get('build_id'),user['id'],r['year'])).fetchone()
  if not build:raise a.ServiceError('Choose your matching-year approved compilation',404)
  build=a.unseal(build['payload']);d=p['data']
  for key in MONEY:d[key]='0.00'
  totals={key:0 for key in MONEY}
  for item in build.get('records',[]):
   if item['kind']=='expense':totals['expense_other']+=cents_rate(amount(item['amount']),str(Decimal(item['business_percent'])/100))
   elif item['category']=='business_income':totals['gross_receipts']+=amount(item['amount'])
   else:totals[{'wages':'wages','interest':'interest','dividend':'ordinary_dividends'}.get(item['category'],'interest')]+=amount(item['amount']) if item['category'] in ('wages','interest','dividend') else 0
  for f in build.get('tax_fields',[]):
   key={('W-2','1'):'wages',('W-2','2'):'withholding',('1099-INT','1'):'interest',('1099-INT','4'):'withholding',('1099-DIV','1a'):'ordinary_dividends',('1099-DIV','1b'):'qualified_dividends',('1099-DIV','4'):'withholding'}.get((f['form'].upper().replace(' ',''),f['box'].lower().removeprefix('box').strip()))
   if key:totals[key]+=amount(f['value'])
  for key,value in totals.items():d[key]=format(Decimal(value)/100,'.2f')
  for key in CHECKS:d[key]=False
  p['analyst_review']=build.get('analyst_review',{});p['source_build']=body['build_id'];p['data']=clean(d)
 elif route=='archive':
  if type(body.get('archived')) is not bool:raise a.ServiceError('Choose archive status')
 else:raise a.ServiceError('Return route not found',404)
 state=('archived' if body['archived'] else 'draft') if route=='archive' else 'draft'
 if c.execute('UPDATE tax_filing_cases SET payload=?,state=?,revision=revision+1,updated=? WHERE id=? AND owner=? AND revision=?',(a.seal(p),state,int(time.time()),r['id'],user['id'],body.get('revision'))).rowcount!=1:raise a.ServiceError('Return changed; reload first',409)
 a.audit(c,user['id'],'Federal return '+route+' '+r['id']);r,p=read(c,user,r['id']);return view(r,p)
