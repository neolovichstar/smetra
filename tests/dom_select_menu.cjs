const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
(async()=>{
 const dom=new JSDOM('<form><label for="currency">Валюта</label><select id="currency" name="currency" required><option value="">Выберите</option><option value="RUB">Рубли</option><option value="USD">Доллары</option><optgroup label="Недоступные" disabled><option value="EUR">Евро</option></optgroup></select></form>',{url:'https://test.invalid',runScripts:'dangerously'}),w=dom.window,d=w.document;
 try{
  w.matchMedia=()=>({matches:true});w.HTMLElement.prototype.scrollIntoView=()=>{};
  const script=d.createElement('script');script.textContent=fs.readFileSync('apps/web/select-menu.js','utf8');d.head.append(script);
  const select=d.querySelector('select'),trigger=d.querySelector('.select-trigger');let inputs=0,changes=0;
  select.addEventListener('input',()=>inputs++);select.addEventListener('change',()=>changes++);
  assert.equal(d.querySelectorAll('.select-trigger').length,1);assert.equal(select.tabIndex,-1);assert.equal(trigger.getAttribute('aria-expanded'),'false');
  trigger.click();const search=d.querySelector('.select-menu-search');assert.equal(d.activeElement,search);
  search.value='дол';search.dispatchEvent(new w.Event('input'));assert.equal(d.querySelectorAll('.select-option').length,1);
  search.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await tick();assert.equal(select.value,'USD');assert.equal(new w.FormData(d.querySelector('form')).get('currency'),'USD');assert.equal(inputs,1);assert.equal(changes,1);assert.equal(d.activeElement,trigger);assert.equal(d.querySelector('.select-menu'),null);
  select.value='RUB';w.SmetraSelects.enhance(d);assert.equal(trigger.textContent,'Рубли');
  trigger.click();assert.equal(d.querySelector('.select-option:last-child').disabled,true);
  const option=d.createElement('option');option.value='BYN';option.textContent='Белорусские рубли';select.append(option);await tick();assert.ok(d.querySelector('.select-menu').textContent.includes('Белорусские рубли'));
  d.querySelector('.select-menu-search').dispatchEvent(new w.KeyboardEvent('keydown',{key:'End',bubbles:true}));d.querySelector('.select-menu-search').dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await tick();assert.equal(select.value,'BYN');
  const dialog=d.createElement('dialog');dialog.open=true;dialog.innerHTML='<label>Клиент<select><option>Первый</option><option>Второй</option></select></label>';d.body.append(dialog);await tick();dialog.querySelector('.select-trigger').click();assert.ok(dialog.querySelector('.select-menu'),'Fallback popup lives in open dialog');dialog.open=false;await tick();await tick();assert.equal(d.querySelector('.select-menu'),null);
  trigger.click();select.closest('.select-control').remove();await tick();await tick();assert.equal(d.querySelector('.select-menu'),null);
  console.log('PASS: searchable selects, keyboard, form events/data, disabled groups, updates, programmatic restore, dialog and removal cleanup');
 }finally{dom.window.close()}
})().catch(error=>{console.error(error);process.exit(1)});
