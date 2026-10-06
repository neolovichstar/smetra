const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
(async()=>{
 const listeners={},stored=new Map(),deleted=[],network=[];
 const cache={addAll:async requests=>{for(const request of requests)stored.set(request.url.endsWith('/offline.css')?'/offline.css':'/offline.html',{offline:request.url.endsWith('/offline.html')})},match:async key=>stored.get(key)};
 const context={Request:class{constructor(url,options){this.url=url;this.options=options}},Response:{error:()=>({error:true})},URL,caches:{open:async()=>cache,keys:async()=>['other-app','smetra-public-offline-v0','smetra-public-offline-v1'],delete:async name=>deleted.push(name)},self:{location:{origin:'https://example.test'},skipWaiting:async()=>{},clients:{claim:async()=>{}},addEventListener:(name,callback)=>listeners[name]=callback},fetch:async request=>{network.push(request);if(request.offline)throw Error('Offline');return {online:true}}};
 vm.runInNewContext(fs.readFileSync('apps/web/service-worker.js','utf8'),context);
 let task;listeners.install({waitUntil:promise=>task=promise});await task;assert.deepEqual([...stored.keys()],['/offline.html','/offline.css']);
 listeners.activate({waitUntil:promise=>task=promise});await task;assert.deepEqual(deleted,['smetra-public-offline-v0']);
 const test=async(request,handled)=>{let promise;listeners.fetch({request,respondWith:value=>promise=value});assert.equal(!!promise,handled);return promise&&await promise};
 await test({method:'POST',mode:'navigate',url:'https://example.test/api/auth/login'},false);
 await test({method:'GET',mode:'cors',url:'https://example.test/api/profile'},false);
 await test({method:'GET',mode:'navigate',url:'https://other.test/app'},false);
 assert.equal((await test({method:'GET',mode:'navigate',url:'https://example.test/app'},true)).online,true);
 assert.equal((await test({method:'GET',mode:'navigate',url:'https://example.test/app',offline:true},true)).offline,true);
 assert.equal(network.length,2);assert.equal(stored.size,2,'No private pages or responses enter the cache');
 console.log('PASS: public-only offline cache, online navigation, network-error fallback, no API/POST/foreign caching');
})().catch(error=>{console.error(error);process.exit(1)});
