'use strict';
(async function configureIdentity(){
 const host=document.querySelector('#provider-buttons');if(!host)return;
 const errors={unavailable:'Этот способ входа пока подключается. Сейчас можно войти по почте.',expired:'Время входа истекло. Попробуйте ещё раз.',cancelled:'Вход отменён. Можно выбрать другой способ.',provider:'Не удалось получить ответ сервиса входа. Попробуйте ещё раз.',blocked:'Этот аккаунт недоступен.',conflict:'Этот способ входа связан с другим профилем.',link_required:'Аккаунт с такой почтой уже существует. Используйте первоначальный способ входа или обратитесь в поддержку.'};
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
  host.classList.toggle('single',enabled.length===1);
  for(const provider of enabled){
   const button=document.createElement('button');
   button.type='button';button.className='btn'+(provider.id==='yandex'?' primary':'');
   button.textContent='Продолжить с '+provider.name;
   button.onclick=()=>{location.href='/api/auth/oauth/'+encodeURIComponent(provider.id)+'/start'};
   host.append(button);
  }
  if(!enabled.length){
   host.closest('.auth-provider-block')?.classList.add('hidden');
  }else{
   note.textContent='Один профиль для сайта и приложения.';
  }
 }catch{
  window.SmetraEmailDeliveryAvailable=false;
  document.dispatchEvent(new CustomEvent('smetra:email-capability'));
  host.closest('.auth-provider-block')?.classList.add('hidden');
  document.querySelector('#auth-status').textContent='Способы входа временно не загрузились. Войдите по почте.';
 }
})();
const proposalLabels={title:'Название',name:'Название',client:'Клиент',client_id:'Клиент',description:'Описание',amount:'Стоимость',amount_kopecks:'Сумма',price:'Цена',cost_price:'Себестоимость',currency:'Валюта',quantity:'Количество',unit_price:'Цена',items:'Работы',due_date:'Срок',status:'Статус',email:'Почта',phone:'Телефон',terms:'Условия',project_id:'Заказ',note:'Примечание'};
function proposalValue(key,value){if(['amount','amount_kopecks','price','cost_price','unit_price'].includes(key)&&typeof value==='number')return rub(value);if(key==='items'&&Array.isArray(value))return value.map(item=>`${item.name} · ${item.quantity} × ${rub(item.unit_price)}`).join('\n');return typeof value==='object'?JSON.stringify(value):String(value)}
function proposalFields(args){return Object.entries(args).filter(([key])=>!['id','revision'].includes(key)).map(([key,value])=>`<div class="proposal-field"><span>${escapeHtml(proposalLabels[key]||key)}</span><b>${escapeHtml(proposalValue(key,value))}</b></div>`).join('')}
