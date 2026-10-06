const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
function setup(){
 const dom=new JSDOM('<div id="content"></div>',{url:'https://example.test/app#billing',runScripts:'outside-only',pretendToBeVisual:true}),w=dom.window;
 w.user={id:'owner',plan:'free',entitlement_until:0};w.authRevision=1;w.tab='billing';w.escapeHtml=value=>String(value??'');w.rub=value=>String(value);w.date=()=>'';
 const notices=[];w.notify=value=>notices.push(value);w.view=html=>w.document.querySelector('#content').innerHTML=html;
 const offer={email_verified:true,checkout_mode:'live',payments:[],pricing:{plans:{pro_month:{amount_kopecks:49000},pro_year:{amount_kopecks:490000}},annual_saving_kopecks:98000,limits:{free_quotes:10,pro_quotes:10000,pro_ai:100}}};
 let resolve,calls=0,version=0;
 w.api=async path=>path==='/billing'?offer:path==='/billing/sync'?(calls++,new Promise(r=>resolve=r)):{};
 w.eval(fs.readFileSync('apps/web/growth.js','utf8'));
 const render=async()=>{const mine=++version;await w.SmetraGrowth.billing(()=>mine===version&&w.tab==='billing')};w.render=render;
 return {dom,w,offer,notices,render,finish:value=>resolve(value),calls:()=>calls};
}
(async()=>{
 {
  const x=setup();await x.render();x.w.document.querySelector('#sync').click();await tick();x.w.tab='quotes';x.w.view('<p>Quotes</p>');
  x.finish({user:{id:'owner',plan:'pro'},payments:[]});await tick();assert.equal(x.w.user.plan,'free');assert.equal(x.w.document.querySelector('#content').textContent,'Quotes');assert.deepEqual(x.notices,[]);x.dom.window.close();
 }
 {
  const x=setup();await x.render();x.w.document.querySelector('#sync').click();await tick();x.w.authRevision++;
  x.finish({user:{id:'owner',plan:'pro'},payments:[]});await tick();assert.equal(x.w.user.plan,'free','Changed session ignores previous payment response');x.dom.window.close();
 }
 {
  const x=setup();await x.render();x.w.document.querySelector('#sync').click();await tick();await x.render();x.w.document.querySelector('#sync').click();await tick();assert.equal(x.calls(),1,'Rerender cannot create a second concurrent sync');
  x.finish({user:{id:'owner',plan:'free'},payments:[]});await tick();await tick();assert.equal(x.w.user.plan,'free');x.dom.window.close();
 }
 {
  const x=setup();x.w.user.plan='pro';x.w.user.entitlement_until=Date.now()/1000+1000;x.w.sessionStorage.setItem('smetra.checkout.owner.pro_month','pending-key');await x.render();x.w.document.querySelector('#sync').click();await tick();
  x.finish({user:{id:'owner',plan:'pro',entitlement_until:Date.now()/1000+1000},payments:[{status:'pending'}]});await tick();await tick();assert.equal(x.w.sessionStorage.getItem('smetra.checkout.owner.pro_month'),'pending-key','Existing Pro cannot erase a pending renewal key');x.dom.window.close();
 }
 console.log('PASS: payment sync ignores departed pages and sessions; concurrent checks share one request; pending renewal keeps its key');
})().catch(error=>{console.error(error);process.exit(1)});
