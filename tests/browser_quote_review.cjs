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
 await fill('#name','Проверка версий');await fill('#email','versions-'+Date.now()+'@test.invalid');await fill('#password','secure comparison password');await click('#auth-submit');await until("document.querySelector('#capture-text')");
 const id=await evaluate("api('/quotes',{method:'POST',body:JSON.stringify({title:'Ремонт кухни',client:'Клиент',terms:'Срок 10 дней',items:[{name:'Подготовка',unit_price:10000},{name:'Покраска',unit_price:20000},{name:'Доставка',unit_price:3000}]})}).then(r=>r.quote.id)");
 await evaluate(`(async()=>{let q=(await api('/quotes/${id}')).quote;await api('/quotes/${id}/publish',{method:'POST',body:JSON.stringify({revision:q.revision})});q=(await api('/quotes/${id}')).quote;await api('/quotes/${id}',{method:'PATCH',body:JSON.stringify({revision:q.revision,terms:'Срок 7 дней',items:[{...q.items[0],name:'Подготовка поверхности',unit_price:12000},q.items[1],{name:'Защита мебели',unit_price:4000}]})});tab='quotes';location.hash='quotes';await Workspace.openQuote('${id}');})()`);
 await click('#quote-controls [data-work=review]');await until("document.querySelector('.review-item')");
 assert.ok(await evaluate("document.querySelector('#review-report').textContent.includes('Подготовка поверхности')"));
 assert.equal(await evaluate("document.querySelectorAll('.review-added').length"),1);assert.equal(await evaluate("document.querySelectorAll('.review-removed').length"),1);
 for(const width of [320,390,768,1440]){
  await send('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:width<768});await sleep(250);
  assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'No comparison overflow at '+width);
  fs.mkdirSync('data/qa',{recursive:true});fs.writeFileSync('data/qa/quote-review-'+width+'.png',Buffer.from((await send('Page.captureScreenshot')).data,'base64'));
 }
 await fill('#review-target','1');await until("document.querySelector('.review-empty')");assert.ok(await evaluate("document.querySelector('#review-report').textContent.includes('Условия совпадают')"));
 await click('#review-back');await until("document.querySelector('#quote-controls [data-work=publish]')");await click('#quote-controls [data-work=publish]');await until("document.querySelector('#review-publish button')&&!document.querySelector('#review-publish button').disabled");
 await fill('#review-comment','Уточнили состав и срок');await click('#review-publish button');await until("document.querySelector('#quote-controls [data-work=link]')&&!document.querySelector('.quote-review')");
 const verified=await evaluate(`(async()=>{const q=(await api('/quotes/${id}')).quote;const versions=(await api('/quotes/${id}/versions')).versions;const diff=await api('/quotes/${id}/compare?from=1&to=2');let stale;try{await api('/public/accept',{method:'POST',body:JSON.stringify({token:new URL(q.public_url).searchParams.get('quote'),version:1})})}catch(error){stale=error.status}return {version:q.published_version,terms:versions.find(v=>v.version===1).snapshot.terms,summary:diff.summary,stale};})()`);
 assert.equal(verified.version,2);assert.equal(verified.terms,'Срок 10 дней');assert.equal(verified.summary.changed,1);assert.equal(verified.summary.added,1);assert.equal(verified.summary.removed,1);assert.equal(verified.stale,409);
 assert.deepEqual(errors,[]);console.log('PASS: immutable versions → responsive comparison → reviewed republication; old client approval rejected; 320/390/768/1440 widths');ws.close();
})().catch(error=>{console.error(error);process.exit(1)});
