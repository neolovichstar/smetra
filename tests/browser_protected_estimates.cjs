/* Real local API + isolated browser contexts; no customer or production data. */
const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.SMETRA_PLAYWRIGHT_MODULE||'playwright');
const fixture=JSON.parse(fs.readFileSync(process.env.SMETRA_PROTECTED_FIXTURE||'data/protected-estimates-fixture.json','utf8'));
const base=fixture.base;
assert(['127.0.0.1','localhost'].includes(new URL(base).hostname),'Only a disposable loopback fixture is allowed');
fs.mkdirSync('data/qa/protected-estimates',{recursive:true});
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.SMETRA_CHROME_PATH?{executablePath:process.env.SMETRA_CHROME_PATH}:{}),args:['--no-sandbox']}),errors=[],checks=[];
  try{
    const anon=await browser.newContext({viewport:{width:390,height:844}}),page=await anon.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(fixture.url);await page.locator('.protected-document h1').waitFor();
    const html=await page.locator('body').innerHTML();
    for(const hidden of ['Скрытая технология стен','Секретный артикул','cost_price','internal_cost','Не раскрывать'])assert(!html.includes(hidden),hidden);
    assert.equal(await page.locator('[data-export]').count(),0);
    for(const width of [320,390,768,1440]){await page.setViewportSize({width,height:960});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'public width '+width);await page.screenshot({path:'data/qa/protected-estimates/customer-dark-'+width+'.png',fullPage:true})}
    await page.getByRole('button',{name:'Сменить тему'}).click();
    assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:'data/qa/protected-estimates/customer-light-mobile.png',fullPage:true});
    await page.emulateMedia({media:'print'});assert.equal(await page.locator('.protected-document').isVisible(),false);assert(await page.locator('.protected-print-denied').isVisible());await page.emulateMedia({media:'screen'});
    checks.push('320/390/768/1440px, light/dark, no hidden data in DOM, disabled exports and print');

    const owner=await browser.newContext({viewport:{width:1440,height:1000}});
    await owner.addCookies([{name:'session',value:fixture.owner.token,url:base,httpOnly:true,sameSite:'Lax'}]);
    const management=await owner.newPage();management.on('pageerror',error=>errors.push(error.message));
    await management.goto(base+'/app#quotes');
    await management.locator('[data-work="quote"][data-id="'+fixture.quote.id+'"]').first().click();
    await management.getByRole('button',{name:'Доступ и просмотры',exact:true}).click();
    await management.getByRole('button',{name:'Создать защищённую ссылку',exact:true}).click();
    const manager=management.locator('.protected-manager');
    const recipientLabel='Анна Заказчик '+Date.now();
    await manager.locator('[name=recipient_name]').fill(recipientLabel);
    await manager.locator('[name=recipient_email]').fill(fixture.recipient.email);
    await manager.locator('[name=mode]').selectOption('details');
    for(const key of ['show_quantities','show_prices','allow_pdf','allow_excel'])await manager.locator('[name='+key+']').check();
    await manager.locator('[name=code_mode]').selectOption('generate');
    for(const width of [320,390,768,1440]){await management.setViewportSize({width,height:960});assert(await manager.evaluate(el=>el.scrollWidth<=el.clientWidth+1),'manager width '+width)}
    await management.screenshot({path:'data/qa/protected-estimates/owner-settings-desktop.png',fullPage:true});
    await manager.getByRole('button',{name:'Создать защищённую ссылку',exact:true}).click();
    await manager.getByRole('heading',{name:'Ссылка готова',exact:true}).waitFor();
    const url=await manager.getByRole('textbox',{name:'Защищённая ссылка для заказчика',exact:true}).inputValue();
    const code=await manager.locator('input[aria-label="Код доступа"]').inputValue();
    await manager.getByRole('button',{name:'Закрыть настройки доступа',exact:true}).click();
    assert.equal(await manager.locator('input').count(),0,'Closing management removes URL/code and account data from DOM');
    await management.getByRole('button',{name:'Доступ и просмотры',exact:true}).click();
    await manager.getByRole('heading',{name:'Доступ и просмотры',exact:true}).waitFor();
    checks.push('owner creates a recipient-bound link, real disclosure settings and server-generated code');

    const customer=await anon.newPage();customer.on('pageerror',error=>errors.push(error.message));
    await customer.goto(url);await customer.locator('#protected-code').waitFor();
    await customer.locator('#protected-code').fill('wrong-code');await Promise.all([customer.waitForResponse(response=>response.url().endsWith('/api/public/protected/open')&&response.status()===401),customer.getByRole('button',{name:'Открыть предложение',exact:true}).click()]);
    await customer.waitForFunction(()=>document.querySelector('#protected-code')?.value==='');
    await customer.locator('#protected-code').fill(code);await customer.getByRole('button',{name:'Открыть предложение',exact:true}).click();
    await customer.locator('.protected-document h1').waitFor();
    assert((await customer.locator('.protected-table').textContent()).includes('Скрытая технология стен'));
    assert(!(await customer.locator('body').innerHTML()).includes('Секретный артикул'));
    for(const format of ['pdf','xlsx']){const [download]=await Promise.all([customer.waitForEvent('download'),customer.locator('[data-export='+format+']').click()]);await download.saveAs('data/qa/protected-estimates/allowed.'+format);assert.equal(await download.failure(),null)}
    await customer.emulateMedia({media:'print'});assert(await customer.locator('.protected-document').isVisible());assert(await customer.locator('.protected-watermarks').isVisible());await customer.emulateMedia({media:'screen'});
    checks.push('wrong/right access code, allowed redacted PDF/XLSX, watermark in print');

    await management.bringToFront();
    const row=manager.locator('.protected-link-row').filter({hasText:recipientLabel});
    await row.getByRole('button',{name:'Настройки',exact:true}).click();
    for(const key of ['allow_pdf','allow_excel','show_prices'])await manager.locator('[name='+key+']').uncheck();
    await manager.getByRole('button',{name:'Сохранить доступ',exact:true}).click();await manager.getByRole('heading',{name:'Доступ и просмотры',exact:true}).waitFor();
    await customer.bringToFront();await customer.waitForFunction(()=>document.querySelector('.protected-document')&&!document.querySelector('[data-export]'),{},{timeout:15000});
    assert(!(await customer.locator('.protected-table').textContent()).includes('Цена'));
    checks.push('permission changes replace active client document and remove export controls');

    await management.bringToFront();await row.getByRole('button',{name:'Отозвать',exact:true}).click();await manager.locator('input[type=checkbox]').check();await manager.getByRole('button',{name:'Подтвердить',exact:true}).click();
    await manager.getByRole('heading',{name:'Доступ и просмотры',exact:true}).waitFor();
    await customer.bringToFront();await customer.getByRole('heading',{name:'Доступ к смете',exact:true}).waitFor({timeout:15000});assert.equal(await customer.locator('.protected-document').count(),0);
    checks.push('revocation removes the document from an already open page');

    const recipient=await browser.newContext({viewport:{width:390,height:844}});
    await recipient.addCookies([{name:'session',value:fixture.recipient.token,url:base,httpOnly:true,sameSite:'Lax'}]);
    const decision=await recipient.newPage();decision.on('pageerror',error=>errors.push(error.message));
    await decision.goto(fixture.url);await decision.getByRole('button',{name:'Принять предложение',exact:true}).click();
    const confirmation=decision.locator('#protected-decision-dialog');await confirmation.locator('input[type=checkbox]').check();await confirmation.getByRole('button',{name:'Подтвердить решение',exact:true}).click();
    await decision.getByText('Принята',{exact:true}).first().waitFor();
    assert.equal(await decision.locator('[data-decision]').count(),0);
    checks.push('verified recipient accepts version through explicit mobile confirmation');
    assert.deepEqual(errors,[]);console.log(JSON.stringify({checks,errors},null,2));
    fs.writeFileSync('data/qa/protected-estimates/browser-result.json',JSON.stringify({checks,errors},null,2));
  }finally{await browser.close()}
})().catch(error=>{console.error(error.stack);process.exit(1)});
