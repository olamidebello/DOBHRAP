// Locale formatting never changes stored currency, provider amounts or operational data.
let intlState={locale:'en-US',currency:'USD',timezone:'UTC',translations:{},rates:[]},intlCatalog=null,intlObserver=null;
const intlOriginal=new WeakMap();
function t(phrase){return intlState.translations[phrase]||phrase}
function localeFormatter(options){try{return new Intl.NumberFormat(intlState.locale,options)}catch{return new Intl.NumberFormat('en-US',options)}}
function formatMoneyMinor(minor,currency){const digits=intlCatalog?.currencies.find(c=>c.id===currency)?.digits??2;return localeFormatter({style:'currency',currency}).format(Number(minor||0)/10**digits)}
function formatLedgerMinor(minor){
 const original=formatMoneyMinor(minor,'USD');if(intlState.currency==='USD')return original;
 const rate=intlState.rates.find(r=>r.currency===intlState.currency);
 if(!rate)return original;
 const age=(Date.now()-Date.parse(rate.as_of+'T00:00:00Z'))/86400000;
 if(age>=8||age<0)return original;
 return '≈'+localeFormatter({style:'currency',currency:intlState.currency}).format(Number(minor||0)/100*Number(rate.per_usd))+' ('+original+')';
}
function localizedDate(value){try{return new Intl.DateTimeFormat(intlState.locale,{dateStyle:'medium',timeStyle:'short',timeZone:intlState.timezone}).format(new Date(value))}catch{return String(value)}}
function localizeChrome(){
 for(const el of document.querySelectorAll('#workspace-tools button, #logout, #nav-toggle, #content h2, #content button[id], #nav summary')){
  if(el.children.length||el.matches('input,textarea,pre')||el.dataset.ticket)continue;
  const source=intlOriginal.get(el)||el.textContent;
  intlOriginal.set(el,source);const target=t(source);if(el.textContent!==target)el.textContent=target;
 }
}
async function loadInternational(preferences){
 intlCatalog ||= await api('intl/catalog');
 const bundle=await api('intl/bundle');intlState={...intlState,...preferences,...bundle.preferences,translations:bundle.translations,rates:bundle.rates};
 const locale=intlCatalog.locales.find(l=>l.id===intlState.locale);document.documentElement.lang=intlState.locale;document.documentElement.dir=locale?.direction||'ltr';
 if(!intlObserver){intlObserver=new MutationObserver(()=>localizeChrome());intlObserver.observe(document.body,{childList:true,subtree:true})}
 let bar=document.querySelector('#locale-quick');if(!bar){bar=document.createElement('button');bar.id='locale-quick';bar.type='button';bar.onclick=()=>show('locale_settings');document.querySelector('main>header').append(bar)}
 bar.textContent=(locale?.native||intlState.locale)+' · '+intlState.currency;bar.hidden=false;localizeChrome();
}
async function showLocaleSettings(){
 intlCatalog ||= await api('intl/catalog');const pref=await api('intl/preferences');
 const localeOptions=intlCatalog.locales.map(l=>`<option value="${esc(l.id)}" ${pref.locale===l.id?'selected':''}>${esc(l.native+' — '+l.name+' ['+l.id+']')}</option>`).join('');
 const currencyOptions=intlCatalog.currencies.map(c=>`<option value="${c.id}" ${c.id===pref.currency?'selected':''}>${esc(c.id+' — '+c.name+(c.active?'':' (historical / special)'))}</option>`).join('');
 content.innerHTML='<section><h2>'+esc(t('Language & currency'))+'</h2><p>'+esc(intlCatalog.notice)+'</p><p>'+intlCatalog.locales.length+' locale variants · '+intlCatalog.currencies.length+' currency codes. Core navigation translations are included for '+intlCatalog.translation_seed_languages.join(', ')+'. Other interface text uses English until an administrator supplies translations.</p><form id="locale-form"><label>Language / locale<select name="locale">'+localeOptions+'</select></label><label>Preferred display currency<select name="currency">'+currencyOptions+'</select></label><label>Time zone<select name="timezone">'+intlCatalog.timezones.map(z=>'<option '+(z===pref.timezone?'selected':'')+'>'+esc(z)+'</option>').join('')+'</select></label><button>'+esc(t('Save'))+'</button></form><p id="locale-preview"></p><p>Ledger balances remain USD. Optional reference-rate previews never change books or payment settlement. Historical/special codes are available for formatting and do not imply payment support.</p></section>';
 const preview=()=>{const form=content.querySelector('#locale-form');let sample;try{sample=new Intl.NumberFormat(form.elements.locale.value,{style:'currency',currency:form.elements.currency.value}).format(1234.56)}catch{sample='Browser formatting fallback'}content.querySelector('#locale-preview').textContent='Formatting preview (not a conversion): '+sample};
 content.querySelector('#locale-form').onchange=preview;preview();
 content.querySelector('#locale-form').onsubmit=e=>{e.preventDefault();safeRun(async()=>{await api('intl/preferences',Object.fromEntries(new FormData(e.target)));message('Language, currency and time zone saved');await boot();await show('locale_settings')})};
 if(userRole!=='super_admin'){content.querySelector('#locale-form').dataset.localeReady=pref.locale;return;}
 content.insertAdjacentHTML('beforeend','<section><h2>Interface translations</h2><p>Publish plain-text English phrase → translation entries for your selected locale. Empty translations remove an override. Business records, ticket messages and provider payloads are never translated automatically.</p><form id="translation-form"><label>Translation JSON<textarea name="entries" rows="8" required>{"Business dashboard":""}</textarea></label><button>Save translations for '+esc(pref.locale)+'</button></form><button id="translation-export">Export current phrase catalog</button></section><section><h2>Display-only exchange rates</h2><p>Enter target currency units per 1 USD, the date and a named source. Rates older than seven days stop converting the preview. These rates never price a checkout or post a journal.</p><form id="display-fx"><label>Currency<select name="currency">'+currencyOptions+'</select></label><label>Units per USD<input name="per_usd" type="number" min="0.000000000001" step="any" required></label><label>As of<input name="as_of" type="date" required></label><label>Source<input name="source" required maxlength="200"></label><button>Save reference rate</button></form><div id="display-rates"></div></section>');
 content.querySelector('#translation-form').onsubmit=e=>{e.preventDefault();safeRun(async()=>{await api('intl/translations',{locale:pref.locale,entries:JSON.parse(new FormData(e.target).get('entries'))});message('Translations saved');await boot();show('locale_settings')})};
 content.querySelector('#translation-export').onclick=()=>safeRun(async()=>{const bundle=await api('intl/bundle');const entries=Object.fromEntries(bundle.phrases.map(p=>[p,bundle.translations[p]||'']));const url=URL.createObjectURL(new Blob([JSON.stringify(entries,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='interface-'+pref.locale+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
 const renderRates=async()=>{const r=await api('intl/rates');content.querySelector('#display-rates').innerHTML=table(r,['currency','per_usd','as_of','source'])};await renderRates();
 content.querySelector('#display-fx').onsubmit=e=>{e.preventDefault();safeRun(async()=>{await api('intl/rates',Object.fromEntries(new FormData(e.target)));message('Reference display rate saved');await loadInternational(pref);await renderRates()})};
 content.querySelector('#locale-form').dataset.localeReady=pref.locale;
}

function formatLocalizedCell(key,value){
 if(value===null||value===undefined||value==='')return value;
 if(['created','updated','checked','activated','started','last_sync','next_sync','last_signed_event'].includes(key)){
  if(typeof value==='number')return value>0?localizedDate(value*1000):'—';
  if(/^\d{4}-\d{2}-\d{2}[ T]\d{2}:/.test(String(value)))return localizedDate(String(value).replace(' UTC','').replace(' ','T').replace(/Z$/,'')+'Z');
 }
 if(key==='date'&&/^\d{4}-\d{2}-\d{2}$/.test(String(value))){try{return new Intl.DateTimeFormat(intlState.locale,{dateStyle:'medium',timeZone:'UTC'}).format(new Date(value+'T00:00:00Z'))}catch{}}
 return value;
}
