const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.SMETRA_PLAYWRIGHT_MODULE||'playwright');
const fixture=JSON.parse(fs.readFileSync('data/protected-estimates-fixture.json','utf8')),base=fixture.base;
assert.match(base,/^http:\/\/127\.0\.0\.1:\d+$/,'Disposable loopback fixture only');
const out=path.resolve('data/qa/mobile-2.2-density');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.SMETRA_CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const checks=[];
 try{
  for(const theme of ['dark','light'])for(const width of [320,390,640,1440]){
   const context=await browser.newContext({viewport:{width,height:900},reducedMotion:'reduce'});
   await context.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
   await context.addCookies([{name:'session',value:fixture.owner.token,url:base,httpOnly:true,sameSite:'Lax'}]);
   await context.addInitScript(theme=>localStorage.setItem('smetra_theme',theme),theme);
   const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(base+'/app#profile');await page.locator('.profile-stat').first().waitFor();await page.evaluate(()=>document.fonts.ready);
   const stats=await page.locator('.profile-stat strong').allTextContents();assert.equal(stats.length,6);
   const phone=width<=640;
   await page.waitForFunction(phone=>document.querySelector('.profile-help').open!==phone,phone);
   const compact=await page.locator('.profile-overview').evaluate(node=>Math.round(node.getBoundingClientRect().height));
   const baseline=await page.evaluate(()=>{
    const css=[...document.styleSheets].find(sheet=>sheet.href?.includes('mobile-density.css'));css.disabled=true;
    const height=Math.round(document.querySelector('.profile-overview').getBoundingClientRect().height);css.disabled=false;return height;
   });
   if(phone)assert(compact<baseline,`${theme}/${width}: profile occupies less height (${compact}<${baseline})`);
   assert.deepEqual(await page.locator('.profile-stat strong').allTextContents(),stats,'All numerical stats remain');
   const help=page.locator('.profile-help');
   if(phone){await help.locator('summary').focus();await page.keyboard.press('Enter');assert(await help.evaluate(n=>n.open));await help.locator('summary').click()}
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Profile has no horizontal overflow');
   await page.evaluate(()=>{document.activeElement?.blur();scrollTo(0,0)});
   await page.screenshot({path:path.join(out,`profile-${theme}-${width}.png`),fullPage:true});
   await page.locator('[data-account-section=usage]').click();await page.locator('.usage-summary-grid').waitFor();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Usage has no horizontal overflow');
   await page.screenshot({path:path.join(out,`usage-${theme}-${width}.png`),fullPage:true});
   await page.locator('[data-account-section=settings]').click();await page.locator('#hub-tab-account').click();
   await page.locator('#hub-panel-account').waitFor({state:'visible'});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Settings has no horizontal overflow');
   assert(await page.locator('#hub-panel-account .hub-row').first().locator('small').isVisible(),'Account identity is retained');
   await page.screenshot({path:path.join(out,`settings-${theme}-${width}.png`),fullPage:true});
   assert.deepEqual(errors,[],`${theme}/${width}: no JavaScript exceptions`);
   checks.push({theme,width,compact,baseline,stats,keyboardDisclosure:true,noOverflow:true,noErrors:true});await context.close();
  }
 }finally{await browser.close()}
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(checks,null,2));console.log('PASS: compact profile, usage and settings at 320/390/640/1440px in both themes; numerical data, keyboard disclosure, no overflow or JS errors');
})().catch(error=>{console.error(error);process.exit(1)});
