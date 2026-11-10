const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.SMETRA_PLAYWRIGHT_MODULE||'playwright');
const fixture=JSON.parse(fs.readFileSync('data/protected-estimates-fixture.json','utf8'));
const base=fixture.base;
assert.match(base,/^http:\/\/127\.0\.0\.1:\d+$/,'Use only the disposable local fixture');
const out=path.resolve('data/qa/mobile-2.2-guest');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.SMETRA_CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const checks=[];
 try{
  for(const theme of ['dark','light'])for(const width of [320,390,768]){
   const context=await browser.newContext({viewport:{width,height:900},isMobile:true,hasTouch:true,reducedMotion:'reduce'});
   await context.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
   await context.addInitScript(({theme})=>{
    localStorage.setItem('smetra_theme',theme);
    window.SmetraNative={postMessage(raw){const message=JSON.parse(raw);queueMicrotask(()=>this.onmessage?.({data:JSON.stringify({v:1,id:message.id,ok:true,result:message.op==='app.hello'?{features:{},operations:[],platform:'android'}:{}})}))}};
   },{theme});
   const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
   await page.goto(base+'/app');await page.locator('#smetra-guest').waitFor();await page.evaluate(()=>document.fonts.ready);
   assert.equal(await page.locator('#auth').isVisible(),false);
   assert.equal(await page.locator('#shell').isVisible(),false);
   await page.screenshot({path:path.join(out,`home-${theme}-${width}.png`)});
   await page.locator('[data-guest=draft]').click();
   await page.locator('[data-field=name]').fill('Покраска стен');await page.locator('[data-field=quantity]').fill('12,5');await page.locator('[data-field=price]').fill('380,25');
   assert.match(await page.locator('#guest-total').innerText(),/4\s?753,13/);
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
   assert.equal(overflow,false,`No draft overflow: ${theme}/${width}`);
   await page.screenshot({path:path.join(out,`draft-${theme}-${width}.png`),fullPage:true});
   await page.reload();await page.locator('[data-guest=draft]').click();
   assert.equal(await page.locator('[data-field=name]').inputValue(),'Покраска стен');
   await page.locator('[data-guest=save]').click();await page.locator('#auth-title').waitFor({state:'visible'});
   assert.equal(await page.locator('#smetra-guest').count(),0);
   assert.equal(await page.locator('#auth-register-tab').getAttribute('aria-selected'),'true');
   assert.ok(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('smetra.previewDraft')).items[0].unit_price===38025));
   await page.locator('#auth-guest').click();await page.locator('[data-guest=calculators]').click();await page.locator('#smcalc-primary').waitFor();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`No calculator overflow: ${theme}/${width}`);
   assert.deepEqual(errors,[],`No page exceptions: ${theme}/${width}`);
   checks.push({theme,width,guest:true,draft:true,persistence:true,authHandoff:true,calculators:true,noOverflow:true,noErrors:true});await context.close();
  }
 }finally{await browser.close()}
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(checks,null,2));console.log('PASS: real Chrome guest/calculator/draft/auth handoff at 320, 390 and 768px, dark and light; persistence, no overflow and no JavaScript errors');
})().catch(error=>{console.error(error);process.exit(1)});
