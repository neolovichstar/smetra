const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(r=>setTimeout(r,0));
const response=(status,value)=>({ok:status>=200&&status<300,status,json:async()=>value});
function setup({native=true,query='',status=401}={}){
 const dom=new JSDOM(fs.readFileSync('apps/web/app.html','utf8'),{url:'https://smetra.test/app'+query,runScripts:'dangerously'}),w=dom.window;
 w.matchMedia=()=>({matches:false,addEventListener(){}});w.scrollTo=()=>{};
 w.structuredClone=value=>JSON.parse(JSON.stringify(value));
 w.SmetraShell={available:native,has:()=>false,ready:Promise.resolve(null)};
 w.SmetraDialog={confirm:async()=>true};
 const calls=[];
 w.fetch=async path=>{calls.push(path);return path==='/api/me'?response(status,status===200?{user:{id:'owner',name:'Owner',role:'user'}}:{error:'Sign in'}):response(200,{})};
 for(const file of ['guest.js','app.js','workspace.js','calculators.js']){const script=w.document.createElement('script');script.textContent=fs.readFileSync('apps/web/'+file,'utf8');w.document.head.append(script)}
 w.SmetraLoadFeature=async()=>{};
 return {dom,w,doc:w.document,calls};
}
(async()=>{
 for(const options of [{native:true},{native:false},{query:'?register=1'},{query:'?verify=token'},{query:'?payment=return'},{status:403}]){
  const env=setup(options);await tick();await tick();
  assert.equal(env.w.SmetraGuest.active,options.native!==false&&!options.query&&options.status!==403,'Only a normal signed-out Android launch defaults to guest');env.dom.window.close();
 }
 const {dom,w,doc,calls}=setup();await tick();await tick();
 assert.equal(doc.querySelector('#shell').hasAttribute('inert'),true,'Private shell stays inert');
 const baseline=calls.length;
 doc.querySelector('[data-guest=draft]').click();
 const input=(selector,value)=>{const node=doc.querySelector(selector);node.value=value;node.dispatchEvent(new w.Event('input',{bubbles:true}))};
 input('[data-field=name]','Покраска стен');input('[data-field=quantity]','12,5');input('[data-field=price]','380,25');
 assert.match(doc.querySelector('#guest-total').textContent,/4\s?753,13/,'The real estimate decimal calculator rounds to kopecks');
 for(let i=0;i<15;i++)doc.querySelector('[data-guest=add]').click();
 assert.equal(doc.querySelectorAll('[data-row]').length,10);assert.equal(doc.querySelector('[data-guest=add]').disabled,true);
 assert.equal(calls.length,baseline,'Local scratchpad never calls private APIs');
 w.SmetraGuest.leave();doc.querySelector('#auth-guest').click();doc.querySelector('[data-guest=draft]').click();
 assert.equal(doc.querySelector('[data-field=name]').value,'Покраска стен','Draft survives leaving and re-entering guest');
 doc.querySelectorAll('[data-remove]').forEach((button,i)=>{if(i>0)button.click()});
 // The old node list is stale after each render; remove remaining rows from the live DOM.
 while(doc.querySelectorAll('[data-row]').length>1)doc.querySelector('[data-remove="1"]').click();
 input('[data-field=price]','bad');doc.querySelector('[data-guest=save]').click();assert.equal(w.SmetraGuest.active,true,'Invalid money cannot enter the authenticated editor');
 input('[data-field=price]','380,25');doc.querySelector('[data-guest=save]').click();
 assert.equal(w.SmetraGuest.active,false);assert.equal(doc.querySelector('#auth-register-tab').getAttribute('aria-selected'),'true');
 const transferred=JSON.parse(w.sessionStorage.getItem('smetra.previewDraft'));
 assert.equal(transferred.items[0].quantity,'12.5');assert.equal(transferred.items[0].unit_price,38025);
 assert.equal(calls.length,baseline,'Saving asks for auth without sending a guest estimate');
 doc.querySelector('#auth-guest').click();doc.querySelector('[data-guest=calculators]').click();await tick();await tick();
 assert.ok(doc.querySelector('#smetra-calculators'),'Existing real calculator is reused');
 doc.querySelector('#smcalc-draft').click();await tick();await tick();
 assert.ok(doc.querySelector('[data-row]'),'Calculator transfers to the local guest draft');
 assert.equal(calls.length,baseline);
 w.localStorage.setItem('smetra.guest.draft.v1',JSON.stringify({title:'<img src=x onerror=alert(1)>',items:[{name:'<script>alert(1)</script>',quantity:'1',unit:'м²',unit_price:100}]}));
 w.SmetraGuest.leave();doc.querySelector('#auth-guest').click();doc.querySelector('[data-guest=draft]').click();
 assert.equal(doc.querySelector('#smetra-guest img,#smetra-guest script'),null,'Stored content is escaped');
 const clean=w.SmetraGuest.clean({id:'forged',workspace_id:'other',items:Array(30).fill({name:'x',quantity:'1',unit_price:-100})});
 assert.equal(clean.items.length,10);assert.equal(clean.id,undefined);assert.equal(clean.workspace_id,undefined);assert.equal(clean.items[0].unit_price,0);
 dom.window.close();
 console.log('PASS: native guest entry, explicit auth routes, decimal totals, ten-row cap, local persistence, auth handoff, existing calculators, XSS and no private API traffic');
})().catch(error=>{console.error(error);process.exit(1)});
