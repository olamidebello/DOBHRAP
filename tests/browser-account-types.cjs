const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true}),errors=[];
 try{
  for(const kind of ['personal','business']){
   const page=await browser.newPage({viewport:{width:390,height:844}});page.on('pageerror',e=>errors.push(e.message));
   await page.goto('http://127.0.0.1:8765/register');const form=page.locator('#registration');await form.waitFor();
   await form.locator('[name=account_type]').selectOption(kind);
   assert.equal(await form.locator('[name=company]').count(),kind==='personal'?0:1);
   if(kind==='business')await form.locator('[name=company]').fill('Account type browser business');
   await form.locator('[name=email]').fill(kind+'-type-browser@example.com');await form.locator('[name=password]').fill('account-type-password-123');await form.locator('[name=confirm_password]').fill('account-type-password-123');
   await form.locator('#registration-submit').click();await page.locator('#content').getByRole('heading',{name:kind==='personal'?'Tax services & payment':'Business overview',exact:true}).waitFor();
   const me=await page.evaluate(()=>api('me'));assert.equal(me.tenant.service_mode,kind==='personal'?'tax_only':'business');assert.equal(me.role,'admin');
   const pages=await page.locator('#nav [data-page]').evaluateAll(nodes=>nodes.map(n=>n.dataset.page));
   assert(pages.includes('tax_analyst'));assert(pages.includes('wallet'));assert(pages.includes('ai_chat'));
   assert.equal(pages.includes('customers'),kind==='business');assert.equal(pages.includes('employees'),kind==='business');
   for(const target of ['wallet','marketplace','tax_analyst','ai_chat']){
    await page.locator('#nav-toggle').click();await page.locator('#nav [data-page="'+target+'"]').click();await page.waitForFunction(p=>current===p,target);if(target==='wallet')await page.locator('#content').getByRole('heading',{name:'Account balance',exact:true}).waitFor();if(target==='marketplace')await page.locator('#content [data-buy]').first().waitFor();if(target==='tax_analyst')await page.locator('#analyst-file').waitFor();if(target==='ai_chat')await page.locator('#ai-chat-form').waitFor();
   }
   await page.close();
  }
  assert.deepEqual(errors,[]);console.log('Personal/business registration, persisted roles, mobile navigation, wallet, marketplace, tax and AI routes passed');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
