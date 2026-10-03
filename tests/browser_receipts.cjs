/* Compact receipt review against the isolated fixture; no real model or user data. */
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const watchdog=setTimeout(()=>{console.error('FAIL: receipt UI timeout');process.exit(1)},60000);
 const tabs=await(await fetch('http://127.0.0.1:'+(process.env.SMETRA_CDP_PORT||'9223')+'/json')).json();
 const ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 let seq=0;const pending=new Map(),errors=[];
 ws.addEventListener('close',()=>{for(const p of pending.values())p.reject(Error('Browser closed'));pending.clear()});
 ws.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)});
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,userGesture:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value};
 const until=async expression=>{for(let i=0;i<150;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100))}throw Error(expression+'\n'+await evaluate('document.body.innerText'))};
 await send('Runtime.enable');await send('Page.enable');await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 await send('Page.navigate',{url:'http://localhost:8084/app'});
 await until("document.querySelector('#auth-form')?.onsubmit || document.querySelector('[data-work=quote-new]')");
 if(await evaluate("!!document.querySelector('#auth-form')")){await evaluate("document.querySelector('#email').value='android-design@test.invalid';document.querySelector('#password').value='android design test only';document.querySelector('#auth-submit').click()");await until("document.querySelector('[data-work=quote-new]')")}
 const setup=await evaluate(`(async()=>{const post=(p,b)=>api(p,{method:'POST',body:JSON.stringify(b)});const o=(await post('/construction/objects',{name:'Web receipt QA'})).object.id;const zone=(await post('/construction/objects/'+o+'/zones',{name:'Room',length:'2',width:'1'})).zone.id;const material=(await post('/construction/objects/'+o+'/quantities',{zone_id:zone,kind:'material',title:'Material',formula:'area',unit_price:10000})).quantity.id;const file=(await post('/files',{construction_id:o,name:'web-receipt.png',content:(()=>{const c=document.createElement('canvas');c.width=30;c.height=30;c.getContext('2d').fillRect(0,0,30,30);return c.toDataURL('image/png').split(',')[1]})()})).file.id;const purchase=(await post('/construction/objects/'+o+'/purchases',{material_id:material,receipt_file_id:file,quantity:'2',unit_price_kopecks:10000,status:'received',purchased_on:'2026-10-01',notes:'Keep existing note'})).purchase.id;return {object:o,file,purchase}})()`);
 await evaluate("document.querySelector('[data-tab=construction]').click()");await until(`(()=>{const b=document.querySelector('.construction-object[data-id="${setup.object}"]');if(!b)return false;b.click();return true})()`);
 await until(`document.querySelector('#construction-purchase-receipt option[value="${setup.file}"]')`);await evaluate(`document.querySelector('[data-purchase-edit="${setup.purchase}"]').click()`);
 await until("!document.querySelector('#construction-receipt-ocr').disabled");await evaluate("document.querySelector('#construction-receipt-ocr').click()");
 await until("document.querySelector('#construction-ocr-cancel')&&!document.querySelector('#construction-ocr-cancel').hidden");
 await evaluate('window.SmetraAssistant()');await until("document.querySelector('#assistant-input')");await evaluate('window.SmetraConstruction()');
 await until(`document.querySelector('#construction-purchase-receipt option[value="${setup.file}"]')`);await evaluate(`document.querySelector('[data-purchase-edit="${setup.purchase}"]').click()`);
 await until("document.querySelector('#construction-ocr-apply')&&!document.querySelector('#construction-ocr-apply').hidden");
 assert.equal(await evaluate("document.querySelector('#construction-purchase [name=unit_price]').value"),'100');
 assert.equal(await evaluate("document.querySelector('#construction-purchase [name=notes]').value"),'Keep existing note');
 assert.equal((await evaluate(`api('/construction/objects/${setup.object}').then(r=>r.purchases[0].unit_price_kopecks)`)),10000);
 assert.match(await evaluate("document.querySelector('#construction-ocr-note').textContent"),/1 из 3/);
 await evaluate("document.querySelector('#construction-ocr-apply').click()");
 assert.equal(await evaluate("document.querySelector('#construction-purchase [name=unit_price]').value"),'617.25');
 assert.match(await evaluate("document.querySelector('#construction-purchase [name=notes]').value"),/Keep existing note · Тестовый магазин/);
 assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true);
 assert.equal((await evaluate(`api('/construction/objects/${setup.object}').then(r=>r.purchases[0].unit_price_kopecks)`)),10000);
 const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync('data/receipt-web-review.png',Buffer.from(shot.data,'base64'));
 assert.equal(errors.length,0,errors.join('\n'));clearTimeout(watchdog);ws.close();console.log('PASS: 390px receipt job, navigation, persisted review, quota, unchanged purchase and explicit form proposal');
})().catch(error=>{console.error(error);process.exit(1)});
