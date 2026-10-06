/* Only the public offline notice is cached; accounts and API replies stay online. */
if('serviceWorker' in navigator&&window.isSecureContext){
  window.addEventListener('load',()=>{navigator.serviceWorker.register('/service-worker.js',{scope:'/',updateViaCache:'none'}).catch(()=>{});},{once:true});
}
