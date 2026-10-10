const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve}};
const original={id:'quote',title:'Private quote',published_version:2},versions=[{version:2,created_at:2},{version:1,created_at:1}];
const result=(values={})=>({title:'Private quote',source:'2',target:'current',revision:7,can_publish:true,summary:{added:0,removed:0,changed:1,moved:0,unchanged:1},totals:{before:10000,after:12000,before_currency:'RUB',after_currency:'RUB',delta_kopecks:2000},has_changes:true,fields:[{field:'terms',before:'Before',after:'<img src=x onerror=alert(1)>'}],items:[{kind:'changed',before:{name:'Work',unit_price:10000},after:{name:'<script>alert(1)</script>',unit_price:12000},fields:['name','unit_price'],moved:false,delta_kopecks:2000}],...values});
function setup(){
 const dom=new JSDOM('<main id="content"></main><div id="toast"></div>',{url:'https://example.test/app#quotes',runScripts:'dangerously'}),w=dom.window,doc=w.document;
 w.matchMedia=()=>({matches:false,addEventListener(){}});w.scrollTo=()=>{};
 const load=source=>{const script=doc.createElement('script');script.textContent=source;doc.head.append(script)};
 load(fs.readFileSync('apps/web/app.js','utf8').split("if($('#auth')){")[0]);w.eval("user={id:'qa'};tab='quotes'");
 const notices=[],opened=[];w.notify=text=>notices.push(text);w.Workspace={openQuote:async id=>{opened.push(id);w.view('Quote')}};
 w.api=async()=>result();load(fs.readFileSync('apps/web/quote-review.js','utf8'));
 return {dom,w,doc,notices,opened,close:()=>dom.window.close()};
}
(async()=>{
 const failures=[];
 const test=async(name,run)=>{const env=setup();try{await run(env);console.log('PASS:',name)}catch(error){failures.push(name+': '+error.message);console.error('FAIL:',name,error.message)}finally{env.close()}};
 await test('safe report preserves values and does not execute stored HTML',async({w,doc})=>{
  await w.SmetraQuoteReview.open(original,versions);assert.equal(doc.querySelector('.quote-review img'),null);assert.equal(doc.querySelector('.quote-review script'),null);assert.ok(doc.querySelector('#review-report').textContent.includes('<script>alert(1)</script>'));assert.equal(doc.querySelectorAll('.review-field').length,3);
 });
 await test('publishing waits for comparison and uses its exact revision',async({w,doc,opened})=>{
  const request=deferred(),writes=[];w.api=(path,options)=>options?.method==='POST'?(writes.push(JSON.parse(options.body)),Promise.resolve({})):request.promise;
  const pending=w.SmetraQuoteReview.open(original,versions,{publish:true});const form=doc.querySelector('#review-publish');await form.onsubmit({preventDefault(){}});assert.equal(writes.length,0);
  request.resolve(result());await pending;form.querySelector('textarea').value='Reviewed conditions';await form.onsubmit({preventDefault(){}});
  assert.deepEqual(writes,[{revision:7,comment:'Reviewed conditions'}]);assert.deepEqual(opened,['quote']);
 });
 await test('historical target and unavailable state cannot publish',async({w,doc})=>{
  w.api=async()=>result({target:'1',can_publish:false});await w.SmetraQuoteReview.open(original,versions,{publish:true});assert.equal(doc.querySelector('#review-publish button').disabled,true);
  w.api=async()=>result({can_publish:false});await doc.querySelector('#review-target').onchange();assert.equal(doc.querySelector('#review-publish button').disabled,true);assert.ok(doc.querySelector('#review-publish-status').textContent.length>0);
 });
 await test('latest comparison wins when older result arrives last',async({w,doc})=>{
  await w.SmetraQuoteReview.open(original,versions);const requests=[];w.api=()=>{const request=deferred();requests.push(request);return request.promise};const select=doc.querySelector('#review-source');select.value='1';const old=select.onchange();select.value='2';const fresh=select.onchange();
  requests[1].resolve(result({title:'Newest'}));await fresh;requests[0].resolve(result({title:'Old'}));await old;assert.equal(doc.querySelector('#review-title').textContent,'Newest');
 });
 await test('late comparison does not replace another page or account',async({w,doc})=>{
  const request=deferred();w.api=()=>request.promise;const pending=w.SmetraQuoteReview.open(original,versions);w.eval("user={id:'other'};tab='support'");w.view('Support');request.resolve(result());await pending;assert.equal(doc.querySelector('#content').textContent,'Support');
 });
 await test('failed publication keeps comment and reloads comparison before retry',async({w,doc})=>{
  let reads=0;w.api=async(path,options)=>{if(options?.method==='POST')throw Error('Conflict');reads++;return result({revision:reads+6})};await w.SmetraQuoteReview.open(original,versions,{publish:true});const form=doc.querySelector('#review-publish');form.querySelector('textarea').value='Keep this';await form.onsubmit({preventDefault(){}});
  assert.equal(reads,2);assert.equal(form.querySelector('textarea').value,'Keep this');assert.equal(form.querySelector('button').disabled,false);assert.ok(doc.querySelector('#review-publish-status').textContent.includes('Conflict'));
 });
 await test('currency change never invents a conversion difference',async({w,doc})=>{
  w.api=async()=>result({totals:{before:10000,after:20000,before_currency:'RUB',after_currency:'USD',delta_kopecks:null},items:[]});await w.SmetraQuoteReview.open(original,versions);assert.ok(doc.querySelector('.review-total').textContent.includes('Разные валюты'));
 });
 assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);process.exit(1)});
