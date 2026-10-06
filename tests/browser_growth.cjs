/* Disposable CI server only: first-run intent, starter, price and paywall UI. */
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const site='http://localhost:8082',tabs=await(await fetch('http://127.0.0.1:9223/json')).json();
 const ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
 await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}));
 let seq=0;const pending=new Map(),errors=[];
 ws.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)});
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,userGesture:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value};
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const until=async expression=>{for(let n=0;n<100;n++){if(await evaluate(expression))return;await wait(100)}throw Error('Timeout: '+expression)};
 const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
 const fill=(selector,value)=>evaluate(`{const n=document.querySelector(${JSON.stringify(selector)});n.value=${JSON.stringify(value)};n.dispatchEvent(new Event('input',{bubbles:true}));n.dispatchEvent(new Event('change',{bubbles:true}))}`);
 const shot=async name=>{fs.mkdirSync('data/qa',{recursive:true});fs.writeFileSync('data/qa/'+name+'.png',Buffer.from((await send('Page.captureScreenshot')).data,'base64'))};
 await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Network.deleteCookies',{name:'session',url:site});
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 await send('Page.navigate',{url:site+'/app?register=1'});await until("document.querySelector('#auth-form')?.onsubmit");
 await fill('#name','Growth QA');await fill('#email','growth-'+Date.now()+'@test.invalid');await fill('#password','isolated growth password');await click('#auth-submit');
 await until("document.querySelector('[data-activation=estimate]')");await shot('growth-first-run-mobile');await click('[data-activation=estimate]');
 await until("document.querySelector('[data-starter=repair]')");assert.equal(await evaluate("document.querySelectorAll('[data-starter]').length"),7);
 await click('[data-starter=repair]');await until("document.querySelector('#estimate-editor')");
 assert.equal(await evaluate("api('/quotes').then(r=>r.quotes.length)"),0,'Picking a starter must not activate or create a quote');
 assert.equal(await evaluate("[...document.querySelectorAll('[data-key=unit_price]')].every(n=>Number(n.value)===0)"),true);
 await fill('#f-client','Client QA');for(const n of [0,1,2])await fill('[data-row="'+n+'"] [data-key=unit_price]','100');
 await click('#estimate-editor [type=submit]');await until("document.querySelector('#quote-controls')");
 assert.equal(await evaluate("api('/quotes').then(r=>r.quotes.length)"),1);
 await evaluate("tab='billing';render()");await until("document.querySelector('#offer-price')");
 const prices=await evaluate("api('/billing').then(r=>r.pricing)");assert.ok(prices.annual_saving_kopecks>0);
 assert.equal(await evaluate("document.querySelector('#upgrade-checkout').disabled"),true,'CI shop is off, so charging is unavailable');
 await click('[data-period=pro_year]');assert.equal(await evaluate("document.querySelector('#upgrade-checkout').dataset.plan"),'pro_year');
 await shot('growth-billing-mobile');
 for(const width of [320,390,768,1440]){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<701});await wait(150);assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'Billing overflow '+width)}
 await evaluate("tab='quotes';render()");await until("document.querySelector('[data-work=quote-new]')");await click('[data-work=quote-new]');await until("document.querySelector('#estimate-editor')");await fill('#f-title','Preserved draft');
 await evaluate("SmetraGrowth.paywall('quote_limit')");assert.equal(await evaluate("document.querySelector('#f-title').value"),'Preserved draft');await shot('growth-contextual-offer');
 await click('.contextual-upgrade .primary');await until("document.querySelector('#offer-price')");assert.equal(await evaluate("sessionStorage.getItem('smetra.checkout.return.'+user.id)"),'quotes');
 assert.deepEqual(errors,[]);console.log('PASS: first-run → seven honest starters → saved quote; server annual price; no unavailable checkout; contextual offer retains draft; 320/390/768/1440 layouts');ws.close();
})().catch(error=>{console.error(error);process.exit(1)});
