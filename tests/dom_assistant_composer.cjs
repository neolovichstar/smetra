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
 const quota={remaining,limit:3,plan:'free',resets_at:2000000000},requests=[],notices=[];
 let activeRecognition=null,microphoneTrackStopped=false,microphonePermissionRequests=0;
 if(voice){
  Object.defineProperty(w.navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>{microphonePermissionRequests++;return {getTracks:()=>[{stop(){microphoneTrackStopped=true}}]}}}});
  w.SpeechRecognition=class FakeSpeechRecognition{
   constructor(){activeRecognition=this;this.lang='';this.interimResults=false;this.continuous=false;this.maxAlternatives=1;}
   start(){this.started=true;this.onstart?.()}
   stop(){this.stopped=true;this.onend?.()}
  };
 }
 w.notify=text=>notices.push(text);w.scrollTo=()=>{};
 w.TextDecoder=TextDecoder;
 w.api=async(path,options={})=>{
  if(path==='/assistant')return {available:true,quota,messages:[],actions:[]};
  if(path==='/assistant/conversations')return {items:[]};
  if(path==='/assistant/jobs'&&options.method==='POST'){requests.push(options);return {job:{id:'job-1',status:'queued'},quota:{...quota,remaining:2}}}
  if(path==='/assistant/jobs')return {enabled,jobs:[]};
  throw Error('Unexpected path: '+path);
 };
 for(const file of ['vendor/markdown-it-15.0.2.min.js','chat-markdown.js','assistant-chat.js'])w.load(fs.readFileSync('apps/web/'+file,'utf8'));await w.SmetraAssistant();await tick();
 return {w,doc:w.document,requests,notices,recognition:()=>activeRecognition,microphoneTrackStopped:()=>microphoneTrackStopped,microphonePermissionRequests:()=>microphonePermissionRequests,close:()=>dom.window.close()};
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
  rec.onresult({results:[{0:{transcript:'Составь смету'},isFinal:true}],resultIndex:0});
  rec.stop();await tick();
  assert.equal(input.value,'Составь смету');
  assert.equal(button.type,'submit');assert.ok(button.querySelector('svg'),'send has a visible SVG');
  assert.equal(button.disabled,true,'sending remains blocked while quota is exhausted');
  assert.equal(voice.disabled,false,'microphone stays usable after transcription');
  assert.match(doc.querySelector('#assistant-status').textContent,/Текст распознан/);
 },true,true,0);
 await test('empty and whitespace messages cannot be sent while microphone stays available',async({w,doc,requests})=>{
  const button=doc.querySelector('#assistant-send'),voice=doc.querySelector('#assistant-voice');
  assert.equal(button.type,'submit');assert.equal(button.disabled,true);assert.equal(voice.disabled,false);
  assert.ok(voice.querySelector('svg'));assert.ok(button.querySelector('svg'));
  type(w,doc,'   ');assert.equal(button.disabled,true);assert.equal(voice.disabled,false);
  doc.querySelector('#assistant-form').requestSubmit();await tick();assert.equal(requests.length,0,'blank prompts must not queue work');
  type(w,doc,'Prepare estimate');assert.equal(button.type,'submit');assert.equal(button.disabled,false);assert.equal(voice.disabled,false);
 });
 await test('background mode selects delivery and uses the shared submit button',async({w,doc,requests})=>{
  const mode=doc.querySelector('#assistant-background');assert.ok(mode);mode.click();assert.equal(mode.getAttribute('aria-pressed'),'true');assert.equal(requests.length,0);
  type(w,doc,'Prepare estimate');doc.querySelector('#assistant-form').requestSubmit();await tick();
  assert.equal(requests.length,1);assert.equal(JSON.parse(requests[0].body).text,'Prepare estimate');assert.ok(requests[0].headers['Idempotency-Key']);
  assert.equal(doc.querySelector('#assistant-input').value,'');assert.equal(doc.querySelector('#assistant-send').disabled,true,'empty composer cannot send');
  assert.equal(doc.querySelector('#assistant-voice').disabled,false,'microphone stays available when the composer resets');
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
 await test('hidden mode and stop controls stay hidden under the shipped CSS',async({w,doc})=>{
  const style=doc.createElement('style');style.textContent=fs.readFileSync('apps/web/product-ui.css','utf8');doc.head.append(style);
  assert.equal(w.getComputedStyle(doc.querySelector('#assistant-background')).display,'none');assert.equal(w.getComputedStyle(doc.querySelector('#assistant-stop')).display,'none');
 },false);
 assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);process.exit(1)});
