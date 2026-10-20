"""Evidence-linked preparation suggestions; never infers deduction eligibility."""
import datetime, json
from pathlib import Path
import advanced as a

REFERENCES = {
 'schedule_c': {'title':'Schedule C instructions', 'url':'https://www.irs.gov/instructions/i1040sc', 'revision_year':2025},
 '1040': {'title':'Form 1040 instructions', 'url':'https://www.irs.gov/instructions/i1040gi', 'revision_year':2025},
 'travel': {'title':'Publication 463 — travel, meals and vehicles', 'url':'https://www.irs.gov/publications/p463', 'revision_year':2025},
 'assets': {'title':'Form 4562 — depreciation', 'url':'https://www.irs.gov/forms-pubs/about-form-4562', 'revision_year':None},
 'education': {'title':'Form 8863 — education credits', 'url':'https://www.irs.gov/forms-pubs/about-form-8863', 'revision_year':None},
 'itemized': {'title':'Schedule A instructions', 'url':'https://www.irs.gov/instructions/i1040sca', 'revision_year':2025},
 'rental': {'title':'Schedule E instructions', 'url':'https://www.irs.gov/instructions/i1040se', 'revision_year':2025},
}
# Candidate destinations only. No amount is automatically certified deductible.
CANDIDATES = {
 'wages': ('Form 1040','Wages review','1040','Reconcile employer forms and wages; do not duplicate W-2 box 1.'),
 'interest': ('Form 1040 / Schedule B','Taxable interest review','1040','Reconcile 1099-INT and separate tax-exempt interest and special adjustments.'),
 'dividends': ('Form 1040 / Schedule B','Ordinary dividends review','1040','Reconcile ordinary and qualified dividends; qualified amounts are a subset, not additional income.'),
 'other_income': ('Form 1040 / Schedule 1','Other income review','1040','Determine the actual income type and applicable exclusions before reporting.'),
 'advertising': ('Schedule C','Advertising','schedule_c','Confirm business purpose and exclude personal promotion.'),
 'office': ('Schedule C','Office expenses','schedule_c','Separate supplies from inventory, equipment and personal purchases.'),
 'supplies': ('Schedule C','Supplies','schedule_c','Verify consumed business supplies; separate inventory and capital assets.'),
 'professional': ('Schedule C','Legal and professional services','schedule_c','Allocate only the business portion; exclude personal legal or tax work.'),
 'utilities': ('Schedule C','Utilities','schedule_c','Document business allocation; personal telephone and home costs need separate review.'),
 'insurance': ('Schedule C','Insurance other than health','schedule_c','Confirm business coverage; health insurance follows different eligibility rules.'),
 'rent': ('Schedule C','Rent or lease','schedule_c','Confirm business premises/equipment; home-office and personal rent are separate.'),
 'repairs': ('Schedule C','Repairs and maintenance','schedule_c','Distinguish repairs from improvements requiring capitalization.'),
 'travel': ('Schedule C','Travel','travel','Establish tax home, overnight business travel, dates and purpose; exclude commuting.'),
 'meals': ('Schedule C','Deductible meals','travel','Document attendees and business purpose; apply year-specific limits and exceptions separately.'),
 'vehicle': ('Schedule C / Form 4562','Car and truck expenses','travel','Supply mileage log and business use; compare permitted methods without double counting.'),
 'asset': ('Form 4562','Depreciation / section 179 review','assets','Confirm cost, placed-in-service date, business use and year-specific elections/limits.'),
 'business_receipts': ('Schedule C','Gross receipts review','schedule_c','Confirm sole-proprietor business, gross receipts, refunds and no duplicate 1099/bank income.'),
 'rental': ('Schedule E','Rental income / expenses','rental','Confirm property, personal-use days, ownership, basis and passive-activity limitations.'),
 'charity': ('Schedule A','Gifts to charity review','itemized','Verify qualified recipient, substantiation, tax year and itemizing eligibility.'),
 'medical': ('Schedule A','Medical expenses review','itemized','Confirm qualified unreimbursed expenses, tax year and applicable AGI threshold.'),
 'education': ('Form 8863 / Schedule 1','Education benefit review','education','Reconcile 1098-T, actual payments, scholarships, student eligibility and duplicate benefits.'),
 'unresolved': ('Manual review','Unresolved','1040','More facts are needed; do not assume this amount is taxable or deductible.'),
 'excluded': ('Excluded','Personal / transfer','1040','Do not treat personal purchases, transfers, loan proceeds or balances as business deductions/income.'),
}


