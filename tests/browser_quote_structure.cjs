/* Real streaming chat -> server proposal -> visible review -> apply/undo. */
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const watchdog=setTimeout(()=>{console.error('FAIL: quote structure browser timeout');process.exit(1)},90000);
 const tabs=await(await fetch('http://127.0.0.1:'+(process.env.SMETRA_CDP_PORT||'9223')+'/json')).json();
 const ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 let seq=0;const pending=new Map(),errors=[];
 ws.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)});
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,userGesture:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value};
 const until=async expression=>{for(let i=0;i<250;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100))}throw Error(expression+'\n'+await evaluate('document.body.innerText.slice(-3000)'))};
 await send('Runtime.enable');await send('Page.enable');await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 await send('Page.navigate',{url:'http://localhost:8084/app'});
 await until("document.querySelector('#auth-form')?.onsubmit");
 await evaluate("document.querySelector('#email').value='android-design@test.invalid';document.querySelector('#password').value='android design test only';document.querySelector('#auth-submit').click()");
 await until("typeof user!=='undefined'&&!!user?.id&&!document.querySelector('#shell').classList.contains('hidden')&&!!window.Workspace?.currentWorkspaceId?.()");
 await evaluate("document.querySelector('[data-tab=assistant]').onclick()");await until("document.querySelector('.assistant-proposal')?.textContent.includes('Добавить позиции')");
 const quote=await evaluate("api('/quotes').then(r=>r.quotes.find(q=>q.title==='Айдентика и упаковка'))");
 const read=()=>evaluate(`api('/quotes/${quote.id}').then(r=>r.quote)`);
 const original=await read();assert.equal(original.items.length,1);
 const pendingAction=await evaluate("api('/assistant').then(r=>r.actions[0])");
 assert.equal(pendingAction.preview.after_count,2);assert.equal(pendingAction.preview.after_total,original.amount_kopecks+12506);
 assert.match(await evaluate("document.querySelector('.assistant-edit-diff').textContent"),/Позиций: 1 → 2/);
 assert.match(await evaluate("document.querySelector('.assistant-edit-diff').textContent"),/Подготовка стен/);
 await evaluate("document.querySelector('.assistant-proposal').scrollIntoView({block:'center'})");
 let screenshot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync('data/structure-web-preview.png',Buffer.from(screenshot.data,'base64'));
 const apply=async()=>{await evaluate("[...document.querySelectorAll('.assistant-proposal')].find(p=>p.querySelector('[data-confirm]')).querySelector('[data-confirm]').click()");await until("[...document.querySelectorAll('.assistant-proposal:not(.assistant-saved) button')].some(b=>b.textContent==='Отменить изменение')")};
 const undo=async()=>{await evaluate("[...document.querySelectorAll('.assistant-proposal:not(.assistant-saved) button')].find(b=>b.textContent==='Отменить изменение').click()");await until("![...document.querySelectorAll('.assistant-proposal:not(.assistant-saved) button')].some(b=>b.textContent==='Отменить изменение')")};
 const ask=async prompt=>{await evaluate(`document.querySelector('#assistant-input').value=${JSON.stringify(prompt)};document.querySelector('#assistant-send').click()`);await until("document.querySelector('.assistant-proposal [data-confirm]')")};
 await apply();assert.equal((await read()).amount_kopecks,original.amount_kopecks+12506);await undo();assert.deepEqual((await read()).items,original.items);
 await ask('Добавь тестовую опцию');await apply();let state=await read();assert.equal(state.items.length,2);assert.equal(state.items[1].included,false);assert.equal(state.amount_kopecks,original.amount_kopecks);
 // Clear the previous insertion's undo control by reloading. Later mutations
 // intentionally fence that older undo using the quote revision.
 await send('Page.reload',{ignoreCache:true});await until("document.querySelector('.assistant-saved')&&document.querySelector('#assistant-send')&&!document.querySelector('#assistant-send').disabled");
 await ask('Включи тестовую опцию');assert.match(await evaluate("document.querySelector('.assistant-proposal:has([data-confirm])').textContent"),/Включена в расчёт/);await apply();assert.equal((await read()).amount_kopecks,original.amount_kopecks+5000);await undo();assert.equal((await read()).items[1].included,false);
 await ask('Переставь тестовые строки');assert.match(await evaluate("document.querySelector('.assistant-proposal:has([data-confirm])').textContent"),/Переместить/);await apply();assert.equal((await read()).items[0].name,'Опциональная доставка');await undo();assert.equal((await read()).items[0].name,original.items[0].name);
 await ask('Удали тестовую опцию');assert.match(await evaluate("document.querySelector('.assistant-proposal:has([data-confirm])').textContent"),/Удалить/);await apply();assert.equal((await read()).items.length,1);await undo();assert.equal((await read()).items.length,2);
 assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true);
 assert.deepEqual(errors,[]);clearTimeout(watchdog);ws.close();console.log('PASS: 390px streaming proposals for insert/optional/reorder/remove, explicit preview, actual totals, apply/undo and no overflow');
})().catch(error=>{console.error(error);process.exit(1)});
