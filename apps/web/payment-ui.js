/* Purchase presentation. Only authenticated API payment records decide an outcome. */
(() => {
 const e=escapeHtml,requests=new Map();let opened=null;
 const revision=()=>typeof authRevision==='number'?authRevision:0;
 const storage={get:key=>{try{return sessionStorage.getItem(key)}catch{return null}},set:(key,value)=>{try{sessionStorage.setItem(key,value)}catch{}}};
 const valid=(owner,rev)=>user?.id===owner.id&&revision()===rev;
 function modal({owner,rev,title,body,kind='offer',action,label,alive=()=>true}){
  if(!valid(owner,rev)||!alive())return;
  opened?.();const previous=document.activeElement,dialog=document.createElement('dialog');
  dialog.className='payment-dialog payment-dialog--'+kind;
  dialog.setAttribute('aria-labelledby','payment-dialog-title');dialog.setAttribute('aria-describedby','payment-dialog-description');
  const mark=kind==='success'?'<circle cx="40" cy="40" r="30"/><path class="payment-stroke" d="m26 40 10 10 19-21"/>':kind==='failure'?'<circle cx="40" cy="40" r="30"/><path class="payment-stroke" d="m30 30 20 20m0-20-20 20"/>':kind==='waiting'?'<circle cx="40" cy="40" r="30"/><path d="M40 23v18l11 7"/>':'<path d="M24 17h24l13 13v34H24zM47 17v15h14M33 43h18M33 52h12"/>';
  dialog.innerHTML='<button class="payment-close icon-button" type="button" aria-label="Закрыть">×</button><div class="payment-emblem" aria-hidden="true"><svg viewBox="0 0 80 80" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">'+mark+'</svg></div><div class="payment-dialog-content"><span class="overline">'+(kind==='offer'?'СМЕТРА PRO':'СТАТУС ОПЛАТЫ')+'</span><h2 id="payment-dialog-title">'+e(title)+'</h2>'+body+'<button class="btn primary payment-action" type="button">'+e(label)+'</button>'+(kind==='offer'?'<button class="payment-later" type="button">Пока остаться на Старт</button>':'')+'</div>';
  let closed=false;const cleanup=()=>{if(closed)return;closed=true;observer.disconnect();document.removeEventListener('smetra:auth-reset',close);dialog.remove();document.documentElement.classList.remove('payment-dialog-open');if(opened===close)opened=null;if(previous?.isConnected&&valid(owner,rev))previous.focus()};
  const close=()=>{if(dialog.open&&typeof dialog.close==='function')dialog.close();cleanup()};
  const observer=new MutationObserver(()=>{if(!valid(owner,rev)||!alive())close()});
  dialog.querySelector('.payment-close').onclick=close;dialog.querySelector('.payment-later')?.addEventListener('click',close);
  dialog.querySelector('.payment-action').onclick=()=>{if(!valid(owner,rev)||!alive()){close();return}close();action?.()};
  dialog.addEventListener('click',event=>{if(event.target===dialog)close()});dialog.addEventListener('close',cleanup);dialog.addEventListener('cancel',()=>queueMicrotask(cleanup));
  document.body.append(dialog);opened=close;document.documentElement.classList.add('payment-dialog-open');
  document.addEventListener('smetra:auth-reset',close,{once:true});
  observer.observe(document.querySelector('#content')||document.body,{childList:true,subtree:true});
  if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');
  dialog.querySelector('.payment-action').focus();return dialog;
 }
 async function paywall(source,onChoose){
  const owner=user,rev=revision(),place=tab;if(!owner)return;
  let billing=null;try{billing=await api('/billing')}catch{}
  if(!valid(owner,rev)||tab!==place)return;
  const option=billing?.pricing?.plans?.pro_month,price=option&&Number.isSafeInteger(option.amount_kopecks)?rub(option.amount_kopecks):null;
  const details=source==='ai_limit'?['Больше помощи ассистента','Выберите тариф с большим лимитом ИИ или пополните токены отдельно.']:['Больше места для вашей работы','Продолжайте создавать сметы и отправляйте клиентам документы с вашим оформлением.'];
  return modal({owner,rev,title:details[0],alive:()=>tab===place,body:'<p id="payment-dialog-description">'+details[1]+'</p><ul class="payment-benefits"><li>Безлимитные сметы</li><li>PDF и Excel без отметки Сметры</li><li>Ассистент и рабочие файлы в одном месте</li></ul>'+(price?'<div class="paywall-price"><strong>'+e(price)+'</strong><span>за 31 день</span></div>':'')+'<p class="payment-fine">Разовая оплата. Без автоматического продления.<br>Ваши документы и черновик сохранятся.</p>',label:'Посмотреть тарифы',action:onChoose});
 }
 function remember(owner,result){if(typeof result.payment_id==='string')storage.set('smetra.payment.target.'+owner.id,JSON.stringify({id:result.payment_id,time:Date.now()}))}
 function target(owner){try{const value=JSON.parse(storage.get('smetra.payment.target.'+owner.id));return value&&Date.now()-value.time<86400000&&typeof value.id==='string'?value.id:null}catch{return null}}
 function sync(owner,rev){
  const key=owner.id+':'+rev;if(requests.has(key))return requests.get(key);
  const task=api('/billing/sync',{method:'POST'});requests.set(key,task);task.finally(()=>{if(requests.get(key)===task)requests.delete(key)}).catch(()=>{});return task;
 }
 function consumeReturn(){const url=new URL(location.href);if(!url.searchParams.has('payment'))return false;url.searchParams.delete('payment');history.replaceState(history.state,'',url.pathname+url.search+url.hash);return true}
 function outcome(owner,rev,result,{before=[],manual=false,retry}={}){
  if(!valid(owner,rev)||tab!=='billing')return;
  const id=target(owner)||before.find(payment=>payment.status==='pending')?.id;
  const payment=id&&result.payments?.find(payment=>payment.id===id);
  const state=payment?.status==='succeeded'?'success':payment?.status==='canceled'?'failure':payment?.status==='refunded'?'refund':'waiting';
  if(state!=='waiting'){
   const key='smetra.payment.shown.'+owner.id+'.'+payment.id+'.'+payment.status;if(storage.get(key))return;
   storage.set(key,'1');
  }else if(!manual)return;
  const copy=state==='success'?['Оплата прошла','Спасибо! Покупка подтверждена, доступ и баланс обновлены. Можно продолжать работу.','Продолжить работу']:state==='failure'?['Оплата не завершена','Платёж отменён. Новая попытка доступна в тарифах, а статус этой оплаты сохранён в истории.','Вернуться к тарифам']:state==='refund'?['Возврат подтверждён','Сервер подтвердил возврат этой оплаты. Подробности доступны в истории платежей.','Вернуться к тарифам']:['Ждём подтверждение','Платёж пока не подтверждён. Если вы уже оплатили, подождите немного и проверьте статус ещё раз.','Проверить ещё раз'];
  return modal({owner,rev,kind:state,title:copy[0],body:'<p id="payment-dialog-description">'+copy[1]+'</p>',label:copy[2],alive:()=>tab==='billing',action:state==='waiting'?retry:state==='success'?()=>{tab=storage.get('smetra.checkout.return.'+owner.id)||'assistant';if(!['assistant','dashboard','quotes','projects','documents','files'].includes(tab))tab='assistant';location.hash=tab;render()}:()=>document.querySelector('#plan-cards,#upgrade-checkout')?.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'})});
 }
 window.SmetraPaymentUI={paywall,remember,target,sync,outcome,consumeReturn,close:()=>opened?.()};
})();
