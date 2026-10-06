const OFFLINE_CACHE='smetra-public-offline-v1';
const OFFLINE_PAGE='/offline.html';
self.addEventListener('install',event=>{
  event.waitUntil((async()=>{const cache=await caches.open(OFFLINE_CACHE);await cache.addAll([OFFLINE_PAGE,'/offline.css'].map(url=>new Request(url,{cache:'reload'})));await self.skipWaiting()})());
});
self.addEventListener('activate',event=>{
  event.waitUntil((async()=>{for(const key of await caches.keys())if(key.startsWith('smetra-public-offline-')&&key!==OFFLINE_CACHE)await caches.delete(key);await self.clients.claim()})());
});
self.addEventListener('fetch',event=>{
  const request=event.request;
  const url=new URL(request.url);
  if(request.method!=='GET'||url.origin!==self.location.origin)return;
  if(url.pathname==='/offline.css'&&!url.search){event.respondWith((async()=>{const cache=await caches.open(OFFLINE_CACHE);return (await cache.match('/offline.css'))||fetch(request)})());return;}
  if(request.mode!=='navigate')return;
  event.respondWith((async()=>{try{return await fetch(request)}catch{const cache=await caches.open(OFFLINE_CACHE);return (await cache.match(OFFLINE_PAGE))||Response.error()}})());
});
