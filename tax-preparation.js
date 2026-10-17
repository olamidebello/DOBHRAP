// Tax data is kept in authenticated memory and encrypted server storage, never browser storage.
let taxViewToken=0,taxCleanup=null,taxSelectedYear=null;
async function showTaxPreparation(page){
 if(taxCleanup)await taxCleanup();
 const token=++taxViewToken;
 const [schema,returns]=await Promise.all([api('tax-prep/schema'),api('tax-prep/returns')]);
 if(token!==taxViewToken)return;
 const writable=userRole!=='viewer';let selectedYear=schema.years.includes(taxSelectedYear)?taxSelectedYear:schema.current_year;
 if(page==='tax_preparation'){
  content.innerHTML='<section><h2>Tax preparation</h2><p>Prepare private current and prior-year worksheets through a guided, slide-by-slide interview. Resume on another device after saving. Personal tax drafts are visible only to their owner, including in shared workspaces.</p><button data-go="tax_return_2026">Tax returns — select year</button><h3>Included preparation areas</h3><p>Personal and household details, income documents, investments, business and rental intake, deductions, credits, states, payments, encrypted documents and review.</p><p class="notice">This is a preparation interview, not TurboTax, an official IRS return, a complete tax calculation or an e-file service. Business/entity routes and state taxes are intake only.</p><a href="https://www.irs.gov/forms-pubs/about-form-1040" target="_blank" rel="noopener noreferrer">IRS Form 1040 information</a></section>';goButtons();return;
 }
 function list(){
  content.innerHTML='<section><h2>Tax returns</h2><label>Tax year<select id="preparation-year">'+schema.years.map(y=>'<option '+(y===selectedYear?'selected':'')+'>'+y+'</option>').join('')+'</select></label><p>USD · Encrypted private drafts · Preparation worksheet only</p><button id="tax-new" '+(writable?'':'disabled')+'>Start selected-year preparation</button><button data-go="tax_preparation">Preparation overview</button></section><section><h3>Your saved preparations</h3>'+returns.filter(r=>r.year===selectedYear).map(r=>`<div class="card"><h3>${esc(r.name)}</h3><p>${esc(r.status)} · Slide ${r.step+1} · ${esc(localizedDate(r.updated*1000))}</p><button data-tax-open="${r.id}" ${writable?'':'disabled'}>Continue preparation</button></div>`).join('')+(!returns.length?'<p>No saved preparations yet.</p>':'')+'</section>';
  goButtons();document.querySelector('#preparation-year').onchange=e=>{selectedYear=Number(e.target.value);taxSelectedYear=selectedYear;list()};document.querySelector('#tax-new').onclick=()=>safeRun(async()=>{const r=await api('tax-prep/create',{year:selectedYear});await interview(r)});
  content.querySelectorAll('[data-tax-open]').forEach(b=>b.onclick=()=>safeRun(async()=>interview(await api('tax-prep/open',{id:b.dataset.taxOpen}))));
 }
 async function interview(initial){
  taxSelectedYear=initial.year;
  let draft=initial,index=draft.step,timer=null,chain=Promise.resolve(),busy=false,alive=true,pendingSaves=0;
  const steps=schema.steps;
  taxCleanup=()=>{alive=false;clearTimeout(timer)};
  const money=v=>formatMoneyMinor(v,'USD');
  content.innerHTML='<div id="tax-workspace"><section><h2>'+draft.year+' Tax Return</h2><p class="notice">Private preparation worksheet — NOT FOR FILING. No completed 1040, refund guarantee, state calculation or tax transmission.</p><div class="tax-progress"><progress id="tax-progress" max="16" value="0"></progress><span id="tax-step-count"></span></div><p id="tax-save-state" role="status">Saved</p><div id="tax-step-links" class="tax-step-links"></div></section><section id="tax-slide" class="tax-slide" aria-live="polite"></section><div class="tax-actions"><button id="tax-back">Back</button><button id="tax-save">Save draft</button><button id="tax-next">Save & continue</button><button id="tax-exit">Save & exit</button></div></div>';
  const workspace=content.querySelector('#tax-workspace'),slide=workspace.querySelector('#tax-slide');
  const status=message=>{const el=workspace.querySelector('#tax-save-state');if(el)el.textContent=message};
  function renderField(f,value,prefix=''){
   const name=prefix+f.key,label=esc(f.label)+(f.required?' *':'');
   if(f.type==='select')return `<label>${label}<select name="${name}" ${f.required?'required':''}><option value="">Choose…</option>${f.options.map(o=>`<option value="${o}" ${o===value?'selected':''}>${esc(title(o))}</option>`).join('')}</select></label>`;
   if(f.type==='textarea')return `<label>${label}<textarea name="${name}" maxlength="3000">${esc(value||'')}</textarea></label>`;
   const type=f.type==='tax_id'?'password':['money','signed_money','integer'].includes(f.type)?'number':['date','email'].includes(f.type)?f.type:'text';
   return `<label>${label}<input name="${name}" type="${type}" value="${esc(value||'')}" ${f.required?'required':''} ${type==='number'?'step="'+(f.type==='integer'?'1':'0.01')+'" '+(f.type==='signed_money'?'':'min="0"'):''} ${f.type==='tax_id'?'autocomplete="off" maxlength="11"':'maxlength="300"'}></label>`;
  }
  function collect(){
   const step=steps[index];if(!step.fields.length)return;
   if(step.repeat){draft.data[step.key]=Array.from(slide.querySelectorAll('[data-tax-row]')).map(row=>{const result={_row_id:row.dataset.taxRow};for(const f of step.fields)result[f.key]=row.querySelector('[name="'+f.key+'"]').value;return result})}
   else{const form=slide.querySelector('#tax-fields');draft.data[step.key]=Object.fromEntries(new FormData(form))}
  }
  function save(mark=false,reviewed=false,next=index){
   clearTimeout(timer);timer=null;collect();const snapshot=JSON.parse(JSON.stringify(draft.data));const completed=[...draft.completed];
   if(mark&&!completed.includes(steps[index].key))completed.push(steps[index].key);
   status('Saving…');
   const task=chain.catch(()=>{}).then(async()=>{pendingSaves++;try{const r=await api('tax-prep/save',{id:draft.id,revision:draft.revision,data:snapshot,completed,step:next,reviewed,auto_ai_consent:workspace.querySelector('#tax-auto-ai')?.checked??draft.auto_ai_consent??false});draft={...r,data:r.data};if(alive)status('Saved · '+new Date().toLocaleTimeString());return r}finally{pendingSaves--}});
   chain=task;task.catch(error=>{if(alive)status('Not saved: '+error.message)});return task;
  }
  const schedule=()=>{clearTimeout(timer);status('Unsaved changes');timer=setTimeout(()=>save().catch(()=>{}),900)};
  async function move(next){if(busy||!alive||next<0||next>=steps.length)return;const form=slide.querySelector('#tax-fields');if(next>index&&form&&!form.reportValidity())return;busy=true;try{await save(next>index,false,next);index=next;render()}finally{busy=false}}
  function download(name,raw,type){const url=URL.createObjectURL(new Blob([raw],{type}));const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
  async function showDocuments(){
   slide.insertAdjacentHTML('beforeend','<div id="tax-documents">'+draft.documents.map(d=>`<p>${esc(d.name)} · ${Math.round(d.size/1024)} KB <button data-tax-download="${d.id}">Download</button> <button data-tax-remove-doc="${d.id}">Delete</button></p>`).join('')+'</div><label>Upload supporting PDF / image<input id="tax-upload" type="file" accept="application/pdf,image/png,image/jpeg"></label><button id="tax-csv-template">Download income CSV template</button><label>Import income CSV<input id="tax-income-csv" type="file" accept=".csv,text/csv"></label><p>CSV headers: kind,payer,amount,withholding,qualified_dividends. Imports append rows for your review; do not reimport the same file. No extraction or verification of uploaded document values is performed.</p>');
   slide.querySelector('#tax-upload').onchange=e=>safeRun(async()=>{const file=e.target.files[0];if(!file)return;if(file.size>2_000_000)throw Error('Maximum 2 MB per document');await save();const bytes=new Uint8Array(await file.arrayBuffer());let raw='';for(let p=0;p<bytes.length;p+=8192)raw+=String.fromCharCode(...bytes.subarray(p,p+8192));await api('tax-prep/document',{id:draft.id,name:file.name,type:file.type,base64:btoa(raw)});draft=await api('tax-prep/open',{id:draft.id});render()});
   slide.querySelectorAll('[data-tax-download]').forEach(b=>b.onclick=()=>safeRun(async()=>{const d=await api('tax-prep/document-download',{id:draft.id,document_id:b.dataset.taxDownload});const bytes=Uint8Array.from(atob(d.base64),c=>c.charCodeAt(0));download(d.name,bytes,d.type)}));
   slide.querySelectorAll('[data-tax-remove-doc]').forEach(b=>b.onclick=()=>safeRun(async()=>{await api('tax-prep/document-delete',{id:draft.id,document_id:b.dataset.taxRemoveDoc});draft=await api('tax-prep/open',{id:draft.id});render()}));
   slide.querySelector('#tax-csv-template').onclick=()=>download('2026-income-template.csv','kind,payer,amount,withholding,qualified_dividends\nw2,Example employer,50000.00,5000.00,0.00\n','text/csv');
   slide.querySelector('#tax-income-csv').onchange=e=>safeRun(async()=>{const file=e.target.files[0];if(!file)return;if(file.size>50000)throw Error('CSV limit is 50 KB');const text=await file.text();const rows=parseTaxCsv(text);if(rows.length+(draft.data.income||[]).length>100)throw Error('Income limit is 100 rows');draft.data.income=[...(draft.data.income||[]),...rows.map(r=>({_row_id:crypto.randomUUID(),...r}))];draft.completed=draft.completed.filter(x=>x!=='income');await save();message('Income imported. Review all rows and check for duplicate receipts.');index=steps.findIndex(s=>s.key==='income');render()});
  }
  function reviewHtml(){const r=draft.review;return '<h3>Preparation checks</h3><p>Reported income documents: '+money(r.reported_income_cents)+' · Reported federal withholding: '+money(r.reported_withholding_cents)+' · Business receipts less entered expenses: '+money(r.business_subtotal_cents)+'</p><p>These subtotals may overlap. They are not AGI, taxable income, refund or balance due.</p>'+r.issues.map(x=>`<p class="tax-error">${esc(x.message)} <button data-tax-fix="${x.step}">Review section</button></p>`).join('')+'<h3>Items requiring additional preparation</h3>'+r.unsupported.map(x=>'<p>'+esc(x)+'</p>').join('')+(r.estimate?'<h3>Limited ordinary-income estimate</h3><p>'+money(r.estimate.ordinary_income_tax_cents)+' before any uncalculated tax or credit. Basic standard deduction: '+money(r.estimate.standard_deduction_cents)+'</p>':'<p>No tax estimate is shown because information is missing or the return includes unsupported calculations.</p>')+'<p class="notice">'+esc(r.notice)+'</p>'}
  function bindFixes(){slide.querySelectorAll('[data-tax-fix]').forEach(b=>b.onclick=()=>safeRun(()=>move(steps.findIndex(s=>s.key===b.dataset.taxFix))))}
  function render(){
   if(!alive||!workspace.isConnected)return;
   const step=steps[index],data=draft.data[step.key]||(step.repeat?[]:{});
   workspace.querySelector('#tax-step-count').textContent=`${index+1} / ${steps.length} · ${draft.completed.length} sections reviewed`;
   workspace.querySelector('#tax-progress').value=index+1;
   workspace.querySelector('#tax-step-links').innerHTML=steps.map((s,n)=>`<button data-tax-step="${n}" aria-current="${n===index?'step':'false'}">${n+1}. ${esc(s.title)}</button>`).join('');
   workspace.querySelectorAll('[data-tax-step]').forEach(b=>b.onclick=()=>safeRun(()=>move(Number(b.dataset.taxStep))));
   slide.innerHTML='<h3 tabindex="-1" id="tax-slide-title">'+esc(step.title)+'</h3><p>'+esc(step.help)+'</p>';
   if(step.repeat){slide.insertAdjacentHTML('beforeend','<form id="tax-fields">'+data.map((row,n)=>`<div class="tax-row" data-tax-row="${esc(row._row_id||crypto.randomUUID())}"><h4>Entry ${n+1}</h4>${step.fields.map(f=>renderField(f,row[f.key])).join('')}<button type="button" data-tax-remove="${n}">Remove entry</button></div>`).join('')+'</form><button id="tax-add-row">Add another entry</button>');
    slide.querySelector('#tax-add-row').onclick=()=>{collect();draft.data[step.key].push({_row_id:crypto.randomUUID()});render();schedule()};
    slide.querySelectorAll('[data-tax-remove]').forEach(b=>b.onclick=()=>{collect();draft.data[step.key].splice(Number(b.dataset.taxRemove),1);render();schedule()});
   }else if(step.fields.length)slide.insertAdjacentHTML('beforeend','<form id="tax-fields">'+step.fields.map(f=>renderField(f,data[f.key])).join('')+'</form>');
   const form=slide.querySelector('#tax-fields');if(form){form.onsubmit=e=>{e.preventDefault();safeRun(()=>move(index+1))};form.oninput=schedule;form.onchange=schedule}
   if(step.key==='documents')showDocuments();
   if(step.key==='review'){
    const ai=draft.ai_review||{};
    slide.insertAdjacentHTML('beforeend','<h4>Available-record autofill</h4><button id="tax-record-preview">Preview workspace income and expense records</button><div id="tax-records"></div><h4>AI deduction and credit opportunity review</h4><label><input id="tax-auto-ai" type="checkbox" '+(draft.auto_ai_consent?'checked':'')+'> Automatically review my saved preparation: I consent to sending redacted categories and totals to OpenAI. Suggestions never change tax figures or claim benefits.</label><p>Automatic review status: '+esc(draft.ai_suggestion_status||'off')+'</p><button id="tax-ai-refresh">Refresh saved AI suggestions</button><p>AI suggests eligibility questions only. It does not calculate or guarantee a maximum refund. It receives only redacted categories and totals, never names, IDs, addresses, notes or documents.</p><label><input id="tax-ai-consent" type="checkbox"> I consent to sending this redacted tax summary to OpenAI.</label><button id="tax-ai-review">Review potential tax opportunities with AI</button><div id="tax-ai-output">'+(ai.notice?'<p>'+esc(ai.notice)+'</p>':'')+(ai.suggestions||[]).map(s=>'<article class="card"><h4>'+esc(s.topic)+'</h4><p>'+esc(s.question)+'</p></article>').join('')+'</div>');
    slide.querySelector('#tax-auto-ai').onchange=()=>safeRun(()=>save());
    slide.querySelector('#tax-ai-refresh').onclick=()=>safeRun(async()=>{await save();draft=await api('tax-prep/open',{id:draft.id});render()});
    slide.querySelector('#tax-record-preview').onclick=()=>safeRun(async()=>{await save();const preview=await api('tax-prep/record-preview',{id:draft.id});const box=slide.querySelector('#tax-records');box.innerHTML='<p>'+esc(preview.notice)+'</p>'+preview.items.map(x=>`<label><input type="checkbox" data-tax-source="${esc(x.key)}"> ${esc(x.source+' · '+x.name+' · USD '+x.amount)} · Confirm year and ownership</label>`).join('')+'<label><input id="tax-import-consent" type="checkbox"> I confirm the selected records belong in this 2026 preparation and have checked for duplicate amounts.</label><button id="tax-record-import">Import approved records</button>';box.querySelector('#tax-record-import').onclick=()=>safeRun(async()=>{const selected=Array.from(box.querySelectorAll('[data-tax-source]:checked')).map(b=>preview.items.find(x=>x.key===b.dataset.taxSource));draft=await api('tax-prep/record-import',{id:draft.id,revision:draft.revision,items:selected.map(x=>({key:x.key,hash:x.hash})),consent:box.querySelector('#tax-import-consent').checked});message('Imported '+draft.imported+' records. Review income and business entries before continuing.');render()})});
    slide.querySelector('#tax-ai-review').onclick=()=>safeRun(async()=>{if(!slide.querySelector('#tax-ai-consent').checked)throw Error('Consent is required before sharing a redacted summary');if(busy)return;busy=true;const b=slide.querySelector('#tax-ai-review');b.disabled=true;try{await save();status('AI opportunity review running…');draft=await api('tax-prep/ai-review',{id:draft.id,revision:draft.revision,consent:true});status('AI review completed — verify all suggestions');render()}catch(error){draft=await api('tax-prep/open',{id:draft.id});throw error}finally{busy=false;if(b.isConnected)b.disabled=false}});

    slide.insertAdjacentHTML('beforeend',(refundControls(draft.refund_review||{},draft.year))+reviewHtml()+'<label><input id="tax-ack" type="checkbox"> I reviewed this preparation worksheet and understand it is not a completed or filed return.</label><button id="tax-reviewed">Mark worksheet reviewed</button>');bindFixes();
    slide.querySelector('#tax-refund-review').onclick=()=>safeRun(async()=>{const verified_records=slide.querySelector('#tax-refund-verified').checked,no_other_taxes_or_credits=slide.querySelector('#tax-refund-other').checked,charity_verified=slide.querySelector('#tax-refund-charity').checked;await save();draft=await api('tax-prep/refund-review',{id:draft.id,revision:draft.revision,verified_records,no_other_taxes_or_credits,charity_verified});render();message('Supported refund review updated; this is not a guaranteed maximum or a filing-ready return')});
    slide.querySelector('#tax-reviewed').onclick=()=>safeRun(async()=>{if(!slide.querySelector('#tax-ack').checked)throw Error('Acknowledge the preparation limitations first');await save(true,true);message('Worksheet reviewed. It remains not filing-ready.');render()});
   }
   if(step.key==='export'){
    slide.insertAdjacentHTML('beforeend',reviewHtml()+'<button id="tax-json">Download redacted preparation JSON</button> <button id="tax-print">Print preparation worksheet</button> <button id="tax-help">Request product support</button><button disabled>E-file unavailable from this interview</button><h4>Official references</h4>'+schema.sources.map(s=>`<p><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a></p>`).join('')+'<pre id="tax-export-preview"></pre><label>To delete this preparation, type DELETE<input id="tax-delete-confirm"></label><button id="tax-delete">Delete private preparation</button>');bindFixes();
    slide.querySelector('#tax-json').onclick=()=>safeRun(async()=>{await save();const r=await api('tax-prep/export',{id:draft.id});download(draft.year+'-preparation-NOT-FOR-FILING.json',JSON.stringify(r,null,2),'application/json')});
    slide.querySelector('#tax-print').onclick=()=>safeRun(async()=>{await save();const r=await api('tax-prep/export',{id:draft.id});slide.querySelector('#tax-export-preview').textContent=JSON.stringify(r,null,2);window.print()});
    slide.querySelector('#tax-help').onclick=()=>safeRun(async()=>{await save();await api('support/tickets',{subject:draft.year+' tax preparation product help',message:'I need assistance with the preparation interview. No personal tax data is attached.',priority:'normal',ai_consent:false});message('Support ticket created without your tax data');show('support_center')});
    slide.querySelector('#tax-delete').onclick=()=>safeRun(async()=>{await api('tax-prep/delete',{id:draft.id,confirm:slide.querySelector('#tax-delete-confirm').value});alive=false;show('tax_return_2026')});
   }
   workspace.querySelector('#tax-back').disabled=index===0;workspace.querySelector('#tax-next').disabled=index===steps.length-1;
   slide.querySelector('#tax-slide-title').focus({preventScroll:true});
  }
  workspace.querySelector('#tax-back').onclick=()=>safeRun(()=>move(index-1));workspace.querySelector('#tax-next').onclick=()=>safeRun(()=>move(index+1));workspace.querySelector('#tax-save').onclick=()=>safeRun(()=>save());
  workspace.querySelector('#tax-exit').onclick=()=>safeRun(async()=>{await save();alive=false;show('tax_return_2026')});
  let start=null;slide.addEventListener('touchstart',e=>{if(e.target.closest('input,select,textarea,button,a'))return;const p=e.changedTouches[0];start={x:p.clientX,y:p.clientY}},{passive:true});
  slide.addEventListener('touchend',e=>{if(!start)return;const p=e.changedTouches[0],dx=p.clientX-start.x,dy=p.clientY-start.y;start=null;if(Math.abs(dx)>80&&Math.abs(dy)<60){const direction=document.documentElement.dir==='rtl'?-1:1;safeRun(()=>move(index+(dx*direction<0?1:-1)))}},{passive:true});
  const warn=e=>{if(timer||busy||pendingSaves){e.preventDefault();e.returnValue=''}};window.addEventListener('beforeunload',warn);
  taxCleanup=async()=>{if(alive&&timer&&workspace.isConnected)await save();await chain.catch(()=>{});alive=false;clearTimeout(timer);window.removeEventListener('beforeunload',warn)};
  render();
 }
 list();
}
function parseTaxCsv(raw){
 const rows=[];let row=[],cell='',quoted=false;
 for(let n=0;n<raw.length;n++){const ch=raw[n];if(ch==='"'){if(quoted&&raw[n+1]==='"'){cell+='"';n++}else quoted=!quoted}else if(ch===','&&!quoted){row.push(cell);cell=''}else if(ch==='\n'&&!quoted){row.push(cell.replace(/\r$/,''));if(row.some(x=>x))rows.push(row);row=[];cell=''}else cell+=ch}
 if(quoted)throw Error('CSV quote is not closed');if(cell||row.length){row.push(cell.replace(/\r$/,''));rows.push(row)}
 const headers=rows.shift()||[],expected=['kind','payer','amount','withholding','qualified_dividends'];if(headers.join(',')!==expected.join(','))throw Error('Use the income CSV template headers');
 if(rows.length>100||rows.some(r=>r.length!==headers.length))throw Error('Invalid CSV rows');return rows.map(r=>Object.fromEntries(headers.map((h,n)=>[h,r[n]])));
}

function refundControls(review,year=2026){
 const m=v=>formatMoneyMinor(v,'USD'),p=review.projection;
 return '<h3>Lawful refund optimization review</h3><p>Find documented opportunities and compare supported year-specific estimated-tax scenarios. No guaranteed maximum refund. AI cannot invent income, expenses, dependents or eligibility. Complete the interview and resolve unsupported issues before a projection is available.</p><label><input id="tax-refund-verified" type="checkbox"> I verified all income, federal withholding and payments, their tax year, and absence of duplicates.</label><label><input id="tax-refund-other" type="checkbox"> I verified that no other taxes, credits, adjustments or special situations apply. I understand unimplemented benefits need separate qualified review.</label><label><input id="tax-refund-charity" type="checkbox"> If claiming cash charity: I verified eligible 2026 cash donations, organization eligibility, supporting records, and that excluded gifts (including donor-advised funds) are not included.</label><button id="tax-refund-review">Calculate supported refund projection & review opportunities</button>'+(review.notice?'<p class="notice">'+esc(review.notice)+'</p>':'')+(review.blockers||[]).map(b=>'<p class="tax-error">'+esc(b)+'</p>').join('')+(p?'<h4>Best supported scenario: '+esc(p.selected)+'</h4><p>Estimated federal tax: '+m(p.estimated_federal_tax_cents)+' · Verified reported payments/withholding: '+m(p.payments_and_withholding_cents)+'</p><p>Estimated refund: '+m(p.estimated_refund_cents)+' · Estimated balance due: '+m(p.estimated_balance_due_cents)+' · Tax reduction within supported scenarios: '+m(p.supported_tax_savings_cents)+'</p>'+p.scenarios.map(s=>'<p>'+esc(s.name)+': estimated tax '+m(s.tax_cents)+'</p>').join(''):'')+(review.checklist||[]).map(c=>'<article class="card"><h4>'+esc(c.topic)+'</h4><p>'+esc(c.review)+'</p></article>').join('')+(review.sources||[]).map(s=>'<p><a href="'+esc(s.url)+'" target="_blank" rel="noopener noreferrer">'+esc(s.title)+'</a></p>').join('');
}
