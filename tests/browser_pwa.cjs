const assert=require('node:assert/strict');
(async()=>{
 const site='http://localhost:'+(process.env.SMETRA_TEST_PORT||'8082');
 const tabs=await(await fetch('http://127.0.0.1:'+(process.env.SMETRA_CDP_PORT||'9223')+'/json')).json();
 const ws=new WebSocket(tabs.find(tab=>tab.type==='page').webSocketDebuggerUrl);await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}));
 let seq=0;const pending=new Map();
 ws.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result)}});
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value};
 const until=async expression=>{for(let i=0;i<100;i++){try{if(await evaluate(expression))return}catch{}await new Promise(resolve=>setTimeout(resolve,100))}throw Error('Timed out: '+expression)};
 try{
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Page.navigate',{url:site+'/app'});
  await until("navigator.serviceWorker.controller!==null");
  const manifest=await evaluate("fetch(document.querySelector('[rel=manifest]').href).then(r=>r.json())");assert.equal(manifest.display,'standalone');assert.equal(manifest.start_url,'/app');
  const keys=await evaluate("caches.open('smetra-public-offline-v1').then(c=>c.keys()).then(keys=>keys.map(k=>new URL(k.url).pathname).sort())");assert.deepEqual(keys,['/offline.css','/offline.html']);
  await send('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:0,uploadThroughput:0});await send('Page.navigate',{url:site+'/app'});
  await until("document.title==='Нет подключения · Сметра'");assert.equal(await evaluate("getComputedStyle(document.body).backgroundColor==='rgb(0, 0, 0)'||getComputedStyle(document.documentElement).backgroundColor==='rgb(0, 0, 0)'"),true);
  await send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});await send('Page.navigate',{url:site+'/app'});await until("document.querySelector('#auth-form')?.onsubmit");
  console.log('PASS: PWA manifest, active service worker, branded offline fallback, reconnect and public-only cache');
 }finally{await send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});ws.close()}
})().catch(error=>{console.error(error);process.exit(1)});
