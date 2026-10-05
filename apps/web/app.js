const $ = (s) => document.querySelector(s);
const escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rub = (kopecks) => new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:0}).format(kopecks / 100);
const date = (seconds) => new Intl.DateTimeFormat('ru-RU',{dateStyle:'medium'}).format(new Date(seconds * 1000));
let user = null, quotes = [], tab = location.hash.slice(1) || 'dashboard', registering = false, toastTimer, renderRevision=0;
try{sessionStorage.removeItem('mobile_token')}catch{}
async function api(path, options = {}) {
  const headers = {'Content-Type':'application/json',...options.headers};
  const workspaceId=sessionStorage.getItem('workspace_id');
  if(workspaceId)headers['X-Workspace-Id']=workspaceId;
  const response = await fetch('/api' + path,{credentials:'same-origin',...options,headers});
  let result;
  try { result = await response.json(); } catch { throw Error('Сервер вернул некорректный ответ'); }
  if (!response.ok) {const error=Error(result.error || `Ошибка ${response.status}`);error.status=response.status;throw error;}
  return result;
}
function notify(message) { const el=$('#toast'); if(!el){alert(message);return;} el.textContent=message;el.classList.remove('hidden');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.add('hidden'),4500); }
function syncThemeLabel() { const dark=document.body.classList.contains('dark'); for(const id of ['theme','theme-alt']){const button=$('#'+id);if(!button)continue;const label=dark?'Включить светлую тему':'Включить тёмную тему';button.innerHTML='<img class="icon" src="/assets/icons/'+(dark?'sun':'moon')+'.svg" alt="">'+(id==='theme-alt'?label:'');button.setAttribute('aria-label',label);button.title=label;} }
function theme() { const dark=document.body.classList.toggle('dark');document.documentElement.dataset.theme=dark?'dark':'light';try{localStorage.setItem('smetra_theme',dark?'dark':'light');}catch{} syncThemeLabel(); }
let savedTheme;try{savedTheme=localStorage.getItem('smetra_theme');}catch{}
document.body.classList.toggle('dark',document.body.classList.contains('landing-page') || savedTheme!=='light');
document.documentElement.dataset.theme=document.body.classList.contains('dark')?'dark':'light';
syncThemeLabel();
$('#theme')?.addEventListener('click',theme);
function view(html) { const content=$('#content');content.dataset.section=tab;content.innerHTML=html;content.classList.remove('app-view-enter');void content.offsetWidth;content.classList.add('app-view-enter'); }
function syncSidebarAccess(){const mobile=matchMedia('(max-width:800px)').matches;const hidden=mobile?!document.body.classList.contains('nav-open'):document.body.classList.contains('sidebar-compact');const sidebar=$('#sidebar');if(sidebar){sidebar.inert=hidden;sidebar.setAttribute('aria-hidden',String(hidden))}}
function closeNavigation(){document.body.classList.remove('nav-open');$('#nav-toggle')?.setAttribute('aria-expanded','false');$('#nav-toggle')?.setAttribute('aria-label','Открыть разделы');syncSidebarAccess()}
function showAuth() { renderRevision++;closeNavigation();document.body.classList.add('auth-mode');$('.skip-link')?.setAttribute('href','#auth-title');$('#auth').classList.remove('hidden');$('#shell').classList.add('hidden'); }
async function showApp() { closeNavigation();document.body.classList.remove('auth-mode');$('.skip-link')?.setAttribute('href','#content');$('#auth').classList.add('hidden');$('#shell').classList.remove('hidden');$('#header-user').textContent=user.name;$('#admin-nav').classList.toggle('hidden',user.role!=='admin');await render();try{const draft=JSON.parse(sessionStorage.getItem('smetra.previewDraft')||'null');if(draft&&window.Workspace){await window.Workspace.editor(draft);sessionStorage.removeItem('smetra.previewDraft')}}catch(err){notify(err.message)} }
async function loadQuotes(q='') { const result=await api('/quotes?q='+encodeURIComponent(q));quotes=result.quotes;return quotes; }
function header(title, subtitle, action='') { return `<div class="topline"><div><h1>${title}</h1>${subtitle?`<p class="muted">${subtitle}</p>`:''}</div>${action?`<div class="topline-actions">${action}</div>`:''}</div>${user && !user.email_verified && window.SmetraEmailDeliveryAvailable===true ? '<div class="panel"><strong>Подтвердите почту</strong><p class="muted">Перед оплатой откройте ссылку из письма.</p><button class="btn small" data-resend="1">Отправить письмо повторно</button></div>' : ''}`; }
function quoteCard(q) {
  const label={draft:'Черновик',sent:'Отправлено',accepted:'Согласовано',declined:'Отказ',completed:'Завершено'}[q.status];
  return `<div class="quote"><div><strong>${escapeHtml(q.title)}</strong><small>${escapeHtml(q.client)} · ${date(q.created_at)} · <span class="pill">${label}</span></small></div><div class="quote-actions"><b>${rub(q.amount_kopecks)}</b>${q.status==='draft'?`<button class="btn small" data-action="send" data-id="${q.id}">Отправить</button>`:''}${q.status==='sent'?`<button class="btn small" data-action="copy" data-url="${escapeHtml(q.public_url)}">Ссылка</button><button class="btn small" data-action="decline" data-id="${q.id}">Отказ</button>`:''}${q.status==='accepted'?`<button class="btn small" data-action="complete" data-id="${q.id}">Завершить</button>`:''}<button class="btn small danger" data-action="remove" data-id="${q.id}" title="Удалить">Удалить</button></div></div>`;
}
function quoteList() { return quotes.length?quotes.map(quoteCard).join(''):'<div class="empty"><h3>Здесь пока пусто</h3><p>Создайте первое предложение, чтобы отправить клиенту точную стоимость.</p></div>'; }
async function render() {
  if(!user)return;
  const owner=user,section=tab,mine=++renderRevision;
  const active=()=>mine===renderRevision&&user===owner&&tab===section;
  for(const b of document.querySelectorAll('[data-tab]'))b.classList.toggle('active',b.dataset.tab===tab);
  try {
    if(tab==='assistant' && window.SmetraAssistant){await window.SmetraAssistant(active);return;}
    if(tab==='construction' && window.SmetraConstruction){await window.SmetraConstruction();return;}
    const handled=window.Workspace && await window.Workspace.render(tab);
    if(!active()||handled)return;
    if(tab==='dashboard'||tab==='quotes') {
      await loadQuotes();
      if(!active())return;
      const counts={sent:quotes.filter(x=>x.status==='sent').length,accepted:quotes.filter(x=>x.status==='accepted').length};
      const stats=tab==='dashboard'?`<div class="stats"><div class="stat"><strong>${user.quote_count}</strong><span>Создано всего</span></div><div class="stat"><strong>${counts.sent}</strong><span>Ожидают ответа</span></div><div class="stat"><strong>${counts.accepted}</strong><span>Согласованы</span></div></div>`:'';
      view(header(tab==='dashboard'?'Обзор':'Предложения',`Здравствуйте, ${escapeHtml(user.name)}. Всё по текущим клиентам здесь.`, '<button class="btn primary" id="new-quote">+ Предложение</button>')+stats+`<section class="panel"><div class="toolbar"><h3>Ваши предложения</h3><input id="search" type="search" placeholder="Найти по названию или клиенту" aria-label="Поиск" class="search-input"></div><div id="quote-list">${quoteList()}</div><button class="btn small" id="next-page">Показать ещё</button></section>`);
      let searchTimer;$('#search').addEventListener('input',(e)=>{clearTimeout(searchTimer);searchTimer=setTimeout(async()=>{try{await loadQuotes(e.target.value);$('#quote-list').innerHTML=quoteList();}catch(err){notify(err.message)}},250)});
      $('#next-page').addEventListener('click',async()=>{try{const r=await api('/quotes?offset='+quotes.length+'&q='+encodeURIComponent($('#search').value));quotes.push(...r.quotes);$('#quote-list').innerHTML=quoteList();if(!r.quotes.length)notify('Больше предложений нет')}catch(err){notify(err.message)}});
      $('#new-quote').addEventListener('click',showNewQuote);
      $('#quote-list').addEventListener('click',quoteAction);
    } else if(tab==='billing') {
      const billing=await api('/billing');
      if(!active())return;
      const checkoutReady=billing.email_verified&&['test','live'].includes(billing.checkout_mode);
      const paymentNote=billing.checkout_mode==='off'?'Приём оплаты Про пока подключается.':!billing.email_verified?'Для оплаты подтвердите почту в профиле. Пока можно работать на бесплатном тарифе.':billing.checkout_mode==='test'?'Тестовая оплата: деньги не списываются.':'Оплата откроется на защищённой странице ЮKassa.';
      const planNames={pro_month:'Про · 31 день',pro_year:'Про · 366 дней'},paymentNames={pending:'Ожидает оплаты',succeeded:'Оплачено',canceled:'Отменено',refunded:'Возврат'};
      view(`<div class="billing-hero"><div><span class="overline">Ваш ритм работы</span><h1>Больше возможностей.<br>Та же ясность.</h1><p class="muted">Один тариф для сайта и приложения. Без автоматических списаний.</p><p class="note">Сейчас: ${escapeHtml(user.plan==='free'?'Старт':'Про')} · ${user.quote_count} смет${user.entitlement_until>Math.floor(Date.now()/1000)?' · до '+date(user.entitlement_until):''}</p></div><img class="black-art" src="/assets/black/flight.png" alt=""></div><div class="billing-plans"><section><span class="overline">Для начала</span><h3>Старт</h3><div class="open-price">0 ₽</div><ul class="open-benefits"><li>Первые 10 смет</li><li>Клиенты и согласования</li><li>Сайт и Android-приложение</li></ul></section><section><span class="overline">Для постоянной работы</span><h3>Про</h3><div class="open-price">490 ₽<small> / 31 день</small></div><ul class="open-benefits"><li>До 10 000 смет</li><li>Единый доступ на всех устройствах</li><li>Учёт заказов и поступлений</li></ul><div class="row"><button class="btn primary" data-plan="pro_month" ${checkoutReady?'':'disabled'}>Выбрать Про</button><button class="btn" data-plan="pro_year" ${checkoutReady?'':'disabled'}>Год · 4 900 ₽</button></div><p class="note">${paymentNote}</p></section></div><section><div class="section-top"><h3>История платежей</h3><button class="btn small" id="sync">Проверить оплату</button></div>${billing.payments.length?billing.payments.map(p=>`<div class="quote"><span>${escapeHtml(planNames[p.plan]||p.plan)} · ${date(p.created_at)}</span><b>${rub(p.amount_kopecks)} · ${escapeHtml(paymentNames[p.status]||p.status)}</b></div>`).join(''):'<p class="muted">Здесь появятся оплаты подписки.</p>'}</section>`);
      $('#content').insertAdjacentHTML('beforeend','<p class="note billing-legal">Оплату принимает самозанятый МУРАВЬЕВ КОНСТАНТИН АЛЕКСЕЕВИЧ · ИНН 713304603876. <a href="/terms">Условия оплаты и возврата</a> · <a href="/contacts">Контакты</a></p>');
      document.querySelectorAll('[data-plan]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;const keyName='smetra.checkout.'+b.dataset.plan;let key=sessionStorage.getItem(keyName);if(!key){key=crypto.randomUUID();sessionStorage.setItem(keyName,key)}try{const r=await api('/billing/checkout',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({plan:b.dataset.plan})});location.href=r.url}catch(err){notify(err.message);b.disabled=false}}));
      $('#sync').addEventListener('click',async event=>{const button=event.currentTarget;if(button.disabled)return;button.disabled=true;try{const result=await api('/billing/sync',{method:'POST'});if(user!==owner)return;user=result.user;if(tab==='billing')await render();notify(user.plan==='pro'&&user.entitlement_until>Date.now()/1000?'Про активен до '+date(user.entitlement_until):'Тариф Старт. Подтверждённой оплаты Про нет.')}catch(err){if(user===owner)notify(err.message)}finally{if(button.isConnected)button.disabled=false}});
    } else if(tab==='support') {
      view(header('Давайте разберёмся.','Поддержка Сметры — рядом.')+`<div class="support-layout"><aside class="support-guide"><span class="support-symbol" aria-hidden="true"></span><h2>Что случилось?</h2><p>Выберите тему или сразу напишите вопрос.</p><div class="support-topics"><button type="button" data-support-topic="Вход в аккаунт">Вход в аккаунт</button><button type="button" data-support-topic="Оплата и подписка">Оплата и подписка</button><button type="button" data-support-topic="Работа со сметой">Работа со сметой</button></div><a href="mailto:reyzin378@gmail.com">Написать на почту ↗</a></aside><div class="support-panel"><form id="support-form"><div class="field"><label for="message">Ваш вопрос</label><textarea id="message" rows="7" minlength="5" maxlength="2000" placeholder="Расскажите, что не получается…" required></textarea></div><button class="btn primary">Отправить сообщение</button></form></div></div>`);
      const topics=[...document.querySelectorAll('[data-support-topic]')];let selectedTopic='';
      topics.forEach(button=>{button.setAttribute('aria-pressed','false');button.onclick=()=>{const input=$('#message');const prefix=selectedTopic+': ';const text=selectedTopic&&input.value.startsWith(prefix)?input.value.slice(prefix.length):input.value;selectedTopic=button.dataset.supportTopic;input.value=selectedTopic+': '+text;topics.forEach(item=>item.setAttribute('aria-pressed',String(item===button)));input.focus()}});
      $('#support-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget,button=form.querySelector('[type=submit],button:not([type])'),input=form.querySelector('#message'),message=input.value;if(button.disabled)return;button.disabled=true;try{await api('/support',{method:'POST',body:JSON.stringify({message})});if(input.value===message)input.value='';if(user===owner)notify('Сообщение отправлено')}catch(err){if(user===owner)notify(err.message)}finally{if(button.isConnected)button.disabled=false}};
    } else if(tab==='settings') {
      view(header('Настройки','Управление аккаунтом и отображением.')+`<div class="panel"><h3>${escapeHtml(user.name)}</h3><p>${escapeHtml(user.email)}</p><p class="muted">Для изменения почты и имени напишите в поддержку.</p><button class="btn" id="theme-alt" type="button">Переключить тему</button></div><div class="panel"><h3>Удалить аккаунт</h3><p class="muted">Предложения и доступ будут удалены без возможности восстановления.</p><button class="btn danger" id="delete-account" type="button">Удалить мой аккаунт</button></div>`);
      syncThemeLabel();$('#theme-alt').onclick=theme;$('#delete-account').onclick=async event=>{const button=event.currentTarget;if(button.disabled||!confirm('Удалить аккаунт и все предложения без восстановления?'))return;button.disabled=true;try{await api('/me',{method:'DELETE'});if(user!==owner)return;sessionStorage.removeItem('mobile_token');sessionStorage.removeItem('workspace_id');window.Workspace?.reset();user=null;showAuth()}catch(err){if(user===owner)notify(err.message)}finally{if(button.isConnected)button.disabled=false}};
    } else if(tab==='admin'&&user.role==='admin') {
      await window.SmetraAdmin();
    } else {tab='dashboard';return render()}
  } catch(err) { if(!active())return;view(`<div class="panel"><h2>Не удалось загрузить раздел</h2><p class="muted">${escapeHtml(err.message)}</p><button class="btn" id="retry">Повторить</button></div>`);$('#retry').onclick=render; }
}
window.render=render;
function showNewQuote(){
  if(window.Workspace)return window.Workspace.editor();
  view(header('Новое предложение','Заполните детали и отправьте ссылку клиенту.')+`<div class="panel editor-panel"><form id="quote-form"><div class="form-grid"><div class="field"><label for="title">Название работы</label><input id="title" maxlength="120" required placeholder="Например, разработка сайта"></div><div class="field"><label for="client">Клиент</label><input id="client" maxlength="120" required placeholder="Имя или компания"></div></div><div class="field"><label for="amount">Стоимость в рублях</label><input id="amount" type="number" min="1" max="100000000" step="0.01" required placeholder="50000"></div><div class="field"><label for="description">Описание работ</label><textarea id="description" maxlength="3000" rows="5" placeholder="Что входит в работу"></textarea></div><div class="row"><button class="btn primary">Сохранить черновик</button><button type="button" class="btn" id="cancel-new">Отмена</button></div></form></div>`);
  $('#cancel-new').onclick=render;
  $('#quote-form').onsubmit=async(e)=>{e.preventDefault();const amount=Math.round(Number($('#amount').value)*100);if(!Number.isSafeInteger(amount)){notify('Некорректная сумма');return;}try{await api('/quotes',{method:'POST',body:JSON.stringify({title:$('#title').value,client:$('#client').value,description:$('#description').value,amount})});user.quote_count++;tab='quotes';render();notify('Черновик создан')}catch(err){notify(err.message)}};
}
async function quoteAction(e){const b=e.target.closest('[data-action]');if(!b)return;const action=b.dataset.action;try{if(action==='copy'){await navigator.clipboard.writeText(b.dataset.url);notify('Ссылка скопирована');return;}if(action==='remove'){if(!confirm('Удалить предложение?'))return;await api('/quotes/'+b.dataset.id,{method:'DELETE'});user.quote_count--;}else{const status={send:'sent',decline:'declined',complete:'completed'}[action];const result=await api('/quotes/'+b.dataset.id,{method:'PATCH',body:JSON.stringify({status})});if(action==='send'){try{await navigator.clipboard.writeText(result.quote.public_url);notify('Отправлено. Ссылка скопирована')}catch{notify('Отправлено. Ссылка: '+result.quote.public_url)}}}await render()}catch(err){notify(err.message)}}
if($('#auth')){
  const syncEmailActions=()=>{$('#forgot').classList.toggle('hidden',registering||window.SmetraEmailDeliveryAvailable!==true)};
  document.addEventListener('smetra:email-capability',syncEmailActions);syncEmailActions();
  const setAuthMode=(mode)=>{registering=mode==='register';$('#auth-title').textContent=registering?'Ваша работа начинается здесь.':'С возвращением.';$('#auth-copy').textContent=registering?'Создайте пространство для смет, клиентов и заказов. Первые 10 смет бесплатно.':'Продолжите работу с того места, где остановились.';$('#auth-submit').innerHTML=registering?'Создать пространство <span aria-hidden="true">↗</span>':'Войти в пространство <span aria-hidden="true">↗</span>';$('#name-field').classList.toggle('hidden',!registering);$('#name').required=registering;$('#forgot').classList.toggle('hidden',registering||window.SmetraEmailDeliveryAvailable!==true);$('#password').value='';$('#password').autocomplete=registering?'new-password':'current-password';$('#auth-login-tab').setAttribute('aria-selected',String(!registering));$('#auth-register-tab').setAttribute('aria-selected',String(registering));$('#auth-login-tab').tabIndex=registering?-1:0;$('#auth-register-tab').tabIndex=registering?0:-1;$('#auth-form-error').textContent='';$('#email-disclosure').open=true};
  $('#auth-login-tab').onclick=()=>setAuthMode('login');
  $('#auth-register-tab').onclick=()=>setAuthMode('register');
  $('.auth-tabs').onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const mode=event.key==='Home'?'login':event.key==='End'?'register':registering?'login':'register';setAuthMode(mode);$(mode==='login'?'#auth-login-tab':'#auth-register-tab').focus()};
  $('#auth-form').onsubmit=async(e)=>{e.preventDefault();const button=$('#auth-submit');button.disabled=true;$('#auth-form-error').textContent='';try{const result=await api('/auth/'+(registering?'register':'login'),{method:'POST',body:JSON.stringify({email:$('#email').value.trim(),password:$('#password').value,name:$('#name').value.trim()})});user=result.user;sessionStorage.removeItem('workspace_id');window.Workspace?.reset();await showApp()}catch(err){$('#auth-form-error').textContent=err.message}finally{button.disabled=false}};
  $('#forgot').onclick=async event=>{const button=event.currentTarget;if(button.disabled||window.SmetraEmailDeliveryAvailable!==true)return;const email=$('#email').value.trim();if(!email){$('#auth-form-error').textContent='Сначала укажите почту';$('#email').focus();return}button.disabled=true;try{await api('/auth/reset/request',{method:'POST',body:JSON.stringify({email})});$('#auth-status').textContent='Если адрес зарегистрирован, мы отправили письмо для сброса пароля.'}catch(err){$('#auth-form-error').textContent=err.message}finally{button.disabled=false}};
  $('#content').addEventListener('click',async(e)=>{const button=e.target.closest('[data-resend]');if(!button||button.disabled||window.SmetraEmailDeliveryAvailable!==true)return;button.disabled=true;try{await api('/auth/verify/resend',{method:'POST'});notify('Письмо отправлено')}catch(err){notify(err.message)}});
   document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=async()=>{if(tab===b.dataset.tab){closeNavigation();return}tab=b.dataset.tab;location.hash=tab;closeNavigation();await render();$('#content').focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'})});
  $('#nav-backdrop').classList.remove('hidden');
  $('#nav-toggle').onclick=()=>{const open=!document.body.classList.contains('nav-open');document.body.classList.toggle('nav-open',open);$('#nav-toggle').setAttribute('aria-expanded',String(open));$('#nav-toggle').setAttribute('aria-label',open?'Закрыть разделы':'Открыть разделы');syncSidebarAccess()};
  matchMedia('(max-width:800px)').addEventListener('change',()=>{closeNavigation()});syncSidebarAccess();
  $('#nav-backdrop').onclick=closeNavigation;
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.body.classList.contains('nav-open')){closeNavigation();$('#nav-toggle').focus()}});
  $('#logout').onclick=async()=>{try{await api('/auth/logout',{method:'POST'})}catch{}sessionStorage.removeItem('mobile_token');sessionStorage.removeItem('workspace_id');window.Workspace?.reset();user=null;showAuth()};
  const params=new URLSearchParams(location.search);
  if(params.has('register') && !params.has('reset')) setAuthMode('register');
  if(params.has('reset')){
    showAuth();$('#auth-title').textContent='Новый пароль';$('#auth-copy').textContent='Придумайте новый пароль для вашего пространства.';
    $('#name-field').classList.add('hidden');$('#email').closest('.field').classList.add('hidden');
    $('#email').required=false;$('.auth-tabs').classList.add('hidden');$('.auth-provider-block').classList.add('hidden');$('#forgot').classList.add('hidden');
    $('#password').autocomplete='new-password';$('#auth-submit').textContent='Сохранить новый пароль';
    $('#auth-form').onsubmit=async(e)=>{e.preventDefault();try{await api('/auth/reset/confirm',{method:'POST',body:JSON.stringify({token:params.get('reset'),password:$('#password').value})});history.replaceState({},'', '/app');location.reload()}catch(err){$('#auth-form-error').textContent=err.message}};
  }else{
    const verification=params.get('verify');
    const verificationTask=verification?api('/auth/verify',{method:'POST',body:JSON.stringify({token:verification})}).then(()=>{history.replaceState({},'', '/app');notify('Почта подтверждена')}).catch(e=>notify(e.message)):Promise.resolve();
    verificationTask.finally(()=>api('/me').then(r=>{user=r.user;showApp();if(params.has('payment')){sessionStorage.removeItem('smetra.checkout.pro_month');sessionStorage.removeItem('smetra.checkout.pro_year');api('/billing/sync',{method:'POST'}).then(r=>{user=r.user;tab='billing';render()}).catch(e=>notify(e.message))}}).catch(()=>showAuth()));
  }
}
document.addEventListener('DOMContentLoaded',()=>{const params=new URLSearchParams(location.search),intake=params.get('intake'),quote=params.get('quote');if(intake&&document.querySelector('#public-quote'))window.Workspace.intakePage(intake);else if(quote&&document.querySelector('#public-quote'))window.Workspace.publicPage(quote)});
