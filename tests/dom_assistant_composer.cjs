/* Composer behavior with controlled API replies; no provider or production calls. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}};
async function setup(enabled=true,voice=false,remaining=3){
 const dom=new JSDOM('<body class="workspace-page"><main id="content"></main></body>',{url:'https://example.test/app',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window;
 w.load=source=>{const script=w.document.createElement('script');script.textContent=source;w.document.head.append(script)};
 w.load("let user={id:'qa'},tab='assistant'; const escapeHtml=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c])); const view=html=>document.querySelector('#content').innerHTML=html;");
 w.sessionStorage.setItem('workspace_id','qa-workspace');w.Workspace={currentWorkspaceId:()=> 'qa-workspace'};
 const quota={remaining,limit:3,plan:'free',resets_at:2000000000},requests=[],uploads=[],notices=[];
 let activeRecognition=null,microphoneTrackStopped=false,microphonePermissionRequests=0;
 if(voice){
  Object.defineProperty(w.navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>{microphonePermissionRequests++;return {getTracks:()=>[{stop(){microphoneTrackStopped=true}}]}}}});
  w.SpeechRecognition=class FakeSpeechRecognition{
   constructor(){activeRecognition=this;this.lang='';this.interimResults=false;this.continuous=false;this.maxAlternatives=1;}
   start(){this.started=true;this.onstart?.()}
   stop(){this.stopped=true;this.onend?.()}
   abort(){this.aborted=true;this.onend?.()}
  };
 }
 w.notify=text=>notices.push(text);w.scrollTo=()=>{};
 w.TextDecoder=TextDecoder;w.proposalFields=()=>'';
 w.fetch=async()=>({ok:true,body:new ReadableStream({start(controller){
  controller.enqueue(new TextEncoder().encode('event: background\ndata: {"job":{"id":"job-1","status":"running"}}\n\n'));controller.close();
 }})});
 w.api=async(path,options={})=>{
  if(path==='/assistant')return {available:true,quota,messages:[],actions:[]};
  if(path==='/assistant/conversations')return {items:[]};
  if(path==='/files'&&options.method==='POST'){uploads.push(options);return {file:{id:'saved-photo-'+uploads.length}};}
  if(path==='/assistant/jobs'&&options.method==='POST'){requests.push(options);return {job:{id:'job-1',status:'queued'},quota:{...quota,remaining:2}}}
  if(path==='/assistant/jobs')return {enabled,jobs:[]};
  throw Error('Unexpected path: '+path);
 };
 for(const file of ['ui/icons.js','vendor/markdown-it-15.0.2.min.js','chat-markdown.js','assistant-chat.js'])w.load(fs.readFileSync('apps/web/'+file,'utf8'));await w.SmetraAssistant();await tick();
 return {w,doc:w.document,requests,uploads,notices,recognition:()=>activeRecognition,microphoneTrackStopped:()=>microphoneTrackStopped,microphonePermissionRequests:()=>microphonePermissionRequests,close:()=>dom.window.close()};
}
(async()=>{
 const failures=[];
 const test=async(name,run,enabled=true,voice=false,remaining=3)=>{const env=await setup(enabled,voice,remaining);try{await run(env);console.log('PASS:',name)}catch(error){failures.push(name+': '+error.message);console.error('FAIL:',name,error.message)}finally{env.close()}};
 const type=(w,doc,text)=>{const input=doc.querySelector('#assistant-input');input.value=text;input.dispatchEvent(new w.Event('input'));return input};
 await test('microphone works with exhausted AI quota and produces an editable draft',async({w,doc,recognition,microphonePermissionRequests})=>{
  const button=doc.querySelector('#assistant-send'),voice=doc.querySelector('#assistant-voice'),input=doc.querySelector('#assistant-input');
  assert.equal(button.type,'submit');assert.equal(button.disabled,true,'empty message cannot send');
  assert.equal(voice.type,'button');assert.ok(voice.querySelector('svg'),'microphone has a visible SVG');
  assert.equal(voice.disabled,false,'voice input should not be blocked by exhausted AI quota');
  voice.click();await tick();await tick();
  const rec=recognition();assert.ok(rec,'SpeechRecognition instance should be created');assert.equal(rec.started,true);
  assert.equal(microphonePermissionRequests(),0,'SpeechRecognition must not compete with a second permission request');
  assert.match(doc.querySelector('#assistant-status').textContent,/Слушаю/);
  rec.onresult({results:[{0:{transcript:'Состав'},isFinal:false}],resultIndex:0});
  assert.equal(input.value,'Состав','interim words must appear in the message textarea');
  rec.onresult({results:[{0:{transcript:'Составь смету'},isFinal:true}],resultIndex:0});
  assert.equal(input.value,'Составь смету','final result replaces interim, without duplication');
  assert.doesNotMatch(doc.querySelector('#assistant-status').textContent,/Распознаю:/,'transcript must not render in the footer');
  rec.stop();await tick();
  assert.equal(input.value,'Составь смету');
  assert.equal(button.type,'submit');assert.ok(button.querySelector('svg'),'send has a visible SVG');
  assert.equal(button.disabled,true,'sending remains blocked while quota is exhausted');
  assert.equal(voice.disabled,false,'microphone stays usable after transcription');
  assert.match(doc.querySelector('#assistant-status').textContent,/Текст в поле/);
 },true,true,0);
 await test('starting a new assistant screen aborts the old microphone session',async({w,doc,recognition})=>{
  const voice=doc.querySelector('#assistant-voice'),input=doc.querySelector('#assistant-input');
  voice.click();await tick();
  const rec=recognition();
  rec.onresult({results:[{0:{transcript:'Первый черновик'},isFinal:false}],resultIndex:0});
  assert.equal(input.value,'Первый черновик');
  doc.dispatchEvent(new w.Event('smetra:before-view'));
  assert.equal(rec.aborted,true,'navigating away must stop microphone capture');
  assert.equal(rec.onresult,null,'late recognition events must not update a detached composer');
 },true,true);
 await test('submitting background job aborts speech before clearing the editor',async({w,doc,recognition,requests})=>{
  const input=doc.querySelector('#assistant-input');
  doc.querySelector('#assistant-voice').click();await tick();
  const rec=recognition();
  rec.onresult({results:[{0:{transcript:'Покраска потолка'},isFinal:false}],resultIndex:0});
  assert.equal(input.value,'Покраска потолка');
  doc.querySelector('#assistant-form').requestSubmit();await tick();
  assert.equal(rec.aborted,true,'recognition must stop when the prompt is submitted');
  assert.equal(rec.onresult,null,'late partial results must be disabled');
  assert.equal(requests.length,1);
  assert.equal(JSON.parse(requests[0].body).text,'Покраска потолка');
  assert.equal(input.value,'','submitting must clear the composer only once');
 },true,true);
 await test('delayed Android bridge never opens microphone after navigation',async({w,doc})=>{
  const ready=deferred(),calls=[];
  w.SmetraShell={available:true,ready:ready.promise,has:feature=>feature==='speech',
    call:async op=>{calls.push(op);return {text:'Не отправлять'}}};
  doc.querySelector('#assistant-voice').click();await tick();
  doc.dispatchEvent(new w.Event('smetra:before-view'));
  w.eval("tab='dashboard'");
  ready.resolve({});
  await tick();await tick();
  assert.deepEqual(calls,[],'do not call Android recognizer after leaving the assistant');
 },true,false);
 await test('empty and whitespace messages cannot be sent while microphone stays available',async({w,doc,requests})=>{
  const button=doc.querySelector('#assistant-send'),voice=doc.querySelector('#assistant-voice');
  assert.equal(button.type,'submit');assert.equal(button.disabled,true);assert.equal(voice.disabled,false);
  assert.ok(voice.querySelector('svg'));assert.ok(button.querySelector('svg'));
  type(w,doc,'   ');assert.equal(button.disabled,true);assert.equal(voice.disabled,false);
  doc.querySelector('#assistant-form').requestSubmit();await tick();assert.equal(requests.length,0,'blank prompts must not queue work');
  type(w,doc,'Prepare estimate');assert.equal(button.type,'submit');assert.equal(button.disabled,false);assert.equal(voice.disabled,false);
 });
 await test('every message is queued automatically without a background button',async({w,doc,requests})=>{
  assert.equal(doc.querySelector('#assistant-background'),null);
  type(w,doc,'Prepare estimate');doc.querySelector('#assistant-form').requestSubmit();await tick();await tick();
  assert.equal(requests.length,1);assert.equal(JSON.parse(requests[0].body).text,'Prepare estimate');assert.ok(requests[0].headers['Idempotency-Key']);
  assert.equal(doc.querySelector('#assistant-input').value,'');assert.equal(doc.querySelector('#assistant-send').disabled,true);
  assert.equal(doc.querySelector('#assistant-voice').disabled,false);assert.match(doc.querySelector('#assistant-status').textContent,/сохранён|диалоге/);
 });
 await test('unconfigured worker blocks submission without exposing a mode switch',async({w,doc,requests})=>{
  assert.equal(doc.querySelector('#assistant-background'),null);
  type(w,doc,'Prepare estimate');assert.equal(doc.querySelector('#assistant-send').disabled,true);
  doc.querySelector('#assistant-form').requestSubmit();await tick();assert.equal(requests.length,0);
 },false);
 await test('failed queue requests keep draft and reuse their idempotency key',async({w,doc})=>{
  const original=w.api,keys=[];w.api=async(path,options={})=>{if(path==='/assistant/jobs'&&options.method==='POST'){keys.push(options.headers['Idempotency-Key']);throw Error('Queue unavailable')}return original(path,options)};
  type(w,doc,'Keep this draft');
  for(let i=0;i<2;i++){doc.querySelector('#assistant-form').requestSubmit();await tick();assert.equal(doc.querySelector('#assistant-input').value,'Keep this draft')}
  assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);assert.match(doc.querySelector('#assistant-status').textContent,/Queue unavailable/);
 });
 await test('queue response after navigation cannot clear another page or its draft',async({w,doc})=>{
  const task=deferred(),original=w.api;w.api=(path,options={})=>path==='/assistant/jobs'&&options.method==='POST'?task.promise:original(path,options);
  type(w,doc,'Keep pending draft');doc.querySelector('#assistant-form').requestSubmit();await tick();
  w.eval("tab='support'");doc.querySelector('#content').textContent='Support';w.sessionStorage.setItem('smetra.assistant.draft:qa:qa-workspace:global','New unsent draft');task.resolve({job:{id:'qa'},quota:{remaining:2,limit:3,plan:'free',resets_at:2000000000}});await tick();
  assert.equal(doc.querySelector('#content').textContent,'Support');assert.equal(w.sessionStorage.getItem('smetra.assistant.draft:qa:qa-workspace:global'),'New unsent draft');
 });
 await test('completed jobs expose an answer action',async({w,doc})=>{
  const original=w.api;w.api=(path,options={})=>path==='/assistant/jobs'&&!options.method?Promise.resolve({enabled:true,jobs:[{id:'qa',kind:'chat',prompt:'Estimate',status:'completed',updated_at:Date.now()/1000}]}):original(path,options);
  await w.SmetraAssistant();await tick();const button=doc.querySelector('.assistant-job button');assert.ok(button);assert.equal(button.disabled,false);
 });
 await test('cancelled background jobs disappear and stay dismissed after refresh',async({w,doc})=>{
  const original=w.api,now=Date.now()/1000;let deletes=0;
  const jobs=[
   {id:'cancelled-old',kind:'chat',prompt:'This was already cancelled',status:'cancelled',updated_at:now},
   {id:'active-job',kind:'chat',prompt:'Remove this job',status:'queued',updated_at:now}
  ];
  w.api=async(path,options={})=>{
   if(path==='/assistant/jobs'&&!options.method)return {enabled:true,jobs};
   if(path==='/assistant/jobs/active-job'&&options.method==='DELETE'){deletes++;return {quota:{remaining:2,limit:3,plan:'free',resets_at:2000000000}}}
   return original(path,options);
  };
  await w.SmetraAssistant();await tick();
  assert.equal(doc.querySelectorAll('.assistant-job').length,1,'cancelled records must never be rendered');
  assert.match(doc.querySelector('.assistant-job').textContent,/Remove this job/);
  doc.querySelector('.assistant-job button').click();await tick();await tick();
  assert.equal(deletes,1);assert.equal(doc.querySelector('.assistant-job'),null,'task should be removed immediately after successful cancellation');
  assert.ok(JSON.parse(w.sessionStorage.getItem('smetra.assistant.dismissedJobs:qa:qa-workspace')).includes('active-job'));
  await w.SmetraAssistant();await tick();
  assert.equal(doc.querySelector('.assistant-job'),null,'dismissed task must not reappear from a stale queue response');
 });
 await test('normal send queues once and streams the same durable job',async({w,doc,requests})=>{
  let sent;
  w.fetch=async(path,options)=>{sent={path,options};return {ok:true,body:new ReadableStream({start(controller){
   const event=(kind,payload)=>controller.enqueue(new TextEncoder().encode('event: '+kind+'\ndata: '+JSON.stringify(payload)+'\n\n'));
   event('delta',{text:'**Ready**'});event('done',{answer:'**Ready**',actions:[],quota:{remaining:2,limit:3,plan:'free',resets_at:2000000000}});controller.close();
  }})}};
  type(w,doc,'Normal question');doc.querySelector('#assistant-form').requestSubmit();await tick();await tick();
  assert.equal(sent.path,'/api/assistant/stream');assert.equal(JSON.parse(sent.options.body).job_id,'job-1');assert.equal(JSON.parse(requests[0].body).text,'Normal question');assert.equal(requests.length,1);
  assert.equal(doc.querySelector('.assistant-message.assistant strong').textContent,'Ready');assert.equal(doc.querySelector('#assistant-stop').hidden,true);assert.equal(doc.querySelector('#assistant-input').value,'');
 });

 await test('text and photos leave the composer before the network replies, using their original snapshot',async({w,doc,uploads,requests})=>{
  const task=deferred(),sent=[],revoked=[];
  w.URL.createObjectURL=()=> 'blob:fixture-photo';w.URL.revokeObjectURL=url=>revoked.push(url);
  const file=new w.File(['photo'],'photo.jpg',{type:'image/jpeg'});
  Object.defineProperty(file,'arrayBuffer',{value:async()=>Uint8Array.from([1,2,3]).buffer});
  const picker=doc.querySelector('#assistant-attach-input');
  Object.defineProperty(picker,'files',{configurable:true,value:[file]});await picker.onchange();
  type(w,doc,'Проверь это фото');
  w.fetch=(path,options)=>{sent.push({path,options});return task.promise};
  doc.querySelector('#assistant-form').requestSubmit();
  assert.equal(doc.querySelector('#assistant-input').value,'','clear text at submit time');
  assert.equal(doc.querySelectorAll('.assistant-attachment-tile').length,0,'clear photo tray at submit time');
  assert.equal(doc.querySelector('.assistant-attachment-preview').hidden,true);
  assert.equal(w.sessionStorage.getItem('smetra.assistant.draft:qa:qa-workspace:global'),null);
  await tick();await tick();
  assert.equal(uploads.length,1,'sent photo saves to workspace before AI stream');
  assert.equal(JSON.parse(uploads[0].body).name,'photo.jpg');
  const payload=JSON.parse(requests[0].body);
  assert.equal(payload.text,'Проверь это фото');assert.equal(payload.file_ids.length,1);
  assert.equal(payload.file_ids[0],'saved-photo-1');assert.equal(JSON.parse(sent[0].options.body).job_id,'job-1');assert.equal(revoked.length,1);
  task.resolve({ok:true,body:new ReadableStream({start(controller){
   controller.enqueue(new TextEncoder().encode('event: done\ndata: '+JSON.stringify({answer:'Проверено',actions:[],quota:{remaining:2,limit:3,plan:'free',resets_at:2000000000}})+'\n\n'));controller.close();
  }})});
  await tick();await tick();assert.equal(doc.querySelector('#assistant-input').value,'');
 });
 await test('failed queue save restores text and photo for an idempotent retry',async({w,doc})=>{
  let created=0,revoked=0;w.URL.createObjectURL=()=> 'blob:fixture-'+(++created);w.URL.revokeObjectURL=()=>revoked++;
  const file=new w.File(['photo'],'retry.jpg',{type:'image/jpeg'});
  Object.defineProperty(file,'arrayBuffer',{value:async()=>Uint8Array.from([1]).buffer});
  const picker=doc.querySelector('#assistant-attach-input');
  Object.defineProperty(picker,'files',{configurable:true,value:[file]});await picker.onchange();
  const original=w.api;w.api=async(path,options={})=>{if(path==='/assistant/jobs'&&options.method==='POST')throw Error('Network unavailable');return original(path,options)};
  type(w,doc,'Не потеряй вложение');
  doc.querySelector('#assistant-form').requestSubmit();await tick();await tick();
  assert.equal(doc.querySelector('#assistant-input').value,'Не потеряй вложение');
  assert.equal(doc.querySelectorAll('.assistant-attachment-tile').length,1);
  assert.equal(created,2,'restored photo receives a fresh preview URL');assert.equal(revoked,1);
  assert.match(doc.querySelector('.assistant-error').textContent,/Network unavailable/);
 });
 await test('sending a selected document snapshots context and remains saved after stream loss',async({w,doc,requests})=>{
  const original=w.api,task=deferred();let sent;
  const context={entity:'files',id:'document-1',label:'estimate.pdf',workspace_id:'qa-workspace'};
  w.sessionStorage.setItem('smetra.assistant.context',JSON.stringify(context));
  w.api=async(path,options={})=>path==='/files/document-1/metadata'?{
   file:{id:'document-1',name:'estimate.pdf',size:10},processing:{state:'ready',pages:1}
  }:original(path,options);
  await w.SmetraAssistant();await tick();
  assert.equal(doc.querySelectorAll('.assistant-attachment-document').length,1);
  type(w,doc,'Проверь документ');w.fetch=(path,options)=>{sent=JSON.parse(options.body);return task.promise};
  doc.querySelector('#assistant-form').requestSubmit();await tick();
  assert.equal(doc.querySelector('#assistant-input').value,'');
  assert.equal(doc.querySelectorAll('.assistant-attachment-tile').length,0);
  assert.ok(doc.querySelector('#assistant-context').classList.contains('hidden'));
  assert.equal(w.sessionStorage.getItem('smetra.assistant.context'),null);
  assert.equal(sent.job_id,'job-1');const submitted=JSON.parse(requests[0].body);assert.equal(submitted.context.entity,'files');assert.equal(submitted.context.id,'document-1');
  task.resolve({ok:false,status:503,json:async()=>({error:'Try again'})});await tick();await tick();
  assert.equal(doc.querySelector('#assistant-input').value,'');
  assert.equal(doc.querySelectorAll('.assistant-attachment-document').length,0);
  assert.match(doc.querySelector('#assistant-status').textContent,/сохранён/);
 });

 await test('a sent document is detached from a named conversation after success',async({w,doc})=>{
  const original=w.api,changes=[];
  const item={id:'thread-document',title:'Файл',context_entity:'files',context_id:'document-2'};
  w.sessionStorage.setItem('smetra.assistant.conversation',item.id);
  w.api=async(path,options={})=>{
   if(path==='/assistant/conversations')return {items:[item]};
   if(path==='/assistant/conversations/'+item.id){
    if(options.method==='PATCH'){changes.push(JSON.parse(options.body));return {conversation:{...item,context_entity:'',context_id:''}}}
    return {conversation:item,messages:[]};
   }
   if(path==='/files/document-2/metadata')return {file:{id:'document-2',name:'notes.txt',size:10},processing:{state:'ready',pages:1}};
   return original(path,options);
  };
  await w.SmetraAssistant();await tick();
  w.fetch=async()=>({ok:true,body:new ReadableStream({start(controller){
   controller.enqueue(new TextEncoder().encode('event: done\ndata: '+JSON.stringify({answer:'Прочитано',actions:[],quota:{remaining:2,limit:3,plan:'free',resets_at:2000000000}})+'\n\n'));controller.close();
  }})});
  type(w,doc,'Прочитай');doc.querySelector('#assistant-form').requestSubmit();await tick();await tick();
  assert.equal(doc.querySelector('#assistant-input').value,'');
  assert.equal(doc.querySelectorAll('.assistant-attachment-tile').length,0);
  assert.deepEqual(changes,[{context_entity:'',context_id:''}]);
 });
 await test('an accepted background job clears the composer before its reply arrives',async({w,doc})=>{
  const task=deferred(),original=w.api;
  w.api=(path,options={})=>path==='/assistant/jobs'&&options.method==='POST'?task.promise:original(path,options);
  type(w,doc,'Фоновая задача');
  doc.querySelector('#assistant-form').requestSubmit();
  assert.equal(doc.querySelector('#assistant-input').value,'');
  task.resolve({job:{id:'job'},quota:{remaining:2,limit:3,plan:'free',resets_at:2000000000}});await tick();
  assert.equal(doc.querySelector('#assistant-input').value,'');
 });
 await test('consent cancellation leaves text and attachments in place',async({w,doc})=>{
  w.URL.createObjectURL=()=> 'blob:fixture';w.URL.revokeObjectURL=()=>{};
  const picker=doc.querySelector('#assistant-attach-input'),file=new w.File(['photo'],'keep.jpg',{type:'image/jpeg'});
  Object.defineProperty(picker,'files',{configurable:true,value:[file]});await picker.onchange();
  w.SmetraEstimateSafety={ensureConsent:async()=>false};type(w,doc,'Черновик');
  doc.querySelector('#assistant-form').requestSubmit();await tick();
  assert.equal(doc.querySelector('#assistant-input').value,'Черновик');
  assert.equal(doc.querySelectorAll('.assistant-attachment-tile').length,1);
 });
 await test('in-flight queue submission cannot be sent twice',async({w,doc})=>{
  const task=deferred(),original=w.api;let calls=0;w.api=(path,options={})=>{if(path==='/assistant/jobs'&&options.method==='POST'){calls++;return task.promise}return original(path,options)};
  type(w,doc,'One job');doc.querySelector('#assistant-form').requestSubmit();await tick();
  assert.equal(doc.querySelector('#assistant-input').disabled,false,'next draft remains editable');assert.equal(doc.querySelector('#assistant-send').disabled,true);assert.equal(doc.querySelector('#assistant-background'),null);
  doc.querySelector('#assistant-form').requestSubmit();await tick();assert.equal(calls,1);task.resolve({job:{id:'qa'},quota:{remaining:2,limit:3,plan:'free',resets_at:2000000000}});await tick();
 });
 await test('a photo without text changes microphone into Send and can be removed',async({w,doc})=>{
  let revoked=0;
  w.URL.createObjectURL=()=> 'blob:https://example.test/qa-photo';
  w.URL.revokeObjectURL=()=>{revoked++};
  const input=doc.querySelector('#assistant-attach-input');
  const photo=new w.File(['image bytes'],'example.jpg',{type:'image/jpeg'});
  Object.defineProperty(input,'files',{configurable:true,value:[photo]});
  await input.onchange();await tick();
  const send=doc.querySelector('#assistant-send');
  assert.equal(send.type,'submit','Image-only messages must be sendable');
  assert.equal(send.disabled,false,'Image-only messages must enable Send');
  assert.ok(send.querySelector('svg'),'send button retains SVG');
  assert.equal(doc.querySelector('#assistant-input').required,false);
  assert.equal(doc.querySelectorAll('.assistant-attachment-tile').length,1);
  doc.querySelector('.assistant-attachment-remove').click();
  assert.equal(send.type,'submit','Send remains a distinct submit button');
  assert.equal(send.disabled,true,'Removing the last image disables empty Send');
  assert.equal(doc.querySelector('#assistant-voice').disabled,false,'microphone remains independently available');
  assert.equal(doc.querySelector('#assistant-input').required,true);
  assert.equal(revoked,1);
 });
 await test('background switch is absent and idle Stop remains hidden under shipped CSS',async({w,doc})=>{
  const style=doc.createElement('style');style.textContent=['ui/tokens.css','ui/base.css','ui/components.css','ui/assistant.css'].map(file=>fs.readFileSync('apps/web/'+file,'utf8')).join('\n');doc.head.append(style);
  assert.equal(doc.querySelector('#assistant-background'),null);assert.equal(w.getComputedStyle(doc.querySelector('#assistant-stop')).display,'none');
 },false);
 await test('done frame unlocks the composer without waiting for socket EOF',async({w,doc})=>{
  let cancelled=0;
  w.fetch=async()=>({ok:true,body:new ReadableStream({start(controller){
   controller.enqueue(new TextEncoder().encode('event: done\ndata: '+JSON.stringify({answer:'Готово без EOF',actions:[],quota:{remaining:2,limit:3,plan:'free',resets_at:2000000000}})+'\n\n'));
  },cancel(){cancelled++}})});
  type(w,doc,'Заверши ответ');doc.querySelector('#assistant-form').requestSubmit();await tick();await tick();await tick();
  assert.match(doc.querySelector('#assistant-messages').textContent,/Готово без EOF/);
  assert.equal(doc.querySelector('#assistant-stop').hidden,true);assert.equal(cancelled,1);
  type(w,doc,'Следующий вопрос');assert.equal(doc.querySelector('#assistant-send').disabled,false);
 });
 await test('completed foreground reply does not rebuild the chat or erase the next draft',async({w,doc})=>{
   const oldApi=w.api;
   let stream,finished=false;
   w.api=async(path,options={})=>{
    if(path==='/assistant/jobs'&&!options.method)return {enabled:true,jobs:[{id:'job-1',kind:'chat',status:finished?'completed':'running',conversation_id:null,prompt:'Первый вопрос'}]};
    return oldApi(path,options);
   };
   w.fetch=async()=>({ok:true,body:new ReadableStream({start(controller){stream=controller}})});
   type(w,doc,'Первый вопрос');doc.querySelector('#assistant-form').requestSubmit();await tick();await tick();
   const editor=type(w,doc,'Следующий черновик');
   finished=true;
   stream.enqueue(new TextEncoder().encode('event: done\ndata: '+JSON.stringify({answer:'Первый ответ',actions:[]})+'\n\n'));
   stream.close();await tick();await tick();await tick();
   assert.equal(doc.querySelector('#assistant-input'),editor);
   assert.equal(editor.value,'Следующий черновик');
   assert.match(doc.querySelector('#assistant-messages').textContent,/Первый ответ/);
  });
  await test('split UTF-8 and a final SSE frame without separator remain readable',async({w,doc})=>{
  const answer='Смета: 1 234,56 ₽';
  const bytes=new TextEncoder().encode('event: delta\r\ndata: '+JSON.stringify({text:answer})+'\r\n\r\nevent: done\r\ndata: '+JSON.stringify({answer,actions:[],quota:{remaining:2,limit:3,plan:'free',resets_at:2000000000}}));
  w.fetch=async()=>({ok:true,body:new ReadableStream({start(controller){for(let i=0;i<bytes.length;i+=3)controller.enqueue(bytes.slice(i,i+3));controller.close()}})});
  type(w,doc,'Проверь символы');doc.querySelector('#assistant-form').requestSubmit();await tick();await tick();
  assert.equal(doc.querySelector('.assistant-message.assistant .assistant-markdown').textContent.trim(),answer);
  assert.equal(doc.querySelector('#assistant-stop').hidden,true);
 });
 await test('accepted work survives a lost stream without restoring or resending its prompt',async({w,doc,requests})=>{
  w.fetch=async()=>{throw Error('Socket lost')};
  type(w,doc,'Сохранённая задача');doc.querySelector('#assistant-form').requestSubmit();await tick();await tick();
  assert.equal(requests.length,1);assert.equal(doc.querySelector('#assistant-input').value,'');
  assert.equal(doc.querySelector('.assistant-error'),null);assert.match(doc.querySelector('#assistant-status').textContent,/сохранён/);
  assert.equal(doc.querySelector('#assistant-stop').hidden,true);
 });
 await test('late SSE completion cannot insert proposals or change quota in another chat view',async({w,doc,notices})=>{
  let controller;
  w.fetch=async()=>({ok:true,body:new ReadableStream({start(value){controller=value}})});
  type(w,doc,'Старый запрос');doc.querySelector('#assistant-form').requestSubmit();await tick();await tick();
  doc.dispatchEvent(new w.Event('smetra:before-view'));await w.SmetraAssistant();await tick();
  type(w,doc,'Новый несохранённый черновик');
  controller.enqueue(new TextEncoder().encode('event: done\ndata: '+JSON.stringify({answer:'Старый ответ',actions:[{id:'old-action',tool:'create_clients',summary:'Не вставлять',arguments:{name:'Old'}}],quota:{remaining:0,limit:3,plan:'free',resets_at:2000000000}})+'\n\n'));
  await tick();await tick();await tick();
  assert.equal(doc.querySelector('#assistant-input').value,'Новый несохранённый черновик');
  assert.equal(doc.querySelector('#assistant-send').disabled,false);assert.equal(doc.querySelector('.assistant-proposal'),null);
  assert.doesNotMatch(doc.querySelector('#assistant-messages').textContent,/Старый ответ/);assert.deepEqual(notices,[]);
 });
 await test('Stop cancels the durable job instead of only hiding the local stream',async({w,doc})=>{
  const original=w.api;let cancelled=0;
  w.api=async(path,options={})=>{if(path==='/assistant/jobs/job-1'&&options.method==='DELETE'){cancelled++;return {quota:{remaining:3,limit:3,plan:'free'}}}return original(path,options)};
  w.fetch=(path,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new w.DOMException('Stopped','AbortError')),{once:true}));
  type(w,doc,'Останови меня');doc.querySelector('#assistant-form').requestSubmit();await tick();await tick();
  doc.querySelector('#assistant-stop').click();await tick();await tick();
  assert.equal(cancelled,1);assert.equal(doc.querySelector('#assistant-input').value,'Останови меня');
  assert.equal(doc.querySelector('.assistant-error'),null);assert.match(doc.querySelector('#assistant-status').textContent,/остановлен/);
 });
 await test('new dialog stays available while a saved response is running',async({w,doc})=>{
  const original=w.api;let created=0,controller;
  const thread={id:'new-thread',title:'Новый диалог',context_entity:'',context_id:''};
  w.api=async(path,options={})=>{
   if(path==='/assistant/conversations'&&options.method==='POST'){created++;return {conversation:thread}}
   if(path==='/assistant/conversations'&&created)return {items:[thread]};
   if(path==='/assistant/conversations/new-thread')return {conversation:thread,messages:[]};
   return original(path,options);
  };
  w.fetch=async()=>({ok:true,body:new ReadableStream({start(value){controller=value}})});
  type(w,doc,'Первый запрос');doc.querySelector('#assistant-form').requestSubmit();await tick();await tick();
  assert.equal(doc.querySelector('#assistant-new-thread').disabled,false);
  doc.querySelector('#assistant-new-thread').click();await tick();await tick();
  assert.equal(created,1);assert.equal(w.sessionStorage.getItem('smetra.assistant.conversation'),'new-thread');
  controller.enqueue(new TextEncoder().encode('event: done\ndata: '+JSON.stringify({answer:'Первый ответ',actions:[],quota:{remaining:2,limit:3,plan:'free',resets_at:2000000000}})+'\n\n'));await tick();
  assert.doesNotMatch(doc.querySelector('#assistant-messages').textContent,/Первый ответ/);
 });
 await test('pending proposals are scoped to their conversation and old creation cards do not return',async({w,doc})=>{
  const original=w.api;const thread={id:'thread-a',title:'A',context_entity:'',context_id:''};
  w.api=async(path,options={})=>{
   if(path==='/assistant')return {available:true,quota:{remaining:3,limit:3,plan:'free'},messages:[],actions:[
    {id:'own',conversation_id:'thread-a',tool:'create_clients',summary:'Только свой чат',arguments:{}},
    {id:'other',conversation_id:'thread-b',tool:'create_clients',summary:'Чужой диалог',arguments:{}}
   ],recent_actions:[{id:'old-created',quote_id:'q',summary:'Старый черновик'}]};
   if(path==='/assistant/conversations')return {items:[thread]};
   if(path==='/assistant/conversations/thread-a')return {conversation:thread,messages:[]};
   return original(path,options);
  };
  w.sessionStorage.setItem('smetra.assistant.conversation','thread-a');await w.SmetraAssistant();await tick();
  const text=doc.querySelector('#assistant-actions').textContent;assert.match(text,/Только свой чат/);assert.doesNotMatch(text,/Чужой диалог|Старый черновик/);
 });

 assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);process.exit(1)});
