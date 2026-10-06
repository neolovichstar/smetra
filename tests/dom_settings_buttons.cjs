const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
function setup(saved){
 const dom=new JSDOM('<body class="workspace-page"><button id="theme"></button><main id="content"></main><div id="toast"></div><section id="auth"></section><section id="shell"></section></body>',{url:'https://example.test/app',runScripts:'dangerously'}),w=dom.window,doc=w.document;
 w.load=source=>{const script=doc.createElement('script');script.textContent=source;doc.head.append(script)};
 if(saved)w.localStorage.setItem('smetra_theme',saved);
 for(const file of ['style.css','black.css','cabinet.css','product-ui.css','themes.css'])if(fs.existsSync('apps/web/'+file)){const style=doc.createElement('style');style.textContent=fs.readFileSync('apps/web/'+file,'utf8');doc.head.append(style)}
 w.matchMedia=()=>({matches:false,addEventListener(){}});w.confirm=()=>false;
 const source=fs.readFileSync('apps/web/app.js','utf8');w.load(source.slice(0,source.indexOf("if($('#auth')){")));
 w.eval("user={id:'qa',name:'QA',email:'qa@example.test',role:'user',email_verified:true,quote_count:0,plan:'free'};tab='settings'");
 w.Workspace={render:async()=>false,reset(){}};w.api=async()=>({});
 w.load(fs.readFileSync('apps/web/growth.js','utf8'));
 return {w,doc,close:()=>dom.window.close()};
}
(async()=>{
 const failures=[];async function test(name,run,saved){const env=setup(saved);try{await run(env);console.log('PASS:',name)}catch(e){failures.push(name+': '+e.message);console.error('FAIL:',name,e.message)}finally{env.close()}}
 await test('settings remove identity linking and placeholder providers',async({w,doc})=>{await w.render();assert.equal(doc.querySelector('#identity-link'),null);assert.ok(!doc.querySelector('#content').textContent.includes('Привяжите'))});
 await test('unconfigured email service never displays a nonworking resend action',async({w,doc})=>{w.eval("user.email_verified=false;tab='support'");await w.render();assert.equal(doc.querySelector('[data-resend]'),null);w.SmetraEmailDeliveryAvailable=true;await w.render();assert.ok(doc.querySelector('[data-resend]'))});
 await test('theme button changes actual page color and updates both controls',async({w,doc})=>{
  await w.render();assert.equal(w.getComputedStyle(doc.body).backgroundColor,'rgb(0, 0, 0)');doc.querySelector('#theme-alt').click();
  assert.equal(doc.documentElement.dataset.theme,'light');assert.notEqual(w.getComputedStyle(doc.body).backgroundColor,'rgb(0, 0, 0)');assert.equal(w.localStorage.getItem('smetra_theme'),'light');
  assert.match(doc.querySelector('#theme-alt').getAttribute('aria-label'),/тёмную/);doc.querySelector('#theme').click();assert.equal(doc.documentElement.dataset.theme,'dark');assert.equal(w.getComputedStyle(doc.body).backgroundColor,'rgb(0, 0, 0)');
 });
 await test('saved light theme survives rerender',async({w,doc})=>{await w.render();assert.equal(doc.documentElement.dataset.theme,'light');assert.notEqual(w.getComputedStyle(doc.body).backgroundColor,'rgb(0, 0, 0)');await w.render();assert.match(doc.querySelector('#theme-alt').getAttribute('aria-label'),/тёмную/)},'light');
 await test('cancelled account deletion makes no request',async({w,doc})=>{let calls=0;w.api=async()=>{calls++;return {}};await w.render();doc.querySelector('#delete-account').click();await tick();assert.equal(calls,0);assert.ok(doc.querySelector('#delete-account'))});
 await test('failed account deletion prevents duplicate requests and enables retry',async({w,doc})=>{
  w.confirm=()=>true;let reject,calls=0;w.api=()=>{calls++;return new Promise((yes,no)=>reject=no)};await w.render();const button=doc.querySelector('#delete-account');button.click();button.click();assert.equal(calls,1);assert.equal(button.disabled,true);reject(Error('Try again'));await tick();assert.equal(button.disabled,false);assert.match(doc.querySelector('#toast').textContent,/Try again/);
 });
 await test('support topic buttons change selection and retain the written question',async({w,doc})=>{
  w.eval("tab='support'");await w.render();const topics=[...doc.querySelectorAll('[data-support-topic]')];topics[0].click();doc.querySelector('#message').value+='My question';topics[1].click();assert.equal(doc.querySelector('#message').value,topics[1].dataset.supportTopic+': My question');assert.equal(topics[1].getAttribute('aria-pressed'),'true');
 });
 await test('support submit prevents duplicates and keeps text on failure',async({w,doc})=>{
  w.eval("tab='support'");await w.render();let reject,calls=0;w.api=()=>{calls++;return new Promise((yes,no)=>reject=no)};doc.querySelector('#message').value='Help me';const form=doc.querySelector('#support-form');form.requestSubmit();form.requestSubmit();assert.equal(calls,1);reject(Error('Offline'));await tick();assert.equal(doc.querySelector('#message').value,'Help me');assert.equal(form.querySelector('button').disabled,false);
 });
 await test('billing status refresh prevents duplicate calls and never grants unpaid Pro',async({w,doc})=>{
  const billing={email_verified:true,checkout_mode:'off',payments:[],pricing:{plans:{pro_month:{amount_kopecks:49000},pro_year:{amount_kopecks:490000}},annual_saving_kopecks:98000,limits:{free_quotes:10,pro_quotes:10000,pro_ai:100}}};w.api=async path=>path==='/billing'?billing:{};w.eval("tab='billing'");await w.render();let resolve,calls=0;w.api=path=>path==='/billing'?Promise.resolve(billing):path==='/billing/sync'?(calls++,new Promise(yes=>resolve=yes)):Promise.resolve({});const button=doc.querySelector('#sync');button.click();button.click();assert.equal(calls,1);resolve({user:{id:'qa',name:'QA',role:'user',plan:'free',quote_count:0,email_verified:true}});await tick();assert.match(doc.querySelector('#toast').textContent,/Старт/);
 });
 assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);process.exit(1)});
