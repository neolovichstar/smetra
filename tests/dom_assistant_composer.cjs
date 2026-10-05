/* Composer behavior with controlled API replies; no provider or production calls. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}};
async function setup(enabled=true){
 const dom=new JSDOM('<body class="workspace-page"><main id="content"></main></body>',{url:'https://example.test/app',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window;
 w.load=source=>{const script=w.document.createElement('script');script.textContent=source;w.document.head.append(script)};
 w.load("let user={id:'qa'},tab='assistant'; const escapeHtml=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c])); const view=html=>document.querySelector('#content').innerHTML=html;");
 w.sessionStorage.setItem('workspace_id','qa-workspace');w.Workspace={currentWorkspaceId:()=> 'qa-workspace'};
 const quota={remaining:3,limit:3,plan:'free',resets_at:2000000000},requests=[],notices=[];
 w.notify=text=>notices.push(text);w.scrollTo=()=>{};
 w.TextDecoder=TextDecoder;
 w.api=async(path,options={})=>{
  if(path==='/assistant')return {available:true,quota,messages:[],actions:[]};
  if(path==='/assistant/conversations')return {items:[]};
  if(path==='/assistant/jobs'&&options.method==='POST'){requests.push(options);return {job:{id:'job-1',status:'queued'},quota:{...quota,remaining:2}}}
  if(path==='/assistant/jobs')return {enabled,jobs:[]};
  throw Error('Unexpected path: '+path);
 };
 w.load(fs.readFileSync('apps/web/assistant-chat.js','utf8'));await w.SmetraAssistant();await tick();
 return {w,doc:w.document,requests,notices,close:()=>dom.window.close()};
}
(async()=>{
 const failures=[];
 const test=async(name,run,enabled=true)=>{const env=await setup(enabled);try{await run(env);console.log('PASS:',name)}catch(error){failures.push(name+': '+error.message);console.error('FAIL:',name,error.message)}finally{env.close()}};
 const type=(w,doc,text)=>{const input=doc.querySelector('#assistant-input');input.value=text;input.dispatchEvent(new w.Event('input'));return input};
 await test('empty and whitespace messages cannot be sent',async({w,doc})=>{
  assert.equal(doc.querySelector('#assistant-send').disabled,true);type(w,doc,'   ');assert.equal(doc.querySelector('#assistant-send').disabled,true);
  type(w,doc,'Prepare estimate');assert.equal(doc.querySelector('#assistant-send').disabled,false);
 });
 await test('background mode selects delivery and uses the shared submit button',async({w,doc,requests})=>{
  const mode=doc.querySelector('#assistant-background');assert.ok(mode);mode.click();assert.equal(mode.getAttribute('aria-pressed'),'true');assert.equal(requests.length,0);
  type(w,doc,'Prepare estimate');doc.querySelector('#assistant-form').requestSubmit();await tick();
  assert.equal(requests.length,1);assert.equal(JSON.parse(requests[0].body).text,'Prepare estimate');assert.ok(requests[0].headers['Idempotency-Key']);
  assert.equal(doc.querySelector('#assistant-input').value,'');assert.equal(doc.querySelector('#assistant-send').disabled,true);
  assert.ok(doc.querySelector('#assistant-status').textContent.length>0);
 });
 await test('missing worker cannot be selected or receive a job',async({w,doc,requests})=>{
  const mode=doc.querySelector('#assistant-background');assert.ok(mode);assert.equal(mode.hidden,true);assert.equal(mode.disabled,true);
  mode.click();type(w,doc,'Prepare estimate');assert.equal(mode.getAttribute('aria-pressed'),'false');assert.equal(requests.length,0);
 },false);
 await test('failed queue requests keep draft and reuse their idempotency key',async({w,doc})=>{
  const original=w.api,keys=[];w.api=async(path,options={})=>{if(path==='/assistant/jobs'&&options.method==='POST'){keys.push(options.headers['Idempotency-Key']);throw Error('Queue unavailable')}return original(path,options)};
  doc.querySelector('#assistant-background').click();type(w,doc,'Keep this draft');
  for(let i=0;i<2;i++){doc.querySelector('#assistant-form').requestSubmit();await tick();assert.equal(doc.querySelector('#assistant-input').value,'Keep this draft')}
  assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);assert.match(doc.querySelector('#assistant-status').textContent,/Queue unavailable/);
 });
 await test('queue response after navigation cannot clear another page or its draft',async({w,doc})=>{
  const task=deferred(),original=w.api;w.api=(path,options={})=>path==='/assistant/jobs'&&options.method==='POST'?task.promise:original(path,options);
  doc.querySelector('#assistant-background').click();type(w,doc,'Keep pending draft');doc.querySelector('#assistant-form').requestSubmit();await tick();
  w.eval("tab='support'");doc.querySelector('#content').textContent='Support';w.sessionStorage.setItem('smetra.assistant.draft:qa:qa-workspace:global','New unsent draft');task.resolve({job:{id:'qa'},quota:{remaining:2,limit:3,plan:'free',resets_at:2000000000}});await tick();
  assert.equal(doc.querySelector('#content').textContent,'Support');assert.equal(w.sessionStorage.getItem('smetra.assistant.draft:qa:qa-workspace:global'),'New unsent draft');
 });
 await test('completed jobs expose an answer action',async({w,doc})=>{
  const original=w.api;w.api=(path,options={})=>path==='/assistant/jobs'&&!options.method?Promise.resolve({enabled:true,jobs:[{id:'qa',kind:'chat',prompt:'Estimate',status:'completed',updated_at:Date.now()/1000}]}):original(path,options);
  await w.SmetraAssistant();await tick();const button=doc.querySelector('.assistant-job button');assert.ok(button);assert.equal(button.disabled,false);
 });
 await test('normal send still streams Markdown without queueing',async({w,doc,requests})=>{
  let sent;
  w.fetch=async(path,options)=>{sent={path,options};return {ok:true,body:new ReadableStream({start(controller){
   const event=(kind,payload)=>controller.enqueue(new TextEncoder().encode('event: '+kind+'\ndata: '+JSON.stringify(payload)+'\n\n'));
   event('delta',{text:'**Ready**'});event('done',{answer:'**Ready**',actions:[],quota:{remaining:2,limit:3,plan:'free',resets_at:2000000000}});controller.close();
  }})}};
  type(w,doc,'Normal question');doc.querySelector('#assistant-form').requestSubmit();await tick();await tick();
  assert.equal(sent.path,'/api/assistant/stream');assert.equal(JSON.parse(sent.options.body).text,'Normal question');assert.equal(requests.length,0);
  assert.equal(doc.querySelector('.assistant-message.assistant strong').textContent,'Ready');assert.equal(doc.querySelector('#assistant-stop').hidden,true);assert.equal(doc.querySelector('#assistant-input').value,'');
 });
 await test('in-flight queue submission cannot be sent twice',async({w,doc})=>{
  const task=deferred(),original=w.api;let calls=0;w.api=(path,options={})=>{if(path==='/assistant/jobs'&&options.method==='POST'){calls++;return task.promise}return original(path,options)};
  doc.querySelector('#assistant-background').click();type(w,doc,'One job');doc.querySelector('#assistant-form').requestSubmit();await tick();
  assert.equal(doc.querySelector('#assistant-input').disabled,true);assert.equal(doc.querySelector('#assistant-send').disabled,true);assert.equal(doc.querySelector('#assistant-background').disabled,true);
  doc.querySelector('#assistant-form').requestSubmit();await tick();assert.equal(calls,1);task.resolve({job:{id:'qa'},quota:{remaining:2,limit:3,plan:'free',resets_at:2000000000}});await tick();
 });
 await test('hidden mode and stop controls stay hidden under the shipped CSS',async({w,doc})=>{
  const style=doc.createElement('style');style.textContent=fs.readFileSync('apps/web/product-ui.css','utf8');doc.head.append(style);
  assert.equal(w.getComputedStyle(doc.querySelector('#assistant-background')).display,'none');assert.equal(w.getComputedStyle(doc.querySelector('#assistant-stop')).display,'none');
 },false);
 assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);process.exit(1)});
