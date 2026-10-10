const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}};
function setup(){
 const dom=new JSDOM('<main id="content"></main><div id="toast"></div>',{url:'https://example.test/app#quotes',runScripts:'dangerously'}),w=dom.window,d=w.document;
 w.structuredClone=structuredClone;w.matchMedia=()=>({matches:false});w.scrollTo=()=>{};
 const load=file=>{const script=d.createElement('script');script.textContent=fs.readFileSync('apps/web/'+file,'utf8');d.head.append(script)};
 const app=fs.readFileSync('apps/web/app.js','utf8').split("if($('#auth')){")[0];const script=d.createElement('script');script.textContent=app;d.head.append(script);
 w.eval("user={id:'qa',quote_count:1};tab='quotes'");
 const quote={id:'q',revision:4,title:'Работы',client:'Клиент',currency:'RUB',items:[{line_id:'first',name:'Стены',quantity:'1',unit:'м²',unit_price:10000,cost_price:5000},{line_id:'second',name:'Пол',quantity:'2',unit:'м²',unit_price:20000,cost_price:6000}]};
 const writes=[];w.api=async(path,options)=>{if(options){const body=JSON.parse(options.body);writes.push({path,body,key:options.headers?.['Idempotency-Key']});return {quote:{...quote,...body,id:'q',revision:(body.revision||4)+1}}}if(path==='/workspace')return {workspace:{id:'w',name:'QA',currency:'RUB',role:'owner'},workspaces:[]};if(path==='/capabilities')return {};return {items:[]}};
 load('workspace.js');load('quote-editor-state.js');
 const fill=(selector,value)=>{const input=d.querySelector(selector);input.value=value;input.dispatchEvent(new w.Event('input',{bubbles:true}));return input};
 return {dom,w,d,quote,writes,fill,close:()=>dom.window.close()};
}
(async()=>{
 const failures=[];const test=async(name,run)=>{const e=setup();try{await run(e);console.log('PASS:',name)}catch(error){failures.push(name+': '+error.stack);console.error('FAIL:',name,error.message)}finally{e.close()}};
 await test('full history preserves rows, amounts, metadata and new duplicate identity',async({w,d,quote,fill})=>{
  await w.Workspace.editor(quote);fill('#f-title','Новые работы');d.querySelector('[data-duplicate="0"]').click();assert.equal(d.querySelectorAll('[data-row]').length,3);d.querySelector('[data-move="0"][data-direction="1"]').click();
  const history=w.SmetraQuoteEditorState.History;assert.ok(history);d.querySelector('#editor-undo').click();assert.equal(d.querySelector('[data-row="0"] [data-key=name]').value,'Стены');d.querySelector('#editor-undo').click();assert.equal(d.querySelectorAll('[data-row]').length,2);d.querySelector('#editor-undo').click();assert.equal(d.querySelector('#f-title').value,'Работы');d.querySelector('#editor-redo').click();assert.equal(d.querySelector('#f-title').value,'Новые работы');
 });
 await test('invalid financial input is local and undo restores exact raw input',async({w,d,quote,fill,writes})=>{
  await w.Workspace.editor(quote);fill('[data-row="0"] [data-key=quantity]','-1');d.querySelector('#editor-retry').click();await tick();assert.equal(writes.length,0);const stored=JSON.parse(w.localStorage.getItem('smetra.draft.qa.w.q'));assert.equal(stored.snapshot.items[0]._raw.quantity,'-1');d.querySelector('#editor-undo').click();assert.equal(d.querySelector('[data-row="0"] [data-key=quantity]').value,'1');
 });
 await test('manual checkpoint, expiry and custom metadata restore without replacing server revision',async({w,d,quote,fill})=>{
  await w.Workspace.editor(quote);fill('#f-expiry','2026-12-15');d.querySelector('#local-draft').click();fill('#f-title','Changed');fill('#f-expiry','2026-12-20');await d.querySelector('#restore-draft').onclick();assert.equal(d.querySelector('#f-title').value,'Работы');assert.equal(d.querySelector('#f-expiry').value,'2026-12-15');
 });
 await test('typing during save queues the latest input with returned revision',async({w,quote})=>{
  let data={title:'First'},snap=()=>structuredClone(data),first=deferred(),writes=[],stored;
  const writer=w.SmetraQuoteEditorState.writer({quote,active:()=>true,data:()=>data,snapshot:snap,valid:()=>true,persist:value=>stored=value,state(){},accept(){},request:async(path,options)=>{writes.push(JSON.parse(options.body));if(writes.length===1)return first.promise;return {quote:{id:'q',revision:6}}}});
  data={title:'Second'};const saving=writer.retry();data={title:'Third'};writer.changed();first.resolve({quote:{id:'q',revision:5}});await saving;await writer.flush();assert.equal(writes.length,2);assert.equal(writes[0].title,'Second');assert.equal(writes[1].title,'Third');assert.equal(writes[1].revision,5);assert.equal(stored.quote.revision,6);writer.stop();
 });
 await test('network retry preserves captured body and creation key without duplicate creation',async({w})=>{
  let data={title:'First'},writes=[];const writer=w.SmetraQuoteEditorState.writer({active:()=>true,data:()=>data,snapshot:()=>data,valid:()=>true,persist(){},state(){},accept(){},request:async(path,options)=>{writes.push({path,key:options.headers['Idempotency-Key'],body:JSON.parse(options.body)});if(writes.length===1)throw Error('lost response');return {quote:{id:'created',revision:writes.length}}}});
  await writer.retry();data={title:'New input'};writer.changed();await writer.flush();assert.equal(writes.length,3);assert.deepEqual(writes[0],writes[1]);assert.equal(writes[2].path,'/quotes/created/autosave');assert.equal(writes[2].body.title,'New input');writer.stop();
 });
 await test('conflict blocks automatic retries and late account replies cannot mutate UI',async({w,quote})=>{
  let data={title:'Original'},count=0,states=[];const options={quote,active:()=>true,data:()=>data,snapshot:()=>data,valid:()=>true,persist(){},accept(){},state:(kind)=>states.push(kind),request:async()=>{count++;throw Object.assign(Error('conflict'),{status:409})}};
  const writer=w.SmetraQuoteEditorState.writer(options);data={title:'Changed'};await writer.retry();writer.changed();await writer.retry();assert.equal(count,1);assert.equal(writer.blocked,true);writer.stop();
  const pending=deferred();let active=true,accepted=0;const late=w.SmetraQuoteEditorState.writer({...options,active:()=>active,request:()=>pending.promise,accept:()=>accepted++});data={title:'Another'};const save=late.retry();active=false;pending.resolve({quote:{id:'q',revision:5}});await save;assert.equal(accepted,0);late.stop();
 });
 await test('replayed creation modified by another device enters conflict instead of overwriting',async({w})=>{
  let data={title:'Original'},states=[];const writer=w.SmetraQuoteEditorState.writer({active:()=>true,data:()=>data,snapshot:()=>data,valid:()=>true,persist(){},accept(){},state:kind=>states.push(kind),request:async()=>({replayed:true,quote:{id:'q',revision:3,title:'Another device'}})});
  assert.equal(await writer.retry(),null);assert.equal(writer.blocked,true);assert.ok(states.includes('conflict'));writer.stop();
 });
 assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);process.exit(1)});
