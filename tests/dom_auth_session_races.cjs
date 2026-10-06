const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve}};
const response=(status,value)=>({ok:status===200,status,json:async()=>value});
function setup(payment=false){
 const dom=new JSDOM(fs.readFileSync('apps/web/app.html','utf8'),{url:'https://example.test/app'+(payment?'?payment=return':''),runScripts:'dangerously'}),w=dom.window,doc=w.document;
 w.matchMedia=()=>({matches:false,addEventListener(){}});w.scrollTo=()=>{};
 const boot=deferred(),calls=[];
 w.fetch=async path=>{calls.push(path);if(path==='/api/me')return boot.promise;return response(200,{user:{id:'new',name:'New account',role:'user',quote_count:0}})};
 w.Workspace={reset(){},render:async section=>{w.view('<p>'+section+'</p>');return true}};
 const script=doc.createElement('script');script.textContent=fs.readFileSync('apps/web/app.js','utf8');doc.head.append(script);
 return {dom,w,doc,boot,calls};
}
(async()=>{
 for(const status of [200,401]){
  const {dom,w,doc,boot}=setup();await tick();
  doc.querySelector('#auth-form').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();await tick();
  assert.equal(w.eval('user.id'),'new');
  boot.resolve(response(status,status===200?{user:{id:'old',name:'Old account',role:'admin'}}:{error:'Expired session'}));await tick();await tick();
  assert.equal(w.eval('user.id'),'new','Late bootstrap cannot replace the new account');
  assert.equal(doc.querySelector('#shell').classList.contains('hidden'),false,'Old failure cannot hide the new session');dom.window.close();
 }
 {
  const {dom,w,doc,boot}=setup(true);await tick();boot.resolve(response(200,{user:{id:'old',name:'Old account',role:'user'}}));await tick();await tick();
  assert.equal(doc.querySelector('#content').dataset.section,'billing','Payment return opens billing before status checks');
  doc.querySelector('#logout').click();await tick();await tick();assert.equal(w.eval('user'),null);assert.equal(doc.querySelector('#content').childNodes.length,0,'Logout clears private page DOM');dom.window.close();
 }
 console.log('PASS: late session success/failure cannot replace a new login; payment return chooses its page immediately; logout clears private DOM');
})().catch(error=>{console.error(error);process.exit(1)});
