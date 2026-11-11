/* Real local API; responsive density, disclosure accessibility and draft safety. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require(process.env.SMETRA_PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const origin=process.env.SMETRA_COMPACT_ORIGIN||'http://localhost:8084';
 assert.ok(['localhost','127.0.0.1'].includes(new URL(origin).hostname),'Disposable fixture only');
 const browser=await chromium.launch({headless:true,executablePath:process.env.SMETRA_CHROME_PATH});
 const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,reducedMotion:'reduce'});
 const page=await context.newPage(),errors=[],measurements=[];
 const output='data/qa/mobile-compact';fs.mkdirSync(output,{recursive:true});
 page.on('pageerror',error=>errors.push(error.message));
 await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
 const navigate=async route=>{await page.evaluate(async route=>{tab=route;await render()},route);await page.waitForFunction(route=>document.querySelector('#content')?.dataset.section===route,route);await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(100)};
 const noOverflow=async label=>assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),label+' fits the viewport');
 try{
  await page.goto(origin+'/app');await page.waitForFunction(()=>document.querySelector('#auth-form')?.onsubmit);
  await page.evaluate(()=>{document.querySelector('#email').value='android-design@test.invalid';document.querySelector('#password').value='android design test only';document.querySelector('#auth-submit').click()});
  await page.waitForSelector('#assistant-form');
  for(const theme of ['dark','light'])for(const width of [320,390,430,640,768,1440]){
   await page.setViewportSize({width,height:844});await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
   for(const route of ['profile','usage','calculators','files','billing']){
    await navigate(route);await noOverflow(theme+' '+width+' '+route);
    await page.waitForFunction(compact=>[...document.querySelectorAll('[data-mobile-disclosure]')].every(node=>node.open!==compact),width<=640);
    if(width===390){
     const height=await page.evaluate(()=>document.documentElement.scrollHeight);measurements.push({theme,route,height});
     if(route==='profile')assert.ok(height<1600,'Profile summary is compact');
     if(route==='usage')assert.ok(height<1300,'Usage summary is compact');
     if(route==='calculators')assert.ok(height<1050,'Calculator result is close to the inputs');
     await page.screenshot({path:output+'/'+route+'-'+theme+'.png',fullPage:true});
    }
   }
  }
  await page.setViewportSize({width:390,height:844});await navigate('profile');
  const chart=page.locator('.profile-chart-details');
  await chart.locator('summary').focus();await page.keyboard.press('Enter');await page.waitForFunction(()=>document.querySelector('.profile-chart-details').open);
  assert.ok(await page.locator('.profile-chart-bars').isVisible(),'Chart can be opened with the keyboard');
  await page.locator('[data-profile-period=month]').click();await page.waitForFunction(()=>document.querySelector('.profile-chart-details').open);
  await page.setViewportSize({width:1440,height:900});await page.waitForFunction(()=>[...document.querySelectorAll('[data-mobile-disclosure]')].every(node=>node.open));
  await page.setViewportSize({width:390,height:844});assert.ok(await chart.evaluate(node=>node.open),'Phone expansion survives a viewport change');
  await navigate('usage');await page.locator('.usage-history summary').click();assert.ok(await page.locator('.usage-ledger').isVisible(),'All token transactions remain available');
  await navigate('calculators');
  await page.locator('#smcalc-fields input').first().fill('5');
  assert.equal((await page.locator('#smcalc-primary').textContent()).trim(),'16,5');
  await page.locator('.smcalc-options summary').click();await page.locator('#smcalc-unit-mode').selectOption('packages');
  assert.match(await page.locator('#smcalc-draft-qty').textContent(),/12/,'Package rounding survives the compact layout');
  await page.locator('.smcalc-options summary').click();assert.ok(await page.locator('#smcalc-draft').isVisible(),'Primary action remains outside the collapsed options');
  await navigate('construction');await page.locator('.construction-object').first().click();
  await page.waitForSelector('.construction-section[data-mobile-disclosure]',{state:'attached'});
  assert.equal(await page.locator('.construction-section[data-mobile-disclosure]').count(),10,'All object sections, including own rates, remain available');
  assert.equal(await page.locator('#construction-actual-rates').count(),1,'Own rates section must stay available on mobile');
  await page.waitForFunction(()=>[...document.querySelectorAll('.construction-section[data-mobile-disclosure]')].every(node=>!node.open));
  const section=page.locator('.construction-section').filter({has:page.locator('#construction-zone')});
  await section.locator(':scope > summary').click();
  await page.locator('#construction-zone [name=name]').fill('Draft room');
  await section.locator(':scope > summary').click();await section.locator(':scope > summary').click();
  assert.equal(await page.locator('#construction-zone [name=name]').inputValue(),'Draft room','Collapsing never recreates form controls');
  await page.setViewportSize({width:844,height:390});await noOverflow('Landscape object');
  await page.waitForFunction(()=>[...document.querySelectorAll('.construction-section[data-mobile-disclosure]')].every(node=>node.open));
  assert.equal(await page.locator('#construction-zone [name=name]').inputValue(),'Draft room','Rotation preserves unfinished form values');
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>document.activeElement?.blur());
  await page.screenshot({path:output+'/object-outline.png',fullPage:true});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(output+'/result.json',JSON.stringify({measurements,errors},null,2));
  console.log('PASS: compact mobile screens in dark/light at 320–1440, native keyboard disclosure, live calculator, visible primary action, object form drafts and rotation; no overflow or JS errors');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exit(1)});
