/* Local fixture only. Payment provider responses are simulated; no money moves. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.SMETRA_PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const origin=process.env.SMETRA_PAYMENT_TEST_ORIGIN||'http://localhost:8084';assert.ok(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
 const browser=await chromium.launch({executablePath:process.env.SMETRA_CHROME_PATH,headless:true});
 const folder='data/qa/payments';fs.mkdirSync(folder,{recursive:true});const errors=[],external=[];
 try{
  const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  await context.route('**/*',route=>{const url=new URL(route.request().url());if(['http:','https:'].includes(url.protocol)&&url.origin!==origin){external.push(url.hostname);return route.abort()}return route.continue()});
  await page.goto(origin+'/app');await page.waitForFunction(()=>document.querySelector('#auth-form')?.onsubmit);
  await page.evaluate(()=>{document.querySelector('#email').value='android-design@test.invalid';document.querySelector('#password').value='android design test only';document.querySelector('#auth-submit').click()});
  await page.waitForSelector('#assistant-input');await page.evaluate(async()=>{tab='billing';await render()});await page.waitForFunction(()=>!!window.SmetraPaymentUI);
  // The local API owns pricing and auth; only its synchronization outcome is stubbed.
  let paymentStatus='pending',calls=0;
  await page.route('**/api/billing/sync',async route=>{calls++;const current=await page.evaluate(()=>JSON.parse(JSON.stringify(user)));await route.fulfill({contentType:'application/json',body:JSON.stringify({user:current,payments:[{id:'qa-payment-'+paymentStatus,status:paymentStatus}]})})});
  const screenshot=async name=>page.screenshot({path:path.join(folder,name+'.png')});
  for(const theme of ['dark','light'])for(const width of [320,390,768,1440]){
   await page.setViewportSize({width,height:844});await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
   await page.evaluate(async()=>{await SmetraPaymentUI.paywall('other',()=>{})});await page.waitForSelector('dialog.payment-dialog[open]');await page.waitForFunction(()=>Number(getComputedStyle(document.querySelector('.payment-dialog')).opacity)>.999);
   const bounds=await page.locator('.payment-dialog').boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=width+1,'Paywall is inside '+width);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
   assert.equal(await page.evaluate(()=>document.activeElement.classList.contains('payment-action')),true,'Dialog has keyboard focus');
   await screenshot('offer-'+theme+'-'+width);await page.keyboard.press('Escape');await page.waitForSelector('.payment-dialog',{state:'detached'});
  }
  for(const status of ['pending','succeeded','canceled']){
   paymentStatus=status;await page.evaluate(status=>SmetraPaymentUI.remember(user,{payment_id:'qa-payment-'+status}),status);
   await page.locator('#catalog-sync,#sync').click();const kind=status==='succeeded'?'success':status==='canceled'?'failure':'waiting';
   await page.waitForSelector('.payment-dialog--'+kind);await page.waitForTimeout(700);await screenshot('status-'+status);
   assert.equal(await page.locator('.payment-dialog .payment-stroke').count(),status==='pending'?0:1);
   await page.locator('.payment-close').click();
  }
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.evaluate(()=>{SmetraPaymentUI.remember(user,{payment_id:'qa-reduced'});SmetraPaymentUI.outcome(user,authRevision,{payments:[{id:'qa-reduced',status:'succeeded'}]},{manual:true})});
  assert.equal(await page.locator('.payment-stroke').evaluate(element=>getComputedStyle(element).animationName),'none');await screenshot('success-reduced-motion');
  assert.deepEqual(errors,[]);assert.deepEqual(external,[],'Core UI works with third-party browser requests blocked');assert.equal(calls,3);
  console.log('PASS: real Chrome paywall at 320–1440, dark/light, keyboard, actual billing sync handlers, three outcomes, reduced motion, no external browser dependencies');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exit(1)});
