(() => {
'use strict';
const $ = (s,r=document)=>r.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = v => new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:2}).format(Number(v||0)/100);
const num = v => new Intl.NumberFormat('ru-RU').format(Number(v||0));
const time = v => v ? new Intl.DateTimeFormat('ru-RU',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}).format(new Date(Number(v)*1000)) : '';
const state = {open:false,tab:'direct',current:null,messages:[],chats:[],channels:[],workspaces:[],role:'user',userId:'',publicId:'',mode:'user',busy:false,poll:null,observer:null,adminLoading:false,lastWaitingHuman:null};
let sessionEpoch=0;
const tabs = [['direct','Личные'],['object','Объекты'],['community','Сообщество'],['support','Поддержка']];
const ico = {
 chat:'<path d="M21 11.5a8.5 8.5 0 0 1-12.9 7.3L3 20l1.2-4.1A8.5 8.5 0 1 1 21 11.5Z"/>',
 copy:'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
 users:'<path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M20 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
 send:'<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
 plus:'<path d="M12 5v14M5 12h14"/>',
 close:'<path d="m18 6-12 12M6 6l12 12"/>',
 support:'<path d="M4 13v-2a8 8 0 0 1 16 0v2"/><path d="M4 13a2 2 0 0 0-2 2v2a2 2 0 0 0 2 2h2v-6Zm16 0a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-2v-6Z"/>',
 search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>'
};
const icon = n => '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+(ico[n]||ico.chat)+'</svg>';
async function api(path,options={}) {
 const epoch=sessionEpoch;
 const response=await fetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
 let data={};try{data=await response.json()}catch{}
 if(epoch!==sessionEpoch)throw new Error('Сессия изменилась');
 if(!response.ok)throw new Error(data.error||'Не удалось выполнить действие');
 return data;
}
function notify(message){const e=$('#toast');if(e){e.textContent=message;e.classList.remove('hidden');setTimeout(()=>e.classList.add('hidden'),3500)}else alert(message)}
function style(){
 if(document.querySelector('link[data-comms-style]'))return;
 const link=document.createElement('link');link.rel='stylesheet';link.href='/communication-center.css?v=20261024-layout-v2';link.dataset.commsStyle='1';document.head.append(link);
}
function mount(){
 style();if($('#communication-center'))return;
 const shell=document.createElement('div');shell.id='communication-center';shell.className='comms-shell';shell.setAttribute('aria-hidden','true');
 shell.innerHTML='<section class="comms-window" role="dialog" aria-modal="true" aria-labelledby="comms-heading"><header class="comms-top"><div class="comms-brand"><div class="comms-brand-mark">'+icon('chat')+'</div><div><div class="comms-eyebrow">сметра. / связь</div><h2 class="comms-title" id="comms-heading">Центр общения</h2></div></div><div class="comms-top-actions"><div class="comms-my-id" id="comms-my-id"><span>Ваш ID</span><code>Загрузка…</code><button class="comms-btn" type="button" data-copy-id aria-label="Скопировать ID">'+icon('copy')+'</button></div><button class="comms-btn" type="button" data-close aria-label="Закрыть">'+icon('close')+'</button></div></header><div class="comms-body"><aside class="comms-sidebar"><nav class="comms-tabs" aria-label="Типы общения">'+tabs.map(t=>'<button type="button" class="comms-tab" data-tab="'+t[0]+'">'+icon(t[0]==='support'?'support':t[0]==='object'?'users':'chat')+'<span>'+t[1]+'</span></button>').join('')+'</nav><div class="comms-tools" id="comms-tools"></div><div class="comms-list" id="comms-list"></div></aside><section class="comms-main"><header class="comms-conversation-head" id="comms-conversation-head"><div class="comms-avatar">'+icon('chat')+'</div><div><h3 class="comms-name">Выберите переписку</h3><div class="comms-sub">Рабочие обсуждения в одном месте</div></div></header><div class="comms-messages" id="comms-messages"><div class="comms-empty"><div class="comms-empty-icon">'+icon('chat')+'</div><h3>Рабочие разговоры рядом</h3><p>Выберите чат слева или начните новую переписку.</p></div></div><div class="comms-compose-wrap" id="comms-compose-wrap"><form class="comms-compose" id="comms-compose"><textarea id="comms-message" rows="1" maxlength="4000" placeholder="Написать сообщение…" aria-label="Текст сообщения" disabled></textarea><button class="comms-btn primary" type="submit" aria-label="Отправить" disabled>'+icon('send')+'</button></form></div></section></div></section>';
 document.body.append(shell);
 shell.addEventListener('click',e=>{if(e.target===shell||e.target.closest('[data-close]'))close()});
 shell.querySelectorAll('[data-tab]').forEach(b=>b.onclick=async()=>{state.tab=b.dataset.tab;state.current=null;state.messages=[];await refresh(true)});
 $('#comms-tools').addEventListener('submit',async e=>{e.preventDefault();if(e.target.id==='comms-direct-form')await findPerson();if(e.target.id==='comms-object-form')await createObjectChat();if(e.target.id==='comms-quote-form')await createQuoteChat()});
 $('#comms-tools').addEventListener('click',async e=>{const b=e.target.closest('[data-new-ticket],[data-handoff],[data-join]');if(!b)return;if(b.hasAttribute('data-new-ticket'))await newTicket();if(b.hasAttribute('data-handoff'))await handoff();if(b.hasAttribute('data-join'))await joinCommunity(b.dataset.join)});
 $('#comms-list').addEventListener('click',e=>{const b=e.target.closest('[data-conv]');if(b)select(b.dataset.conv)});
 $('#comms-compose').onsubmit=sendMessage;
 shell.querySelector('[data-copy-id]').onclick=async()=>{try{await navigator.clipboard.writeText(state.publicId);notify('ID скопирован')}catch{notify('Ваш ID: '+state.publicId)}};
 shell.addEventListener('keydown',e=>{if(e.key==='Escape'&&state.open)close()});
}
async function open(tab='direct'){
 mount();state.open=true;state.tab=tabs.some(t=>t[0]===tab)?tab:'direct';
 $('#communication-center').classList.add('is-open');$('#communication-center').setAttribute('aria-hidden','false');document.body.classList.add('comms-scroll-locked');
 clearInterval(state.poll);await refresh(true);
 let lastRefresh=Date.now();state.poll=setInterval(async()=>{if(state.open&&!state.busy&&!document.hidden){if(Date.now()-lastRefresh>=30000){await refresh(false);lastRefresh=Date.now()}if(state.current)await loadMessages(false)}},8000);
 $('#communication-center [data-close]')?.focus();
}
function close(){state.open=false;clearInterval(state.poll);state.poll=null;const el=$('#communication-center');if(el){el.classList.remove('is-open');el.setAttribute('aria-hidden','true')}document.body.classList.remove('comms-scroll-locked')}
function renderTools(){
 const el=$('#comms-tools');if(!el)return;
 if(state.tab==='direct')el.innerHTML='<form class="comms-form" id="comms-direct-form"><label for="comms-id">Найти человека по ID</label><input id="comms-id" maxlength="40" placeholder="SM-…" required><button class="comms-btn" type="submit">'+icon('search')+' Найти пользователя</button><p class="comms-note">Точный поиск по публичному ID. Почта и закрытые данные не раскрываются.</p><div id="comms-found"></div></form><details class="comms-quote-details"><summary>Создать чат по смете</summary><form class="comms-form" id="comms-quote-form"><label for="comms-quote-id">Обсуждение по смете</label><input id="comms-quote-id" maxlength="80" placeholder="ID сметы" required><label for="comms-quote-client">Публичный ID клиента</label><input id="comms-quote-client" maxlength="40" placeholder="SM-…" required><button class="comms-btn" type="submit">Создать чат сметы</button><p class="comms-note">Чат будет закреплён за точным ID сметы и доступен участникам.</p></form></details>';
 else if(state.tab==='object'){
 const enabled=state.workspaces.filter(w=>w.enabled);
 el.innerHTML=enabled.length?'<form class="comms-form" id="comms-object-form"><label for="comms-workspace">Рабочее пространство TEAM</label><select id="comms-workspace">'+enabled.map(w=>'<option value="'+esc(w.id)+'">'+esc(w.name)+'</option>').join('')+'</select><label for="comms-object-name">Название объекта или бригады</label><input id="comms-object-name" maxlength="120" placeholder="Например, ЖК Октябрьский"><button class="comms-btn" type="submit">'+icon('plus')+' Создать чат объекта</button><p class="comms-note">Участники добавятся из списка команды.</p></form>':'<div class="comms-form"><p class="comms-note">Объектные чаты доступны рабочим пространствам с активным тарифом TEAM / Компания.</p></div>';
 }else if(state.tab==='community')el.innerHTML='<div class="comms-form"><label>Сообщество мастеров СНГ</label><p class="comms-note">Открытые профессиональные каналы: обсуждайте работу, обменивайтесь опытом, не публикуйте данные клиентов.</p></div>';
 else el.innerHTML=state.mode==='admin'?'<div class="comms-form"><label>Очередь команды поддержки</label><p class="comms-note">Сначала обращения, которым требуется человек.</p><button class="comms-btn" data-handoff type="button">Обновить очередь</button></div>':'<div class="comms-form"><label>Поддержка Сметры</label><p class="comms-note">Бесплатный ИИ-помощник. Сложный вопрос или просьба о сотруднике попадёт в очередь.</p><button class="comms-btn" data-new-ticket type="button">'+icon('plus')+' Новое обращение</button></div>';
}
function renderList(){
 const el=$('#comms-list');if(!el)return;
 const rows=state.tab==='community'?state.channels:state.chats;
 if(!rows.length){el.innerHTML='<div class="comms-empty comms-empty-list"><div class="comms-empty-icon">'+icon(state.tab==='support'?'support':'chat')+'</div><h3>Пока пусто</h3><p>'+(state.tab==='direct'?'Найдите человека по публичному ID.':state.tab==='object'?'Создайте чат объекта в TEAM.':state.tab==='community'?'Каналы появятся после загрузки.':'Создайте новое обращение.')+'</p></div>';return}
 el.innerHTML=rows.map(row=>{
 const title=(row.kind==='direct'&&row.partner_name)||row.subject||row.partner_name||row.label||row.name||'Переписка',id=row.id;
 const preview=row.last_message|| (row.needs_human?'Ожидает сотрудника':row.kind==='community'?'Профессиональный канал':'Открыть переписку');
 return '<button type="button" class="comms-row '+(state.current&&state.current.id===id?'active':'')+'" data-conv="'+esc(id)+'"><span class="comms-avatar">'+esc(title.slice(0,1).toUpperCase())+'</span><span class="comms-copy"><span class="comms-label">'+esc(title)+'</span><span class="comms-preview">'+esc(preview)+'</span></span><span class="comms-time">'+esc(time(row.last_message_at||row.updated_at||row.created_at))+'</span>'+(row.needs_human?'<i class="comms-human-needed" aria-label="Требуется сотрудник"></i>':'')+'</button>';
 }).join('');
}
function renderMessages(){
 const el=$('#comms-messages'),head=$('#comms-conversation-head'),compose=$('#comms-compose-wrap'),box=$('#comms-message'),send=$('#comms-compose button[type="submit"]');
 if(!state.current){el.innerHTML='<div class="comms-empty"><div class="comms-empty-icon">'+icon('chat')+'</div><h3>Вся рабочая переписка здесь</h3><p>Сметы, объекты и обращения собраны в одном месте.</p></div>';head.innerHTML='<div class="comms-avatar">'+icon('chat')+'</div><div><h3 class="comms-name">Центр общения</h3><div class="comms-sub">Выберите или создайте переписку</div></div>';box.disabled=true;send.disabled=true;compose.querySelector('.comms-banner')?.remove();return}
 const c=state.current;
 const subtitle=c.kind==='estimate'?'Обсуждение привязано к смете '+c.quote_id:c.kind==='object'?'Команда рабочего пространства':c.kind==='community'?'Открытый профессиональный канал':state.tab==='support'&&state.mode==='admin'?'Обращение пользователя':state.tab==='support'?'Бесплатный ИИ-помощник поддержки':(c.partner_public_id?'Публичный ID '+c.partner_public_id:'Личная переписка');
 head.innerHTML='<div class="comms-avatar">'+icon(c.kind==='support'?'support':c.kind==='object'?'users':'chat')+'</div><div class="comms-head-copy"><h3 class="comms-name">'+esc(c.subject||c.partner_name||c.label||'Переписка')+'</h3><div class="comms-sub">'+esc(subtitle)+'</div></div><span class="comms-status">'+(c.status==='closed'?'Закрыт':c.needs_human?'Нужен сотрудник':'Доступ открыт')+'</span>';
 if(state.tab==='support'&&c.needs_human){if(!compose.querySelector('.comms-banner')){const n=document.createElement('div');n.className='comms-banner';n.textContent='Обращение передано сотруднику. История останется здесь.';compose.prepend(n)}}else compose.querySelector('.comms-banner')?.remove();
 box.disabled=c.status==='closed'||(state.tab==='support'&&c.needs_human&&state.mode==='user');box.placeholder=box.disabled?'Ожидайте ответа сотрудника…':'Написать сообщение…';send.disabled=box.disabled||state.busy;
 if(!state.messages.length)el.innerHTML='<div class="comms-empty"><div class="comms-empty-icon">'+icon('chat')+'</div><h3>Начните разговор</h3><p>История сохранится в этой переписке.</p></div>';
 else el.innerHTML=state.messages.map(m=>{
 const mine=m.sender_id&&m.sender_id===state.userId;
 const author=m.sender_type==='assistant'?'ИИ поддержки':m.sender_type==='admin'?'Сотрудник поддержки':m.sender_type==='system'?'Система':mine?'Вы':(c.partner_name||'Участник');
 return '<article class="comms-message '+(mine?'mine ':'')+(m.sender_type==='system'?'system':'')+'"><span class="comms-author">'+esc(author)+'</span><p>'+esc(m.body)+'</p><time>'+esc(time(m.created_at))+'</time></article>';
 }).join('');
 if(state.tab==='support'&&state.mode==='user'&&!c.needs_human&&c.status!=='closed'){
 if(!compose.querySelector('[data-call-staff]')){const b=document.createElement('button');b.type='button';b.className='comms-btn';b.dataset.callStaff='1';b.textContent='Позвать сотрудника';b.classList.add('comms-staff-action');b.onclick=handoff;compose.prepend(b)}
 }else compose.querySelector('[data-call-staff]')?.remove();
 el.scrollTop=el.scrollHeight;
}
async function refresh(reset){
 if(state.busy)return;state.busy=true;
 try{
 const me=await api('/profile/id');state.userId=me.id;state.role=me.role||'user';state.publicId=me.public_id||'';state.mode=state.tab==='support'&&state.role==='admin'?'admin':'user';
 $('#comms-my-id code').textContent=state.publicId||'не задан';
 document.querySelectorAll('#communication-center [data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===state.tab));
 if(state.tab==='direct'){const d=await api('/profile/chats');state.chats=d.chats||[];state.channels=[]}
 else if(state.tab==='object'){const d=await api('/profile/object-chats');state.chats=d.chats||[];state.workspaces=d.workspaces||[];state.channels=[]}
 else if(state.tab==='community'){const d=await api('/profile/communities');state.channels=(d.channels||[]).map(c=>({...c,subject:c.label,kind:'community'}));state.chats=[]}
 else if(state.mode==='admin'){const d=await api('/admin/communication/threads');state.chats=d.threads||[];state.channels=[]}
 else{const d=await api('/support/threads');state.chats=d.threads||[];state.channels=[]}
 renderTools();renderList();
 if(reset){const rows=state.tab==='community'?state.channels:state.chats;state.current=rows.find(x=>state.current&&x.id===state.current.id)||null;state.messages=[];renderMessages();if(!state.current&&rows.length&&state.tab==='community'){state.current=rows[0];await loadMessages(true)}}
 else if(state.current){const rows=state.tab==='community'?state.channels:state.chats;const newer=rows.find(x=>x.id===state.current.id);if(newer)state.current=newer;renderList();renderMessages()}
 }catch(error){if($('#comms-list'))$('#comms-list').innerHTML='<div class="comms-error">'+esc(error.message)+'</div>'}
 finally{state.busy=false}
}
async function select(id){const rows=state.tab==='community'?state.channels:state.chats;state.current=rows.find(x=>x.id===id)||null;state.messages=[];renderList();renderMessages();await loadMessages(true)}
async function loadMessages(force){
 if(!state.current)return;const c=state.current;let path;
 if(state.tab==='support'&&state.mode==='admin')path='/admin/communication/threads/'+encodeURIComponent(c.id)+'/messages';
 else if(state.tab==='support')path='/support/threads/'+encodeURIComponent(c.id)+'/messages';
 else path='/profile/chats/'+encodeURIComponent(c.id)+'/messages';
 try{const after=force?0:Math.max(0,state.messages.reduce((v,m)=>Math.max(v,Number(m.created_at||0)),0)-1);const data=await api(path+(after?'?after='+after:''));const incoming=data.messages||[];if(!state.current||state.current.id!==c.id)return;if(force)state.messages=incoming;else{const seen=new Set(state.messages.map(m=>m.id));state.messages.push(...incoming.filter(m=>!seen.has(m.id)))}if(state.current&&state.current.id===c.id)renderMessages()}catch(error){if(force)$('#comms-messages').innerHTML='<div class="comms-error">'+esc(error.message)+'</div>'}
}
async function sendMessage(e){
 e.preventDefault();if(!state.current||state.busy)return;const box=$('#comms-message'),message=box.value.trim();if(!message)return;
 state.busy=true;$('#comms-compose button').disabled=true;
 try{const id=encodeURIComponent(state.current.id);
 let path='/profile/chats/'+id+'/messages';
 if(state.tab==='support'&&state.mode==='admin')path='/admin/communication/threads/'+id+'/messages';
 else if(state.tab==='support')path='/support/threads/'+id+'/messages';
 await api(path,{method:'POST',body:JSON.stringify({message})});box.value='';await loadMessages(true);await refresh(false)
 }catch(error){notify(error.message)}finally{state.busy=false;renderMessages()}
}
async function findPerson(){
 const value=$('#comms-id')?.value.trim();const out=$('#comms-found');if(!value||!out)return;out.textContent='Ищем…';
 try{const d=await api('/profile/directory?q='+encodeURIComponent(value));const p=d.user;out.innerHTML='<div class="comms-found-person">'+esc(p.name)+' <code class="comms-found-id">'+esc(p.public_id)+'</code> <button class="comms-btn" type="button" id="comms-start-chat">Написать</button></div>';$('#comms-start-chat').onclick=async()=>{try{const x=await api('/profile/chats',{method:'POST',body:JSON.stringify({public_id:p.public_id})});state.tab='direct';state.current=null;await refresh(true);await select(x.chat.id)}catch(error){notify(error.message)}}
 }catch(error){out.innerHTML='<div class="comms-error">'+esc(error.message)+'</div>'}
}
async function createQuoteChat(){
 const quote_id=$('#comms-quote-id')?.value.trim(),public_id=$('#comms-quote-client')?.value.trim();
 if(!quote_id||!public_id)return;
 try{const d=await api('/profile/quote-chats',{method:'POST',body:JSON.stringify({quote_id,public_id})});await refresh(true);await select(d.chat.id);notify('Чат привязан к смете')}catch(error){notify(error.message)}
}
async function createObjectChat(){
 const workspace=$('#comms-workspace')?.value;if(!workspace){notify('Нет активного пространства TEAM');return}
 const subject=$('#comms-object-name')?.value.trim()||'Рабочий чат объекта';
 try{const d=await api('/profile/object-chats',{method:'POST',body:JSON.stringify({workspace_id:workspace,subject})});state.tab='object';state.current=null;await refresh(true);await select(d.chat.id);notify('Чат объекта создан')}catch(error){notify(error.message)}
}
async function joinCommunity(category){
 try{const d=await api('/profile/communities',{method:'POST',body:JSON.stringify({category})});await refresh(true);await select(d.chat.id)}catch(error){notify(error.message)}
}
async function newTicket(){
 const subject=prompt('Тема обращения','Новый вопрос в поддержку');if(subject===null)return;
 try{const d=await api('/support/threads',{method:'POST',body:JSON.stringify({subject:subject.trim()||'Новый вопрос'})});await refresh(true);await select(d.thread.id)}catch(error){notify(error.message)}
}
async function handoff(){
 if(!state.current)return;
 try{if(state.mode==='admin'){await refresh(true);return}
 await api('/support/threads/'+encodeURIComponent(state.current.id)+'/handoff',{method:'POST',body:JSON.stringify({reason:'user_requested_human'})});notify('Запрос передан сотруднику');await refresh(false);await loadMessages(true)
 }catch(error){notify(error.message)}
}
function addTrigger(){
 // Chat entry point belongs in the workspace sidebar, not the mobile top bar.
 // Keeping the top bar untouched preserves the validated mobile layout.
 const support=$('#sidebar [data-tab="support"]');
 if(support&&!$('#sidebar-open-comms')){
  const b=document.createElement('button');b.id='sidebar-open-comms';b.type='button';b.className='comms-sidebar-trigger';
  b.innerHTML=icon('chat')+'<span class="sidebar-item-label">Чаты и сообщения</span>';
  b.querySelector('svg')?.classList.add('sidebar-item-icon');b.setAttribute('aria-label','Открыть чаты и сообщения');
  b.addEventListener('click',()=>open('direct'));
  support.insertAdjacentElement('afterend',b);
 }
}
function supportPage(){
 const content=$('#content');
 if(!content||content.dataset.section!=='support')return;
 // Retain the existing support page markup/topics so older web and Android
 // navigation flows keep their selectors and history behavior.
 const form=content.querySelector('#support-form');
 if(!form||state.supportForm===form)return;
 state.supportForm=form;
 const guide=content.querySelector('.support-guide');
 const actions=guide||form.parentElement||content;
 if(!actions.querySelector('[data-comms-open-support]')){
  const button=document.createElement('button');
  button.type='button';button.className='comms-btn';button.dataset.commsOpenSupport='1';
  button.textContent='Открыть историю обращений';
  button.classList.add('comms-support-launch');button.onclick=()=>open('support');
  const topics=actions.querySelector('.support-topics');
  if(topics)topics.insertAdjacentElement('afterend',button);else actions.append(button);
 }
 const panel=content.querySelector('.support-panel')||form.parentElement;
 if(panel&&!panel.querySelector('[data-comms-support-note]')){
  const note=document.createElement('p');note.dataset.commsSupportNote='1';note.className='comms-note';
  note.classList.add('comms-support-note');
  note.textContent='Бесплатный ИИ поддержки отвечает в чате. Если он не справится или вы позовёте сотрудника, обращение попадёт в очередь команды, а история сохранится.';
  panel.insertBefore(note,form);
 }
 form.onsubmit=async event=>{
  event.preventDefault();
  const button=form.querySelector('[type=submit],button:not([type])');
  const input=form.querySelector('#message');
  const message=input?.value.trim();
  if(!message||!button||button.disabled)return;
  button.disabled=true;
  try{
   const data=await api('/support',{method:'POST',body:JSON.stringify({message})});
   if(input.value.trim()===message)input.value='';
   await open('support');
   await select(data.ticket_id);
   notify(data.needs_human?'Обращение передано в очередь поддержки':'Ответ поддержки получен');
  }catch(error){notify(error.message)}
  finally{if(button.isConnected)button.disabled=false}
 };
}
async function adminPage(){
 const content=$('#content');if(!content||content.dataset.section!=='admin')return;
 if(state.adminLoading)return;
 state.adminLoading=true;
 try{
  const profile=await api('/profile/id');
  state.role=profile.role||'user';
 }catch(error){state.adminLoading=false;return}
 if(state.role!=='admin'){state.adminLoading=false;return}
 const base=content.querySelector('.admin-metrics');if(!base){state.adminLoading=false;return}
 let panel=content.querySelector('[data-comms-admin-overview]');
 if(!panel){panel=document.createElement('section');panel.className='comms-admin-panel';panel.dataset.commsAdminOverview='1';panel.innerHTML='<div class="comms-eyebrow">СМЕТРА / ОПЕРАЦИОННАЯ АНАЛИТИКА</div><h3>Экосистема в цифрах</h3><p>Сводные показатели сервиса и очередь поддержки. Личные переписки и содержимое документов здесь не показываются.</p><div class="comms-admin-metrics" data-admin-metrics></div><button type="button" class="comms-btn" data-admin-queue>'+icon('support')+' Открыть очередь поддержки</button>';base.insertAdjacentElement('afterend',panel);panel.querySelector('[data-admin-queue]').onclick=()=>open('support')}
 try{const d=await api('/admin/communication/overview');const waiting=Number(d.support_waiting_human||0);if(state.lastWaitingHuman!==null&&waiting>state.lastWaitingHuman)notify('Новое обращение ждёт сотрудника поддержки');state.lastWaitingHuman=waiting;const rows=[['Пользователи',d.users_total],['DAU · сутки',d.users_dau],['MAU · 30 дней',d.users_mau],['Все сметы',d.estimates_total],['Сметы за месяц',d.estimates_30d],['Рабочие пространства',d.workspaces_total],['Объекты',d.projects_total],['Клиенты',d.clients_total],['Файлы',d.files_total],['Расходы',d.expenses_total],['Переписки',d.chats_total],['Сообщения',d.messages_total],['Ожидают сотрудника',d.support_waiting_human],['Открытые обращения',d.support_open],['Получено за всё время',money(d.revenue_kopecks)],['Получено за 30 дней',money(d.revenue_30d_kopecks)],['Оплаченные платежи',d.paid_transactions],['Ожидают оплаты',d.pending_payments],['Доход сегодня',money(d.revenue_today_kopecks)]];
 panel.querySelector('[data-admin-metrics]').innerHTML=rows.map(r=>'<div class="comms-admin-metric"><span>'+esc(r[0])+'</span><strong>'+(typeof r[1]==='number'?num(r[1]):esc(r[1]))+'</strong></div>').join('');
 panel.querySelector('[data-admin-queue]').innerHTML=icon('support')+' Открыть очередь поддержки'+(d.support_waiting_human?' · '+num(d.support_waiting_human)+' ожидают':'');
 }catch(error){panel.querySelector('p').textContent='Не удалось обновить статистику: '+error.message}
 finally{state.adminLoading=false}
}
function watch(){
 const root=$('#content');if(!root||state.observer)return;
 state.observer=new MutationObserver(()=>{addTrigger();if(root.dataset.section==='support')supportPage();if(root.dataset.section==='admin'&&!root.querySelector('[data-comms-admin-overview]'))adminPage()});
 state.observer.observe(root,{childList:true,subtree:true});addTrigger();
 if(root.dataset.section==='support')supportPage();if(root.dataset.section==='admin')adminPage();
}
let presenceTimer=null;
let presenceBusy=false;
let presenceEnabled=false;
function stopPresence(){
 presenceEnabled=false;
 if(presenceTimer){clearInterval(presenceTimer);presenceTimer=null}
}
async function heartbeat(){
 if(!presenceEnabled||presenceBusy||document.hidden||document.body.classList.contains('auth-mode'))return;
 const auth=$('#auth');
 if(auth&&!auth.classList.contains('hidden'))return;
 presenceBusy=true;
 try{await api('/profile/presence',{method:'POST',body:'{}'})}
 catch(error){if(/401|авторизац|сессия изменилась/i.test(error.message||''))stopPresence()}
 finally{presenceBusy=false}
}
function startPresence(){
 if(presenceEnabled)return;
 presenceEnabled=true;
 void heartbeat();
 presenceTimer=setInterval(()=>{void heartbeat()},60000);
}
document.addEventListener('DOMContentLoaded',()=>{
 mount();watch();
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)void heartbeat()});
 setInterval(()=>{if(!document.body.classList.contains('auth-mode')&&location.hash==='#admin')adminPage()},30000);
});
function reset(){
 stopPresence();
 sessionEpoch++;close();state.current=null;state.messages=[];state.chats=[];state.channels=[];state.workspaces=[];state.userId='';state.publicId='';state.role='user';state.mode='user';state.busy=false;state.adminLoading=false;state.lastWaitingHuman=null;
 if($('#communication-center')){renderList();renderMessages();$('#comms-tools')?.replaceChildren();$('#comms-my-id code').textContent='';}
}
window.SmetraCommunication={open,close,reset,startPresence,refresh:()=>refresh(true)};
})();