/* Isolated CI browser: clean composer, responsive layout and existing quote access. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require(process.env.SMETRA_PLAYWRIGHT_MODULE||'playwright');
const fixture=JSON.parse(fs.readFileSync('data/protected-estimates-fixture.json','utf8'));
assert.equal(new URL(fixture.base).hostname,'127.0.0.1','Disposable loopback fixture only');
(async()=>{
 const thread={id:fixture.assistant_thread_id};assert.ok(thread.id,'Fixture includes a saved quote conversation');
 const browser=await chromium.launch({headless:true,executablePath:process.env.SMETRA_CHROME_PATH});
 const errors=[],output='data/qa/document-assistant';fs.mkdirSync(output,{recursive:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
  await context.addCookies([{name:'session',value:fixture.owner.token,url:fixture.base,httpOnly:true,sameSite:'Lax'}]);
  await context.route('**/*',route=>new URL(route.request().url()).origin===fixture.base?route.continue():route.abort());
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await page.goto(fixture.base+'/app#assistant');await page.locator('#assistant-input').waitFor();
  const threadButton=page.locator('[data-conversation="'+thread.id+'"]');
  if(!await threadButton.isVisible())await page.locator('#assistant-history-toggle').click();
  await threadButton.click();
  await page.locator('[data-thread-id="'+thread.id+'"].is-active').waitFor();
  await page.waitForFunction(()=>typeof document.querySelector('#assistant-form')?.onsubmit==='function');
  await page.locator('#assistant-input').fill('Проверь дизайн-проект и ведомость отделки');
  const footer=page.locator('.assistant-composer-foot');
  assert.equal(await page.locator('#assistant-context,.smetra-quote-chip').count(),0);
  await page.locator('#smetra-quote-preview').waitFor({state:'attached'});
  if(await page.locator('#smetra-quote-preview').isVisible()){
   await page.getByRole('button',{name:'Закрыть предпросмотр',exact:true}).click();
   await page.locator('#smetra-quote-preview').waitFor({state:'hidden'});
  }
  await page.locator('#assistant-quotes').click();
  await page.locator('#smetra-quote-preview').waitFor({state:'visible'});
  await page.getByRole('button',{name:'Закрыть предпросмотр',exact:true}).click();
  await page.locator('#smetra-quote-preview').waitFor({state:'hidden'});
  for(const theme of ['dark','light'])for(const width of [320,390,768,1440]){
   await page.setViewportSize({width,height:900});
   await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;
    document.querySelector('#assistant-status').textContent='Анализирую запрос…';},theme);
   await page.waitForTimeout(100);
   assert.equal((await footer.textContent()).trim(),'ИИ может ошибаться. Проверяйте важные данные.');
   assert.ok(await footer.isVisible(),theme+' '+width+' disclaimer visible');
   const layout=await page.evaluate(()=>{
    const form=document.querySelector('#assistant-form').getBoundingClientRect(),
     note=document.querySelector('.assistant-composer-foot').getBoundingClientRect(),
     status=document.querySelector('#assistant-status').getBoundingClientRect();
    return {overflow:document.documentElement.scrollWidth>innerWidth+1,
     form:{left:form.left,right:form.right,bottom:form.bottom},note:{top:note.top,bottom:note.bottom},statusWidth:status.width};
   });
   assert.equal(layout.overflow,false,theme+' '+width+' no overflow');
   assert.ok(layout.form.left>=-1&&layout.form.right<=width+1,'Composer fits viewport');
   assert.ok(layout.note.top>=layout.form.bottom-1,'Only disclaimer below input');
   assert.ok(layout.statusWidth<=1,'Operational status stays visually hidden');
   assert.equal(await page.locator('#assistant-context,.smetra-quote-chip').count(),0);
   assert.equal(await page.locator('#assistant-input').inputValue(),'Проверь дизайн-проект и ведомость отделки');
   if(width===390)await page.screenshot({path:output+'/composer-'+theme+'.png',fullPage:true});
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: clean assistant composer, quote panel access, saved draft, fixed disclaimer and hidden live statuses at 320/390/768/1440 in dark/light; no overflow or JS errors');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
