'use strict';
(async function configureIdentity(){
 const host=document.querySelector('#provider-buttons');if(!host)return;
 const errors={unavailable:'Этот способ входа пока подключается. Сейчас можно войти по почте.',expired:'Время входа истекло. Попробуйте ещё раз.',cancelled:'Вход отменён. Можно выбрать другой способ.',provider:'Не удалось получить ответ сервиса входа. Попробуйте ещё раз.',blocked:'Этот аккаунт недоступен.',conflict:'Этот способ входа связан с другим профилем.',link_required:'Аккаунт с такой почтой уже существует. Используйте первоначальный способ входа или обратитесь в поддержку.',registration_consent_required:'Аккаунта ещё нет. Поставьте отметку «Создать аккаунт после входа» и повторите вход.'};
 host.addEventListener('click',event=>{
  const link=event.target.closest('a[data-provider]');if(!link)return;
  const mode=document.querySelector('#auth')?.dataset.mode==='register'?'register':'login';
  const consent=mode==='register'
   ?document.querySelector('#legal-consent')?.checked===true
   :document.querySelector('#oauth-first-signin-consent')?.checked===true;
  if(mode==='register'&&!consent){
   event.preventDefault();document.querySelector('#auth-status').textContent='Примите условия перед регистрацией.';return;
  }
  const args={provider:link.dataset.provider,intent:mode,legal_acceptance:consent,legal_version:consent?'2026-10-19-registration-v1':''};
  const query=new URLSearchParams({intent:mode});
  if(consent){query.set('legal_acceptance','1');query.set('legal_version',args.legal_version)}
  const url='/api/auth/oauth/'+encodeURIComponent(args.provider)+'/start?'+query.toString();
  link.href=url;
  // The embedded WebView is not a trusted OAuth user-agent. Android's
  // browser Custom Tab is displayed over the app and returns via deep link.
  if(window.SmetraShell?.available){
   event.preventDefault();
   void window.SmetraShell.call('auth.start',args,{timeout:15000}).catch(error=>{
    document.body.classList.remove('smetra-app-transitioning');
    delete document.body.dataset.appState;
    document.querySelector('#auth-status').textContent=error.message||'Не удалось открыть вход';
   });
  }
  document.body.classList.add('smetra-app-transitioning');
  document.body.dataset.appState='authorizing';
  const label=document.querySelector('#app-startup-label');
  if(label)label.textContent='Открываем защищённый вход '+(args.provider==='google'?'Google':'Яндекс ID')+'…';
 });
 document.addEventListener('smetra:auth-method',()=>{
  const label=document.querySelector('#oauth-first-signin-label');
  if(label)label.hidden=document.querySelector('#auth')?.dataset.mode==='register';
 });
 const params=new URLSearchParams(location.search);document.body.classList.toggle('auth-password-reset',params.has('reset'));if(params.has('auth_error')){document.querySelector('#auth-status').textContent=errors[params.get('auth_error')]||'Не удалось войти';history.replaceState({},'',location.pathname+location.hash)}
 const note=document.querySelector('#provider-note');
 try{
  const data=await api('/auth/providers');
  window.SmetraEmailDeliveryAvailable=data.email_delivery_available===true;
  window.SmetraEmailCodeAvailable=data.email_code_available===true;
  window.SmetraEmailSignupAvailable=data.email_signup_available!==false;
  document.dispatchEvent(new CustomEvent('smetra:email-capability'));
  const enabled=data.providers.filter(provider=>provider.enabled&&['yandex','google'].includes(provider.id));
  const enabledIds=new Set(enabled.map(provider=>provider.id));
  // OAuth links are present in initial HTML; this API only filters unconfigured routes.
  host.querySelectorAll('[data-provider]').forEach(button=>{
   button.classList.toggle('hidden',!enabledIds.has(button.dataset.provider));
  });
  host.classList.toggle('single',enabled.length===1);
 const firstLoginLabel=document.querySelector('#oauth-first-signin-label');if(firstLoginLabel)firstLoginLabel.hidden=document.querySelector('#auth')?.dataset.mode==='register';
  if(!enabled.length){
   host.closest('.auth-provider-block')?.classList.add('hidden');
   document.querySelector('#auth-status').textContent='Вход через сервисы временно недоступен. Обратитесь в поддержку.';
  }else{
   note.textContent='Один профиль для сайта и приложения.';
  } }catch{
  window.SmetraEmailDeliveryAvailable=false;
  window.SmetraEmailCodeAvailable=false;
  document.dispatchEvent(new CustomEvent('smetra:email-capability'));
  // Keep pre-rendered OAuth links available during capability API outages.
  host.closest('.auth-provider-block')?.classList.remove('hidden');
  note.textContent='Не удалось проверить подключение сервисов. Если вход не откроется, попробуйте позднее.';
 }
})();
const proposalLabels={title:'Название',name:'Название',client:'Клиент',client_id:'Клиент',description:'Описание',amount:'Стоимость',amount_kopecks:'Сумма',price:'Цена',cost_price:'Себестоимость',currency:'Валюта',quantity:'Количество',unit_price:'Цена',items:'Работы',due_date:'Срок',status:'Статус',email:'Почта',phone:'Телефон',terms:'Условия',project_id:'Заказ',note:'Примечание'};
function proposalValue(key,value){if(['amount','amount_kopecks','price','cost_price','unit_price'].includes(key)&&typeof value==='number')return rub(value);if(key==='items'&&Array.isArray(value))return value.map(item=>`${item.name} · ${item.quantity} × ${rub(item.unit_price)}`).join('\n');return typeof value==='object'?JSON.stringify(value):String(value)}
function proposalFields(args){return Object.entries(args).filter(([key])=>!['id','revision'].includes(key)).map(([key,value])=>`<div class="proposal-field"><span>${escapeHtml(proposalLabels[key]||key)}</span><b>${escapeHtml(proposalValue(key,value))}</b></div>`).join('')}
