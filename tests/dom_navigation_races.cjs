/* Delayed-network regression checks; no browser launch and no production API. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve}};
function setup(){
 const dom=new JSDOM('<body><div id="content"></div><div id="toast"></div><div id="auth"></div><div id="shell"></div></body>',{url:'https://example.test/app',runScripts:'dangerously'}),w=dom.window;
 w.load=source=>{const script=w.document.createElement('script');script.textContent=source;w.document.head.append(script)};
 w.matchMedia=()=>({matches:false,addEventListener(){}});w.confirm=()=>true;
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true};
 w.HTMLDialogElement.prototype.close=function(){this.open=false;w.setTimeout(()=>this.dispatchEvent(new w.Event('close')),0)};
 const source=fs.readFileSync('apps/web/app.js','utf8');w.load(source.slice(0,source.indexOf("if($('#auth')){")));
 w.eval("user={id:'qa-user',name:'QA',role:'user',email_verified:true};tab='files'");
 w.api=async path=>path==='/workspace'?{workspace:{id:'qa-workspace',name:'QA',role:'owner',currency:'RUB',settings:{}},workspaces:[]}:{items:[]};
 w.load(fs.readFileSync('apps/web/workspace.js','utf8'));
 for(const file of ['vendor/markdown-it-15.0.2.min.js','chat-markdown.js'])w.load(fs.readFileSync('apps/web/'+file,'utf8'));
 return {dom,w,doc:w.document,close:()=>dom.window.close()};
}
(async()=>{
 const failures=[];
 const test=async(name,run)=>{const env=setup();try{await run(env);console.log('PASS:',name)}catch(error){failures.push(name+': '+error.message);console.error('FAIL:',name,error.message)}finally{env.close()}};
 await test('billing response cannot replace a page opened later',async({w,doc})=>{
  const request=deferred();const original=w.api;w.api=path=>path==='/billing'?request.promise:original(path);
  w.eval("tab='billing'");const pending=w.render();await sleep(0);w.eval("tab='support'");await w.render();
  request.resolve({email_verified:true,checkout_mode:'off',payments:[]});await pending;
  assert.ok(doc.querySelector('#support-form'));assert.equal(doc.querySelector('.billing-hero'),null);
 });
 await test('logout invalidates pending rendering',async({w,doc})=>{
  const request=deferred();const original=w.api;w.api=path=>path==='/billing'?request.promise:original(path);
  w.eval("tab='billing'");const pending=w.render();await sleep(0);w.eval('user=null');w.showAuth();
  doc.querySelector('#content').textContent='Signed out';request.resolve({email_verified:true,checkout_mode:'off',payments:[]});await pending;
  assert.equal(doc.querySelector('#content').textContent,'Signed out');
 });
 await test('file search keeps newest query when older reply arrives last',async({w,doc})=>{
  await w.Workspace.render('files');const requests=[];w.api=path=>{const task=deferred();requests.push({path,...task});return task.promise};
  const search=doc.querySelector('#file-center-search');search.value='old';search.oninput();await sleep(230);search.value='new';search.oninput();await sleep(230);
  const row=name=>({id:name,name:name+'.txt',mime:'text/plain',size:1,created_at:1});
  requests[1].resolve({items:[row('new')]});await sleep(0);requests[0].resolve({items:[row('old')]});await sleep(0);
  assert.ok(doc.querySelector('#file-center-list').textContent.includes('new.txt'));assert.ok(!doc.querySelector('#file-center-list').textContent.includes('old.txt'));
 });
 await test('catalog filters keep newest query when older reply arrives last',async({w,doc})=>{
  await w.Workspace.render('catalog');const requests=[];w.api=path=>{const task=deferred();requests.push({path,...task});return task.promise};
  const search=doc.querySelector('#workspace-search');search.value='old';search.oninput();await sleep(250);search.value='new';search.oninput();await sleep(250);
  const row=name=>({id:name,name,price:100,unit:'шт.',item_type:'work',category:'',favorite:false});
  requests[1].resolve({items:[row('new')]});await sleep(0);requests[0].resolve({items:[row('old')]});await sleep(0);
  assert.ok(doc.querySelector('#records').textContent.includes('new'));assert.ok(!doc.querySelector('#records').textContent.includes('old'));
 });
 await test('account reset closes and clears workspace modal',async({w,doc})=>{
  await w.Workspace.render('files');await w.Workspace.palette();assert.ok(doc.querySelector('#workspace-dialog').open);
  w.Workspace.reset();assert.equal(doc.querySelector('#workspace-dialog').open,false);assert.equal(doc.querySelector('#workspace-dialog').childNodes.length,0);
 });
 await test('Markdown download cannot replace a page opened later',async({w,doc})=>{
  w.load(fs.readFileSync('apps/web/file-editor.js','utf8'));const request=deferred();w.fetch=()=>request.promise;
  const pending=w.SmetraFileEditor.open({id:'note',name:'note.md',sha256:'qa'});w.eval("tab='support'");doc.querySelector('#content').textContent='Support';
  request.resolve({ok:true,text:async()=>'Private old text'});await pending;assert.equal(doc.querySelector('#content').textContent,'Support');
 });
 await test('construction response cannot replace a page opened later',async({w,doc})=>{
  w.load(fs.readFileSync('apps/web/construction.js','utf8'));const request=deferred();w.api=()=>request.promise;w.eval("tab='construction'");
  const pending=w.SmetraConstruction();w.eval("tab='support'");doc.querySelector('#content').textContent='Support';request.resolve({items:[]});await pending;
  assert.equal(doc.querySelector('#content').textContent,'Support');
 });
 await test('assistant initialization cannot replace a page opened later',async({w,doc})=>{
  w.load(fs.readFileSync('apps/web/assistant-chat.js','utf8'));const request=deferred();w.api=path=>path==='/assistant'?request.promise:Promise.resolve({items:[]});w.eval("tab='assistant'");
  const pending=w.SmetraAssistant();w.eval("tab='support'");doc.querySelector('#content').textContent='Support';request.resolve({});await pending;
  assert.equal(doc.querySelector('#content').textContent,'Support');
 });
 await test('workspace reply cannot replace assistant navigation',async({w,doc})=>{
  const request=deferred(),original=w.api;w.api=path=>path==='/files'?request.promise:original(path);
  const pending=w.Workspace.render('files');await sleep(0);w.eval("tab='assistant'");doc.querySelector('#content').textContent='Assistant';request.resolve({items:[]});await pending;
  assert.equal(doc.querySelector('#content').textContent,'Assistant');
 });
 await test('support does not fetch unrelated workspace data',async({w})=>{
  const requests=[];w.api=async path=>{requests.push(path);return {items:[]}};w.eval("tab='support'");await w.render();assert.deepEqual(requests,[]);
 });
 await test('quote editor initialization cannot replace a page opened later',async({w,doc})=>{
  await w.Workspace.render('files');const request=deferred();w.api=()=>request.promise;
  const pending=w.Workspace.editor();w.eval("tab='support'");doc.querySelector('#content').textContent='Support';request.resolve({items:[]});await pending;
  assert.equal(doc.querySelector('#content').textContent,'Support');
 });
 await test('client detail reply cannot replace a page opened later',async({w,doc})=>{
  const original=w.api;w.api=path=>path==='/clients'?Promise.resolve({items:[{id:'client',name:'QA'}]}):original(path);w.eval("tab='clients'");await w.Workspace.render('clients');
  const request=deferred();w.api=()=>request.promise;doc.querySelector('[data-work="entity"]').click();await sleep(0);
  w.eval("tab='support'");doc.querySelector('#content').textContent='Support';request.resolve({item:{id:'client',name:'QA'}});await sleep(0);
  assert.equal(doc.querySelector('#content').textContent,'Support');
 });
 await test('late client attachments do not appear on another page',async({w,doc})=>{
  const original=w.api;w.api=path=>path==='/clients'?Promise.resolve({items:[{id:'client',name:'QA'}]}):original(path);w.eval("tab='clients'");await w.Workspace.render('clients');
  const request=deferred();w.api=path=>path.startsWith('/files?')?request.promise:Promise.resolve({item:{id:'client',name:'QA',projects:[],quotes:[],timeline:[],requests:[],payments:[]}});
  doc.querySelector('[data-work="entity"]').click();await sleep(0);w.eval("tab='support'");doc.querySelector('#content').textContent='Support';request.resolve({items:[]});await sleep(0);
  assert.equal(doc.querySelector('#content').textContent,'Support');
 });
 await test('first assistant use loads tools before applying record context',async({w,doc})=>{
  w.eval("tab='quotes'");const request=deferred();w.SmetraLoadFeature=()=>request.promise;
  const original=w.api;w.api=path=>path==='/quotes/quote'?Promise.resolve({quote:{id:'quote',title:'Context quote',client:'QA',currency:'RUB',items:[],approval_state:'draft'},activity:[]}):path==='/quotes/quote/versions'?Promise.resolve({versions:[]}):original(path);
  await w.Workspace.openQuote('quote');let clicked=false,context;
  const navigation=doc.createElement('button');navigation.dataset.tab='assistant';navigation.onclick=()=>clicked=true;doc.body.append(navigation);
  doc.querySelector('#ask-ai').click();await sleep(0);assert.equal(clicked,false);
  w.SmetraAssistantContext=value=>context=value;request.resolve();await sleep(0);assert.equal(clicked,true);assert.equal(context.id,'quote');
 });
 assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);process.exit(1)});
