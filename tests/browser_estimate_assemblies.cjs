/* Real editor, server calculations and autosave against a disposable fixture. */
const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.SMETRA_PLAYWRIGHT_MODULE||'playwright');
const fixture=JSON.parse(fs.readFileSync('data/protected-estimates-fixture.json','utf8'));
assert.equal(new URL(fixture.base).hostname,'127.0.0.1');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.SMETRA_CHROME_PATH,args:['--no-sandbox']}),errors=[];
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.addCookies([{name:'session',value:fixture.owner.token,url:fixture.base,httpOnly:true,sameSite:'Lax'}]);
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await page.goto(fixture.base+'/app#quotes');
  await page.locator('[data-work="quote"][data-id="'+fixture.quote.id+'"]').first().click();
  await page.getByRole('button',{name:'Редактировать',exact:true}).click();
  const editor=page.locator('#estimate-editor');await editor.waitFor();
  await editor.locator('.assembly-panel summary').click();
  await editor.getByRole('button',{name:'Сохранить выбранные позиции как сборку'}).click();
  let dialog=page.locator('#workspace-dialog');
  await dialog.locator('[name=title]').fill('Облицовка из моих расценок');
  await dialog.locator('[name=base]').fill('2');
  await dialog.locator('[data-kind="1"]').selectOption('material');
  await dialog.getByRole('button',{name:'Сохранить сборку',exact:true}).click();await dialog.waitFor({state:'hidden'});
  await editor.getByRole('button',{name:'Добавить сборку',exact:true}).click();
  await dialog.locator('[data-param=volume]').fill('4');await dialog.getByRole('button',{name:'Рассчитать',exact:true}).click();
  await dialog.locator('[data-apply-assembly]').waitFor();
  assert.equal(await editor.locator('.editor-item').count(),2,'preview must not change estimate');
  await dialog.locator('[data-apply-assembly]').click();await dialog.waitFor({state:'hidden'});
  assert.equal(await editor.locator('.editor-item').count(),4);
  await editor.locator('.assembly-panel summary').click();
  await editor.getByRole('button',{name:'Изменить параметры',exact:true}).click();
  await dialog.locator('[data-param=volume]').fill('6');await dialog.getByRole('button',{name:'Рассчитать',exact:true}).click();
  await dialog.locator('[data-apply-assembly]').click();await dialog.waitFor({state:'hidden'});
  assert.equal(await editor.locator('.editor-item').nth(2).locator('[data-key=quantity]').inputValue(),'6.0000');
  assert.equal(await editor.locator('.editor-item').nth(3).locator('[data-key=quantity]').inputValue(),'9.0000');
  await editor.locator('.assembly-scope summary').click();
  await editor.locator('[name=scope_customer]').fill('Плитка заказчика');
  await editor.locator('[name=scope_excluded]').fill('Вывоз мусора');
  for(const width of [320,390,768,1440]){await page.setViewportSize({width,height:1000});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'editor width '+width)}
  await editor.getByRole('button',{name:'Сохранить и закрыть',exact:true}).click();
  await page.getByRole('button',{name:'Редактировать',exact:true}).waitFor();
  assert((await page.locator('.quote-detail').textContent()).includes('Плитка заказчика'));
  const result=await page.evaluate(async id=>{const r=await fetch('/api/quotes/'+id);return r.json()},fixture.quote.id);
  assert.equal(result.quote.items.length,4);assert.equal(result.quote.items[3].quantity,'9.0000');
  assert.equal(result.quote.items[3].assembly.parameters.volume,'6');
  assert.deepEqual(result.quote.scope.customer,['Плитка заказчика']);
  const published=await page.evaluate(async quote=>{const response=await fetch('/api/quotes/'+quote.id+'/publish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:quote.revision,review_confirmed:true})});return response.json()},result.quote);
  assert(published.quote);
  const link=await page.evaluate(async quote=>{const response=await fetch('/api/protected-links',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({quote_id:quote.id})});return response.json()},published.quote);
  assert(link.url);
  const customer=await browser.newContext({viewport:{width:390,height:844}}),document=await customer.newPage();document.on('pageerror',error=>errors.push(error.message));
  await document.goto(link.url);await document.locator('.protected-document h1').waitFor();
  assert((await document.locator('.protected-document').textContent()).includes('Плитка заказчика'));
  assert(!(await document.locator('.protected-document').innerHTML()).includes('volume *'));
  assert.deepEqual(errors,[]);
  console.log('PASS: create, server preview, explicit apply, linked recalculation, scope, autosave and 320/390/768/1440px editor');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
