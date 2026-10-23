const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true}),page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8765/');await page.locator('#login input[name=email]').fill('ui@example.com');await page.locator('#login input[name=password]').fill('browser-test-password-123');await page.locator('#login button').click();await page.locator('#content').getByRole('heading',{name:'Business overview',exact:true}).waitFor();
  const pages=await page.locator('#nav [data-page]').evaluateAll(nodes=>[...new Set(nodes.map(n=>n.dataset.page))]);
  for(const target of pages){
   const result=await page.evaluate(async p=>{document.querySelector('#status').textContent='';content.innerHTML='';await show(p);return {text:content.textContent,status:document.querySelector('#status').textContent,current};},target);
   assert.equal(result.current,target);assert(result.text.trim().length>10,target+': empty page; '+result.status);assert(!/ReferenceError|TypeError|is not defined|Cannot read properties/.test(result.status),target+': '+result.status);
  }
  assert.deepEqual(errors,[]);console.log('All '+pages.length+' visible super admin navigation destinations rendered against authenticated backend routes');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
