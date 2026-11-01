const OFFLINE_CACHE='smetra-public-offline-v2';
const OFFLINE_PAGE='/offline.html';
const OFFLINE_ASSETS=['/offline.css','/assets/pwa/drops.svg','/assets/fonts/onest-variable.woff2'];
self.addEventListener('install',event=>{
  event.waitUntil((async()=>{const cache=await caches.open(OFFLINE_CACHE);await cache.addAll([OFFLINE_PAGE,...OFFLINE_ASSETS].map(url=>new Request(url,{cache:'reload'})));await self.skipWaiting()})());
});
self.addEventListener('activate',event=>{
  event.waitUntil((async()=>{for(const key of await caches.keys())if(key.startsWith('smetra-public-offline-')&&key!==OFFLINE_CACHE)await caches.delete(key);await self.clients.claim()})());
});
self.addEventListener('fetch',event=>{
  const request=event.request;
  const url=new URL(request.url);
  if(request.method!=='GET'||url.origin!==self.location.origin)return;
  if(OFFLINE_ASSETS.includes(url.pathname)&&!url.search){event.respondWith((async()=>{const cache=await caches.open(OFFLINE_CACHE);return (await cache.match(url.pathname))||fetch(request)})());return;}
  if(request.mode!=='navigate')return;
  event.respondWith((async()=>{try{return await fetch(request)}catch{const cache=await caches.open(OFFLINE_CACHE);return (await cache.match(OFFLINE_PAGE))||Response.error()}})());
});
