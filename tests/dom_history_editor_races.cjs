/* Browser history and delayed note actions must preserve the current screen. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve,reject;const promise=new Promise((done,fail)=>{resolve=done;reject=fail});return {promise,resolve,reject}};
function setup(full=false){
 const dom=new JSDOM(full?fs.readFileSync('apps/web/app.html','utf8'):'<div id="content"></div><div id="toast" class="hidden"></div>',{url:'https://example.test/app#files',runScripts:'dangerously'}),w=dom.window,doc=w.document;
 w.matchMedia=()=>({matches:false,addEventListener(){}});w.scrollTo=()=>{};w.confirm=()=>true;
 w.TextEncoder=TextEncoder;w.TextDecoder=TextDecoder;
 w.load=source=>{const script=doc.createElement('script');script.textContent=source;doc.head.append(script)};
 w.Workspace={render:async section=>{w.view('<p>'+section+'</p>');return true},reset(){}};
 w.fetch=async()=>({ok:true,status:200,json:async()=>({user:{id:'qa',name:'QA',role:'user'}}),text:async()=>'current'});
 const source=fs.readFileSync('apps/web/app.js','utf8');w.load(full?source:source.split("if($('#auth')){")[0]);
 if(!full)w.eval("user={id:'qa',name:'QA',role:'user'};tab='files'");
 w.api=async path=>path==='/me'?{user:{id:'qa',name:'QA',role:'user'}}:path.endsWith('/versions')?{items:[{id:'v1',revision:1,created_at:1},{id:'v2',revision:2,created_at:2}]}:{items:[]};
 w.load(fs.readFileSync('apps/web/file-editor.js','utf8'));
 return {dom,w,doc,close:()=>dom.window.close()};
}
(async()=>{
 const failures=[];
 const test=async(name,run,full=false)=>{const env=setup(full);try{await tick();await tick();await run(env);console.log('PASS:',name)}catch(error){failures.push(name+': '+error.message);console.error('FAIL:',name,error.message)}finally{env.close()}};
 await test('browser back and forward update screen and sidebar',async({w,doc})=>{
  doc.querySelector('[data-tab="support"]').click();await tick();assert.equal(doc.querySelector('#content').dataset.section,'support');
  w.history.back();await tick();await tick();await tick();assert.equal(doc.querySelector('#content').dataset.section,'files');assert.ok(doc.querySelector('[data-tab="files"]').classList.contains('active'));
  w.history.forward();await tick();await tick();await tick();assert.equal(doc.querySelector('#content').dataset.section,'support');
 },true);
 await test('content anchor does not navigate away from current section',async({w,doc})=>{
  doc.querySelector('[data-tab="support"]').click();await tick();w.location.hash='content';await tick();assert.equal(doc.querySelector('#content').dataset.section,'support');
 },true);
 await test('old save cannot navigate away from another screen',async({w,doc})=>{
  await w.SmetraFileEditor.open({id:'note',name:'note.md',sha256:'qa'});await tick();
  const request=deferred();w.api=()=>request.promise;const form=doc.querySelector('#file-editor-form');
  const pending=form.onsubmit({preventDefault(){}});w.eval("tab='support'");w.view('Support');request.resolve({});await pending;
  assert.equal(w.eval('tab'),'support');assert.equal(doc.querySelector('#content').textContent,'Support');assert.ok(doc.querySelector('#toast').classList.contains('hidden'));
 });
 await test('late navigation completion cannot steal focus or scroll',async({w,doc})=>{
  const request=deferred(),focus=[];doc.querySelector('#content').focus=()=>focus.push(w.eval('tab'));
  const original=w.Workspace.render;w.Workspace.render=section=>section==='support'?request.promise:original(section);
  const pending=doc.querySelector('[data-tab="support"]').onclick();doc.querySelector('[data-tab="files"]').click();await tick();
  request.resolve(true);await pending;assert.deepEqual(focus,['files']);
 },true);
 await test('save from old account cannot notify new account',async({w,doc})=>{
  await w.SmetraFileEditor.open({id:'note',name:'note.md',sha256:'qa'});await tick();const request=deferred();w.api=()=>request.promise;
  const pending=doc.querySelector('#file-editor-form').onsubmit({preventDefault(){}});w.eval("user={id:'another',name:'Another'}");request.resolve({});await pending;
  assert.ok(doc.querySelector('#toast').classList.contains('hidden'));assert.equal(w.location.hash,'#files');
 });
 await test('download cannot resurrect note after leave and return to files',async({w,doc})=>{
  const request=deferred();w.fetch=()=>request.promise;const pending=w.SmetraFileEditor.open({id:'note',name:'note.md',sha256:'qa'});
  w.eval("tab='support'");await w.render();w.eval("tab='files'");await w.render();request.resolve({ok:true,text:async()=>'old private note'});await pending;
  assert.equal(doc.querySelector('#file-editor-form'),null);assert.equal(doc.querySelector('#content').textContent,'files');
 });
 await test('latest selected note version wins delayed replies',async({w,doc})=>{
  await w.SmetraFileEditor.open({id:'note',name:'note.md',sha256:'qa'});await tick();const requests=[];
  w.api=()=>{const request=deferred();requests.push(request);return request.promise};const buttons=doc.querySelectorAll('.file-editor-version');
  buttons[0].click();buttons[1].click();requests[1].resolve({content:w.btoa('new version')});await tick();requests[0].resolve({content:w.btoa('old version')});await tick();
  assert.equal(doc.querySelector('#file-editor-history-preview').textContent,'new version');
 });
 await test('latest history refresh wins delayed replies',async({w,doc})=>{
  await w.SmetraFileEditor.open({id:'note',name:'note.md',sha256:'qa'});await tick();const requests=[];
  w.api=()=>{const request=deferred();requests.push(request);return request.promise};const button=doc.querySelector('#file-editor-history-refresh');
  button.click();button.click();requests[1].resolve({items:[{id:'v3',revision:3,created_at:3}]});await tick();requests[0].resolve({items:[{id:'v1',revision:1,created_at:1}]});await tick();
  const list=doc.querySelector('#file-editor-history-list');assert.ok(list.textContent.includes('3'));assert.ok(!list.textContent.includes('Версия 1'));
 });
 await test('restore applies captured version even if another preview completes',async({w,doc})=>{
  await w.SmetraFileEditor.open({id:'note',name:'note.md',sha256:'qa'});await tick();w.api=async()=>({content:w.btoa('first version')});
  const buttons=doc.querySelectorAll('.file-editor-version');buttons[0].click();await tick();const request=deferred();w.api=path=>path.endsWith('/restore')?request.promise:path.endsWith('/versions')?Promise.resolve({items:[]}):Promise.resolve({content:w.btoa('second version')});
  const pending=doc.querySelector('#file-editor-restore').onclick();buttons[1].click();await tick();request.resolve({file:{sha256:'changed'}});await pending;
  assert.equal(doc.querySelector('#file-editor-text').value,'first version');
 });
 await test('typing while a note saves preserves new text and the latest server hash',async({w,doc})=>{
  await w.SmetraFileEditor.open({id:'note',name:'note.md',sha256:'qa'});await tick();
  const input=doc.querySelector('#file-editor-text'),form=doc.querySelector('#file-editor-form'),request=deferred();
  const writes=[];w.api=(path,options)=>{writes.push({path,options});return request.promise};
  input.value='First saved text';const pending=form.onsubmit({preventDefault(){}});input.value='New unsaved text';
  request.resolve({file:{id:'note',sha256:'saved-hash'}});await pending;
  assert.equal(input.value,'New unsaved text');assert.ok(form.isConnected);assert.match(form.textContent,/Новые правки ещё не сохранены/);
  w.api=async(path,options)=>{writes.push({path,options});return {file:{id:'note',sha256:'next-hash'}}};
  await form.onsubmit({preventDefault(){}});
  assert.equal(JSON.parse(writes[1].options.body).sha256,'saved-hash','Next save uses the confirmed server revision');
 });
 await test('a lost create response replays one key then keeps newer text for PATCH',async({w,doc})=>{
  w.api=async path=>({items:path==='/projects'?[{id:'project',name:'Project'}]:[]});
  await w.SmetraFileEditor.open();const input=doc.querySelector('#file-editor-text'),form=doc.querySelector('#file-editor-form');
  form.elements.name.value='New note';input.value='Original text';const writes=[];
  w.api=async(path,options)=>{writes.push({path,options});if(writes.length===1)throw Error('Ответ потерян');return {file:{id:'created-note',name:'New note.md',sha256:'created-hash'}}};
  await form.onsubmit({preventDefault(){}});input.value='Text entered after lost response';
  await form.onsubmit({preventDefault(){}});
  assert.equal(writes[0].options.headers['Idempotency-Key'],writes[1].options.headers['Idempotency-Key']);
  assert.ok(writes[0].options.headers['Idempotency-Key']);assert.equal(writes[0].options.body,writes[1].options.body,'Recovery resolves the original creation before writing new text');
  assert.equal(input.value,'Text entered after lost response');assert.ok(form.isConnected);
  await form.onsubmit({preventDefault(){}});
  assert.equal(writes[2].path,'/files/created-note');assert.equal(writes[2].options.method,'PATCH');
  assert.equal(JSON.parse(writes[2].options.body).sha256,'created-hash');
 });
 await test('a restore confirmation cannot mutate a note after navigation',async({w,doc})=>{
  await w.SmetraFileEditor.open({id:'note',name:'note.md',sha256:'qa'});await tick();
  w.api=async()=>({content:w.btoa('old version')});doc.querySelector('.file-editor-version').click();await tick();
  doc.querySelector('#file-editor-text').value='Unsaved draft';const confirmation=deferred();w.SmetraDialog={confirm:()=>confirmation.promise};
  let writes=0;w.api=async()=>{writes++;return {file:{sha256:'changed'}}};
  const pending=doc.querySelector('#file-editor-restore').onclick();w.eval("tab='support'");w.view('Support');
  confirmation.resolve(true);await pending;assert.equal(writes,0);assert.equal(doc.querySelector('#content').textContent,'Support');
 });
 await test('typing during restore preserves the new draft',async({w,doc})=>{
  await w.SmetraFileEditor.open({id:'note',name:'note.md',sha256:'qa'});await tick();
  w.api=async()=>({content:w.btoa('restored content')});doc.querySelector('.file-editor-version').click();await tick();
  const request=deferred();w.api=path=>path.endsWith('/restore')?request.promise:Promise.resolve({items:[]});
  const pending=doc.querySelector('#file-editor-restore').onclick();const input=doc.querySelector('#file-editor-text');input.value='New typing during restore';
  request.resolve({file:{sha256:'restored-hash'}});await pending;
  assert.equal(input.value,'New typing during restore');assert.match(doc.querySelector('#file-editor-status').textContent,/Новые правки ещё не сохранены/);
 });
 assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);process.exit(1)});
