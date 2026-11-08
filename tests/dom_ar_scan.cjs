'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return{promise,resolve,reject}};
async function setup({capture,native}={}){
 const dom=new JSDOM('<body><main id="content"></main></body>',{url:'https://smetra.test/app#ar-scan',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window,d=w.document,calls=[],camera=[];
 const script=d.createElement('script');script.textContent="let user={id:'qa'},tab='ar-scan'; const escapeHtml=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));const view=html=>{document.dispatchEvent(new Event('smetra:before-view'));document.querySelector('#content').innerHTML=html};";d.head.append(script);
 w.sessionStorage.setItem('workspace_id','workspace');w.HTMLMediaElement.prototype.play=async()=>{};
 let stops=0;const stream={getTracks:()=>[{stop:()=>stops++}]};
 Object.defineProperty(w.navigator,'mediaDevices',{value:{getUserMedia:async options=>{camera.push(options);return capture?capture.promise:stream}}});
 w.api=async(path,options={})=>{calls.push({path,options});if(path==='/construction/objects'&&!options.method)return{items:[{id:'object',name:'Тестовый объект'}]};if(path.endsWith('/scan/preview'))return{rooms:JSON.parse(options.body).rooms};if(path.endsWith('/scan/import'))return{zones:[{id:'zone'}]};throw Error('Unexpected request '+path)};
 w.SmetraNavigateTo=async()=>{};if(native)w.SmetraShell=native;
 const source=d.createElement('script');source.textContent=fs.readFileSync('apps/web/ar-scan.js','utf8');d.head.append(source);
 const rendering=w.SmetraARScan.render();await tick();await tick();if(!capture)await rendering;
 return{w,d,calls,camera,stream,rendering,stops:()=>stops,close:()=>{w.SmetraARScan.stop();dom.window.close()}};
}
(async()=>{
 const failures=[];const test=async(name,run,options)=>{const e=await setup(options);try{await run(e);console.log('PASS:',name)}catch(error){failures.push(name+': '+error.message);console.error('FAIL:',name,error.stack)}finally{e.close()}};
 await test('AR page requests the rear camera without microphone or network image upload',async({d,calls,camera})=>{
  assert.equal(camera.length,1);assert.equal(camera[0].audio,false);assert.equal(camera[0].video.facingMode.ideal,'environment');assert.equal(calls.length,0);assert.equal(d.querySelectorAll('.ar-page').length,1);assert.match(d.querySelector('[data-ar-instruction]').textContent,/размеры нужно ввести вручную/);assert.equal(d.querySelector('[data-ar-point]').hidden,true);
 });
 await test('leaving AR stops every live camera track',async({w,d,stops})=>{d.dispatchEvent(new w.Event('smetra:before-view'));assert.equal(stops(),1);assert.equal(d.querySelector('video').srcObject,null)});
 await test('logout releases the camera even when authentication clears the screen without navigation',async({w,d,stops})=>{w.eval('user=null');d.dispatchEvent(new w.Event('smetra:auth-reset'));assert.equal(stops(),1);assert.equal(d.querySelector('video').srcObject,null)});
 const late=deferred();await test('a late camera permission result is closed after navigation',async({w,d,rendering,stream,stops})=>{d.dispatchEvent(new w.Event('smetra:before-view'));late.resolve(stream);await rendering;assert.equal(stops(),1);assert.equal(d.querySelector('video').srcObject,null)},{capture:late});
 const denied=deferred();await test('camera denial offers a retry and manual dimensions without invented measurements',async({d,rendering})=>{denied.reject(new DOMException('Denied','NotAllowedError'));await rendering;assert.match(d.querySelector('[data-ar-state]').textContent,/Разрешите доступ/);assert.equal(d.querySelector('[data-ar-start]').hidden,false);d.querySelector('[data-ar-manual]').click();await tick();assert.equal(d.querySelector('.ar-review').hidden,false);assert.equal(d.querySelector('input[name=length]').value,'')},{capture:denied});
 const nativeResult=deferred(),nativeCalls=[];
 await test('Android opens the native AR camera and preserves the returned dimensions for review',async({d,camera,calls})=>{
  assert.deepEqual(nativeCalls,['ar.status','ar.measure']);assert.equal(camera.length,0);assert.equal(calls.length,0);
  nativeResult.resolve({rooms:[{name:'Кухня',length:'4',width:'3',height:'2.7',source:'arcore'}]});await tick();await tick();assert.equal(d.querySelector('.ar-review').hidden,false);assert.equal(d.querySelector('input[name=length]').value,'4');assert.equal(calls.filter(c=>c.options.method==='POST').length,0);
 },{native:{available:true,ready:Promise.resolve(),call:async op=>{nativeCalls.push(op);return op==='ar.status'?{status:'supported'}:nativeResult.promise}}});
 let availabilityChecks=0,measurements=0;
 await test('a transient ARCore availability check is retried before choosing manual camera mode',async({camera})=>{
  assert.equal(availabilityChecks,2);assert.equal(measurements,1);assert.equal(camera.length,0);
 },{native:{available:true,ready:Promise.resolve(),call:async op=>{if(op==='ar.status')return{status:++availabilityChecks===1?'checking':'supported'};measurements++;return new Promise(()=>{})}}});
 await test('dimensions require review and a server preview before an import',async({d,calls})=>{
  d.querySelector('[data-ar-manual]').click();await tick();await tick();
  for(const [name,value]of Object.entries({name:'Комната',length:'4',width:'3',height:'2.7',openings_m2:'1'}))d.querySelector('[name='+name+']').value=value;
  d.querySelector('[data-ar-object]').value='object';d.querySelector('[data-ar-form]').requestSubmit();await tick();assert.equal(calls.filter(c=>c.options.method==='POST').length,0);
  d.querySelector('[data-ar-confirm]').checked=true;d.querySelector('[data-ar-form]').requestSubmit();await tick();await tick();
  const writes=calls.filter(c=>c.options.method==='POST');assert.deepEqual(writes.map(c=>c.path),['/construction/objects/object/scan/preview','/construction/objects/object/scan/import']);assert.equal(JSON.parse(writes[1].options.body).rooms[0].source,'manual');assert.equal(JSON.parse(writes[1].options.body).review_confirmed,true);assert.equal(d.querySelector('[data-ar-save]').hidden,true);
  let opened;const w=d.defaultView;w.SmetraLoadFeature=async()=>{};w.SmetraConstruction={openObject:async id=>{opened=id}};
  d.querySelector('[data-ar-open-object]').click();await tick();assert.equal(opened,'object','Open the exact measured object');
 });
 assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);process.exitCode=1});
