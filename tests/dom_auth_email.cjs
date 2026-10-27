/* Email method exclusivity, mobile OTP controls and asynchronous auth races. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}};
async function setup(query='?register=1'){
 const dom=new JSDOM(fs.readFileSync('apps/web/app.html','utf8'),{url:'https://example.test/app'+query,runScripts:'outside-only'});
 const w=dom.window,doc=w.document,timers=[],completed=[];
 w.matchMedia=()=>({matches:true,addEventListener(){}});w.scrollTo=()=>{};
 w.setInterval=callback=>{timers.push(callback);return timers.length};
 w.fetch=async()=>({ok:false,status:401,json:async()=>({error:'Войдите'})});
 w.eval(fs.readFileSync('apps/web/app.js','utf8'));w.eval(fs.readFileSync('apps/web/auth-email.js','utf8'));
 await tick();await tick();
 w.SmetraCompleteAuth=async user=>{completed.push(user)};
 const capability=(code,signup=code)=>{w.SmetraEmailCodeAvailable=code;w.SmetraEmailSignupAvailable=signup;w.SmetraEmailDeliveryAvailable=code;doc.dispatchEvent(new w.Event('smetra:email-capability'))};
 const consent=()=>{doc.querySelector('#legal-consent').checked=true;doc.querySelector('#legal-consent').dispatchEvent(new w.Event('change',{bubbles:true}))};
 const submit=selector=>doc.querySelector(selector).dispatchEvent(new w.Event('submit',{cancelable:true}));
 const enabledEmails=()=>[...doc.querySelectorAll('#auth input[type=email]')].filter(input=>!input.disabled).map(input=>input.id);
 const details={dom,w,doc,timers,completed,capability,consent,submit,enabledEmails};capability(true);
 return details;
}
async function start(s){
 s.doc.querySelector('#email-code-name').value='Константин';
 s.doc.querySelector('#email-code-address').value='builder@example.test';
 s.consent();s.submit('#email-code-start');await tick();
}
function fillCode(s,value='123456'){
 const cells=[...s.doc.querySelectorAll('.email-code-cells input')];
 cells[0].value=value;cells[0].dispatchEvent(new s.w.Event('input',{bubbles:true}));
 assert.equal(cells.map(cell=>cell.value).join(''),value,'OS autofill distributes the six digits');
}
(async()=>{
 {
  const s=await setup(),{doc,w}=s;
  assert.deepEqual(s.enabledEmails(),['email-code-address']);
  assert.equal(doc.querySelector('#password').disabled,true);
  assert.equal(doc.querySelector('#name').required,false);
  assert.equal(doc.querySelector('#legal-consent').form.id,'email-code-start','Terms belong to the active email form');
  assert.equal(doc.querySelector('#email-code-start-button').disabled,true);
  s.consent();assert.equal(doc.querySelector('#email-code-start-button').disabled,false);
  doc.querySelector('#email-code-address').value='saved@example.test';doc.querySelector('#auth-login-tab').click();
  doc.querySelector('#auth-method-switch').click();assert.deepEqual(s.enabledEmails(),['email']);
  assert.equal(doc.querySelector('#email').value,'saved@example.test');
  doc.querySelector('#auth-method-switch').click();assert.deepEqual(s.enabledEmails(),['email-code-address']);
  // A late capability response never reopens the password form.
  s.capability(true);assert.equal(doc.querySelector('#email-disclosure').classList.contains('hidden'),true);
  s.capability(false,false);doc.querySelector('#auth-register-tab').click();
  assert.deepEqual(s.enabledEmails(),[]);assert.equal(doc.querySelector('#name').required,false);
  assert.equal(doc.querySelector('#legal-consent').disabled,false);
  assert.equal(doc.querySelector('#legal-consent').form,null);
  doc.querySelector('#auth-login-tab').click();assert.deepEqual(s.enabledEmails(),['email']);
  w.api=async()=>{throw Error('offline')};s.dom.window.close();
 }
 {
  const s=await setup(),pending=deferred();let calls=0;s.w.api=()=>{calls++;return pending.promise};
  await start(s);s.submit('#email-code-start');assert.equal(calls,1,'Repeated taps send only one code');
  s.doc.querySelector('#auth-login-tab').click();pending.resolve({challenge_id:'old',expires_in:600});await tick();
  assert.equal(s.doc.querySelector('#email-code-confirm').classList.contains('hidden'),true);
  assert.deepEqual(s.enabledEmails(),['email-code-address']);
  assert.equal(s.doc.querySelector('#email-code-start-button').disabled,false);s.dom.window.close();
 }
 {
  const s=await setup();let calls=0,now=Date.now();s.w.Date.now=()=>now;
  s.w.api=async()=>{calls++;if(calls===1)return {challenge_id:'valid-old-code',expires_in:600,retry_after:60};throw Error('mail unavailable')};
  await start(s);assert.equal(s.doc.querySelector('#email-code-confirm').classList.contains('hidden'),false);
  assert.deepEqual(s.enabledEmails(),[],'The address form is inactive on the code step');
  fillCode(s);now+=61000;s.timers.forEach(callback=>callback());
  s.doc.querySelector('#email-code-resend').click();await tick();
  assert.equal(s.doc.querySelector('#email-code-confirm').classList.contains('hidden'),false,'Failed resend keeps the old challenge');
  assert.equal([...s.doc.querySelectorAll('.email-code-cells input')].map(cell=>cell.value).join(''),'123456');
  let body;s.w.api=async(_path,options)=>{body=JSON.parse(options.body);return {user:{id:'same-account'}}};
  s.submit('#email-code-confirm');await tick();
  assert.equal(body.challenge_id,'valid-old-code');assert.equal(s.completed.length,1);s.dom.window.close();
 }
 {
  const s=await setup(),pending=deferred();s.w.api=async()=>({challenge_id:'first',expires_in:600});
  await start(s);fillCode(s);s.w.api=()=>pending.promise;s.submit('#email-code-confirm');
  s.doc.querySelector('#auth-login-tab').click();s.doc.querySelector('#auth-method-switch').click();
  pending.resolve({user:{id:'stale'}});await tick();
  assert.deepEqual(s.completed,[],'A late OTP response cannot complete another auth mode');
  assert.deepEqual(s.enabledEmails(),['email']);s.dom.window.close();
 }
 {
  const s=await setup(),pending=deferred();s.w.api=()=>pending.promise;await start(s);
  s.doc.querySelector('#email-code-back').click();pending.resolve({challenge_id:'late',expires_in:600});await tick();
  assert.equal(s.doc.querySelector('#email-code-confirm').classList.contains('hidden'),true,'Back invalidates a pending send');
  assert.equal(s.doc.querySelector('#email-code-address').value,'builder@example.test');s.dom.window.close();
 }
 {
  const s=await setup(''),pending=deferred();
  s.doc.querySelector('#auth-method-switch').click();s.w.api=()=>pending.promise;s.submit('#auth-form');
  s.doc.querySelector('#auth-register-tab').click();pending.resolve({user:{id:'old-password-request'}});await tick();
  assert.deepEqual(s.completed,[],'A late password response cannot sign in after switching to registration');
  assert.equal(s.doc.querySelector('#email-code-start-button').disabled,true,'Registration still requires consent');s.dom.window.close();
 }
 {
  const s=await setup('?reset=fixture');assert.deepEqual(s.enabledEmails(),[]);
  assert.equal(s.doc.querySelector('#password').disabled,false);
  assert.equal(s.doc.querySelector('#email-code-flow').classList.contains('hidden'),true);
  assert.equal(s.doc.querySelector('.auth-tabs').classList.contains('hidden'),true);s.dom.window.close();
 }
 console.log('PASS: one active email form, preserved address, legal gate, OTP autofill, duplicate taps, resend recovery, mode/back races and password reset');
})().catch(error=>{console.error(error);process.exit(1)});
