const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}};
async function setup(existing=false){
 const dom=new JSDOM('<body><main id="content"></main></body>',{url:'https://smetra.test/app',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window,notices=[],posts=[];
 let poll;w.setInterval=callback=>{poll=callback;return 1};w.clearInterval=()=>{};
 w.matchMedia=()=>({matches:false});
 const initial=w.document.createElement('script');initial.textContent="let user={id:'fixture-user'},tab='support';const view=html=>document.querySelector('#content').innerHTML=html;";w.document.head.append(initial);
 w.notify=text=>notices.push(text);
 let threads=existing?[{id:'thread-1',subject:'Вопрос',status:'open',needs_human:false}]:[];
 const task=deferred();
 w.api=async(path,options={})=>{
  if(options.method==='POST'){posts.push({path,body:JSON.parse(options.body)});const result=await task.promise;threads=[{id:'thread-1',subject:'Вопрос',status:'open',needs_human:false}];return result}
  if(path==='/support/threads')return {threads};
  if(path==='/support/threads/thread-1/messages')return {messages:[{id:'msg-1',body:'Ответ поддержки',sender_type:'assistant',created_at:1}]};
  throw Error('Unexpected API '+path);
 };
 for(const file of ['ui/icons.js','ui/chat-kit.js','support-chat.js']){const el=w.document.createElement('script');el.textContent=fs.readFileSync('apps/web/'+file,'utf8');w.document.head.append(el)}
 await w.SmetraSupport.render();
 if(existing){w.document.querySelector('[data-thread]').click();await tick()}
 return {w,doc:w.document,task,posts,notices,poll:()=>poll?.(),close:()=>{w.SmetraSupport.stop();dom.window.close()}};
}
(async()=>{
 const failures=[];
 const test=async(name,run,existing=false)=>{const env=await setup(existing);try{await run(env);console.log('PASS:',name)}catch(error){failures.push(name+': '+error.message);console.error('FAIL:',name,error.stack)}finally{env.close()}};
 const type=(w,doc,text)=>{const input=doc.querySelector('#message');input.value=text;input.dispatchEvent(new w.Event('input'));return input};
 await test('support has an internal neutral send control and no canned topics',async({doc})=>{
  assert.ok(doc.querySelector('.support-compose-surface .tg-send'));assert.ok(doc.querySelector('#support-attach'));assert.equal(doc.querySelector('[data-support-topic]'),null);assert.match(doc.querySelector('.tg-welcome').textContent,/Чем помочь/);
 });
 await test('pasted screenshots are previewed, sent without text and restored after failure',async({w,doc,task,posts})=>{
  w.URL.createObjectURL=()=> 'blob:test';w.URL.revokeObjectURL=()=>{};
  w.Image=class{constructor(){this.naturalWidth=100;this.naturalHeight=80}set src(value){w.setTimeout(()=>this.onload(),0)}};
  w.HTMLCanvasElement.prototype.getContext=()=>({drawImage(){}});w.HTMLCanvasElement.prototype.toBlob=function(callback){callback(new w.Blob(['fake-fixture-pixels'],{type:'image/webp'}))};
  const paste=new w.Event('paste',{bubbles:true,cancelable:true});Object.defineProperty(paste,'clipboardData',{value:{files:[new w.File(['fixture'],'Снимок.png',{type:'image/png'})]}});doc.querySelector('#message').dispatchEvent(paste);
  for(let i=0;i<15&&!doc.querySelector('.support-attachment');i++)await new Promise(resolve=>setTimeout(resolve,5));
  assert.equal(paste.defaultPrevented,true);assert.ok(doc.querySelector('.support-attachment img'));assert.equal(doc.querySelector('#message').required,false);doc.querySelector('#support-form').requestSubmit();
  assert.equal(posts[0].body.attachments.length,1);assert.equal(posts[0].body.message,'');assert.ok(doc.querySelector('.tg-attachment-image'));
  task.reject(Error('Offline'));await tick();await tick();assert.ok(doc.querySelector('.support-attachment img'));assert.equal(doc.querySelector('.tg-send').disabled,false);
 });
 await test('new support message clears immediately and a later response preserves the next draft',async({w,doc,task,posts})=>{
  const input=type(w,doc,'Как работает ассистент?');doc.querySelector('#support-form').requestSubmit();
  assert.equal(input.value,'');assert.equal(posts[0].body.message,'Как работает ассистент?');
  assert.match(doc.querySelector('#support-messages').textContent,/Как работает ассистент/);
  type(w,doc,'Следующий вопрос');task.resolve({ticket_id:'thread-1'});await tick();await tick();
  assert.equal(input.value,'Следующий вопрос');
 });
 await test('failed support send restores the unsent text',async({w,doc,task})=>{
  const input=type(w,doc,'Верни черновик');doc.querySelector('#support-form').requestSubmit();assert.equal(input.value,'');
  task.reject(Error('Network unavailable'));await tick();
  assert.equal(input.value,'Верни черновик');assert.equal(doc.querySelector('.tg-msg.is-pending'),null);
 });
 await test('failed support send never overwrites a newer draft',async({w,doc,task})=>{
  const input=type(w,doc,'Первый вопрос');doc.querySelector('#support-form').requestSubmit();
  type(w,doc,'Новый черновик');task.reject(Error('Network unavailable'));await tick();assert.equal(input.value,'Новый черновик');
 });
 await test('response to an older ticket cannot replace a new conversation draft',async({w,doc,task})=>{
  type(w,doc,'Первый вопрос');doc.querySelector('#support-form').requestSubmit();
  doc.querySelector('#support-new').click();const input=type(w,doc,'Другой вопрос');
  task.resolve({ticket_id:'thread-1'});await tick();await tick();
  assert.equal(input.value,'Другой вопрос');assert.equal(doc.querySelector('#support-title').textContent,'Поддержка Сметры');
  assert.doesNotMatch(doc.querySelector('#support-messages').textContent,/Ответ поддержки/);
 });
 await test('existing support thread clears the composer before waiting for AI',async({w,doc,task,posts})=>{
  const input=type(w,doc,'Продолжим');doc.querySelector('#support-form').requestSubmit();
  assert.equal(input.value,'');assert.equal(posts[0].path,'/support/threads/thread-1/messages');
  task.resolve({ok:true});await tick();await tick();assert.equal(input.value,'');
 },true);
 await test('late failure from an older ticket leaves a newly opened draft intact',async({w,doc,task})=>{
  type(w,doc,'Первый вопрос');doc.querySelector('#support-form').requestSubmit();
  doc.querySelector('#support-new').click();const input=type(w,doc,'Другой вопрос');
  task.reject(Error('Network unavailable'));await tick();assert.equal(input.value,'Другой вопрос');
  assert.doesNotMatch(doc.querySelector('#support-messages').textContent,/Первый вопрос/);
 });
 await test('late loading failure cannot replace a new support conversation',async({w,doc})=>{
  const response=deferred(),original=w.api;
  w.api=path=>path.endsWith('/messages')?response.promise:original(path);
  doc.querySelector('[data-thread]').click();
  doc.querySelector('#support-new').click();
  response.reject(Error('Old ticket failed'));await tick();await tick();
  assert.ok(doc.querySelector('.tg-welcome'));
  assert.equal(doc.querySelector('.tg-error'),null);
 },true);
 await test('reopening the same ticket ignores its older loading response',async({w,doc})=>{
  const response=deferred(),original=w.api;let reads=0;
  w.api=path=>path.endsWith('/messages')&&++reads===1?response.promise:original(path);
  doc.querySelector('[data-thread]').click();
  doc.querySelector('#support-new').click();doc.querySelector('[data-thread]').click();await tick();
  response.resolve({messages:[{id:'old',body:'Outdated response',sender_type:'assistant',created_at:1}]});await tick();await tick();
  assert.match(doc.querySelector('#support-messages').textContent,/Ответ поддержки/);
  assert.doesNotMatch(doc.querySelector('#support-messages').textContent,/Outdated response/);
 },true);
 await test('handoff confirmation cannot target a ticket after switching conversations',async({w,doc,posts})=>{
  const confirmation=deferred();w.SmetraDialog={confirm:()=>confirmation.promise};
  doc.querySelector('#support-handoff').click();doc.querySelector('#support-new').click();
  confirmation.resolve(true);await tick();await tick();
  assert.equal(posts.length,0,'No request for the previously selected ticket');
  assert.equal(doc.querySelector('#support-title').textContent,'Поддержка Сметры');
 },true);
 await test('polling preserves reading position and follows new messages only near the bottom',async({w,doc,poll})=>{
  const log=doc.querySelector('#support-messages');let count=1;
  Object.defineProperties(log,{scrollHeight:{get:()=>1000},clientHeight:{get:()=>200}});
  w.api=async()=>({messages:Array.from({length:++count},(_,index)=>({id:'m'+index,body:'Message '+index,sender_type:'assistant',created_at:index}))});
  log.scrollTop=120;poll();await tick();await tick();
  assert.equal(log.scrollTop,120,'Do not jump while reading older messages');
  log.scrollTop=790;poll();await tick();await tick();
  assert.equal(log.scrollTop,1000,'Follow replies when already near the bottom');
 },true);
 assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);process.exitCode=1});
