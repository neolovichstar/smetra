'use strict';
(async function configureIdentity(){
 const host=document.querySelector('#provider-buttons');if(!host)return;
 const errors={unavailable:'Этот способ входа пока подключается. Сейчас можно войти по почте.',expired:'Время входа истекло. Попробуйте ещё раз.',cancelled:'Вход отменён. Можно выбрать другой способ.',provider:'Не удалось получить ответ сервиса входа. Попробуйте ещё раз.',blocked:'Этот аккаунт недоступен.',conflict:'Этот способ входа связан с другим профилем.',link_required:'Аккаунт с такой почтой уже существует. Войдите по почте и привяжите этот способ в настройках.'};
 const params=new URLSearchParams(location.search);if(params.has('auth_error')){document.querySelector('#auth-status').textContent=errors[params.get('auth_error')]||'Не удалось войти';history.replaceState({},'',location.pathname+location.hash)}
 if(params.has('reset'))document.querySelector('#email-disclosure').open=true;
 const note=document.querySelector('#provider-note');
 const email=document.querySelector('#email-disclosure');
 email.open=true;
 try{
  const data=await api('/auth/providers');
  const enabled=data.providers.filter(provider=>provider.enabled);
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
  host.closest('.auth-provider-block')?.classList.add('hidden');
  document.querySelector('#auth-status').textContent='Способы входа временно не загрузились. Войдите по почте.';
 }
})();
const proposalLabels={title:'Название',name:'Название',client:'Клиент',client_id:'Клиент',description:'Описание',amount:'Стоимость',amount_kopecks:'Сумма',price:'Цена',cost_price:'Себестоимость',currency:'Валюта',quantity:'Количество',unit_price:'Цена',items:'Работы',due_date:'Срок',status:'Статус',email:'Почта',phone:'Телефон',terms:'Условия',project_id:'Заказ',note:'Примечание'};
function proposalValue(key,value){if(['amount','amount_kopecks','price','cost_price','unit_price'].includes(key)&&typeof value==='number')return rub(value);if(key==='items'&&Array.isArray(value))return value.map(item=>`${item.name} · ${item.quantity} × ${rub(item.unit_price)}`).join('\n');return typeof value==='object'?JSON.stringify(value):String(value)}
function proposalFields(args){return Object.entries(args).filter(([key])=>!['id','revision'].includes(key)).map(([key,value])=>`<div class="proposal-field"><span>${escapeHtml(proposalLabels[key]||key)}</span><b>${escapeHtml(proposalValue(key,value))}</b></div>`).join('')}
window.SmetraIdentityLink=async function(){
 const host=document.querySelector('#identity-link');
 if(!host)return;
 try{
  const data=await api('/auth/providers');
  for(const provider of data.providers){
   const button=document.createElement('button');
   button.type='button';button.className='btn small';
   button.textContent=provider.enabled?'Привязать '+provider.name:provider.name+' · скоро';
   button.disabled=!provider.enabled;
   button.onclick=()=>{location.href='/api/auth/oauth/'+encodeURIComponent(provider.id)+'/start?link=1'};
   host.append(button);
  }
 }catch{host.textContent='Не удалось загрузить способы входа.'}
};
window.SmetraAssistant=async function(){
 const data=await api('/assistant');view(`<section class="assistant-page"><span class="overline"><span class="assistant-mark"></span>Сметра рядом</span><h1>Ассистент</h1><div id="assistant-messages"></div><div id="assistant-actions"></div><div class="assistant-composer"><form id="assistant-form"><textarea id="assistant-input" aria-label="Сообщение ассистенту" placeholder="Что нужно сделать?" rows="1" maxlength="6000" required></textarea><button class="btn primary" id="assistant-send">Отправить</button></form><small>Сообщение и нужные данные пространства обрабатывает OpenRouter. Изменения применяются после вашего подтверждения.</small><p class="auth-status" id="assistant-status" role="status"></p></div></section>`);
 const messages=document.querySelector('#assistant-messages'),actions=document.querySelector('#assistant-actions');
 const addMessage=(role,text)=>{const item=document.createElement('article');item.className='assistant-message '+role;const who=document.createElement('small');who.textContent=role==='user'?'ВЫ':'АССИСТЕНТ';const body=document.createElement('p');body.textContent=text;item.append(who,body);messages.append(item)};
 const addAction=action=>{const item=document.createElement('section');item.className='assistant-proposal';item.innerHTML=`<span class="overline">Предложение · ещё не сохранено</span><h3>${escapeHtml(action.summary)}</h3><div class="proposal-fields">${proposalFields(action.arguments)}</div><div class="row"><button class="btn primary" data-confirm>Применить</button><button class="btn ghost" data-dismiss>Не сейчас</button></div>`;actions.append(item);item.querySelector('[data-confirm]').onclick=async()=>{const buttons=item.querySelectorAll('button');buttons.forEach(b=>b.disabled=true);try{await api('/assistant/confirm',{method:'POST',body:JSON.stringify({id:action.id})});item.replaceChildren();const text=document.createElement('p');text.textContent='Сохранено · '+action.summary;item.append(text);notify('Изменения сохранены')}catch(error){notify(error.message);buttons.forEach(b=>b.disabled=false)}};item.querySelector('[data-dismiss]').onclick=async()=>{try{await api('/assistant/dismiss',{method:'POST',body:JSON.stringify({id:action.id})});item.remove()}catch(error){notify(error.message)}}};
 if(!data.messages.length){messages.innerHTML='<div class="assistant-welcome"><h2>Освободим время<br>для самой работы.</h2><p class="muted">Найду нужное, помогу с расчётами и подготовлю изменения.</p><div class="assistant-suggestions"><button class="btn" data-prompt="Покажи, какие сметы ждут согласования">Что ждёт согласования?</button><button class="btn" data-prompt="Помоги составить новую смету. Спроси необходимые детали.">Составить смету</button><button class="btn" data-prompt="Расскажи о поступлениях и остатках по заказам">Разобраться в оплатах</button></div></div>';messages.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>{document.querySelector('#assistant-input').value=b.dataset.prompt;document.querySelector('#assistant-input').focus()})}
 data.messages.forEach(m=>addMessage(m.role,m.content));data.actions.forEach(addAction);
 if(!data.available)document.querySelector('#assistant-status').textContent='Ассистент пока не подключён. Остальные разделы работают как обычно.';
 document.querySelector('#assistant-form').onsubmit=async event=>{event.preventDefault();const input=document.querySelector('#assistant-input'),button=document.querySelector('#assistant-send'),status=document.querySelector('#assistant-status'),text=input.value.trim();if(!text||button.disabled)return;button.disabled=true;status.textContent='Разбираюсь в задаче…';try{const answer=await api('/assistant/chat',{method:'POST',body:JSON.stringify({text})});messages.querySelector('.assistant-welcome')?.remove();addMessage('user',text);addMessage('assistant',answer.answer);answer.actions.forEach(addAction);input.value='';status.textContent=''}catch(error){status.textContent=error.message}finally{button.disabled=false}};
};
