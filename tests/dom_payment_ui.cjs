const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
function fixture(url='https://example.test/app#billing'){
 const dom=new JSDOM('<button id="opener">Тарифы</button><main id="content"><input id="draft" value="Сохранённый черновик"></main>',{url,runScripts:'outside-only',pretendToBeVisual:true}),w=dom.window;
 w.user={id:'owner',plan:'free'};w.authRevision=1;w.tab='billing';w.escapeHtml=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));w.rub=n=>(n/100).toFixed(2)+' ₽';w.date=()=>'';
 w.matchMedia=()=>({matches:true});w.Element.prototype.scrollIntoView=()=>{};w.notify=()=>{};
 const billing={email_verified:true,checkout_mode:'live',payments:[],pricing:{catalog:{starter:{},pro_solo:{}},plans:{pro_month:{amount_kopecks:49900},pro_year:{amount_kopecks:499000}}}};
 const space={workspace:{id:'space',owner_id:'owner'},entitlements:{tier:'starter'}};
 let syncCalls=0,resolveSync,version=0;
 w.api=async path=>path==='/billing'?billing:path==='/workspace'?space:path==='/billing/sync'?(syncCalls++,new Promise(resolve=>resolveSync=resolve)):path==='/billing/checkout'?{status:'succeeded',payment_id:'new-payment'}:{};
 w.view=html=>{w.document.querySelector('#content').innerHTML=html};
 for(const file of ['payment-ui.js','ecosystem-billing.js','growth.js'])w.eval(fs.readFileSync('apps/web/'+file,'utf8'));
 w.render=async()=>{const mine=++version;await w.SmetraGrowth.billing(()=>mine===version&&w.tab==='billing')};
 return {dom,w,billing,space,calls:()=>syncCalls,resolve:value=>resolveSync(value)};
}
(async()=>{
 {
  const x=fixture(),w=x.w;w.document.querySelector('#opener').focus();
  await w.SmetraGrowth.paywall('ai_limit');
  assert.match(w.document.querySelector('.payment-dialog--offer').textContent,/499.00/,'Price comes from API');
  assert.equal(w.document.querySelector('#draft').value,'Сохранённый черновик');
  assert.equal(w.document.activeElement.className.includes('payment-action'),true,'Keyboard focus enters dialog');
  w.document.querySelector('.payment-close').click();assert.equal(w.document.activeElement.id,'opener','Closing restores focus');
  await w.SmetraGrowth.paywall('ai_limit');assert.equal(w.document.querySelector('dialog'),null,'Cooldown prevents repeated offers');
  x.dom.window.close();
 }
 for(const [status,kind] of [['succeeded','success'],['canceled','failure'],['refunded','refund'],['pending','waiting']]){
  const x=fixture(),w=x.w;w.SmetraPaymentUI.remember(w.user,{payment_id:'new-payment'});
  w.SmetraPaymentUI.outcome(w.user,1,{payments:[{id:'new-payment',status}]},{manual:true});
  assert.ok(w.document.querySelector('.payment-dialog--'+kind),'Verified '+status+' has the correct presentation');
  w.SmetraPaymentUI.close();
  if(status!=='pending'){w.SmetraPaymentUI.outcome(w.user,1,{payments:[{id:'new-payment',status}]},{manual:true});assert.equal(w.document.querySelector('dialog'),null,'Terminal animation is shown once per payment');}
  x.dom.window.close();
 }
 {
  const x=fixture('https://example.test/app?payment=succeeded#billing'),w=x.w;w.SmetraPaymentUI.remember(w.user,{payment_id:'new-payment'});
  assert.equal(w.SmetraPaymentUI.consumeReturn(),true);assert.equal(w.location.search,'');
  w.SmetraPaymentUI.outcome(w.user,1,{payments:[{id:'old-payment',status:'succeeded'}]},{manual:true});
  assert.equal(w.document.querySelector('.payment-dialog--success'),null,'URL and an older purchase cannot prove this payment');
  assert.ok(w.document.querySelector('.payment-dialog--waiting'));
  w.authRevision++;w.document.dispatchEvent(new w.Event('smetra:auth-reset'));assert.equal(w.document.querySelector('dialog'),null,'Logout closes sensitive dialogs');
  x.dom.window.close();
 }
 {
  const x=fixture('https://example.test/app?payment=return#billing'),w=x.w;x.billing.payments=[{id:'new-payment',plan:'pro_month',created_at:1,status:'pending',amount_kopecks:49900}];
  w.SmetraPaymentUI.remember(w.user,{payment_id:'new-payment'});const rendering=w.render();await tick();assert.equal(x.calls(),1);
  x.resolve({user:{id:'owner',plan:'free'},payments:[{id:'new-payment',status:'pending'}]});await rendering;await tick();
  assert.equal(x.calls(),1,'A pending return cannot recursively synchronize');assert.ok(w.document.querySelector('.payment-dialog--waiting'));
  w.SmetraPaymentUI.close();w.document.querySelector('#catalog-sync').click();await tick();w.tab='quotes';w.view('<p>Сметы</p>');
  x.resolve({user:{id:'owner',plan:'pro'},payments:[{id:'new-payment',status:'succeeded'}]});await tick();await tick();
  assert.equal(w.user.plan,'free','Late sync cannot mutate a departed page');assert.equal(w.document.querySelector('dialog'),null);
  x.dom.window.close();
 }
 {
  const x=fixture(),w=x.w;const original=w.api;
  w.api=async path=>{if(path==='/billing/sync')throw Error('Сверка временно недоступна');return original(path)};
  await w.render();w.document.querySelector('#catalog-sync').click();await tick();
  assert.match(w.document.querySelector('#catalog-checkout-note').textContent,/временно недоступна/);
  assert.equal(w.document.querySelector('dialog'),null,'A network failure is not a declined or successful payment');
  assert.equal(w.document.querySelector('#catalog-sync').disabled,false,'Status checks can be retried');x.dom.window.close();
 }
 {
  const x=fixture(),w=x.w;await w.render();w.document.querySelector('[data-product="pro_solo"]').click();await tick();assert.equal(x.calls(),1);
  x.resolve({user:{id:'owner',plan:'pro'},payments:[{id:'new-payment',status:'succeeded'}]});await tick();await tick();
  assert.ok(w.document.querySelector('.payment-dialog--success'),'Checkout tracks its exact API-issued payment ID through rerender');x.dom.window.close();
 }
 console.log('PASS: paywall price, draft/focus preservation, exact payment outcomes, stale sessions, no recursive sync and confirmed checkout');
})().catch(error=>{console.error(error);process.exit(1)});
