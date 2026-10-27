const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const source=fs.readFileSync('apps/web/public-profile-ui.js','utf8');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const id='SM-'+'A'.repeat(32);
const photo='/api/public/avatars/'+id+'/'+'a'.repeat(64)+'.webp';
function setup(url='https://example.test/app',html='<div id="host"></div>'){
 const dom=new JSDOM(html,{url,runScripts:'dangerously'}),w=dom.window;
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true};
 w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'))};
 w.HTMLCanvasElement.prototype.getContext=()=>({clearRect(){},drawImage(){}});
 w.HTMLCanvasElement.prototype.toDataURL=()=>('data:image/webp;base64,dGVzdA==');
 w.fetch=async()=>{throw Error('unexpected request')};
 w.eval(source);return {dom,w,host:w.document.querySelector('#host'),ui:w.SmetraPublicProfile};
}
(async()=>{
 {
  const {dom,w,host,ui}=setup();let resolveBitmap,closed=0,posted=0,changed=0,active=true;
  w.createImageBitmap=()=>new Promise(resolve=>resolveBitmap=resolve);
  ui.mountAvatar({host,user:{name:'Anna'},api:async()=>{posted++;return {avatar_url:photo}},active:()=>active,onChange:()=>changed++});
  const input=host.querySelector('input');Object.defineProperty(input,'files',{value:[new w.File(['x'],'photo.png',{type:'image/png'})]});
  input.dispatchEvent(new w.Event('change'));await tick();active=false;resolveBitmap({width:80,height:60,close(){closed++}});
  await tick();assert.equal(posted,0);assert.equal(changed,0);assert.equal(closed,1);dom.window.close();
 }
 {
  const {dom,w,host,ui}=setup();let posted=0,resolver,changes=0;
  w.createImageBitmap=async()=>({width:80,height:60,close(){}});
  ui.mountAvatar({host,user:{name:'Anna'},api:()=>{posted++;return new Promise(resolve=>resolver=resolve)},onChange:()=>changes++});
  const input=host.querySelector('input');Object.defineProperty(input,'files',{value:[new w.File(['x'],'photo.png',{type:'image/png'})]});
  input.dispatchEvent(new w.Event('change'));await tick();
  assert.equal(posted,0,'choosing a file must wait for explicit save');
  w.document.querySelector('[data-save]').click();await tick();assert.equal(posted,1);
  const cancel=new w.Event('cancel',{cancelable:true});w.document.querySelector('dialog').dispatchEvent(cancel);
  assert(cancel.defaultPrevented,'escape cannot cancel a running upload and allow a racing second upload');
  resolver({avatar_url:photo});await tick();assert.equal(changes,1);assert.equal(w.document.querySelector('dialog'),null);dom.window.close();
 }
 {
  const {dom,w,ui}=setup('https://example.test/app?person='+id+'&intent=message#chats');
  ui.captureIntent();assert.equal(JSON.parse(w.sessionStorage.getItem('smetra.profileIntent')).person,id);
  assert.equal(w.location.search,'');let calls=0,message='';
  await ui.resume({api:async path=>{calls++;assert(path.startsWith('/public/profiles/'));return {profile:{public_id:id,allow_messages:false}}},notify:text=>message=text});
  assert.equal(calls,1);assert(message.includes('отключил'));assert.equal(w.sessionStorage.getItem('smetra.profileIntent'),null);dom.window.close();
 }
 {
  const {dom,w}=setup('https://example.test/u/anna','<div id="public-profile-page"></div>');
  // publicPage waits for fetch; replace the failed request with a fresh module instance.
  w.fetch=async()=>({ok:true,json:async()=>({profile:{public_id:id,url:'/u/anna',name:'<img src=x onerror=alert(1)>',bio:'<script>steal()</script>',avatar_url:'javascript:alert(1)',allow_messages:true,allow_quotes:true}})});
  w.eval(source);await tick();await tick();
  const root=w.document.querySelector('#public-profile-page');
  assert.equal(root.querySelectorAll('h1').length,1);assert.equal(root.querySelectorAll('script,img').length,0);
  assert(root.textContent.includes('<script>steal()</script>'));dom.window.close();
 }
 console.log('PASS: avatar confirmation, session isolation, upload races, login intent, contact permissions and public HTML escaping');
})().catch(error=>{console.error(error);process.exit(1)});
