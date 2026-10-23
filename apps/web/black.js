'use strict';
(async function configureIdentity(){
 const host=document.querySelector('#provider-buttons');if(!host)return;
 const errors={unavailable:'Этот способ входа пока подключается. Сейчас можно войти по почте.',expired:'Время входа истекло. Попробуйте ещё раз.',cancelled:'Вход отменён. Можно выбрать другой способ.',provider:'Не удалось получить ответ сервиса входа. Попробуйте ещё раз.',blocked:'Этот аккаунт недоступен.',conflict:'Этот способ входа связан с другим профилем.',link_required:'Аккаунт с такой почтой уже существует. Используйте первоначальный способ входа или обратитесь в поддержку.',registration_consent_required:'Перед регистрацией через сервис входа примите Пользовательское соглашение и Политику отказа от ответственности.'};
 host.addEventListener('click',event=>{
  const link=event.target.closest('a[data-provider]');if(!link)return;
  const mode=document.querySelector('#auth')?.dataset.mode==='register'?'register':'login';
  const query=new URLSearchParams({intent:mode});
  if(mode==='register'){
   if(!document.querySelector('#legal-consent')?.checked){event.preventDefault();document.querySelector('#auth-status').textContent='Примите соглашение и предупреждение перед регистрацией.';return}
   query.set('legal_acceptance','1');query.set('legal_version','2026-10-19-registration-v1');
  }
  link.href='/api/auth/oauth/'+encodeURIComponent(link.dataset.provider)+'/start?'+query.toString();
 });
 const params=new URLSearchParams(location.search);if(params.has('auth_error')){document.querySelector('#auth-status').textContent=errors[params.get('auth_error')]||'Не удалось войти';history.replaceState({},'',location.pathname+location.hash)}
 if(params.has('reset'))document.querySelector('#email-disclosure').open=true;
 const note=document.querySelector('#provider-note');
 const email=document.querySelector('#email-disclosure');
 email.open=true;
 try{
  const data=await api('/auth/providers');
  window.SmetraEmailDeliveryAvailable=data.email_delivery_available===true;
  window.SmetraEmailSignupAvailable=data.email_signup_available!==false;
  document.dispatchEvent(new CustomEvent('smetra:email-capability'));
  const enabled=data.providers.filter(provider=>provider.enabled);
  const enabledIds=new Set(enabled.map(provider=>provider.id));
  // OAuth links are present in initial HTML; this API only filters unconfigured routes.
  host.querySelectorAll('[data-provider]').forEach(button=>{
   button.classList.toggle('hidden',!enabledIds.has(button.dataset.provider));
  });
  host.classList.toggle('single',enabled.length===1);
  if(!enabled.length){
   host.closest('.auth-provider-block')?.classList.add('hidden');
  }else{
   note.textContent='Один профиль для сайта и приложения.';
  } }catch{
  window.SmetraEmailDeliveryAvailable=false;
  document.dispatchEvent(new CustomEvent('smetra:email-capability'));
  // Keep pre-rendered OAuth links available during capability API outages.
  host.closest('.auth-provider-block')?.classList.remove('hidden');
  note.textContent='Не удалось проверить способы входа. Попробуйте открыть сервис ещё раз или войдите по почте.';
 }
})();
const proposalLabels={title:'Название',name:'Название',client:'Клиент',client_id:'Клиент',description:'Описание',amount:'Стоимость',amount_kopecks:'Сумма',price:'Цена',cost_price:'Себестоимость',currency:'Валюта',quantity:'Количество',unit_price:'Цена',items:'Работы',due_date:'Срок',status:'Статус',email:'Почта',phone:'Телефон',terms:'Условия',project_id:'Заказ',note:'Примечание'};
function proposalValue(key,value){if(['amount','amount_kopecks','price','cost_price','unit_price'].includes(key)&&typeof value==='number')return rub(value);if(key==='items'&&Array.isArray(value))return value.map(item=>`${item.name} · ${item.quantity} × ${rub(item.unit_price)}`).join('\n');return typeof value==='object'?JSON.stringify(value):String(value)}
function proposalFields(args){return Object.entries(args).filter(([key])=>!['id','revision'].includes(key)).map(([key,value])=>`<div class="proposal-field"><span>${escapeHtml(proposalLabels[key]||key)}</span><b>${escapeHtml(proposalValue(key,value))}</b></div>`).join('')}
