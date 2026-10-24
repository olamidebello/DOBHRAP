const assert=require('node:assert/strict'),fs=require('fs'),{JSDOM}=require('jsdom');
(async()=>{
 const d=new JSDOM('<div id="content"></div>',{runScripts:'outside-only',url:'https://example.test/'}),w=d.window,calls=[];
 w.content=w.document.querySelector('#content');w.userRole='super_admin';w.esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');w.title=v=>v.replaceAll('_',' ');w.formatMoneyMinor=(v,c)=>c+' '+(v/100).toFixed(2);w.goButtons=()=>{};w.message=()=>{};w.confirm=()=>true;w.table=()=>'<table></table>';let pending=Promise.resolve();w.safeRun=fn=>(pending=Promise.resolve().then(fn));
 const policy={enabled:true,rates_verified:true,model:'gpt-4.1',input_per_million:'2',cached_per_million:'0.5',output_per_million:'8',max_output_tokens:2000,daily_requests:50};
 w.api=async(route,body)=>{calls.push({route,body});if(route==='ai-service/status')return {values:policy,key_configured:true,balance_cents:1000,requests:[]};if(route==='ai-service/admin')return {values:policy,revision:1,requests:[]};if(route==='ai-service/quote')return {maximum_cents:5,revision:1};if(route==='ai-service/chat')return {id:'request-1',state:'completed',reserved:5,charged:1,model:'gpt-4.1',answer:'<script>unsafe()</script>',billing:{provider_cost_usd:'0.001'}};throw Error(route)};
 w.eval(fs.readFileSync('ai-services.js','utf8'));await w.showAIService();const f=w.document.querySelector('#ai-chat-form');f.elements.prompt.value='Test';f.elements.consent.checked=true;f.dispatchEvent(new w.Event('submit',{cancelable:true}));await pending;
 assert.equal(w.document.querySelector('#ai-response script'),null);assert(w.document.querySelector('#ai-response').textContent.includes('<script>unsafe()'));
 const sent=calls.find(c=>c.route==='ai-service/chat');assert.equal(sent.body.maximum_cents,5);assert.equal(sent.body.consent,true);assert(sent.body.request_key);
 w.document.querySelector('#ai-admin-open').click();await pending;const admin=w.document.querySelector('#ai-policy');assert(admin);admin.elements.provider.value='claude';admin.dispatchEvent(new w.Event('submit',{cancelable:true}));await pending;
 const save=calls.find(c=>c.route==='ai-service/admin'&&c.body);assert.equal(save.body.policy.input_per_million,'2');assert.equal(save.body.policy.enabled,true);assert.equal(save.body.policy.provider,'claude');assert.equal(save.body.revision,1);
 console.log('AI assistant consent, quote, safe answer rendering and admin pricing GUI passed');
})().catch(e=>{console.error(e);process.exit(1)});
