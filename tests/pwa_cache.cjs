const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
(async()=>{
 // Keep the installable web app compatible with modern Chromium and iOS.
 const appHtml=fs.readFileSync('apps/web/app.html','utf8');
 assert.match(appHtml,/<meta\s+name="mobile-web-app-capable"\s+content="yes">/);
 assert.match(appHtml,/<meta\s+name="apple-mobile-web-app-capable"\s+content="yes">/);
 assert.match(appHtml,/<link\s+rel="manifest"\s+href="\/manifest\.webmanifest">/);
 // Our page never intentionally imports extension bundles or off-site JS.
 const pageScripts=[...appHtml.matchAll(/<script\b[^>]*\bsrc="([^"]+)"/g)].map(match=>match[1]);
 assert.ok(pageScripts.length>0&&pageScripts.every(source=>source.startsWith('/')&&!source.startsWith('//')),'All app scripts must use first-party URLs');
 const vercel=JSON.parse(fs.readFileSync('vercel.json','utf8'));
 const csp=vercel.headers.flatMap(block=>block.headers).find(header=>header.key==='Content-Security-Policy')?.value||'';
 assert.match(csp,/(?:^|;\s*)script-src 'self'(?:;|$)/,'CSP must not allow third-party scripts');
 assert.match(csp,/(?:^|;\s*)connect-src 'self'(?:;|$)/,'CSP must not allow third-party network requests');
 const listeners={},stored=new Map(),deleted=[],network=[];
 const cache={addAll:async requests=>{for(const request of requests)stored.set(new URL(request.url,'https://example.test').pathname,{offline:request.url.endsWith('/offline.html')})},match:async key=>stored.get(key)};
 const context={Request:class{constructor(url,options){this.url=url;this.options=options}},Response:{error:()=>({error:true})},URL,caches:{open:async()=>cache,keys:async()=>['other-app','smetra-public-offline-v1','smetra-public-offline-v2'],delete:async name=>deleted.push(name)},self:{location:{origin:'https://example.test'},skipWaiting:async()=>{},clients:{claim:async()=>{}},addEventListener:(name,callback)=>listeners[name]=callback},fetch:async request=>{network.push(request);if(request.offline)throw Error('Offline');return {online:true}}};
 vm.runInNewContext(fs.readFileSync('apps/web/service-worker.js','utf8'),context);
 let task;listeners.install({waitUntil:promise=>task=promise});await task;assert.deepEqual([...stored.keys()],['/offline.html','/offline.css','/assets/pwa/drops.svg','/assets/fonts/onest-variable.woff2']);
 listeners.activate({waitUntil:promise=>task=promise});await task;assert.deepEqual(deleted,['smetra-public-offline-v1']);
 const test=async(request,handled)=>{let promise;listeners.fetch({request,respondWith:value=>promise=value});assert.equal(!!promise,handled);return promise&&await promise};
 await test({method:'POST',mode:'navigate',url:'https://example.test/api/auth/login'},false);
 await test({method:'GET',mode:'cors',url:'https://example.test/api/profile'},false);
 await test({method:'GET',mode:'navigate',url:'https://other.test/app'},false);
 assert.equal((await test({method:'GET',mode:'navigate',url:'https://example.test/app'},true)).online,true);
 assert.equal((await test({method:'GET',mode:'navigate',url:'https://example.test/app',offline:true},true)).offline,true);
 assert.equal(network.length,2);assert.equal(stored.size,4,'No private pages or responses enter the cache');
 assert.ok(await test({method:'GET',mode:'no-cors',url:'https://example.test/assets/pwa/drops.svg'},true),'Offline page artwork comes from the cache');
 console.log('PASS: public-only offline cache, online navigation, network-error fallback, no API/POST/foreign caching');
})().catch(error=>{console.error(error);process.exit(1)});