def online_references():
 try:
  data=json.loads(Path('/var/lib/oob-irs-references/status.json').read_text())
  return {key: data[key] for key in REFERENCES if key in data and data[key].get('url')==REFERENCES[key]['url']}
 except (OSError,ValueError,TypeError):return {}


def destination(row):
 category=row.get('category','unclassified')
 if row.get('kind') in ('personal','transfer') or category in ('personal','transfer'):return 'excluded'
 hint=row.get('irs_candidate')
 if hint in CANDIDATES and hint!='unresolved':return hint
 if category in ('wages','interest','dividend','other_income'):return {'dividend':'dividends'}.get(category,category)
 if category=='business_income':return 'business_receipts'
 return 'unresolved'


SCHEDULE_C_LINES_2025={'advertising':'8','office':'18','supplies':'22','professional':'17','utilities':'25','insurance':'15','repairs':'21','travel':'24a','meals':'24b','vehicle':'9','asset':'13','business_receipts':'1'}
FORM_1040_LINES_2025={('W-2','1'):'1a',('W-2','2'):'25a',('1099-INT','1'):'2b',('1099-INT','4'):'25b',('1099-DIV','1a'):'3b',('1099-DIV','1b'):'3a',('1099-DIV','4'):'25b'}


def build(docs, year):
 lines=[];groups={};warnings=[];signatures=set();form_signatures={}
 for d in docs:
  if d['year']!=year:continue
  by_form={}
  for f in d.get('tax_fields') or []:
   if f.get('approved'):by_form.setdefault(f.get('form','').upper().replace(' ',''),[]).append((str(f.get('box')),str(f.get('value')),str(f.get('currency')),str(f.get('year'))))
  for form,fields in by_form.items():form_signatures.setdefault((form,tuple(sorted(fields))),set()).add(d['id'])
 duplicate_forms={did for ids in form_signatures.values() if len(ids)>1 for did in ids}
 if duplicate_forms:warnings.append('Possible duplicate approved tax forms: '+', '.join(sorted(duplicate_forms))+'. Reconcile originals before using field totals or compiling.')
 for doc in docs:
  if doc['year']!=year:continue
  if doc.get('state')!='review':warnings.append(doc.get('name',doc['id'])+': '+str(doc.get('notice') or doc.get('state')))
  if not (doc.get('coverage') or {}).get('verified_complete'):warnings.append(doc.get('name',doc['id'])+': source coverage needs human reconciliation.')
  for n,row in enumerate(doc.get('records') or []):
   key=destination(row);form,label,ref,question=CANDIDATES[key]
   approved=row.get('approved') is True
   ready=approved and key not in ('unresolved','excluded') and row.get('currency')=='USD' and str(row.get('date','')).startswith(str(year)+'-') and bool(row.get('evidence'))
   if row.get('kind')=='expense':ready=ready and row.get('category')=='business_expense' and row.get('business_percent',0)>0
   elif row.get('kind')=='income':ready=ready and ((row.get('category')=='business_income' and key=='business_receipts') or row.get('category') in ('wages','interest','dividend','other_income'))
   else:ready=False
   signature=(row.get('date'),row.get('amount'),row.get('currency'),row.get('description','').casefold())
   if signature in signatures:ready=False;warnings.append('Possible duplicate entry: '+doc['id']+' / '+str(n+1))
   signatures.add(signature)
   entry={'document_id':doc['id'],'document':doc.get('name','Document'),'entry':n+1,'source':row.get('evidence',''), 'description':row.get('description',''), 'amount':row.get('amount'), 'currency':row.get('currency'), 'date':row.get('date',''), 'form':form,'destination':label,'candidate':key,'irs_line_form':'Schedule C','irs_line':SCHEDULE_C_LINES_2025.get(key) if year==2025 else None,'approved':approved,'status':'Reviewed intake; eligibility pending' if ready else ('Excluded' if key=='excluded' else 'Needs review'),'question':question,'reference':ref,'business_percent':row.get('business_percent',0),'draft_amount_cents':None}
   # Even reviewed intake is not a deduction: meal limits, asset elections etc. are not computed here.
   lines.append(entry);groups.setdefault(form,[]).append(entry)
  for n,f in enumerate(doc.get('tax_fields') or []):
   form=f.get('form','').upper().replace(' ','');box=f.get('box','').lower().removeprefix('box').strip()
   dest={('W-2','1'):'Form 1040 wages',('W-2','2'):'Form 1040 W-2 withholding',('1099-INT','1'):'Form 1040 taxable interest / Schedule B review',('1099-INT','4'):'Form 1040 1099 withholding',('1099-DIV','1a'):'Form 1040 ordinary dividends / Schedule B review',('1099-DIV','1b'):'Form 1040 qualified dividends (subset of ordinary dividends)',('1099-DIV','4'):'Form 1040 1099 withholding'}.get((form,box),'Manual form/box review: '+form+' '+box)
   numeric=None
   if doc['id'] not in duplicate_forms and f.get('approved') and f.get('year')==year and f.get('currency')=='USD' and (form,box) in {('W-2','1'),('W-2','2'),('1099-INT','1'),('1099-INT','4'),('1099-DIV','1a'),('1099-DIV','1b'),('1099-DIV','4')}:
    try:numeric=a.cents(f['value'])
    except a.ServiceError:pass
   entry={'document_id':doc['id'],'document':doc.get('name','Document'),'entry':'Box '+f.get('box',''),'source':f.get('evidence',''),'description':f.get('label',''),'amount':f.get('value'),'currency':f.get('currency'),'date':str(f.get('year',0)),'form':'Form 1040' if numeric is not None else form,'destination':dest,'irs_line_form':'Form 1040','irs_line':FORM_1040_LINES_2025.get((form,box)) if year==2025 else None,'approved':f.get('approved',False),'status':'Approved field; reconcile duplicates' if numeric is not None else 'Needs review','question':'Verify printed form, owner, year, currency and duplicates. Other boxes may change treatment.','reference':'1040','draft_amount_cents':numeric}
   lines.append(entry);groups.setdefault(entry['form'],[]).append(entry)
 if year!=2025:warnings.append('Exact IRS line mappings for '+str(year)+' are not certified. References currently identify 2025 instructions or general form guidance; verify the selected-year revision before filing.')
 worksheets={}
 for line in lines:
  if not line.get('irs_line'):continue
  key=line['irs_line_form']+' / Line '+line['irs_line']
  worksheet=worksheets.setdefault(key,{'form':line['irs_line_form'],'line':line['irs_line'],'description':line['destination'],'approved_field_total_cents':None,'sources':[],'status':'Draft worksheet; reconcile duplicates and complete remaining form fields'})
  worksheet['sources'].append({'document_id':line['document_id'],'entry':line['entry'],'amount':line['amount'],'approved':line['approved'],'evidence':line['source']})
  if line['draft_amount_cents'] is not None:worksheet['approved_field_total_cents']=(worksheet['approved_field_total_cents'] or 0)+line['draft_amount_cents']
 online=online_references()
 if not online or any(online.get(k,{}).get('status')!='available' for k in REFERENCES):warnings.append('Some official IRS references have not been refreshed successfully. Open the links and verify the applicable tax-year guidance.')
 return {'form_worksheets':list(worksheets.values()),'online_references':online,'year':year,'generated':datetime.datetime.now(datetime.timezone.utc).isoformat(),'lines':lines,'form_groups':groups,'warnings':list(dict.fromkeys(warnings)), 'references':REFERENCES,'summary':{'documents':len([d for d in docs if d['year']==year]),'entries':len(lines),'approved':sum(bool(x['approved']) for x in lines),'needs_review':sum(x['status']=='Needs review' for x in lines)},'recommendations':['Reconcile every source page/line and resolve missing or unreadable entries.','Reconcile statements, receipts and tax forms to prevent duplicate income or deductions.','Allocate expenses to the correct business and document business use; compare lawful methods and elections with a preparer.','Review retirement, health insurance, education, dependents and credit eligibility in the return interview; never assume eligibility from a payment description.','Check estimated payments and all documented withholding. Refund depends on total tax, payments and eligible credits; no minimum or maximum refund is guaranteed.'],'filing_ready':False,'notice':'Preparation report and candidate form worksheets only. Supported approved tax fields integrate through Compile approved records. Other destinations require eligibility review and manual completion; this is not an official completed IRS return or e-file submission.'}
