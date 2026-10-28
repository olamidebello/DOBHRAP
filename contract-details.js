let contractGridLibrary;
function loadContractGrid(){
 if(window.agGrid)return Promise.resolve();
 if(!contractGridLibrary)contractGridLibrary=new Promise((resolve,reject)=>{const s=document.createElement('script');s.src='https://cdn.jsdelivr.net/npm/ag-grid-community@34.3.1/dist/ag-grid-community.min.js';s.integrity='sha384-1m5FM32cqWvkVPC2kdiP5dLsQUO3OCeEAGgZ4RqzCWlsWcCVIM9HXAjD1A99GPs3';s.crossOrigin='anonymous';s.onload=resolve;s.onerror=()=>{contractGridLibrary=null;reject(Error('AG Grid could not load. Check connection and retry.'))};document.head.append(s)});
 return contractGridLibrary;
}
let contractResultsGrid,contractDetailsGrid,contractDetailsTimer;
let contractInfoGrids=[];
let contractDetailsGeneration=0;
function stopContractDetails(){for(const grid of contractInfoGrids)grid.destroy();contractInfoGrids=[];clearTimeout(contractDetailsTimer);contractDetailsGeneration++;if(contractDetailsGrid){contractDetailsGrid.destroy();contractDetailsGrid=null}}
async function renderContractResults(box,rows){
 if(contractResultsGrid){contractResultsGrid.destroy();contractResultsGrid=null}box.replaceChildren();
 await loadContractGrid();if(!box.isConnected)return;
 const fold=document.createElement('details');fold.open=true;const summary=document.createElement('summary');summary.textContent='Opportunities ('+rows.length+')';const filter=document.createElement('input');filter.placeholder='Filter these results…';filter.setAttribute('aria-label','Filter current opportunities');const gridBox=document.createElement('div');fold.append(summary,filter,gridBox);box.append(fold);box=gridBox;filter.oninput=()=>contractResultsGrid?.setGridOption('quickFilterText',filter.value);
 box.style.height='clamp(260px,52vh,420px)';box.style.width='100%';box.style.minWidth='0';
 contractResultsGrid=agGrid.createGrid(box,{theme:agGrid.themeQuartz,rowHeight:48,rowData:rows,pagination:true,suppressPaginationPanel:true,paginationPageSize:10,paginationPageSizeSelector:[10,25,50],defaultColDef:{sortable:true,filter:true,resizable:true,minWidth:150},columnDefs:[{headerName:'Contract',field:'title',flex:2,minWidth:250,wrapText:true,autoHeight:true},{headerName:'Organization',field:'fullParentPathName',flex:1,hide:true},{headerName:'Solicitation',field:'solicitationNumber',hide:true},{headerName:'Response deadline',field:'responseDeadLine'},{headerName:'NAICS',field:'naicsCode',hide:true},{headerName:'Actions',pinned:'left',width:110,minWidth:110,sortable:false,filter:false,cellRenderer:p=>{const b=document.createElement('button');b.textContent='Details';b.disabled=userRole==='viewer';b.onclick=()=>safeRun(()=>showContractDetails(p.data.notice_id));return b}}]});
 addContractPager(box,contractResultsGrid);
}
function addContractPager(container,grid){
 const nav=document.createElement('nav');nav.setAttribute('aria-label','Grid pages');nav.style.cssText='display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:12px 0';
 const previous=document.createElement('button'),next=document.createElement('button'),label=document.createElement('span');previous.textContent='Previous page';next.textContent='Next page';previous.type=next.type='button';
 previous.onclick=()=>grid.paginationGoToPreviousPage();next.onclick=()=>grid.paginationGoToNextPage();nav.append(previous,label,next);container.after(nav);
 const refresh=()=>{if(!nav.isConnected)return;const page=grid.paginationGetCurrentPage(),total=grid.paginationGetTotalPages();label.textContent='Page '+(total?page+1:0)+' of '+total;previous.hidden=page===0;next.hidden=page+1>=total;nav.hidden=total<=1};
 grid.addEventListener('paginationChanged',refresh);refresh();return nav;
}
function contractRows(value,prefix=''){
 if(value&&typeof value==='object')return Object.entries(value).flatMap(([key,v])=>contractRows(v,prefix?prefix+' · '+key:key));
 return [{field:prefix.replace(/([a-z])([A-Z])/g,'$1 $2'),value:String(value??'Not supplied')}];
}
function contractInfoGrid(parent,rows){
 const holder=document.createElement('div');holder.style.cssText='height:clamp(240px,48vh,380px);width:100%;min-width:0';parent.append(holder);
 const grid=agGrid.createGrid(holder,{theme:agGrid.themeQuartz,rowData:rows,pagination:true,suppressPaginationPanel:true,paginationPageSize:8,defaultColDef:{sortable:true,filter:true,resizable:true,wrapText:true,autoHeight:true},columnDefs:[{field:'field',headerName:'Item',width:180,minWidth:130},{field:'value',headerName:'Details',flex:1,minWidth:220}]});contractInfoGrids.push(grid);addContractPager(holder,grid);return grid;
}
function contractDownload(name,text){const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function sourceValue(value){return typeof value==='object'?JSON.stringify(value,null,2):String(value??'Not supplied')}
function detailProgress(state,d){
 const progress=d.progress||{stage:d.state,message:d.state==='queued'?'Waiting for the document worker':'Preparing contract details'};
 const stages=['queued','notice','description','attachments','organizing','ready'];
 state.replaceChildren();const strong=document.createElement('strong');strong.textContent=progress.message;state.append(strong);
 if(progress.total){const count=document.createElement('p');count.textContent=progress.completed+' of '+progress.total+' attachments processed';state.append(count)}
 const list=document.createElement('ol');const current=stages.indexOf(['download','extraction'].includes(progress.stage)?'attachments':progress.stage);
 for(const [i,label] of ['Queued','Current notice','Description','Attachments: download & extraction / OCR','Organizing details','Ready'].entries()){const li=document.createElement('li');li.textContent=(i<current?'✓ ':i===current?'● ':'○ ')+label;if(i===current)li.setAttribute('aria-current','step');list.append(li)}
 state.append(list);
}
async function showContractDetails(nid,loaded=null){
 stopContractDetails();const generation=contractDetailsGeneration;
 if(contractResultsGrid){contractResultsGrid.destroy();contractResultsGrid=null}
 content.innerHTML='<section class="contract-screen"><button id="details-back">Back to opportunities</button><h2>Contract details</h2><div id="details-state" role="status" aria-live="polite">Opening contract details…</div><div id="details-body"></div></section>';
 content.querySelector('#details-back').onclick=()=>safeRun(showContracting);
 const state=content.querySelector('#details-state'),box=content.querySelector('#details-body');
 let d;
 try{d=loaded||await api('contracting/details',{notice_id:nid})}catch(error){if(generation===contractDetailsGeneration&&state.isConnected)state.textContent='Unable to load details: '+error.message;return}
 if(generation!==contractDetailsGeneration||!state.isConnected)return;
 detailProgress(state,d);
 if(d.state!=='ready'){
  const p=document.createElement('p');p.textContent=d.error||'This view updates automatically. You can return to the results while processing continues.';box.append(p);
  if(d.state==='failed'){const retry=document.createElement('button');retry.textContent='Retry retrieval';retry.onclick=()=>safeRun(async()=>{await api('contracting/details',{notice_id:nid,refresh:true});await showContractDetails(nid)});box.append(retry);return}
  const poll=async()=>{if(generation!==contractDetailsGeneration||!state.isConnected)return;try{const next=await api('contracting/details',{notice_id:nid});if(generation!==contractDetailsGeneration||!state.isConnected)return;if(next.state==='ready'||next.state==='failed'){await showContractDetails(nid,next);return}detailProgress(state,next)}catch(error){state.textContent='Progress connection interrupted. Retrying shortly.'}if(generation===contractDetailsGeneration&&state.isConnected)contractDetailsTimer=setTimeout(poll,5000)};
  contractDetailsTimer=setTimeout(poll,3000);return;
 }
 state.replaceChildren();state.textContent='Details ready';
 await loadContractGrid();if(!box.isConnected)return;
 const notice=d.notice;
 const h=document.createElement('h3');h.textContent=notice.title;box.append(h);const fresh=document.createElement('button');fresh.textContent='Refresh notice & attachments';fresh.onclick=()=>safeRun(async()=>{await api('contracting/details',{notice_id:nid,refresh:true});await showContractDetails(nid)});box.append(fresh);
 const warn=document.createElement('p');warn.textContent='Retrieved '+new Date(d.updated*1000).toLocaleString()+'. '+(d.coverage_complete?'Supported source extraction complete.':'INCOMPLETE COVERAGE: some sources require manual review.')+' '+(d.warnings||[]).join(' ');box.append(warn);
 const groups=[['Notice & deadlines',['noticeId','solicitationNumber','type','baseType','postedDate','reponseDeadLine','responseDeadLine','active','archiveDate']],['Organization & classification',['fullParentPathName','fullParentPathCode','naicsCode','classificationCode','typeOfSetAside','typeOfSetAsideDescription']],['Performance & contacts',['placeOfPerformance','officeAddress','pointOfContact']],['Award & other source metadata',Object.keys(notice).filter(k=>!['title','noticeId','solicitationNumber','type','baseType','postedDate','reponseDeadLine','responseDeadLine','active','archiveDate','fullParentPathName','fullParentPathCode','naicsCode','classificationCode','typeOfSetAside','typeOfSetAsideDescription','placeOfPerformance','officeAddress','pointOfContact'].includes(k))]];
 for(const [title,fields] of groups){const section=document.createElement('details');const heading=document.createElement('summary');heading.textContent=title;section.append(heading);box.append(section);const rows=fields.filter(k=>notice[k]!==undefined).flatMap(k=>contractRows(notice[k],k));let initialized=false;section.ontoggle=()=>{if(section.open&&!initialized){initialized=true;contractInfoGrid(section,rows)}}}
 const desc=document.createElement('details'),dh=document.createElement('summary');dh.textContent='Solicitation description';desc.append(dh);box.append(desc);let descriptionGrid=false;desc.ontoggle=()=>{if(desc.open&&!descriptionGrid){descriptionGrid=true;contractInfoGrid(desc,(d.description||'No description retrieved. Check official source.').split(/\n\s*\n/).filter(Boolean).map((value,i)=>({field:'Section '+(i+1),value})))}};

 const original=document.createElement('a');original.href='https://sam.gov/opp/'+encodeURIComponent(nid)+'/view';original.target='_blank';original.rel='noopener noreferrer';original.textContent='Verify current SAM.gov notice and amendments';box.append(original);
 const ah=document.createElement('h3');ah.textContent='Attachments & extracted text';const grid=document.createElement('div');grid.style.height='clamp(240px,45vh,360px)';grid.style.width='100%';box.append(ah,grid);await loadContractGrid();if(!grid.isConnected)return;
 contractDetailsGrid=agGrid.createGrid(grid,{theme:agGrid.themeQuartz,rowHeight:52,rowData:d.attachments||[],pagination:true,suppressPaginationPanel:true,paginationPageSize:10,defaultColDef:{sortable:true,filter:true,resizable:true,minWidth:140},columnDefs:[{field:'name',headerName:'Attachment',flex:2},{headerName:'Extraction',valueGetter:p=>p.data.complete?'Extracted':(p.data.notes||[]).join('; '),flex:2,wrapText:true,autoHeight:true},{field:'bytes',headerName:'Bytes'},{headerName:'Actions',minWidth:380,filter:false,sortable:false,cellRenderer:p=>{const span=document.createElement('span');const b=document.createElement('button');b.textContent='Extracted text';b.onclick=()=>{document.querySelector('#attachment-text').textContent=p.data.text||'No text extracted. Review the original.'};const download=document.createElement('button');download.textContent='Download text';download.onclick=()=>contractDownload(p.data.name+'.txt',p.data.text||'No text extracted');span.append(b,download);if(p.data.url){const a=document.createElement('a');a.href=p.data.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Original';span.append(a)}return span}}]});
 addContractPager(grid,contractDetailsGrid);
 const pre=document.createElement('pre');pre.id='attachment-text';pre.style.whiteSpace='pre-wrap';pre.style.maxHeight='400px';pre.style.overflow='auto';box.append(pre);
 const all=document.createElement('button');all.textContent='Download all extracted text';all.onclick=()=>contractDownload('contract-'+nid+'-sources.txt',JSON.stringify({notice,description:d.description,attachments:d.attachments,warnings:d.warnings},null,2));box.append(all);
 const rh=document.createElement('h3');rh.textContent='Summary & profile-based recommendations';box.append(rh);
 const info=document.createElement('p');info.textContent='Reports analyze each source segment separately. Read every section and check amendments for conflicts. Missing, scanned, restricted or unsupported material is explicitly excluded. Recommendations require human verification.';box.append(info);
 const report=d.report||{};const reportText=Object.entries(report.sections||{}).sort((a,b)=>Number(a[0])-Number(b[0])).map(([i,v])=>'SOURCE SEGMENT '+(Number(i)+1)+'\n'+v.text).join('\n\n');const rp=document.createElement('div');box.append(rp);let reportGrid=null;const renderReport=value=>{const rows=value.split(/\n\s*\n/).filter(Boolean).map((value,i)=>({field:'Report section '+(i+1),value}));if(reportGrid)reportGrid.setGridOption('rowData',rows);else reportGrid=contractInfoGrid(rp,rows)};renderReport(reportText||'No report generated yet.');
 const exportReport=document.createElement('button');exportReport.textContent='Download recommendations report';exportReport.onclick=()=>contractDownload('contract-'+nid+'-report.txt',reportText);box.append(exportReport);
 const quoteButton=document.createElement('button');quoteButton.textContent='Review analysis price';const quoteText=document.createElement('p');const consent=document.createElement('input');consent.type='checkbox';const label=document.createElement('label');label.append(consent,document.createTextNode(' I consent to source text and selected profile facts being sent to the document processing service and approve the displayed maximum total charge.'));const analyze=document.createElement('button');analyze.textContent='Analyze attachments & recommend';analyze.disabled=true;box.append(quoteButton,quoteText,label,analyze);
 let quote=null;const keys=[];
 quoteButton.onclick=()=>safeRun(async()=>{quote=await api('contracting/details-quote',{notice_id:nid});quoteText.textContent=quote.segments+' source segments · '+(quote.quotes[0]?.provider||'')+' / '+(quote.quotes[0]?.model||'')+' · maximum total $'+(quote.maximum_cents/100).toFixed(2)+'. '+quote.notice;analyze.disabled=false;for(let i=0;i<quote.segments;i++)keys[i]=crypto.randomUUID()});
 analyze.onclick=()=>safeRun(async()=>{if(!consent.checked)throw Error('Confirm data sharing and maximum charge first');analyze.disabled=true;quoteButton.disabled=true;try{for(let i=0;i<quote.segments;i++){if(report.fingerprint===quote.fingerprint&&report.sections?.[String(i)])continue;state.textContent='Report: reviewing source segment '+(i+1)+' of '+quote.segments+' — completed sections are saved';const q=quote.quotes[i];const result=await api('contracting/details-analyze',{notice_id:nid,fingerprint:quote.fingerprint,segment:i,consent:true,quote_revision:q.revision,maximum_cents:q.maximum_cents,request_key:keys[i]});if(!result.saved)throw Error('Request needs reconciliation; no automatic retry.');renderReport(Object.values(result.report.sections).map(v=>v.text).join('\n\n'))}await showContractDetails(nid)}finally{analyze.disabled=false;quoteButton.disabled=false}});
 const draft=document.createElement('button');draft.textContent='Draft recommended proposal';draft.disabled=!report.complete;draft.onclick=()=>safeRun(async()=>{const r=await api('contracting/details-draft',{notice_id:nid});contractingOpen=r.id;await showContracting();document.querySelector('#contract-quote').click();message('Review the price and consent, then Generate proposal. The saved review is included as provisional context. No bid has been submitted.')});box.append(draft);
 const foldRange=(first,last,title,open=false)=>{const fold=document.createElement('details');fold.open=open;const summary=document.createElement('summary');summary.textContent=title;box.insertBefore(fold,first);fold.append(summary);let node=first;while(node){const next=node.nextSibling;fold.append(node);if(node===last)break;node=next}return fold};
 foldRange(ah,all,'Attachments ('+(d.attachments||[]).length+') — sources & extracted text');
 foldRange(rh,analyze,'Summary & recommendations'+(report.complete?' — ready':''));
 draft.style.marginTop='16px';
}
