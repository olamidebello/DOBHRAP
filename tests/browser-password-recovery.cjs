const {chromium}=require('playwright');
const assert=require('assert');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:390,height:844}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const origin='http://127.0.0.1:8765';
 const initial='browser-test-password-123',updated='browser-recovered-password-456';
 async function login(password){
  await page.goto(origin+'/');
  await page.locator('#login input[name=email]').fill('ui@example.com');
  await page.locator('#login input[name=password]').fill(password);
  await page.locator('#login button').click();
  await page.locator('#change-password').waitFor();
 }
 try{
  await page.goto(origin+'/');
  await page.getByRole('link',{name:'Forgot password?',exact:true}).click();
  await page.locator('#password-recovery input[name=email]').waitFor();
  await page.getByRole('link',{name:'Back to sign in'}).click();
  const field=page.locator('#login input[name=password]');
  await page.locator('#login [data-password-visibility]').check();
  assert.equal(await field.getAttribute('type'),'text');
  await page.locator('#login [data-password-visibility]').uncheck();
  assert.equal(await field.getAttribute('type'),'password');
  await login(initial);
  await page.locator('#nav [data-page=users]').click();
  const form=page.locator('#admin-password-reset');
  await form.locator('[name=email]').fill('ui@example.com');
  await form.locator('[name=current_password]').fill(initial);
  await form.getByRole('button',{name:'Create reset link'}).click();
  const link=await page.locator('#admin-reset-result input').inputValue();
  const token=new URL(link).hash;
  assert(token.startsWith('#token='));
  await page.goto(origin+'/reset-password'+token);
  await page.locator('#password-recovery [name=password]').fill(updated);
  await page.locator('#password-recovery [name=confirm_password]').fill(updated);
  await page.getByRole('button',{name:'Update password',exact:true}).click();
  await page.getByText('Password updated. Sign in with your new password.',{exact:true}).waitFor();
  const denied=await page.request.get(origin+'/api/me');assert.equal(denied.status(),401);
  await login(updated);
  await page.locator('#change-password').click();
  await page.locator('#change-password-form [name=current_password]').fill(updated);
  await page.locator('#change-password-form [name=password]').fill(initial);
  await page.locator('#change-password-form [name=confirm_password]').fill(initial);
  await page.getByRole('button',{name:'Change password and sign out'}).click();
  await page.locator('#login').waitFor();
  await login(initial);
  assert.deepEqual(errors,[]);
  console.log('Mobile password recovery, visibility, admin link, session revocation and password change passed');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exit(1)});
