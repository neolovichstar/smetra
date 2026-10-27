const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}};
async function setup(existing=false){
 const dom=new JSDOM('<body><main id="content"></main></body>',{url:'https://smetra.test/app',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window,notices=[],posts=[];
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
 return {w,doc:w.document,task,posts,notices,close:()=>{w.SmetraSupport.stop();dom.window.close()}};
}
(async()=>{
 const failures=[];
 const test=async(name,run,existing=false)=>{const env=await setup(existing);try{await run(env);console.log('PASS:',name)}catch(error){failures.push(name+': '+error.message);console.error('FAIL:',name,error.stack)}finally{env.close()}};
 const type=(w,doc,text)=>{const input=doc.querySelector('#message');input.value=text;input.dispatchEvent(new w.Event('input'));return input};
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
 await test('PNG screenshot is compressed to JPEG with matching name and cleared after submit',async({w,doc,task,posts})=>{
  w.createImageBitmap=async()=>({width:320,height:180,close(){}});
  w.HTMLCanvasElement.prototype.getContext=()=>({drawImage(){}});
  w.HTMLCanvasElement.prototype.toDataURL=()=> 'data:image/jpeg;base64,'+'A'.repeat(120);
  const upload=doc.querySelector('#support-image-input');
  Object.defineProperty(upload,'files',{configurable:true,value:[{name:'broken-screen.png',type:'image/png',size:1200}]});
  upload.dispatchEvent(new w.Event('change'));await tick();await tick();
  assert.equal(doc.querySelectorAll('[data-remove-image]').length,1);
  doc.querySelector('#support-form').requestSubmit();
  assert.equal(posts.length,1);
  assert.equal(posts[0].body.images.length,1);
  assert.equal(posts[0].body.images[0].name,'broken-screen.jpg');
  assert.equal(posts[0].body.images[0].content.length,120);
  assert.equal(doc.querySelectorAll('[data-remove-image]').length,0);
  task.resolve({ticket_id:'thread-1'});await tick();
 });
 assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);process.exitCode=1});
