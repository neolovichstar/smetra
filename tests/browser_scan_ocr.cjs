/* End-to-end scan preparation through real browser UI and the isolated worker. */
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const watchdog=setTimeout(()=>{console.error('FAIL: scan OCR browser timeout');process.exit(1)},90000);
 const tabs=await(await fetch('http://127.0.0.1:'+(process.env.SMETRA_CDP_PORT||'9223')+'/json')).json();
 const ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 let seq=0;const pending=new Map(),errors=[];
 ws.addEventListener('close',()=>{for(const p of pending.values())p.reject(Error('Browser closed'));pending.clear()});
 ws.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)});
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,userGesture:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value};
 const until=async expression=>{for(let i=0;i<250;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100))}throw Error(expression+'\n'+await evaluate('document.body.innerText.slice(-3000)'))};
 await send('Runtime.enable');await send('Page.enable');await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 await send('Page.navigate',{url:'http://localhost:8084/app'});await until("(!document.querySelector('#auth')?.classList.contains('hidden')&&!!document.querySelector('#auth-form')?.onsubmit)||(typeof user!=='undefined'&&!!user?.id&&!document.querySelector('#shell')?.classList.contains('hidden'))");
 if(await evaluate("!document.querySelector('#auth').classList.contains('hidden')")){await evaluate("document.querySelector('#email').value='android-design@test.invalid';document.querySelector('#password').value='android design test only';document.querySelector('#auth-submit').click()");await until("typeof user!=='undefined'&&!!user?.id&&!document.querySelector('#shell').classList.contains('hidden')")}
 const raw=fs.readFileSync('apps/mobile/app/src/androidTest/assets/scan.pdf').toString('base64');
 const file=await evaluate(`api('/files',{method:'POST',headers:{'Idempotency-Key':'browser-scan-upload'},body:JSON.stringify({assistant_upload:true,name:'scan-browser.pdf',content:${JSON.stringify(raw)}})}).then(r=>r.file)`);
 const before=await evaluate("api('/assistant').then(r=>r.quota.used)");
 await until("!!window.Workspace?.currentWorkspaceId?.()");
 await evaluate("document.querySelector('[data-tab=assistant]').onclick()");await until("document.querySelector('#assistant-input')");
 await evaluate(`window.SmetraAssistantContext({entity:'files',id:'${file.id}',label:'scan-browser.pdf',workspace_id:window.Workspace.currentWorkspaceId()});window.SmetraAssistant()`);
 await until("document.querySelector('.assistant-file-status')?.textContent.includes('Распознать скан')");
 assert.equal(await evaluate("document.querySelector('#assistant-send').disabled"),true);
 await evaluate("document.querySelector('#assistant-input').value='Сохранённый вопрос о скане';document.querySelector('#assistant-input').dispatchEvent(new Event('input',{bubbles:true}));[...document.querySelectorAll('.assistant-file-status button')].find(b=>b.textContent==='Распознать скан').click()");
 await until("document.querySelector('.assistant-file-status')?.textContent.includes('Отменить подготовку')");
 await evaluate("document.querySelector('[data-tab=construction]').click()");await until("document.querySelector('.construction-object')");await evaluate("document.querySelector('[data-tab=assistant]').click()");
 await until("document.querySelector('.assistant-file-status')?.textContent.includes('OCR: проверьте суммы по оригиналу')");
 assert.equal(await evaluate("document.querySelector('#assistant-input').value"),'Сохранённый вопрос о скане');
 const info=await evaluate(`api('/files/${file.id}/metadata').then(r=>r.processing)`);assert.equal(info.method,'ocr');assert.equal(info.pages,2);assert.equal(info.truncated,true);assert.equal(info.ocr_quota.used,1);
 assert.equal(await evaluate("api('/assistant').then(r=>r.quota.used)"),before);
 await send('Page.navigate',{url:'http://localhost:8084/app#assistant'});await until("document.querySelector('.assistant-file-status')?.textContent.includes('OCR: проверьте суммы по оригиналу')");
 assert.equal(await evaluate("document.querySelector('#assistant-input').value"),'Сохранённый вопрос о скане');
 await evaluate("document.querySelector('#assistant-new-thread').click()");await until("document.querySelector('#assistant-thread-select').value!==''");
 await until("document.querySelector('.assistant-file-status')?.textContent.includes('OCR: проверьте суммы по оригиналу')");
 assert.equal(await evaluate("document.querySelector('#assistant-input').value"),'');
 assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true);
 const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync('data/scan-web-ocr.png',Buffer.from(shot.data,'base64'));
 assert.deepEqual(errors,[]);clearTimeout(watchdog);ws.close();console.log('PASS: 390px PDF scan OCR, blocked unread chat, preserved draft/navigation/reload, first 2 pages, provenance, separate quota and no overflow');
})().catch(error=>{console.error(error);process.exit(1)});
