const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const source=fs.readFileSync('apps/web/ui/native.js','utf8');
const load=(setup)=>{const dom=new JSDOM('<!doctype html><html data-theme="dark"><body><div id="content"></div></body></html>',{runScripts:'outside-only'});setup?.(dom.window);dom.window.eval(source);return dom.window};
(async()=>{
 // In a normal browser the bridge is inert and every call rejects without side effects.
 const web=load();
 assert.equal(web.SmetraShell.available,false);
 assert.equal(web.document.documentElement.classList.contains('in-app'),false);
 await assert.rejects(web.SmetraShell.call('app.hello'),error=>error.code==='unavailable');
 assert.equal(web.SmetraShell.handleBack(),false,'Nothing to close: Android decides');

 // Inside the app: requests are versioned JSON strings, replies settle by id, events fan out.
 const sent=[];let deliver;
 const app=load(w=>{w.SmetraNative={postMessage:raw=>sent.push(JSON.parse(raw)),addEventListener:(type,fn)=>{if(type==='message')deliver=fn}}});
 assert.equal(app.SmetraShell.available,true);
 assert.equal(app.document.documentElement.classList.contains('in-app'),true);
 const hello=sent.find(message=>message.op==='app.hello');
 assert.ok(hello&&hello.v===1&&/^[A-Za-z0-9_-]+$/.test(hello.id),'Hello request uses protocol v1 with a safe id');
 deliver({data:JSON.stringify({v:1,id:hello.id,ok:true,result:{protocol:1,features:{ar:'supported',speech:true,push:false}}})});
 await app.SmetraShell.ready;await tick();
 assert.equal(app.SmetraShell.has('ar'),true);assert.equal(app.SmetraShell.has('push'),false);
 assert.ok(sent.some(message=>message.op==='app.setTheme'&&message.args.dark===true),'System bars follow the page theme');
 const pending=app.SmetraShell.call('ar.measure',{},{timeout:0});
 const measure=sent[sent.length-1];
 deliver({data:JSON.stringify({v:1,id:measure.id,ok:false,error:{code:'cancelled',message:'Замер отменён'}})});
 await assert.rejects(pending,error=>error.code==='cancelled'&&error.message==='Замер отменён');
 deliver({data:'not json'});deliver({data:JSON.stringify({v:2,event:'app.update',data:{}})});
 assert.equal(app.document.querySelector('.app-update'),null,'Malformed and foreign-version messages are ignored');
 deliver({data:JSON.stringify({v:1,event:'app.update',data:{required:true,message:'<img src=x onerror=alert(1)>'}})});
 const bar=app.document.querySelector('.app-update.is-required');
 assert.ok(bar,'Required update shows a blocking banner');
 assert.equal(bar.querySelector('img'),null,'Server message is rendered as text');
 assert.equal(bar.querySelector('[aria-label="Позже"]'),null,'A required update cannot be dismissed');
 bar.querySelector('.btn').click();
 assert.equal(sent[sent.length-1].op,'app.openStore');
 const dialog=app.document.createElement('dialog');dialog.innerHTML='<button data-dialog-close>×</button>';app.document.body.append(dialog);dialog.show?.();dialog.setAttribute('open','');
 let closed=false;dialog.querySelector('button').onclick=()=>{closed=true;dialog.removeAttribute('open')};
 assert.equal(app.SmetraShell.handleBack(),true);assert.equal(closed,true,'Back closes the topmost dialog first');
 console.log('PASS: native bridge client is inert on the web, settles replies by id, ignores foreign messages and renders updates safely');
})().catch(error=>{console.error(error);process.exit(1)});
