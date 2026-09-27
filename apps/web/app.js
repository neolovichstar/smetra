const $ = (s) => document.querySelector(s);
const escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rub = (kopecks) => new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:0}).format(kopecks / 100);
const date = (seconds) => new Intl.DateTimeFormat('ru-RU',{dateStyle:'medium'}).format(new Date(seconds * 1000));
let user = null, quotes = [], tab = location.hash.slice(1) || 'dashboard', registering = false, toastTimer;
const token = () => sessionStorage.getItem('mobile_token');
async function api(path, options = {}) {
  const headers = {'Content-Type':'application/json',...options.headers};
  if (token()) headers.Authorization = `Bearer ${token()}`;
  const response = await fetch('/api' + path,{credentials:'same-origin',...options,headers});
  let result;
  try { result = await response.json(); } catch { throw Error('Сервер вернул некорректный ответ'); }
  if (!response.ok) throw Error(result.error || `Ошибка ${response.status}`);
  return result;
}
function notify(message) { const el=$('#toast'); if(!el){alert(message);return;} el.textContent=message;el.classList.remove('hidden');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.add('hidden'),4500); }
function theme() { document.body.classList.toggle('dark'); localStorage.setItem('smetra_theme',document.body.classList.contains('dark')?'dark':'light'); }
if(localStorage.getItem('smetra_theme')==='dark') document.body.classList.add('dark');
$('#theme')?.addEventListener('click',theme);
function view(html) { $('#content').innerHTML=html; }
function showAuth() { $('#auth').classList.remove('hidden');$('#shell').classList.add('hidden'); }
function showApp() { $('#auth').classList.add('hidden');$('#shell').classList.remove('hidden');$('#header-user').textContent=user.name;$('#admin-nav').classList.toggle('hidden',user.role!=='admin');render(); }
async function loadQuotes(q='') { const result=await api('/quotes?q='+encodeURIComponent(q));quotes=result.quotes;return quotes; }
function header(title, subtitle, action='') { return `<div class="topline"><div><span class="eyebrow">Рабочее пространство</span><h1>${title}</h1><p class="muted">${subtitle}</p></div>${action}</div>`; }
function quoteCard(q) {
  const label={draft:'Черновик',sent:'Отправлено',accepted:'Согласовано',declined:'Отказ',completed:'Завершено'}[q.status];
  return `<div class="quote"><div><strong>${escapeHtml(q.title)}</strong><small>${escapeHtml(q.client)} · ${date(q.created_at)} · <span class="pill">${label}</span></small></div><div class="quote-actions"><b>${rub(q.amount_kopecks)}</b>${q.status==='draft'?`<button class="btn small" data-action="send" data-id="${q.id}">Отправить</button>`:''}${q.status==='sent'?`<button class="btn small" data-action="copy" data-url="${escapeHtml(q.public_url)}">Ссылка</button><button class="btn small" data-action="decline" data-id="${q.id}">Отказ</button>`:''}${q.status==='accepted'?`<button class="btn small" data-action="complete" data-id="${q.id}">Завершить</button>`:''}<button class="btn small danger" data-action="remove" data-id="${q.id}" title="Удалить">Удалить</button></div></div>`;
}
function quoteList() { return quotes.length?quotes.map(quoteCard).join(''):'<div class="empty"><h3>Здесь пока пусто</h3><p>Создайте первое предложение, чтобы отправить клиенту точную стоимость.</p></div>'; }
async function render() {
  if(!user)return;
  for(const b of document.querySelectorAll('[data-tab]'))b.classList.toggle('active',b.dataset.tab===tab);
  try {
    if(tab==='dashboard'||tab==='quotes') {
      await loadQuotes();
      const counts={sent:quotes.filter(x=>x.status==='sent').length,accepted:quotes.filter(x=>x.status==='accepted').length};
      const stats=tab==='dashboard'?`<div class="stats"><div class="stat"><strong>${user.quote_count}</strong><span>Создано всего</span></div><div class="stat"><strong>${counts.sent}</strong><span>Ожидают ответа</span></div><div class="stat"><strong>${counts.accepted}</strong><span>Согласованы</span></div></div>`:'';
      view(header(tab==='dashboard'?'Обзор':'Предложения',`Здравствуйте, ${escapeHtml(user.name)}. Всё по текущим клиентам здесь.`, '<button class="btn primary" id="new-quote">+ Предложение</button>')+stats+`<section class="panel"><div class="toolbar"><h3>Ваши предложения</h3><input id="search" type="search" placeholder="Найти по названию или клиенту" aria-label="Поиск" style="max-width:300px"></div><div id="quote-list">${quoteList()}</div><button class="btn small" id="next-page">Показать ещё</button></section>`);
      let searchTimer;$('#search').addEventListener('input',(e)=>{clearTimeout(searchTimer);searchTimer=setTimeout(async()=>{try{await loadQuotes(e.target.value);$('#quote-list').innerHTML=quoteList();}catch(err){notify(err.message)}},250)});
      $('#next-page').addEventListener('click',async()=>{try{const r=await api('/quotes?offset='+quotes.length+'&q='+encodeURIComponent($('#search').value));quotes.push(...r.quotes);$('#quote-list').innerHTML=quoteList();if(!r.quotes.length)notify('Больше предложений нет')}catch(err){notify(err.message)}});
      $('#new-quote').addEventListener('click',showNewQuote);
      $('#quote-list').addEventListener('click',quoteAction);
    } else if(tab==='billing') {
      const billing=await api('/billing');
      view(header('Тариф и оплата','Доступ на выбранный срок без автоматических списаний.')+`<div class="stats"><div class="stat"><strong>${escapeHtml(user.plan)}</strong><span>Текущий тариф</span></div><div class="stat"><strong>${user.entitlement_until>Math.floor(Date.now()/1000)?date(user.entitlement_until):'—'}</strong><span>Доступ до</span></div><div class="stat"><strong>${user.quote_count}</strong><span>Предложений</span></div></div><div class="pricing"><div class="card"><h3>Про · 31 день</h3><div class="price">490 ₽</div><p class="muted">До 10 000 предложений</p><button class="btn primary" data-plan="pro_month">Выбрать</button></div><div class="card"><h3>Про · год</h3><div class="price">4 900 ₽</div><p class="muted">366 дней доступа</p><button class="btn primary" data-plan="pro_year">Выбрать</button></div></div><div class="panel"><h3>Платежи</h3><button class="btn small" id="sync">Обновить статус</button>${billing.payments.length?billing.payments.map(p=>`<div class="quote"><span>${escapeHtml(p.plan)} · ${date(p.created_at)}</span><b>${rub(p.amount_kopecks)} · ${escapeHtml(p.status)}</b></div>`).join(''):'<p class="muted">Платежей пока нет.</p>'}</div>`);
      document.querySelectorAll('[data-plan]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{const r=await api('/billing/checkout',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({plan:b.dataset.plan})});location.href=r.url}catch(err){notify(err.message);b.disabled=false}}));
      $('#sync').addEventListener('click',async()=>{try{user=(await api('/billing/sync',{method:'POST'})).user;render();notify('Статус обновлён')}catch(err){notify(err.message)}});
    } else if(tab==='support') {
      view(header('Поддержка','Опишите вопрос, мы увидим его в системе.')+`<div class="panel" style="max-width:620px"><form id="support-form"><div class="field"><label for="message">Сообщение</label><textarea id="message" rows="6" minlength="5" maxlength="2000" required></textarea></div><button class="btn primary">Отправить</button></form></div>`);
      $('#support-form').onsubmit=async(e)=>{e.preventDefault();try{await api('/support',{method:'POST',body:JSON.stringify({message:$('#message').value})});$('#message').value='';notify('Сообщение отправлено')}catch(err){notify(err.message)}};
    } else if(tab==='settings') {
      view(header('Настройки','Управление аккаунтом и отображением.')+`<div class="panel"><h3>${escapeHtml(user.name)}</h3><p>${escapeHtml(user.email)}</p><p class="muted">Для изменения почты и имени напишите в поддержку.</p><button class="btn" id="theme-alt">Переключить тему</button></div><div class="panel"><h3>Удалить аккаунт</h3><p class="muted">Предложения и доступ будут удалены без возможности восстановления.</p><button class="btn danger" id="delete-account">Удалить мой аккаунт</button></div>`);
      $('#theme-alt').onclick=theme;$('#delete-account').onclick=async()=>{if(!confirm('Удалить аккаунт и все предложения без восстановления?'))return;try{await api('/me',{method:'DELETE'});sessionStorage.removeItem('mobile_token');user=null;showAuth()}catch(err){notify(err.message)}};
    } else if(tab==='admin'&&user.role==='admin') {
      const data=await api('/admin/overview');
      view(header('Администрирование','Сводка и ручные действия.')+`<div class="stats"><div class="stat"><strong>${data.stats.users}</strong><span>Пользователей</span></div><div class="stat"><strong>${data.stats.subscriptions}</strong><span>Активных доступов</span></div><div class="stat"><strong>${rub(data.stats.revenue_kopecks)}</strong><span>Выручка за всё время</span></div></div><div class="panel table-wrap"><h3>Пользователи</h3><table><thead><tr><th>Почта</th><th>Роль / тариф</th><th>Действия</th></tr></thead><tbody>${data.users.map(u=>`<tr><td>${escapeHtml(u.email)}</td><td>${escapeHtml(u.role)} · ${escapeHtml(u.plan)}</td><td><button class="btn small" data-admin="${u.blocked?'unblock':'block'}" data-id="${u.id}">${u.blocked?'Разблокировать':'Блокировать'}</button> <button class="btn small" data-admin="grant" data-id="${u.id}">+31 день</button> <button class="btn small" data-admin="revoke" data-id="${u.id}">Отозвать</button></td></tr>`).join('')}</tbody></table></div><div class="panel"><h3>Поддержка</h3>${data.tickets.map(t=>`<p><small>${date(t.created_at)}</small> · ${escapeHtml(t.message)}</p>`).join('')||'<p class="muted">Обращений нет</p>'}</div><div class="panel"><h3>Журнал действий</h3>${data.audit.map(a=>`<p><small>${date(a.created_at)}</small> · ${escapeHtml(a.action)} · ${escapeHtml(a.target)}</p>`).join('')||'<p class="muted">Пусто</p>'}</div>`);
      document.querySelectorAll('[data-admin]').forEach(b=>b.onclick=async()=>{if(!confirm('Подтвердить действие?'))return;try{await api('/admin/users/'+b.dataset.id,{method:'PATCH',body:JSON.stringify({action:b.dataset.admin})});render()}catch(err){notify(err.message)}});
    } else {tab='dashboard';return render()}
  } catch(err) { view(`<div class="panel"><h2>Не удалось загрузить раздел</h2><p class="muted">${escapeHtml(err.message)}</p><button class="btn" id="retry">Повторить</button></div>`);$('#retry').onclick=render; }
}
function showNewQuote(){
  view(header('Новое предложение','Заполните детали и отправьте ссылку клиенту.')+`<div class="panel" style="max-width:750px"><form id="quote-form"><div class="form-grid"><div class="field"><label for="title">Название работы</label><input id="title" maxlength="120" required placeholder="Например, разработка сайта"></div><div class="field"><label for="client">Клиент</label><input id="client" maxlength="120" required placeholder="Имя или компания"></div></div><div class="field"><label for="amount">Стоимость в рублях</label><input id="amount" type="number" min="1" max="100000000" step="0.01" required placeholder="50000"></div><div class="field"><label for="description">Описание работ</label><textarea id="description" maxlength="3000" rows="5" placeholder="Что входит в работу"></textarea></div><div class="row"><button class="btn primary">Сохранить черновик</button><button type="button" class="btn" id="cancel-new">Отмена</button></div></form></div>`);
  $('#cancel-new').onclick=render;
  $('#quote-form').onsubmit=async(e)=>{e.preventDefault();const amount=Math.round(Number($('#amount').value)*100);if(!Number.isSafeInteger(amount)){notify('Некорректная сумма');return;}try{await api('/quotes',{method:'POST',body:JSON.stringify({title:$('#title').value,client:$('#client').value,description:$('#description').value,amount})});user.quote_count++;tab='quotes';render();notify('Черновик создан')}catch(err){notify(err.message)}};
}
async function quoteAction(e){const b=e.target.closest('[data-action]');if(!b)return;const action=b.dataset.action;try{if(action==='copy'){await navigator.clipboard.writeText(b.dataset.url);notify('Ссылка скопирована');return;}if(action==='remove'){if(!confirm('Удалить предложение?'))return;await api('/quotes/'+b.dataset.id,{method:'DELETE'});user.quote_count--;}else{const status={send:'sent',decline:'declined',complete:'completed'}[action];const result=await api('/quotes/'+b.dataset.id,{method:'PATCH',body:JSON.stringify({status})});if(action==='send'){try{await navigator.clipboard.writeText(result.quote.public_url);notify('Отправлено. Ссылка скопирована')}catch{notify('Отправлено. Ссылка: '+result.quote.public_url)}}}await render()}catch(err){notify(err.message)}}
if($('#auth')){
  $('#auth-switch').onclick=()=>{registering=!registering;$('#auth-title').textContent=registering?'Регистрация':'Вход';$('#auth-submit').textContent=registering?'Создать аккаунт':'Войти';$('#auth-switch').textContent=registering?'Уже есть аккаунт? Войти':'Создать аккаунт';$('#name-field').classList.toggle('hidden',!registering);$('#password').autocomplete=registering?'new-password':'current-password';};
  $('#auth-form').onsubmit=async(e)=>{e.preventDefault();try{const result=await api('/auth/'+(registering?'register':'login'),{method:'POST',body:JSON.stringify({email:$('#email').value,password:$('#password').value,name:$('#name').value})});user=result.user;showApp()}catch(err){notify(err.message)}};
  document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;location.hash=tab;render()});
  $('#logout').onclick=async()=>{try{await api('/auth/logout',{method:'POST'})}catch{}sessionStorage.removeItem('mobile_token');user=null;showAuth()};
  api('/me').then(r=>{user=r.user;showApp();if(location.search.includes('payment=return')){api('/billing/sync',{method:'POST'}).then(r=>{user=r.user;tab='billing';render()}).catch(e=>notify(e.message))}}).catch(()=>showAuth());
}
if($('#public-quote')){
  const id=new URLSearchParams(location.search).get('quote');
  if(id){$('#landing').classList.add('hidden');$('#public-quote').classList.remove('hidden');api('/public/quote?token='+encodeURIComponent(id)).then(r=>{let q=r.quote;$('#public-quote').innerHTML=`<span class="eyebrow">Предложение от ${escapeHtml(r.author)}</span><h1>${escapeHtml(q.title)}</h1><p>Для ${escapeHtml(q.client)}</p><div class="panel"><p style="white-space:pre-wrap">${escapeHtml(q.description)}</p><div class="price">${rub(q.amount_kopecks)}</div><p class="pill">${{draft:'Черновик',sent:'Ожидает согласования',accepted:'Согласовано',declined:'Отклонено',completed:'Завершено'}[q.status]}</p></div>${q.status==='sent'?'<button class="btn primary" id="accept">Согласовать предложение</button>':'<p class="muted">Предложение уже обработано.</p>'}`;$('#accept')?.addEventListener('click',async()=>{if(!confirm('Вы согласны с предложением и указанной стоимостью?'))return;try{await api('/public/accept',{method:'POST',body:JSON.stringify({token:id})});location.reload()}catch(e){alert(e.message)}})}).catch(e=>$('#public-quote').textContent=e.message)}
}
