/* Slow cloud/store requests must keep the currently selected quote and folder. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const source=fs.readFileSync('apps/web/premium-tools.js','utf8');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}};
const features={cloud_drives:true,product_monitor:true,visual_estimates:true};
const quote=id=>({id,status:'draft',title:id,revision:2,items:[{line_id:'line-'+id,name:'Строка '+id}]});
function setup(override=()=>{}){
 const dom=new JSDOM('<main id="mount"></main>',{url:'https://smetra.online/app#premium',runScripts:'outside-only'}),w=dom.window,doc=w.document;
 const notices=[],calls=[];
 w.escapeHtml=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 w.header=()=>'<h1>Материалы и облака</h1>';w.view=html=>{doc.querySelector('#mount').innerHTML=html};
 w.notify=message=>notices.push(message);w.SmetraDialog={confirm:async()=>true};
 w.api=async(path,options)=>{
  calls.push({path,options});
  const handled=override(path,options);if(handled!==undefined)return handled;
  if(path==='/premium/features')return features;
  if(path==='/quotes')return {quotes:[quote('A'),quote('B')]};
  if(path==='/premium/product-sources')return {sources:[]};
  if(path==='/premium/cloud/connections')return {connections:[{id:'y-1',provider:'yandex_disk',status:'active'}]};
  if(path==='/premium/cloud/folders')return {folders:[]};
  if(path==='/premium/cloud/jobs')return {jobs:[]};
  if(path.startsWith('/premium/cloud/browse-folders?'))return {folders:[{id:'/A',name:'Папка A'},{id:'/B',name:'Папка B'}],files:[]};
  if(path==='/premium/products/preview')return {product:{url:'https://shop.example/product',price_kopecks:1000,currency:'RUB'}};
  throw Error('Unexpected request: '+path);
 };
 w.eval(source);
 const change=id=>{const select=doc.querySelector('#premium-product-quote');select.value=id;select.dispatchEvent(new w.Event('change'))};
 const submit=selector=>doc.querySelector(selector).dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
 return {dom,w,doc,ui:w.SmetraPremiumTools,calls,notices,change,submit};
}
(async()=>{
 {
  const a=deferred(),b=deferred(),save=deferred();
  const t=setup((path,options)=>path==='/quotes/A'?a.promise:path==='/quotes/B'?b.promise:path==='/premium/product-sources'&&options?.method==='POST'?save.promise:undefined);
  try{
   await t.ui.render();await tick();t.submit('#premium-product-form');await tick();
   t.change('A');t.change('B');b.resolve({quote:quote('B')});await tick();a.resolve({quote:quote('A')});await tick();
   assert.equal(t.doc.querySelector('#premium-product-item').value,'line-B','Late quote A cannot replace selected quote B');
   const button=t.doc.querySelector('#premium-save-source');button.click();await tick();
   const request=t.calls.find(x=>x.path==='/premium/product-sources'&&x.options?.method==='POST');
   assert.equal(JSON.parse(request.options.body).quote_id,'B');
   save.reject(Error('Магазин временно недоступен'));await tick();await tick();
   assert.equal(button.disabled,false,'A failed save restores the original button after event.currentTarget is cleared');
   assert.equal(t.notices.at(-1),'Магазин временно недоступен');
   t.change('');assert.equal(t.doc.querySelector('#premium-save-source').disabled,true,'Clearing the quote disables the old product action');
  }finally{t.dom.window.close()}
 }
 {
  const old=deferred();let reads=0;
  const t=setup(path=>path==='/premium/features'&&++reads===1?old.promise:undefined);
  try{
   const stale=t.ui.render();await t.ui.render();await tick();
   const page=t.doc.querySelector('.premium-tools-page');assert.ok(page);
   old.resolve({});await stale;
   assert.equal(t.doc.querySelector('.premium-tools-page'),page,'An older render cannot replace the latest page with a tariff screen');
  }finally{t.dom.window.close()}
 }
 {
  const saved=deferred();let posts=0;
  const t=setup((path,options)=>{if(path==='/premium/cloud/folders'&&options?.method==='POST'){posts++;return saved.promise}});
  try{
   await t.ui.render();await tick();
   const choose=t.doc.querySelectorAll('.premium-folder-select');choose[0].click();
   t.submit('#premium-folder-form');t.submit('#premium-folder-form');await tick();
   assert.equal(posts,1,'Repeated submission while saving cannot create a second operation');
   choose[1].click();assert.equal(t.doc.querySelector('#premium-folder-submit').disabled,true,'Changing the selection cannot bypass a running submission');
   saved.resolve({folder_id:'bound-a'});await tick();await tick();
   assert.equal(t.doc.querySelector('#premium-folder-id').value,'/B','Saving A preserves a newer selection of B');
   assert.equal(t.doc.querySelector('#premium-folder-submit').disabled,false);
  }finally{t.dom.window.close()}
 }
 {
  const confirmation=deferred();let writes=0;
  const t=setup((path,options)=>{if(options?.method==='DELETE'){writes++;return {ok:true}}});
  try{
   await t.ui.render();await tick();t.w.SmetraDialog.confirm=()=>confirmation.promise;
   t.doc.querySelector('[data-premium-disconnect]').click();await tick();
   await t.ui.render();confirmation.resolve(true);await tick();await tick();
   assert.equal(writes,0,'An obsolete confirmation cannot disconnect an account after the page was replaced');
  }finally{t.dom.window.close()}
 }
 {
  let status='failed',retries=0;
  const t=setup((path,options)=>{
   if(path==='/premium/cloud/jobs')return {jobs:[{id:'failed-job',name:'Счёт.pdf',provider:'yandex_disk',status}]};
   if(path==='/premium/cloud/jobs/failed-job/retry'&&options?.method==='POST'){retries++;status='queued';return {status}}
  });
  try{
   await t.ui.render();await tick();const retry=t.doc.querySelector('[data-premium-retry]');assert.ok(retry);
   retry.click();retry.click();await tick();await tick();
   assert.equal(retries,1,'Retry button sends one operation');assert.equal(t.doc.querySelector('[data-premium-retry]'),null);
   assert.match(t.doc.querySelector('.premium-job-copy').textContent,/В очереди/);
  }finally{t.dom.window.close()}
 }
 console.log('PASS: premium quote/render races, failed-save retry, folder submission isolation and stale confirmations');
})().catch(error=>{console.error(error);process.exitCode=1});
