const $ = (s) => document.querySelector(s);
const escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rubFormatter=new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',minimumFractionDigits:0,maximumFractionDigits:2});
const dateFormatter=new Intl.DateTimeFormat('ru-RU',{dateStyle:'medium'});
const rub = (kopecks) => rubFormatter.format(kopecks / 100);
const date = (seconds) => dateFormatter.format(new Date(seconds * 1000));
let user = null, quotes = [], tab = location.hash.slice(1) || 'dashboard', registering = false, toastTimer, renderRevision=0, authRevision=0;
try{sessionStorage.removeItem('mobile_token');const ref=new URLSearchParams(location.search).get('ref');if(ref&&ref.length<=80)sessionStorage.setItem('smetra.referral',ref)}catch{}
const apiRequests=new Map();
async function api(path, options = {}) {
  const headers = {'Content-Type':'application/json',...options.headers};
  const workspaceId=sessionStorage.getItem('workspace_id');
  if(workspaceId)headers['X-Workspace-Id']=workspaceId;
  const method=(options.method||'GET').toUpperCase();
  const owner=user;
  const share=method==='GET'&&Object.keys(options).length===0;
  const key=JSON.stringify([user?.id||'',workspaceId||'',path]);
  if(method!=='GET')apiRequests.clear();
  if(share&&apiRequests.has(key))return apiRequests.get(key);
  const request=(async()=>{
    const controller=options.signal?null:new AbortController();
    const slow=method!=='GET'&&/^\/(assistant|ai|files)(\/|$)/.test(path);
    const timer=controller?setTimeout(()=>controller.abort(),slow?120000:30000):null;
    try{
      const response=await fetch('/api'+path,{credentials:'same-origin',...options,headers,signal:options.signal||controller.signal});
      let result;
      try{result=await response.json()}catch{throw Error('Не удалось прочитать ответ сервера. Повторите попытку.')}
      if(!response.ok){const message=typeof result.error==='string'?result.error:result.error?.message;const error=Error(message||'Не удалось выполнить действие. Повторите попытку.');error.status=response.status;if(response.status===402&&owner&&user===owner&&!path.startsWith('/billing')){const source=path.startsWith('/quotes')?'quote_limit':path.startsWith('/projects')?'project_limit':path.startsWith('/assistant')?'ai_limit':path.startsWith('/files')?'file_analysis':'other';Promise.resolve(window.SmetraLoadFeature?.('growth')).then(()=>{if(user===owner)window.SmetraGrowth?.paywall(source)}).catch(()=>{});}throw error}
      return result;
    }catch(error){
      if(error.name==='AbortError')throw Error('Сервер отвечает слишком долго. Повторите попытку.');
      if(error instanceof TypeError)throw Error('Нет связи с сервером. Проверьте интернет и повторите попытку.');
      throw error;
    }finally{if(timer!==null)clearTimeout(timer)}
  })();
  if(share)apiRequests.set(key,request);
  try{return await request}finally{if(apiRequests.get(key)===request)apiRequests.delete(key)}
}
function notify(message) { const el=$('#toast'); if(!el){alert(message);return;} el.textContent=message;el.classList.remove('hidden');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.add('hidden'),4500); }
function syncThemeLabel() { const dark=document.body.classList.contains('dark'); for(const id of ['theme','theme-alt']){const button=$('#'+id);if(!button)continue;const label=dark?'Включить светлую тему':'Включить тёмную тему';button.innerHTML='<img class="icon" src="/assets/icons/'+(dark?'sun':'moon')+'.svg" alt="">'+(id==='theme-alt'?label:'');button.setAttribute('aria-label',label);button.title=label;} }
function theme() { const dark=document.body.classList.toggle('dark');document.documentElement.dataset.theme=dark?'dark':'light';try{localStorage.setItem('smetra_theme',dark?'dark':'light');}catch{} syncThemeLabel(); }
let savedTheme;try{savedTheme=localStorage.getItem('smetra_theme');}catch{}
document.body.classList.toggle('dark',document.body.classList.contains('landing-page') || savedTheme!=='light');
document.documentElement.dataset.theme=document.body.classList.contains('dark')?'dark':'light';
syncThemeLabel();
$('#theme')?.addEventListener('click',theme);
function view(html) { window.SmetraSelects?.close();window.SmetraQuoteEditor?.leave();const content=$('#content');content.dataset.section=tab;content.innerHTML=html;content.classList.remove('app-view-enter');void content.offsetWidth;content.classList.add('app-view-enter'); }
function syncSidebarAccess(){const mobile=matchMedia('(max-width:800px)').matches;const hidden=mobile?!document.body.classList.contains('nav-open'):document.body.classList.contains('sidebar-compact');const sidebar=$('#sidebar');if(sidebar){sidebar.inert=hidden;sidebar.setAttribute('aria-hidden',String(hidden))}}
function closeNavigation(){document.body.classList.remove('nav-open');$('#nav-toggle')?.setAttribute('aria-expanded','false');$('#nav-toggle')?.setAttribute('aria-label','Открыть разделы');syncSidebarAccess()}
function showAuth() { window.SmetraQuoteEditor?.leave();authRevision++;renderRevision++;apiRequests.clear();closeNavigation();$('#content')?.replaceChildren();document.body.classList.add('auth-mode');$('.skip-link')?.setAttribute('href','#auth-title');$('#auth').classList.remove('hidden');$('#shell').classList.add('hidden'); }
async function showApp() { closeNavigation();document.body.classList.remove('auth-mode');$('.skip-link')?.setAttribute('href','#content');$('#auth').classList.add('hidden');$('#shell').classList.remove('hidden');$('#header-user').textContent=user.name;$('#admin-nav').classList.toggle('hidden',user.role!=='admin');const owner=user;const ref=new URLSearchParams(location.search).get('ref')||sessionStorage.getItem('smetra.referral');if(ref){sessionStorage.setItem('smetra.referral',ref);api('/billing/referral',{method:'POST',body:JSON.stringify({code:ref})}).then(()=>sessionStorage.removeItem('smetra.referral')).catch(()=>{});}await render();if(user!==owner)return;try{const draft=JSON.parse(sessionStorage.getItem('smetra.previewDraft')||'null');if(draft&&window.Workspace){await window.Workspace.editor(draft);sessionStorage.removeItem('smetra.previewDraft')}}catch(err){notify(err.message)} }
async function loadQuotes(q='') { const result=await api('/quotes?q='+encodeURIComponent(q));quotes=result.quotes;return quotes; }
function header(title, subtitle, action='') { return `<div class="topline"><div><h1>${title}</h1>${subtitle?`<p class="muted">${subtitle}</p>`:''}</div>${action?`<div class="topline-actions">${action}</div>`:''}</div>${user && !user.email_verified && window.SmetraEmailDeliveryAvailable===true ? '<div class="panel"><strong>Подтвердите почту</strong><p class="muted">Перед оплатой откройте ссылку из письма.</p><button class="btn small" data-resend="1">Отправить письмо повторно</button></div>' : ''}`; }
function quoteCard(q) {
  const label={draft:'Черновик',sent:'Отправлено',accepted:'Согласовано',declined:'Отказ',completed:'Завершено'}[q.status];
  return `<div class="quote"><div><strong>${escapeHtml(q.title)}</strong><small>${escapeHtml(q.client)} · ${date(q.created_at)} · <span class="pill">${label}</span></small></div><div class="quote-actions"><b>${rub(q.amount_kopecks)}</b>${q.status==='draft'?`<button class="btn small" data-action="send" data-id="${q.id}">Отправить</button>`:''}${q.status==='sent'?`<button class="btn small" data-action="copy" data-url="${escapeHtml(q.public_url)}">Ссылка</button><button class="btn small" data-action="decline" data-id="${q.id}">Отказ</button>`:''}${q.status==='accepted'?`<button class="btn small" data-action="complete" data-id="${q.id}">Завершить</button>`:''}<button class="btn small danger" data-action="remove" data-id="${q.id}" title="Удалить">Удалить</button></div></div>`;
}
function quoteList() { return quotes.length?quotes.map(quoteCard).join(''):'<div class="empty"><h3>Здесь пока пусто</h3><p>Создайте первое предложение, чтобы отправить клиенту точную стоимость.</p></div>'; }
async function render() {
  window.SmetraQuoteEditor?.leave();
  if(!user)return;
  const owner=user,section=tab,mine=++renderRevision;
  const active=()=>mine===renderRevision&&user===owner&&tab===section;
  for(const b of document.querySelectorAll('[data-tab]'))b.classList.toggle('active',b.dataset.tab===tab);
  try {
    const feature=({assistant:'assistant',profile:'profile',settings:'profile',construction:'construction',admin:'admin',billing:'growth'})[section];
    if(feature&&window.SmetraLoadFeature){await window.SmetraLoadFeature(feature);if(!active())return;}
    if(tab==='assistant' && window.SmetraAssistant){await window.SmetraAssistant(active);return;}
    if(tab==='profile' && window.SmetraProfile){await window.SmetraProfile.render(active);return;}
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
      await window.SmetraGrowth.billing(active);
    } else if(tab==='support') {
      view(header('Давайте разберёмся.','Поддержка Сметры — рядом.')+`<div class="support-layout"><aside class="support-guide"><span class="support-symbol" aria-hidden="true"></span><h2>Что случилось?</h2><p>Выберите тему или сразу напишите вопрос.</p><div class="support-topics"><button type="button" data-support-topic="Вход в аккаунт">Вход в аккаунт</button><button type="button" data-support-topic="Оплата и подписка">Оплата и подписка</button><button type="button" data-support-topic="Работа со сметой">Работа со сметой</button></div><a href="mailto:reyzin378@gmail.com">Написать на почту ↗</a></aside><div class="support-panel"><form id="support-form"><div class="field"><label for="message">Ваш вопрос</label><textarea id="message" rows="7" minlength="5" maxlength="2000" placeholder="Расскажите, что не получается…" required></textarea></div><button class="btn primary">Отправить сообщение</button></form></div></div>`);
      const topics=[...document.querySelectorAll('[data-support-topic]')];let selectedTopic='';
      topics.forEach(button=>{button.setAttribute('aria-pressed','false');button.onclick=()=>{const input=$('#message');const prefix=selectedTopic+': ';const text=selectedTopic&&input.value.startsWith(prefix)?input.value.slice(prefix.length):input.value;selectedTopic=button.dataset.supportTopic;input.value=selectedTopic+': '+text;topics.forEach(item=>item.setAttribute('aria-pressed',String(item===button)));input.focus()}});
      $('#support-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget,button=form.querySelector('[type=submit],button:not([type])'),input=form.querySelector('#message'),message=input.value;if(button.disabled)return;button.disabled=true;try{await api('/support',{method:'POST',body:JSON.stringify({message})});if(input.value===message)input.value='';if(user===owner)notify('Сообщение отправлено')}catch(err){if(user===owner)notify(err.message)}finally{if(button.isConnected)button.disabled=false}};
    } else if(tab==='settings') {
      view(header('Настройки','Отображение и поведение ассистента.')+`<div class="panel"><h3>Аккаунт</h3><p>${escapeHtml(user.email)}</p><button class="btn" id="profile-open" type="button">Редактировать профиль</button><button class="btn" id="theme-alt" type="button">Переключить тему</button></div><section id="settings-personalization"></section><div class="panel"><h3>Удалить аккаунт</h3><p class="muted">Предложения и доступ будут удалены без возможности восстановления.</p><button class="btn danger" id="delete-account" type="button">Удалить мой аккаунт</button></div>`);
      $('#profile-open').onclick=()=>{tab='profile';location.hash=tab;render()};
      if(window.SmetraProfile){await window.SmetraProfile.settings(active);if(!active())return;}
      syncThemeLabel();$('#theme-alt').onclick=theme;$('#delete-account').onclick=async event=>{const button=event.currentTarget;if(button.disabled||!confirm('Удалить аккаунт и все предложения без восстановления?'))return;button.disabled=true;try{await api('/me',{method:'DELETE'});if(user!==owner)return;sessionStorage.removeItem('mobile_token');sessionStorage.removeItem('workspace_id');window.Workspace?.reset();user=null;showAuth()}catch(err){if(user===owner)notify(err.message)}finally{if(button.isConnected)button.disabled=false}};
    } else if(tab==='admin'&&user.role==='admin') {
      await window.SmetraAdmin();
    } else {tab='dashboard';history.replaceState({},'',location.pathname+location.search+'#dashboard');return render()}
  } catch(err) { if(!active())return;view(`<div class="panel"><h2>Не удалось загрузить раздел</h2><p class="muted">${escapeHtml(err.message)}</p><button class="btn" id="retry">Повторить</button></div>`);$('#retry').onclick=render; }
}
window.render=render;
const appSections=new Set(['dashboard','clients','quotes','projects','construction','leads','tasks','calendar','assistant','finance','catalog','files','documents','team','notifications','activity','billing','support','profile','settings','admin']);
async function renderNavigation(){
  const owner=user,section=tab,pending=render(),revision=renderRevision;
  await pending;
  if(user!==owner||tab!==section||renderRevision!==revision)return;
  $('#content')?.focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});
}
window.addEventListener('hashchange',()=>{
  const section=location.hash.slice(1)||'dashboard';
  if(!appSections.has(section)||section===tab)return;
  tab=section;closeNavigation();if(user)renderNavigation();
});
function showNewQuote(){
  if(window.Workspace)return window.Workspace.editor();
  view(header('Новое предложение','Заполните детали и отправьте ссылку клиенту.')+`<div class="panel editor-panel"><form id="quote-form"><div class="form-grid"><div class="field"><label for="title">Название работы</label><input id="title" maxlength="120" required placeholder="Например, разработка сайта"></div><div class="field"><label for="client">Клиент</label><input id="client" maxlength="120" required placeholder="Имя или компания"></div></div><div class="field"><label for="amount">Стоимость в рублях</label><input id="amount" type="number" min="1" max="100000000" step="0.01" required placeholder="50000"></div><div class="field"><label for="description">Описание работ</label><textarea id="description" maxlength="3000" rows="5" placeholder="Что входит в работу"></textarea></div><div class="row"><button class="btn primary">Сохранить черновик</button><button type="button" class="btn" id="cancel-new">Отмена</button></div></form></div>`);
  $('#cancel-new').onclick=render;
  $('#quote-form').onsubmit=async(e)=>{e.preventDefault();const amount=Math.round(Number($('#amount').value)*100);if(!Number.isSafeInteger(amount)){notify('Некорректная сумма');return;}try{await api('/quotes',{method:'POST',body:JSON.stringify({title:$('#title').value,client:$('#client').value,description:$('#description').value,amount})});user.quote_count++;tab='quotes';render();notify('Черновик создан')}catch(err){notify(err.message)}};
}
async function quoteAction(e){const b=e.target.closest('[data-action]');if(!b)return;const action=b.dataset.action;try{if(action==='copy'){await navigator.clipboard.writeText(b.dataset.url);notify('Ссылка скопирована');return;}if(action==='remove'){if(!confirm('Удалить предложение?'))return;await api('/quotes/'+b.dataset.id,{method:'DELETE'});user.quote_count--;}else{const status={send:'sent',decline:'declined',complete:'completed'}[action];const result=await api('/quotes/'+b.dataset.id,{method:'PATCH',body:JSON.stringify({status})});if(action==='send'){try{await navigator.clipboard.writeText(result.quote.public_url);notify('Отправлено. Ссылка скопирована')}catch{notify('Отправлено. Ссылка: '+result.quote.public_url)}}}await render()}catch(err){notify(err.message)}}
if($('#auth')){
  const syncEmailActions=()=>{
    if(new URLSearchParams(location.search).has('reset')){$('#forgot').classList.add('hidden');$('#name').required=false;return;}
    const providerOnly=registering&&window.SmetraEmailSignupAvailable===false;
    const divider=$('.auth-provider-divider span');if(divider)divider.textContent=providerOnly?'Продолжить через сервис':'или используйте российский сервис';
    $('#forgot').classList.toggle('hidden',registering||window.SmetraEmailDeliveryAvailable!==true);
    $('#email-disclosure').classList.toggle('hidden',providerOnly);
    $('#name').required=registering&&!providerOnly;
    if(providerOnly)$('#auth-copy').textContent='Создайте аккаунт через доступный сервис ниже. Один профиль для сайта и приложения.';
  };
  document.addEventListener('smetra:email-capability',syncEmailActions);syncEmailActions();
  const setAuthMode=(mode)=>{registering=mode==='register';$('#auth-title').textContent=registering?'Ваша работа начинается здесь.':'С возвращением.';$('#auth-copy').textContent=registering?'Создайте пространство для смет, клиентов и заказов. Первые 10 смет бесплатно.':'Продолжите работу с того места, где остановились.';$('#auth-submit').innerHTML=registering?'Создать пространство <span aria-hidden="true">↗</span>':'Войти в пространство <span aria-hidden="true">↗</span>';$('#name-field').classList.toggle('hidden',!registering);$('#name').required=registering;$('#forgot').classList.toggle('hidden',registering||window.SmetraEmailDeliveryAvailable!==true);$('#password').value='';$('#password').autocomplete=registering?'new-password':'current-password';$('#auth-login-tab').setAttribute('aria-selected',String(!registering));$('#auth-register-tab').setAttribute('aria-selected',String(registering));$('#auth-login-tab').tabIndex=registering?-1:0;$('#auth-register-tab').tabIndex=registering?0:-1;$('#auth-form-error').textContent='';$('#email-disclosure').open=true};
  $('#auth-login-tab').onclick=()=>{setAuthMode('login');syncEmailActions()};
  $('#auth-register-tab').onclick=()=>{setAuthMode('register');syncEmailActions()};
  $('.auth-tabs').onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const mode=event.key==='Home'?'login':event.key==='End'?'register':registering?'login':'register';setAuthMode(mode);syncEmailActions();$(mode==='login'?'#auth-login-tab':'#auth-register-tab').focus()};
  $('#auth-form').onsubmit=async(e)=>{e.preventDefault();const button=$('#auth-submit');if(button.disabled||(registering&&window.SmetraEmailSignupAvailable===false))return;const attempt=++authRevision;button.disabled=true;$('#auth-form-error').textContent='';try{const result=await api('/auth/'+(registering?'register':'login'),{method:'POST',body:JSON.stringify({email:$('#email').value.trim(),password:$('#password').value,name:$('#name').value.trim()})});if(attempt!==authRevision)return;user=result.user;sessionStorage.removeItem('workspace_id');window.Workspace?.reset();await showApp()}catch(err){if(attempt===authRevision)$('#auth-form-error').textContent=err.message}finally{button.disabled=false}};
  $('#forgot').onclick=async event=>{const button=event.currentTarget;if(button.disabled||window.SmetraEmailDeliveryAvailable!==true)return;const email=$('#email').value.trim();if(!email){$('#auth-form-error').textContent='Сначала укажите почту';$('#email').focus();return}button.disabled=true;try{await api('/auth/reset/request',{method:'POST',body:JSON.stringify({email})});$('#auth-status').textContent='Если адрес зарегистрирован, мы отправили письмо для сброса пароля.'}catch(err){$('#auth-form-error').textContent=err.message}finally{button.disabled=false}};
  $('#content').addEventListener('click',async(e)=>{const button=e.target.closest('[data-resend]');if(!button||button.disabled||window.SmetraEmailDeliveryAvailable!==true)return;button.disabled=true;try{await api('/auth/verify/resend',{method:'POST'});notify('Письмо отправлено')}catch(err){notify(err.message)}});
   document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{if(tab===b.dataset.tab){closeNavigation();return}tab=b.dataset.tab;location.hash=tab;closeNavigation();return renderNavigation()});
  $('#nav-backdrop').classList.remove('hidden');
  $('#nav-toggle').onclick=()=>{const open=!document.body.classList.contains('nav-open');document.body.classList.toggle('nav-open',open);$('#nav-toggle').setAttribute('aria-expanded',String(open));$('#nav-toggle').setAttribute('aria-label',open?'Закрыть разделы':'Открыть разделы');syncSidebarAccess()};
  matchMedia('(max-width:800px)').addEventListener('change',()=>{closeNavigation()});syncSidebarAccess();
  $('#nav-backdrop').onclick=closeNavigation;
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.body.classList.contains('nav-open')){closeNavigation();$('#nav-toggle').focus()}});
  $('#logout').onclick=async()=>{const button=$('#logout');if(button.disabled)return;button.disabled=true;const attempt=++authRevision;try{await api('/auth/logout',{method:'POST'})}catch{}finally{button.disabled=false}if(attempt!==authRevision)return;sessionStorage.removeItem('mobile_token');sessionStorage.removeItem('workspace_id');window.Workspace?.reset();user=null;showAuth()};
  const params=new URLSearchParams(location.search);
  if(params.has('register') && !params.has('reset')) {setAuthMode('register');syncEmailActions()}
  if(params.has('reset')){
    showAuth();$('#auth-title').textContent='Новый пароль';$('#auth-copy').textContent='Придумайте новый пароль для вашего пространства.';
    $('#name-field').classList.add('hidden');$('#email').closest('.field').classList.add('hidden');
    $('#email').required=false;$('.auth-tabs').classList.add('hidden');$('.auth-provider-block').classList.add('hidden');$('#forgot').classList.add('hidden');
    $('#password').autocomplete='new-password';$('#auth-submit').textContent='Сохранить новый пароль';
    $('#auth-form').onsubmit=async(e)=>{e.preventDefault();try{await api('/auth/reset/confirm',{method:'POST',body:JSON.stringify({token:params.get('reset'),password:$('#password').value})});history.replaceState({},'', '/app');location.reload()}catch(err){$('#auth-form-error').textContent=err.message}};
  }else{
    const verification=params.get('verify');
    const verificationTask=verification?api('/auth/verify',{method:'POST',body:JSON.stringify({token:verification})}).then(()=>{history.replaceState({},'', '/app');notify('Почта подтверждена')}).catch(e=>notify(e.message)):Promise.resolve();
    const bootRevision=authRevision;
    verificationTask.then(async()=>{
      if(bootRevision!==authRevision)return;
      try{
        const result=await api('/me');
        if(bootRevision!==authRevision)return;
        user=result.user;
        if(params.has('payment')){tab='billing';history.replaceState({},'',location.pathname+location.search+'#billing')}
        await showApp();
      }catch{if(bootRevision===authRevision){user=null;showAuth()}}
    });
  }
}
document.addEventListener('DOMContentLoaded',()=>{const params=new URLSearchParams(location.search),intake=params.get('intake'),quote=params.get('quote');if(intake&&document.querySelector('#public-quote'))window.Workspace.intakePage(intake);else if(quote&&document.querySelector('#public-quote'))window.Workspace.publicPage(quote)});
