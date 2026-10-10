/* Requires the existing disposable CI API and Chrome; never uses production. */
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const site='http://localhost:'+(process.env.SMETRA_TEST_PORT||'8082');
 const tabs=await(await fetch('http://127.0.0.1:'+(process.env.SMETRA_CDP_PORT||'9223')+'/json')).json();
 const ws=new WebSocket(tabs.find(tab=>tab.type==='page').webSocketDebuggerUrl);await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}));
 let sequence=0;const pending=new Map(),errors=[];
 ws.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result)}else if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.exception?.description||message.params.exceptionDetails.text)});
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,userGesture:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result.value};
 const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
 const until=async expression=>{for(let i=0;i<100;i++){if(await evaluate(expression))return;await sleep(100)}throw Error('Timeout: '+expression+'\n'+await evaluate('document.body.innerText.slice(-1800)'))};
 const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
 const fill=(selector,value)=>evaluate(`{const input=document.querySelector(${JSON.stringify(selector)});input.value=${JSON.stringify(value)};input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));}`);
 await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Network.deleteCookies',{name:'session',url:site});
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:site+'/app?register=1'});await until("document.querySelector('#auth-submit')&&typeof api==='function'");
 await fill('#name','Проверка редактора');await fill('#email','editor-'+Date.now()+'@test.invalid');await fill('#password','secure comparison password');await click('#auth-submit');await until("document.querySelector('#capture-text')");
 const id=await evaluate("api('/quotes',{method:'POST',body:JSON.stringify({title:'Ремонт кухни',client:'Клиент',items:[{name:'Подготовка',unit_price:10000},{name:'Покраска',unit_price:20000}]})}).then(r=>r.quote.id)");
 const catalogId=await evaluate("api('/catalog',{method:'POST',body:JSON.stringify({name:'Монтаж плинтуса QA',price:12500,unit:'м'})}).then(r=>r.item.id)");
 const clientId=await evaluate("api('/clients',{method:'POST',body:JSON.stringify({name:'Клиент редактора QA'})}).then(r=>r.item.id)");
 const read=()=>evaluate(`api('/quotes/${id}').then(r=>r.quote)`);
 await evaluate(`(async()=>{tab='quotes';location.hash='quotes';await Workspace.editor((await api('/quotes/${id}')).quote)})()`);
 await until("document.querySelector('#editor-save-state')");
 // The shipped custom menu owns focus while the native select owns form values.
 await until("document.querySelector('#f-currency + .select-trigger')");
 await click('#f-currency + .select-trigger');await fill('.select-menu-search','Доллары');await click('.select-option');assert.equal(await evaluate("document.querySelector('#f-currency').value"),'USD');
 await click('#f-currency + .select-trigger');await fill('.select-menu-search','Рубли');await click('.select-option');assert.equal(await evaluate("document.querySelector('#f-currency').value"),'RUB');
 await click('#f-client_id + .select-trigger');await fill('.select-menu-search','Клиент редактора QA');await click('.select-option');assert.equal(await evaluate("document.querySelector('#f-client').value"),'Клиент редактора QA');assert.equal(await evaluate("document.querySelector('#f-client_id').value"),clientId);
 assert.equal(await evaluate("document.querySelector('#f-client_id + .select-trigger').hasAttribute('data-ui-icon')"),false);
 await click('#f-catalog + .select-trigger');await fill('.select-menu-search','Монтаж плинтуса');await until(`document.querySelector('.select-menu:not(.select-menu-closing) [role=option]').textContent.includes('Монтаж плинтуса')`);await click('.select-menu:not(.select-menu-closing) .select-option');assert.equal(await evaluate("document.querySelectorAll('[data-row]').length"),3);assert.equal(await evaluate("document.querySelector('[data-row=\"2\"] [data-key=name]').value"),'Монтаж плинтуса QA');await click('#editor-undo');assert.equal(await evaluate("document.querySelectorAll('[data-row]').length"),2);assert.ok(catalogId);
 // A popover must also appear above a modal dialog's top layer.
 await evaluate(`{const dialog=document.createElement('dialog');dialog.id='select-test-dialog';dialog.innerHTML='<label>Выбор<select><option>Первый</option><option>Второй</option></select></label>';document.body.append(dialog);dialog.showModal();SmetraSelects.enhance(dialog);dialog.querySelector('.select-trigger').click()}`);
 assert.equal(await evaluate("document.querySelector('.select-menu:not(.select-menu-closing)').matches(':popover-open')"),true);
 await sleep(200);
 assert.equal(await evaluate("{const option=document.querySelector('.select-menu:not(.select-menu-closing) .select-option'),r=option.getBoundingClientRect();option.contains(document.elementFromPoint(r.left+r.width/2,r.top+r.height/2))}"),true);
 await evaluate("SmetraSelects.close();document.querySelector('#select-test-dialog').close();document.querySelector('#select-test-dialog').remove()");await sleep(180);
 await fill('#f-title','Новая кухня');await until("document.querySelector('#editor-save-state').dataset.state==='saved'");assert.equal((await read()).title,'Новая кухня');
 const starting=await read();
 await click('[data-duplicate="0"]');assert.equal(await evaluate("document.querySelectorAll('[data-row]').length"),3);
 await click('[data-move="0"][data-direction="1"]');await click('#editor-undo');await click('#editor-undo');assert.equal(await evaluate("document.querySelectorAll('[data-row]').length"),2);await click('#editor-redo');
 await fill('[data-row="1"] [data-key=name]','Дополнительная подготовка');
 await until("document.querySelector('#editor-save-state').dataset.state==='saved'");const duplicated=await read();assert.equal(duplicated.items.length,3);assert.notEqual(duplicated.items[0].line_id,duplicated.items[1].line_id);assert.equal(duplicated.amount_kopecks,40000);
 await click('.editor-device summary');await fill('#f-expiry','2026-12-15');await click('#local-draft');await fill('#f-expiry','2026-12-20');await click('#restore-draft');assert.equal(await evaluate("document.querySelector('#f-expiry').value"),'2026-12-15');await click('.editor-device summary');
 await until("document.querySelector('#editor-save-state').dataset.state==='saved'");
 for(const width of [320,390,768,1440]){
  await send('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:width<768});await sleep(150);
  assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'No editor overflow at '+width);
  fs.mkdirSync('data/qa',{recursive:true});fs.writeFileSync('data/qa/quote-editor-'+width+'.png',Buffer.from((await send('Page.captureScreenshot')).data,'base64'));
  await click('#f-currency + .select-trigger');await sleep(200);assert.equal(await evaluate("{const r=document.querySelector('.select-menu:not(.select-menu-closing)').getBoundingClientRect();r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight}"),true,'Menu inside viewport at '+width);
  fs.writeFileSync('data/qa/quote-editor-menu-'+width+'.png',Buffer.from((await send('Page.captureScreenshot')).data,'base64'));await evaluate('SmetraSelects.close()');await sleep(180);
 }
 await send('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:-1,uploadThroughput:-1});
 await fill('#f-terms','Условия после обрыва связи');await until("document.querySelector('#editor-save-state').dataset.state==='offline'");
 assert.ok(await evaluate("Object.values(localStorage).some(value=>value.includes('Условия после обрыва связи'))"));
 await send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});await click('#editor-retry');await until("document.querySelector('#editor-save-state').dataset.state==='saved'");assert.equal((await read()).terms,'Условия после обрыва связи');
 // A different device wins its revision; this editor must keep its unsaved input.
 await evaluate(`(async()=>{const q=(await api('/quotes/${id}')).quote;await api('/quotes/${id}',{method:'PATCH',body:JSON.stringify({revision:q.revision,terms:'Правки с другого устройства'})})})()`);
 await fill('#f-description','Мой несохранённый текст');await until("document.querySelector('#editor-save-state').dataset.state==='conflict'");assert.equal((await read()).description,starting.description);assert.equal((await read()).terms,'Правки с другого устройства');
 await click('#editor-save-copy');await until("document.querySelector('#quote-controls')");const copies=await evaluate("api('/quotes').then(r=>r.quotes.filter(q=>q.title.endsWith(' — копия')))");assert.equal(copies.length,1);assert.equal(copies[0].description,'Мой несохранённый текст');assert.equal(copies[0].terms,'Условия после обрыва связи');
 assert.deepEqual(errors,[]);console.log('PASS: autosave, duplicate identities, full undo/redo, expiry checkpoint, mobile reorder, offline recovery, revision conflict and copy at 320/390/768/1440 widths');ws.close();
})().catch(error=>{console.error(error);process.exit(1)});
