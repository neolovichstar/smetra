const $ = (s) => document.querySelector(s);
const escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function userAvatarMarkup(person) {
  const safeName=String(person?.name||'Сметра');
  const first=escapeHtml(safeName.trim().slice(0,1).toLocaleUpperCase('ru-RU'));
  const value=String(person?.avatar_url||'');
  const valid=/^https:\/\/avatars\.yandex\.net\/get-yapic\/[a-zA-Z0-9_/-]{1,150}\/islands-200$/.test(value);
  return valid?'<span class="user-avatar-fallback">'+first+'</span><img class="user-avatar-image" src="'+escapeHtml(value)+'" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">':'<span class="user-avatar-fallback">'+first+'</span>';
}
window.SmetraUserAvatar=userAvatarMarkup;
// Failed remote images reveal the neutral initial without inline event handlers.
document.addEventListener('error',event=>{
  if(event.target?.matches?.('.user-avatar-image'))event.target.remove();
},true);

const rubFormatter=new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',minimumFractionDigits:0,maximumFractionDigits:2});
const dateFormatter=new Intl.DateTimeFormat('ru-RU',{dateStyle:'medium'});
const rub = (kopecks) => rubFormatter.format(kopecks / 100);
const date = (seconds) => dateFormatter.format(new Date(seconds * 1000));
let user = null, quotes = [], tab = location.hash.slice(1) || (new URLSearchParams(location.search).get('cloud') === 'connected' ? 'premium' : 'dashboard'), registering = false, toastTimer, renderRevision=0, authRevision=0;
try{sessionStorage.removeItem('mobile_token');if(new URLSearchParams(location.search).has('partner_sso'))sessionStorage.setItem('smetra.partnerSso','1');const ref=new URLSearchParams(location.search).get('ref');if(ref&&ref.length<=80)sessionStorage.setItem('smetra.referral',ref)}catch{}
const apiRequests=new Map();
const apiResponseCache=new Map();
const API_CACHE_TTL=5000;
let apiCacheEpoch=0;
const cloneApiValue=value=>typeof structuredClone==='function'?structuredClone(value):JSON.parse(JSON.stringify(value));
function clearApiCache(){apiCacheEpoch++;apiResponseCache.clear();apiRequests.clear();}
const CACHEABLE_GET_ROUTES=new Set(['/dashboard','/workspace','/quotes','/clients','/catalog','/projects','/tasks','/leads','/overview','/receipts','/expenses','/documents','/files','/workspace/members','/custom-fields','/search']);
function cacheableApiRead(path){return CACHEABLE_GET_ROUTES.has(String(path).split('?')[0])}
async function api(path, options = {}) {
  const headers = {'Content-Type':'application/json',...options.headers};
  const workspaceId=sessionStorage.getItem('workspace_id');
  if(workspaceId)headers['X-Workspace-Id']=workspaceId;
  const method=(options.method||'GET').toUpperCase();
  const owner=user;
  const share=method==='GET'&&Object.keys(options).length===0;
  const cacheable=share&&cacheableApiRead(path);
  const key=JSON.stringify([user?.id||'',workspaceId||'',path]);
  if(method!=='GET')clearApiCache();
  if(cacheable){
    const cached=apiResponseCache.get(key);
    if(cached&&cached.expiresAt>Date.now())return cloneApiValue(cached.value);
    if(cached)apiResponseCache.delete(key);
  }
  if(share&&apiRequests.has(key))return apiRequests.get(key);
  const cacheEpoch=apiCacheEpoch;
  const request=(async()=>{
    const controller=options.signal?null:new AbortController();
    const slow=method!=='GET'&&/^\/(assistant|ai|files|voice|design-projects)(\/|$)/.test(path);
    const timer=controller?setTimeout(()=>controller.abort(),slow?120000:30000):null;
    try{
      let response=await fetch('/api'+path,{credentials:'same-origin',...options,headers,signal:options.signal||controller.signal});
      let result;
      try{result=await response.json()}catch{throw Error('Не удалось прочитать ответ сервера. Повторите попытку.')}
      if(response.status===428&&(path==='/ai/draft'||path==='/assistant'||path.startsWith('/assistant/'))&&window.SmetraEstimateSafety){
        if(await window.SmetraEstimateSafety.ensureConsent()){
          response=await fetch('/api'+path,{credentials:'same-origin',...options,headers,signal:options.signal||controller.signal});
          try{result=await response.json()}catch{throw Error('Не удалось прочитать ответ сервера. Повторите попытку.')}
        }
      }
      if(!response.ok){const message=typeof result.error==='string'?result.error:result.error?.message;const error=Error(message||'Не удалось выполнить действие. Повторите попытку.');error.status=response.status;if(response.status===402&&owner&&user===owner&&!path.startsWith('/billing')){const source=path.startsWith('/quotes')?'quote_limit':path.startsWith('/projects')?'project_limit':path.startsWith('/assistant')?'ai_limit':path.startsWith('/files')?'file_analysis':'other';Promise.resolve(window.SmetraLoadFeature?.('growth')).then(()=>{if(user===owner)window.SmetraGrowth?.paywall(source)}).catch(()=>{});}throw error}
      if(cacheable&&cacheEpoch===apiCacheEpoch&&user===owner){
        if(apiResponseCache.size>=100){const oldest=apiResponseCache.keys().next().value;if(oldest!==undefined)apiResponseCache.delete(oldest)}
        apiResponseCache.set(key,{value:cloneApiValue(result),expiresAt:Date.now()+API_CACHE_TTL});
      }
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
const LEGAL_CONSENT_VERSION='2026-10-19-ai-estimate-v1';
const REGISTRATION_CONSENT_VERSION='2026-10-19-registration-v1';
const AI_ESTIMATE_DISCLAIMER='Расчет сгенерирован ИИ-ассистентом "сметра." и является предварительным черновиком. Обязательно проверьте объемы, технологию и цены перед подписанием. Сервис не несет ответственности за финансовые риски сторон.';
window.SmetraEstimateSafety=(()=>{
  let consentPromise=null;
  const bannerHtml=()=>'<aside class="estimate-ai-warning" role="note"><strong>Предварительный расчёт</strong><p>'+escapeHtml(AI_ESTIMATE_DISCLAIMER)+'</p></aside>';
  const ensureConsent=()=>{
    if(consentPromise)return consentPromise;
    consentPromise=(async()=>{
      const current=await api('/me/legal-consent');
      if(current.accepted&&current.version===LEGAL_CONSENT_VERSION)return true;
      return new Promise(resolve=>{
        const dialog=document.createElement('dialog');
        dialog.className='estimate-safety-dialog';
        dialog.setAttribute('aria-labelledby','estimate-consent-title');
        dialog.innerHTML='<div class="estimate-safety-heading"><span class="overline">СМЕТРА / УСЛОВИЯ</span><h2 id="estimate-consent-title">Перед использованием AI</h2><p>AI создаёт только предварительные черновики. Объёмы, технология и цены требуют проверки.</p></div><label class="estimate-consent-check"><input type="checkbox" id="estimate-consent-check"><span>Я согласен с <a href="/terms" target="_blank" rel="noopener noreferrer">Пользовательским соглашением</a> и <a href="/disclaimer" target="_blank" rel="noopener noreferrer">Политикой отказа от ответственности (As Is)</a> и понимаю, что результат AI нужно проверить.</span></label><div class="estimate-safety-actions"><button type="button" class="btn" data-consent-cancel>Не сейчас</button><button type="button" class="btn primary" data-consent-accept disabled>Принять и продолжить</button></div><p class="form-error" role="alert" data-consent-error></p>';
        let settled=false;
        const finish=value=>{if(settled)return;settled=true;if(dialog.open)dialog.close();dialog.remove();resolve(value)};
        const checkbox=dialog.querySelector('#estimate-consent-check'),accept=dialog.querySelector('[data-consent-accept]');
        checkbox.addEventListener('change',()=>{accept.disabled=!checkbox.checked});
        dialog.querySelector('[data-consent-cancel]').addEventListener('click',()=>finish(false));
        dialog.addEventListener('cancel',event=>{event.preventDefault();finish(false)});
        accept.addEventListener('click',async()=>{
          if(!checkbox.checked||accept.disabled)return;
          accept.disabled=true;dialog.querySelector('[data-consent-error]').textContent='';
          try{
            const saved=await api('/me/legal-consent',{method:'POST',body:JSON.stringify({accepted:true,version:LEGAL_CONSENT_VERSION})});
            finish(saved.accepted===true&&saved.version===LEGAL_CONSENT_VERSION);
          }catch(error){dialog.querySelector('[data-consent-error]').textContent=error.message;accept.disabled=!checkbox.checked}
        });
        document.body.append(dialog);dialog.showModal();checkbox.focus();
      });
    })();
    return consentPromise.finally(()=>{consentPromise=null});
  };
  const confirmReview=()=>new Promise(resolve=>{
    const dialog=document.createElement('dialog');
    dialog.className='estimate-safety-dialog estimate-review-dialog';
    dialog.setAttribute('aria-labelledby','estimate-review-title');
    dialog.innerHTML='<div class="estimate-safety-heading"><span class="overline">ПРОВЕРКА СМЕТЫ</span><h2 id="estimate-review-title">Вы проверили объёмы и цены?</h2><p>Перед экспортом PDF или отправкой клиенту убедитесь, что позиции, единицы, технология и цены соответствуют объекту.</p></div>'+bannerHtml()+'<div class="estimate-safety-actions"><button type="button" class="btn" data-review-cancel>Вернуться к проверке</button><button type="button" class="btn primary" data-review-confirm>Да, всё верно</button></div>';
    let settled=false;
    const finish=value=>{if(settled)return;settled=true;if(dialog.open)dialog.close();dialog.remove();resolve(value)};
    dialog.querySelector('[data-review-cancel]').addEventListener('click',()=>finish(false));
    dialog.querySelector('[data-review-confirm]').addEventListener('click',()=>finish(true));
    dialog.addEventListener('cancel',event=>{event.preventDefault();finish(false)});
    document.body.append(dialog);dialog.showModal();dialog.querySelector('[data-review-cancel]').focus();
  });
  return {version:LEGAL_CONSENT_VERSION,disclaimer:AI_ESTIMATE_DISCLAIMER,bannerHtml,ensureConsent,confirmReview};
})();

function syncThemeLabel() { const dark=document.body.classList.contains('dark'); for(const id of ['theme','theme-alt']){const button=$('#'+id);if(!button)continue;const label=dark?'Включить светлую тему':'Включить тёмную тему';const icon=window.SmetraIcons?window.SmetraIcons.svg(dark?'sun':'moon',18):'';button.innerHTML=icon+(id==='theme-alt'?'<span>'+label+'</span>':'');button.setAttribute('aria-label',label);button.title=label;} }
function theme() { const dark=document.body.classList.toggle('dark');document.documentElement.dataset.theme=dark?'dark':'light';try{localStorage.setItem('smetra_theme',dark?'dark':'light');}catch{} syncThemeLabel(); }
let savedTheme;try{savedTheme=localStorage.getItem('smetra_theme');}catch{}
document.body.classList.toggle('dark',document.body.classList.contains('landing-page') || savedTheme!=='light');
document.documentElement.dataset.theme=document.body.classList.contains('dark')?'dark':'light';
syncThemeLabel();
$('#theme')?.addEventListener('click',theme);
function loadingView(section){
  const names={fieldwork:'Инструменты смет',inbox:'Полученные сметы',chats:'Чаты объектов',dashboard:'Сегодня',quotes:'Сметы',clients:'Клиенты',catalog:'Расценки',calculators:'Калькуляторы',premium:'Материалы',projects:'Заказы',tasks:'Задачи',leads:'Лиды',finance:'Финансы',calendar:'Календарь',team:'Команда',notifications:'Уведомления',activity:'История',files:'Файлы',documents:'Документы',assistant:'Ассистент',admin:'Администрирование',profile:'Профиль',settings:'Настройки',billing:'Тариф и оплата',support:'Поддержка',construction:'Строительство'};
  const title=names[section]||'Рабочее пространство';
  return `<section class="page-loading" role="status" aria-live="polite" aria-busy="true" aria-label="Загрузка раздела"><div class="page-loading-head"><span class="page-skeleton page-skeleton-kicker"></span><span class="page-skeleton page-skeleton-title"></span><span class="page-skeleton page-skeleton-copy"></span></div><div class="page-loading-metrics"><span class="page-skeleton"></span><span class="page-skeleton"></span><span class="page-skeleton"></span></div><section class="page-loading-card"><span class="page-skeleton page-skeleton-heading"></span><span class="page-skeleton page-skeleton-row"></span><span class="page-skeleton page-skeleton-row"></span><span class="page-skeleton page-skeleton-row"></span><span class="page-skeleton page-skeleton-row short"></span></section><span class="sr-only">Открываем раздел «${escapeHtml(title)}»</span></section>`;
}
let pendingPageLoadingTimer=null;
function view(html) {
  if(pendingPageLoadingTimer!==null){clearTimeout(pendingPageLoadingTimer);pendingPageLoadingTimer=null;}
  document.dispatchEvent(new CustomEvent('smetra:before-view'));
  window.SmetraObjectChats?.stop();
  window.Workspace?.cancelLoading?.();window.SmetraSelects?.close();window.SmetraQuoteEditor?.leave();window.SmetraDataExport?.cancel();
  document.querySelector('.app-shell > .assistant-toolrail')?.remove();
  const content=$('#content');if(!content)return;
  content.dataset.section=tab;content.setAttribute('aria-busy','false');content.classList.remove('app-view-enter');
  content.innerHTML=html;void content.offsetWidth;content.classList.add('app-view-enter');
}
function syncSidebarAccess(){const mobile=matchMedia('(max-width:800px)').matches;const hidden=mobile?!document.body.classList.contains('nav-open'):false;const sidebar=$('#sidebar');if(sidebar){sidebar.inert=hidden;sidebar.setAttribute('aria-hidden',String(hidden))}}
const sidebarIcons={
 fieldwork:'<path d="M9 18v-3M15 18v-3M12 3v11M8 8l4-5 4 5M4 21h16"/>',
 inbox:'<path d="M4 5h16v14H4zM4 15h5l2 3h2l2-3h5M8 9h8"/>',
 chats:'<path d="M21 11a8 8 0 0 1-8 8H5l-4 3 2-7a8 8 0 1 1 18-4Z"/><path d="M7 10h10M7 14h6"/>',
 dashboard:'<path d="m3 10 9-7 9 7"/><path d="M5 9v11h14V9M9 20v-6h6v6"/>',
 clients:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
 quotes:'<path d="M6 3h9l5 5v13H6z"/><path d="M14 3v6h6M9 13h7M9 17h7"/>',
 projects:'<path d="m12 3 9 5-9 5-9-5 9-5z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
 construction:'<path d="M3 21V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v16"/><path d="M3 8h5M3 12h3M3 16h5M16 3v5M12 3v3M8 3v5"/>',
 leads:'<path d="M4 4h16l-6 7v6l-4 3v-9z"/>',
 tasks:'<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m7 12 3 3 7-7"/>',
 calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
 assistant:'<path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3z"/><path d="m19 14 .9 2.1L22 17l-2.1.9L19 20l-.9-2.1L16 17l2.1-.9z"/>',
 finance:'<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20M6 15h4"/>',
 calculators:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 7h8M8 12h2M14 12h2M8 17h2M14 17h2"/>',
 catalog:'<path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v18H6.5A2.5 2.5 0 0 0 4 22z"/><path d="M4 4.5V22M8 7h8M8 11h8"/>',
 premium:'<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3z"/><path d="m4.5 7.8 7.5 4.4 7.5-4.4M12 12.2V21"/>',
 files:'<path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
 documents:'<path d="M6 3h9l5 5v13H6z"/><path d="M14 3v6h6M9 13h7M9 17h7"/><path d="M3 7v14"/>',
 team:'<circle cx="9" cy="8" r="3.5"/><path d="M2 21v-2a7 7 0 0 1 14 0v2M16 5.5a3.5 3.5 0 0 1 0 6.8M19 15a5 5 0 0 1 3 4.5V21"/>',
 notifications:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
 billing:'<rect x="3" y="5" width="18" height="15" rx="2"/><path d="M3 9h18M7 15h4"/>',
 support:'<circle cx="12" cy="12" r="9"/><path d="M9.6 9a2.5 2.5 0 1 1 4.7 1.2c-.8 1.1-2.3 1.4-2.3 3M12 17h.01"/>',
 profile:'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
 settings:'<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3"/><path d="M1 14h6M9 8h6M17 16h6"/>',
 admin:'<path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11z"/><path d="m9 12 2 2 4-4"/>'
};
function enhanceSidebarNavigation(){
 const sidebar=$('#sidebar');if(!sidebar)return;
 const makeSvg=(className,paths)=>{
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('width','18');svg.setAttribute('height','18');
  svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.7');
  svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');svg.setAttribute('aria-hidden','true');
  svg.classList.add(className);svg.innerHTML=paths;return svg;
 };
 const normalizeButton=button=>{
  const label=(button.dataset.navLabel||button.querySelector('.sidebar-item-label')?.textContent||[...button.childNodes].filter(node=>node.nodeType===Node.TEXT_NODE).map(node=>node.textContent).join(' ')).trim()||button.dataset.tab;
  const icon=makeSvg('sidebar-item-icon',sidebarIcons[button.dataset.tab]||sidebarIcons.documents);
  const text=document.createElement('span');text.className='sidebar-item-label';text.textContent=label;
  // Remove any legacy auto-icon source before installing the canonical navigation SVG.
  button.removeAttribute('data-ui-icon');button.removeAttribute('data-ui-icon-only');button.style.removeProperty('--ui-icon');
  // Replace every legacy child in one operation. The nav item has one canonical SVG, never an appended second icon.
  button.replaceChildren(icon,text);
  button.dataset.navLabel=label;button.removeAttribute('title');
 };
 sidebar.querySelectorAll('.sidebar-group button[data-tab]').forEach(normalizeButton);

 // Defense in depth: a later legacy script must not be able to append a second navigation icon.
 const removeDuplicates=()=>{
  sidebar.querySelectorAll('.sidebar-group button[data-tab]').forEach(button=>{
   const canonical=[...button.children].find(node=>node.matches('svg.sidebar-item-icon'));
   if(!canonical){normalizeButton(button);return}
   [...button.querySelectorAll('svg')].forEach(svg=>{if(svg!==canonical)svg.remove()});
   [...button.children].filter(node=>!['sidebar-item-icon','sidebar-item-label','sidebar-accent'].some(name=>node.classList.contains(name))).forEach(node=>node.remove());
   let kept=false;
   [...button.children].filter(node=>node.classList.contains('sidebar-item-icon')).forEach(svg=>{if(kept)svg.remove();else kept=true});
  });
 };
 if(!sidebar.dataset.iconObserver){
  const observer=new MutationObserver(removeDuplicates);
  observer.observe(sidebar,{subtree:true,childList:true});
  sidebar.dataset.iconObserver='true';
 }
 if(!sidebar.dataset.tooltips){
  sidebar.dataset.tooltips='true';
  let tip=null;
  const hide=()=>{tip?.remove();tip=null};
  const show=event=>{
   const button=event.target.closest?.('button[data-nav-label],#sidebar-profile,.comms-sidebar-trigger');
   if(!button||!document.body.classList.contains('sidebar-compact')||matchMedia('(max-width:800px)').matches)return;
   hide();
   const text=button.dataset.navLabel||button.getAttribute('aria-label')||button.textContent.trim();
   if(!text)return;
   tip=document.createElement('div');tip.className='nav-tooltip';tip.setAttribute('role','tooltip');tip.textContent=text;document.body.append(tip);
   const r=button.getBoundingClientRect();tip.style.left=Math.round(r.right+10)+'px';tip.style.top=Math.round(r.top+r.height/2-tip.offsetHeight/2)+'px';
  };
  sidebar.addEventListener('pointerover',show);sidebar.addEventListener('focusin',show);
  sidebar.addEventListener('pointerleave',hide);sidebar.addEventListener('focusout',hide);sidebar.addEventListener('click',hide);
  sidebar.querySelector('.sidebar-scroll')?.addEventListener('scroll',hide,{passive:true});
 }
 const logout=$('#logout');
 if(logout){
  const icon=makeSvg('sidebar-logout-icon','<path d="M10 17l5-5-5-5M15 12H3"/><path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6"/>');
  logout.replaceChildren(icon);
  logout.title='Выйти из аккаунта';
  logout.setAttribute('aria-label','Выйти из аккаунта');
 }
}
function syncSidebarCollapseButton(){
 const button=$('#sidebar-collapse');if(!button)return;
 const collapsed=document.body.classList.contains('sidebar-compact');
 button.setAttribute('aria-expanded',String(!collapsed));button.setAttribute('aria-label',collapsed?'Развернуть меню':'Свернуть меню');button.title=collapsed?'Развернуть меню':'Свернуть меню';
 button.innerHTML=collapsed?'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 9l3 3-3 3M7 4v16"/></svg>':'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 9l-3 3 3 3M7 4v16"/></svg>';
}
// The drawer geometry is owned by CSS (top bar height is a token); nothing to measure.
function syncMobileSidebarGeometry(){}
function closeNavigation(){document.body.classList.remove('nav-open');$('#nav-toggle')?.setAttribute('aria-expanded','false');$('#nav-toggle')?.setAttribute('aria-label','Открыть разделы');syncMobileSidebarGeometry();syncSidebarAccess()}
function setAppState(state){
  document.body.dataset.appState=state;
  if(state!=='boot'){
    document.body.classList.remove('smetra-app-booting','smetra-app-transitioning');
    $('#app-startup')?.setAttribute('aria-hidden','true');
  }
}
function showBootError(message){
  document.body.dataset.appState='boot';
  document.body.classList.add('smetra-app-booting');
  const label=$('#app-startup-label');
  if(label)label.textContent=message||'Не удалось проверить соединение.';
  const button=$('#app-startup-retry');
  if(button)button.hidden=false;
}
function showAuth(){
  window.SmetraFieldFlows?.stop?.();
  window.SmetraCommunication?.reset();
  window.SmetraQuoteEditor?.leave();
  authRevision++;renderRevision++;clearApiCache();closeNavigation();
  $('#content')?.replaceChildren();
  document.body.classList.add('auth-mode');
  $('.skip-link')?.setAttribute('href','#auth-title');
  $('#shell').classList.add('hidden');$('#shell').setAttribute('inert','');
  $('#auth').classList.remove('hidden');
  $('#nav-backdrop')?.classList.add('hidden');
  setAppState('guest');
}
async function showApp(){
  const attempt=authRevision;
  const owner=user;
  if(!owner)return;
  // Signed in after coming from the partner console: go back there with a one-time code.
  try{if(sessionStorage.getItem('smetra.partnerSso')){sessionStorage.removeItem('smetra.partnerSso');location.replace('/api/partners/sso/start');return}}catch{}
  // Keep the previously rendered auth scene underneath a covering transition
  // until the authorized route has finished constructing its first frame.
  document.body.classList.add('smetra-app-transitioning');
  document.body.dataset.appState='authorizing';
  window.SmetraCommunication?.reset();
  closeNavigation();
  $('.skip-link')?.setAttribute('href','#content');
  document.body.classList.remove('auth-mode');
  $('#shell').classList.remove('hidden');
  $('#shell').removeAttribute('inert');
  const profileName=$('#sidebar-profile-name'),avatar=$('#sidebar-avatar');
  if(profileName)profileName.textContent=owner.name;
  if(avatar)avatar.innerHTML=userAvatarMarkup(owner);
  $('#admin-nav').classList.toggle('hidden',owner.role!=='admin');
  const ref=new URLSearchParams(location.search).get('ref')||sessionStorage.getItem('smetra.referral');
  if(ref){
    sessionStorage.setItem('smetra.referral',ref);
    api('/billing/referral',{method:'POST',body:JSON.stringify({code:ref})})
      .then(()=>sessionStorage.removeItem('smetra.referral')).catch(()=>{});
  }
  try{
    await render();
    if(user!==owner||authRevision!==attempt)return;
    $('#auth').classList.add('hidden');
    setAppState('authorized');
    window.SmetraCommunication?.startPresence?.();
    window.SmetraWarmFeatures?.();
    try{
      const draft=JSON.parse(sessionStorage.getItem('smetra.previewDraft')||'null');
      if(draft&&window.Workspace){
        await window.Workspace.editor(draft);
        sessionStorage.removeItem('smetra.previewDraft');
      }
    }catch(error){notify(error.message)}
  }catch(error){
    if(user===owner&&authRevision===attempt){
      // A loading error must not be reclassified as a failed login.
      setAppState('authorized');
      $('#auth').classList.add('hidden');
      notify('Не удалось открыть раздел. Попробуйте обновить страницу.');
    }
  }
}
window.addEventListener('pageshow',event=>{
  // Returning via the browser back-forward cache must reveal auth again.
  if(event.persisted&&document.body.dataset.appState==='authorizing'){
    document.body.classList.remove('smetra-app-transitioning');
    document.body.dataset.appState='guest';
  }
});
window.SmetraCompleteAuth=async profile=>{
  if(!profile?.id)throw Error('Не удалось подтвердить профиль.');
  ++authRevision;
  user=profile;clearApiCache();
  sessionStorage.removeItem('workspace_id');
  window.Workspace?.reset();
  const hash=/^#[a-z-]+$/.test(location.hash)?location.hash:'#dashboard';
  history.replaceState({},'', '/app'+hash);
  await showApp();
};
async function loadQuotes(q='') { const result=await api('/quotes?q='+encodeURIComponent(q));quotes=result.quotes;return quotes; }
// Section rails (settings, support) collapse to icons like the assistant rail.
function railToggleMarkup(collapsed,id){
  const arrow=collapsed?'M12 9l3 3-3 3':'M15 9l-3 3 3 3';
  return `<button class="rail-toggle" id="${id}" type="button" aria-expanded="${!collapsed}" aria-label="${collapsed?'Развернуть панель':'Свернуть панель'}" title="${collapsed?'Развернуть панель':'Свернуть панель'}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16"/><path d="${arrow}"/></svg></button>`;
}
function bindRailToggle(button,root,key){
  if(!button||!root)return;
  button.onclick=()=>{
    const collapsed=root.classList.toggle('is-rail-collapsed');
    button.setAttribute('aria-expanded',String(!collapsed));
    const label=collapsed?'Развернуть панель':'Свернуть панель';button.setAttribute('aria-label',label);button.title=label;
    button.querySelector('path:last-child')?.setAttribute('d',collapsed?'M12 9l3 3-3 3':'M15 9l-3 3 3 3');
    try{localStorage.setItem(key,String(collapsed))}catch{}
  };
}
// Profile and settings share one hub with its own section rail, like the assistant.
const accountHubTabs=[['profile','Профиль','user'],['account','Аккаунт и вход','key'],['assistant','Ассистент','sparkle'],['appearance','Внешний вид','sun'],['data','Данные и экспорт','download'],['danger','Удаление аккаунта','trash']];
function accountHubTab(){
  if(tab==='profile')return 'profile';
  try{const saved=sessionStorage.getItem('smetra.settings.tab');if(saved&&saved!=='profile'&&accountHubTabs.some(item=>item[0]===saved))return saved}catch{}
  return 'account';
}
async function renderAccountHub(active){
  const owner=user,current=accountHubTab(),icon=name=>window.SmetraIcons?.svg(name,18)||'';
  const yandexPhoto=user.avatar_url?'Фото подтянуто из Яндекс ID.':'Фото подтянется из Яндекс ID после подтверждения доступа.';
  const railCollapsed=(()=>{try{return localStorage.getItem('smetra.hub.rail-collapsed')==='true'}catch{return false}})();
  view(`<section class="hub${railCollapsed?' is-rail-collapsed':''}" aria-label="Профиль и настройки">
    <nav class="hub-rail" aria-label="Разделы настроек">
      ${railToggleMarkup(railCollapsed,'hub-rail-toggle')}
      <div class="hub-identity"><span class="hub-avatar sidebar-avatar" aria-hidden="true">${userAvatarMarkup(user)}</span><div><strong>${escapeHtml(user.name)}</strong><small>${escapeHtml(user.email)}</small></div></div>
      <div class="hub-tabs" role="tablist" aria-orientation="vertical">${accountHubTabs.map(([id,label,name])=>`<button type="button" role="tab" id="hub-tab-${id}" class="hub-tab${id==='danger'?' is-danger':''}" data-hub-tab="${id}" title="${label}" aria-controls="hub-panel-${id}" aria-selected="${id===current}" tabindex="${id===current?0:-1}">${icon(name)}<span>${label}</span></button>`).join('')}</div>
    </nav>
    <div class="hub-main">
      <section class="hub-panel" id="hub-panel-profile" role="tabpanel" aria-labelledby="hub-tab-profile"${current==='profile'?'':' hidden'}><header class="hub-head"><h1>Профиль</h1></header><div id="hub-profile-host"><p class="muted">Загружаем профиль…</p></div></section>
      <section class="hub-panel" id="hub-panel-account" role="tabpanel" aria-labelledby="hub-tab-account"${current==='account'?'':' hidden'}><header class="hub-head"><h1>Аккаунт и вход</h1></header>
        <div class="hub-card"><div class="hub-row"><div><strong>Электронная почта</strong><small>${escapeHtml(user.email)}</small></div><span class="pill ${user.email_verified?'status-accepted':'status-draft'}">${user.email_verified?'Подтверждена':'Не подтверждена'}</span></div>
        <div class="hub-row"><div><strong>Публичный ID</strong><small>По нему вас находят в центре общения. Почта не раскрывается.</small></div><span class="hub-id"><code id="hub-public-id">…</code><button class="icon-button" type="button" id="hub-copy-id" aria-label="Скопировать ID" title="Скопировать ID">${icon('copy')}</button></span></div>
        <div class="hub-row"><div class="hub-photo"><span class="hub-avatar sidebar-avatar" aria-hidden="true">${userAvatarMarkup(user)}</span><div><strong>Фото профиля</strong><small>${yandexPhoto}</small></div></div><a class="btn" id="hub-yandex-photo" href="/api/auth/oauth/yandex/start?link=1">${icon('refresh')}Подтянуть из Яндекса</a></div></div>
      </section>
      <section class="hub-panel" id="hub-panel-assistant" role="tabpanel" aria-labelledby="hub-tab-assistant"${current==='assistant'?'':' hidden'}><header class="hub-head"><h1>Ассистент</h1></header><div class="settings-page"><section id="settings-personalization" class="settings-personalization-host"></section></div></section>
      <section class="hub-panel" id="hub-panel-appearance" role="tabpanel" aria-labelledby="hub-tab-appearance"${current==='appearance'?'':' hidden'}><header class="hub-head"><h1>Внешний вид</h1></header><div class="hub-card"><div class="hub-row"><div><strong>Тема</strong><small>Тёмная бережёт глаза вечером, светлая удобнее на ярком солнце.</small></div><button class="btn" id="theme-alt" type="button">Сменить тему</button></div></div></section>
      <section class="hub-panel" id="hub-panel-data" role="tabpanel" aria-labelledby="hub-tab-data"${current==='data'?'':' hidden'}><header class="hub-head"><h1>Данные и экспорт</h1></header><div class="settings-page"><section id="settings-export" class="settings-export-host"></section></div></section>
      <section class="hub-panel" id="hub-panel-danger" role="tabpanel" aria-labelledby="hub-tab-danger"${current==='danger'?'':' hidden'}><header class="hub-head"><h1>Удаление аккаунта</h1><p>Необратимое действие — сметы и доступ будут удалены.</p></header><div class="hub-card hub-danger"><p>Скачайте архив данных перед удалением. После подтверждения восстановить аккаунт будет нельзя.</p><button class="btn danger" id="delete-account" type="button">Удалить мой аккаунт</button></div></section>
    </div>
  </section>`);
  bindRailToggle(document.querySelector('#hub-rail-toggle'),document.querySelector('.hub'),'smetra.hub.rail-collapsed');
  const tabs=[...document.querySelectorAll('[data-hub-tab]')];
  const select=(id,focus=false)=>{
    tabs.forEach(button=>{const on=button.dataset.hubTab===id;button.setAttribute('aria-selected',String(on));button.tabIndex=on?0:-1;if(on&&focus)button.focus()});
    document.querySelectorAll('.hub-panel').forEach(panel=>panel.hidden=panel.id!=='hub-panel-'+id);
    if(id!=='profile')try{sessionStorage.setItem('smetra.settings.tab',id)}catch{}
    const route=id==='profile'?'profile':'settings';
    if(tab!==route){tab=route;history.replaceState({},'',location.pathname+location.search+'#'+route);document.querySelectorAll('#sidebar [data-tab]').forEach(button=>button.classList.toggle('active',button.dataset.tab===route));$('#sidebar-profile')?.classList.toggle('active',route==='profile')}
  };
  tabs.forEach(button=>button.onclick=()=>select(button.dataset.hubTab));
  document.querySelector('.hub-tabs').addEventListener('keydown',event=>{const index=tabs.findIndex(button=>button.getAttribute('aria-selected')==='true');const step={ArrowDown:1,ArrowRight:1,ArrowUp:-1,ArrowLeft:-1}[event.key];if(!step)return;event.preventDefault();select(tabs[(index+step+tabs.length)%tabs.length].dataset.hubTab,true)});
  syncThemeLabel();$('#theme-alt')?.addEventListener('click',theme);
  const deleteAccountButton=$('#delete-account');
  if(deleteAccountButton)deleteAccountButton.onclick=async event=>{const button=event.currentTarget;if(button.disabled)return;button.disabled=true;let confirmed=false;try{confirmed=await window.SmetraDialog.confirm({title:'Удалить аккаунт?',message:'Аккаунт, сметы и доступ будут удалены без возможности восстановления.',confirmLabel:'Удалить аккаунт',danger:true});if(!confirmed||user!==owner)return;await api('/me',{method:'DELETE'});if(user!==owner)return;sessionStorage.removeItem('mobile_token');sessionStorage.removeItem('workspace_id');window.Workspace?.reset();user=null;showAuth()}catch(err){if(user===owner)notify(err.message)}finally{if(button.isConnected)button.disabled=false}};
  api('/profile/id').then(result=>{const code=$('#hub-public-id');if(code&&active())code.textContent=result.public_id||'не задан'}).catch(()=>{const code=$('#hub-public-id');if(code)code.textContent='недоступен'});
  $('#hub-copy-id')?.addEventListener('click',async()=>{const value=$('#hub-public-id')?.textContent||'';try{await navigator.clipboard.writeText(value);notify('ID скопирован')}catch{notify('Ваш ID: '+value)}});
  if(window.SmetraProfile){await window.SmetraProfile.render(active,$('#hub-profile-host'));if(!active())return;await window.SmetraProfile.settings(active);if(!active())return;}
  if(window.SmetraLoadFeature){await window.SmetraLoadFeature('dataExport');if(!active())return;window.SmetraDataExport.render();}
}
function emailNotice(){return user && !user.email_verified && window.SmetraEmailDeliveryAvailable===true ? '<div class="panel email-notice"><strong>Подтвердите почту</strong><p class="muted">Перед оплатой откройте ссылку из письма.</p><button class="btn small" data-resend="1">Отправить письмо повторно</button></div>' : ''}
function header(title, subtitle, action='') { return `<div class="topline"><div><h1>${title}</h1>${subtitle?`<p class="muted">${subtitle}</p>`:''}</div>${action?`<div class="topline-actions">${action}</div>`:''}</div>${emailNotice()}`; }
// Mailboxes for questions that do not fit a chat (documents, company contracts).
const supportContacts='<p class="support-contacts">Почта: <a href="mailto:support@smetra.online">support@smetra.online</a><span aria-hidden="true"> · </span>Документы: <a href="mailto:docs@smetra.online">docs@smetra.online</a><span aria-hidden="true"> · </span>Для компаний: <a href="mailto:sales@smetra.online">sales@smetra.online</a></p>';
function quoteCard(q) {
  const label={draft:'Черновик',sent:'Отправлено',accepted:'Согласовано',declined:'Отказ',completed:'Завершено'}[q.status];
  return `<div class="quote"><div><strong>${escapeHtml(q.title)}</strong><small>${escapeHtml(q.client)} · ${date(q.created_at)} · <span class="pill status-pill status-${escapeHtml(q.status)}">${label}</span></small></div><div class="quote-actions"><b>${rub(q.amount_kopecks)}</b>${q.status==='draft'?`<button class="btn small" data-action="send" data-id="${q.id}">Отправить</button>`:''}${q.status==='sent'?`<button class="btn small" data-action="copy" data-url="${escapeHtml(q.public_url)}">Ссылка</button><button class="btn small" data-action="decline" data-id="${q.id}">Отказ</button>`:''}${q.status==='accepted'?`<button class="btn small" data-action="complete" data-id="${q.id}">Завершить</button>`:''}<button class="btn small danger" data-action="remove" data-id="${q.id}" title="Удалить">Удалить</button></div></div>`;
}
function quoteList() { return quotes.length?quotes.map(quoteCard).join(''):'<div class="empty"><h3>Здесь пока пусто</h3><p>Создайте первое предложение, чтобы отправить клиенту точную стоимость.</p></div>'; }
// Section modules are deferred scripts after this one; the first render must
// not run before they have executed (a fast session check could win the race).
let sectionModulesLoaded=document.readyState==='complete';
const sectionModulesReady=new Promise(resolve=>{const done=()=>{sectionModulesLoaded=true;resolve()};if(sectionModulesLoaded)return done();document.addEventListener('DOMContentLoaded',done,{once:true});addEventListener('load',done,{once:true});setTimeout(done,4000)});
async function render() {
  if(pendingPageLoadingTimer!==null){clearTimeout(pendingPageLoadingTimer);pendingPageLoadingTimer=null;}
  window.SmetraQuoteEditor?.leave();
  if(!user)return;
  if(!sectionModulesLoaded){await sectionModulesReady;if(!user)return;}
  const owner=user,section=tab,mine=++renderRevision;
  const active=()=>mine===renderRevision&&user===owner&&tab===section;
  for(const b of document.querySelectorAll('[data-tab]'))b.classList.toggle('active',b.dataset.tab===tab);
  $('#sidebar-profile')?.classList.toggle('active',tab==='profile');
  const contentBefore=$('#content');
  const initialMarkup=contentBefore?.innerHTML;
  const initialSection=contentBefore?.dataset.section;
  const loadingTimer=setTimeout(()=>{
    const content=$('#content');
    // Never replace a section that has already rendered while a lazy module is still resolving.
    if(active()&&content&&content.innerHTML===initialMarkup&&initialSection!==section)view(loadingView(section));
  },180);pendingPageLoadingTimer=loadingTimer;
  try {
    const feature=({assistant:'assistant',profile:'profile',settings:'profile',construction:'construction',calculators:'calculators',admin:'admin',billing:'growth',premium:'premiumTools',chats:'objectChats'})[section];
    if(feature&&window.SmetraLoadFeature){await window.SmetraLoadFeature(feature);if(!active())return;}
    if(tab==='assistant' && window.SmetraAssistant){await window.SmetraAssistant(active);return;}
    if(tab==='profile'||tab==='settings'){await renderAccountHub(active);return;}
    if(tab==='construction' && window.SmetraConstruction){await window.SmetraConstruction();return;}
    if(tab==='calculators' && window.SmetraCalculators){window.SmetraCalculators.render();return;}
    if(tab==='premium' && window.SmetraPremiumTools){await window.SmetraPremiumTools.render(active);return;}
    if(tab==='chats'&&window.SmetraObjectChats){await window.SmetraObjectChats.render(active);return;}
    if(['fieldwork','inbox'].includes(tab)&&window.SmetraFieldFlows){await window.SmetraFieldFlows.render(tab,active);return;}
    const handled=window.Workspace && await window.Workspace.render(tab);
    if(!active()||handled)return;
    if(tab==='dashboard'||tab==='quotes') {
      await loadQuotes();
      if(!active())return;
      const counts={sent:quotes.filter(x=>x.status==='sent').length,accepted:quotes.filter(x=>x.status==='accepted').length};
      const stats=tab==='dashboard'?`<div class="stats"><div class="stat"><strong>${user.quote_count}</strong><span>Создано всего</span></div><div class="stat"><strong>${counts.sent}</strong><span>Ожидают ответа</span></div><div class="stat"><strong>${counts.accepted}</strong><span>Согласованы</span></div></div>`:'';
      view(header(tab==='dashboard'?'Обзор':'Предложения',`Здравствуйте, ${escapeHtml(user.name)}. Всё по текущим клиентам здесь.`, '<button class="btn primary" id="new-quote">Создать предложение</button>')+stats+`<section class="panel"><div class="toolbar"><h3>Ваши предложения</h3><input id="search" type="search" placeholder="Найти по названию или клиенту" aria-label="Поиск" class="search-input"></div><div id="quote-list">${quoteList()}</div><button class="btn small" id="next-page">Показать ещё</button></section>`);
      let searchTimer;$('#search').addEventListener('input',(e)=>{clearTimeout(searchTimer);searchTimer=setTimeout(async()=>{try{await loadQuotes(e.target.value);$('#quote-list').innerHTML=quoteList();}catch(err){notify(err.message)}},250)});
      $('#next-page').addEventListener('click',async()=>{try{const r=await api('/quotes?offset='+quotes.length+'&q='+encodeURIComponent($('#search').value));quotes.push(...r.quotes);$('#quote-list').innerHTML=quoteList();if(!r.quotes.length)notify('Больше предложений нет')}catch(err){notify(err.message)}});
      $('#new-quote').addEventListener('click',showNewQuote);
      $('#quote-list').addEventListener('click',quoteAction);
    } else if(tab==='billing') {
      await window.SmetraGrowth.billing(active);
    } else if(tab==='support') {
      await window.SmetraSupport.render(active);
    } else if(tab==='admin'&&user.role==='admin') {
      await window.SmetraAdmin();
    } else {tab='dashboard';history.replaceState({},'',location.pathname+location.search+'#dashboard');return render()}
  } catch(err) { if(!active())return;view(`<section class="load-error" role="alert"><span class="load-error-mark" aria-hidden="true">!</span><span class="load-error-kicker">СМЕТРА / ЗАГРУЗКА РАЗДЕЛА</span><h2>Не удалось загрузить раздел</h2><p class="muted">${escapeHtml(err.message)}</p><button class="btn primary" id="retry">Повторить</button></section>`);$('#retry').onclick=render; } finally {clearTimeout(loadingTimer);if(pendingPageLoadingTimer===loadingTimer)pendingPageLoadingTimer=null;}
}
window.render=render;
const appSections=new Set(['fieldwork','inbox','chats','premium','dashboard','clients','quotes','projects','construction','calculators','leads','tasks','calendar','assistant','finance','catalog','files','documents','team','notifications','activity','billing','support','profile','settings','admin']);
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
async function quoteAction(e){const b=e.target.closest('[data-action]');if(!b)return;const action=b.dataset.action;try{if(action==='send'&&window.SmetraEstimateSafety&&!(await window.SmetraEstimateSafety.confirmReview()))return;if(action==='copy'){await navigator.clipboard.writeText(b.dataset.url);notify('Ссылка скопирована');return;}if(action==='remove'){if(!confirm('Удалить предложение?'))return;await api('/quotes/'+b.dataset.id,{method:'DELETE'});user.quote_count--;}else{const status={send:'sent',decline:'declined',complete:'completed'}[action];const result=await api('/quotes/'+b.dataset.id,{method:'PATCH',body:JSON.stringify({status})});if(action==='send'){try{await navigator.clipboard.writeText(result.quote.public_url);notify('Отправлено. Ссылка скопирована')}catch{notify('Отправлено. Ссылка: '+result.quote.public_url)}}}await render()}catch(err){notify(err.message)}}
if($('#auth')){
  const syncEmailActions=()=>{
    if(new URLSearchParams(location.search).has('reset')){$('#forgot').classList.add('hidden');$('#name').required=false;return;}
    const providerOnly=registering&&window.SmetraEmailSignupAvailable===false;
    const divider=$('.auth-provider-divider span');if(divider)divider.textContent=providerOnly?'Продолжить через сервис':'или используйте российский сервис';
    $('#forgot').classList.toggle('hidden',registering||window.SmetraEmailDeliveryAvailable!==true);
    $('#email-disclosure').classList.toggle('hidden',providerOnly);
    $('#name').required=registering&&!providerOnly;
    $('#auth').dataset.mode=registering?'register':'login';
    $('#legal-consent-field').classList.toggle('hidden',!registering);
    $('#legal-consent').required=registering;
    $('#auth-submit').disabled=registering&&!$('#legal-consent').checked;
    document.querySelectorAll('#provider-buttons button').forEach(button=>{button.disabled=registering&&!$('#legal-consent').checked;});
    if(providerOnly)$('#auth-copy').textContent='Создайте аккаунт через доступный сервис ниже. Один профиль для сайта и приложения.';
  };
  $('#legal-consent').addEventListener('change',syncEmailActions);
  document.addEventListener('smetra:email-capability',syncEmailActions);syncEmailActions();
  const setAuthMode=(mode)=>{registering=mode==='register';$('#auth').dataset.mode=registering?'register':'login';$('#legal-consent').checked=false;$('#legal-consent').required=registering;$('#legal-consent-field').classList.toggle('hidden',!registering);$('#auth-submit').disabled=registering;$('#auth-title').textContent=registering?'Ваша работа начинается здесь.':'С возвращением.';$('#auth-copy').textContent=registering?'Создайте пространство для смет, клиентов и заказов. Первые 10 смет бесплатно.':'Продолжите работу с того места, где остановились.';$('#auth-submit').innerHTML=registering?'Создать пространство <span aria-hidden="true">↗</span>':'Войти в пространство <span aria-hidden="true">↗</span>';$('#name-field').classList.toggle('hidden',!registering);$('#name').required=registering;$('#forgot').classList.toggle('hidden',registering||window.SmetraEmailDeliveryAvailable!==true);$('#password').value='';$('#password').autocomplete=registering?'new-password':'current-password';$('#auth-login-tab').setAttribute('aria-selected',String(!registering));$('#auth-register-tab').setAttribute('aria-selected',String(registering));$('#auth-login-tab').tabIndex=registering?-1:0;$('#auth-register-tab').tabIndex=registering?0:-1;$('#auth-form-error').textContent='';$('#email-disclosure').open=true};
  $('#auth-login-tab').onclick=()=>{setAuthMode('login');syncEmailActions()};
  $('#auth-register-tab').onclick=()=>{setAuthMode('register');syncEmailActions()};
  $('.auth-tabs').onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const mode=event.key==='Home'?'login':event.key==='End'?'register':registering?'login':'register';setAuthMode(mode);syncEmailActions();$(mode==='login'?'#auth-login-tab':'#auth-register-tab').focus()};
  $('#auth-form').onsubmit=async(e)=>{e.preventDefault();const button=$('#auth-submit');if(button.disabled||(registering&&window.SmetraEmailSignupAvailable===false))return;if(registering&&!$('#legal-consent').checked){$('#auth-form-error').textContent='Примите условия и предупреждение перед регистрацией.';return}const attempt=++authRevision;button.disabled=true;$('#auth-form-error').textContent='';try{const result=await api('/auth/'+(registering?'register':'login'),{method:'POST',body:JSON.stringify({email:$('#email').value.trim(),password:$('#password').value,name:$('#name').value.trim(),...(registering?{legal_acceptance:$('#legal-consent').checked,legal_version:REGISTRATION_CONSENT_VERSION}:{})})});if(attempt!==authRevision)return;await window.SmetraCompleteAuth(result.user)}catch(err){if(attempt===authRevision)$('#auth-form-error').textContent=err.message}finally{button.disabled=false}};
  $('#forgot').onclick=async event=>{const button=event.currentTarget;if(button.disabled||window.SmetraEmailDeliveryAvailable!==true)return;const email=$('#email').value.trim();if(!email){$('#auth-form-error').textContent='Сначала укажите почту';$('#email').focus();return}button.disabled=true;try{await api('/auth/reset/request',{method:'POST',body:JSON.stringify({email})});$('#auth-status').textContent='Если адрес зарегистрирован, мы отправили письмо для сброса пароля.'}catch(err){$('#auth-form-error').textContent=err.message}finally{button.disabled=false}};
  $('#content').addEventListener('click',async(e)=>{const button=e.target.closest('[data-resend]');if(!button||button.disabled||window.SmetraEmailDeliveryAvailable!==true)return;button.disabled=true;try{await api('/auth/verify/resend',{method:'POST'});notify('Письмо отправлено')}catch(err){notify(err.message)}});
   document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{const next=b.dataset.tab;if(tab===next){closeNavigation();return;}closeNavigation();tab=next;if(location.hash.slice(1)!==next)location.hash=next;return renderNavigation();});
  $('#sidebar-profile').onclick=()=>{if(tab==='profile'){closeNavigation();return;}closeNavigation();tab='profile';if(location.hash.slice(1)!=='profile')location.hash='profile';return renderNavigation();};
  $('#nav-backdrop').classList.remove('hidden');
  $('#nav-toggle').onclick=()=>{syncMobileSidebarGeometry();const open=!document.body.classList.contains('nav-open');document.body.classList.toggle('nav-open',open);$('#nav-toggle').setAttribute('aria-expanded',String(open));$('#nav-toggle').setAttribute('aria-label',open?'Закрыть разделы':'Открыть разделы');syncSidebarAccess()};
  try{document.body.classList.toggle('sidebar-compact',localStorage.getItem('smetra.sidebar-compact')==='true'&&!matchMedia('(max-width:800px)').matches)}catch{}
  enhanceSidebarNavigation();syncSidebarCollapseButton();
  $('#sidebar-collapse').onclick=()=>{if(matchMedia('(max-width:800px)').matches)return;const compact=document.body.classList.toggle('sidebar-compact');try{localStorage.setItem('smetra.sidebar-compact',String(compact))}catch{}syncSidebarCollapseButton();syncSidebarAccess()};
  matchMedia('(max-width:800px)').addEventListener('change',()=>{closeNavigation();syncSidebarCollapseButton()});
  window.addEventListener('resize',syncMobileSidebarGeometry,{passive:true});
  syncMobileSidebarGeometry();syncSidebarAccess();
  $('#nav-backdrop').onclick=closeNavigation;
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.body.classList.contains('nav-open')){closeNavigation();$('#nav-toggle').focus()}});
  $('#logout').onclick=async()=>{window.SmetraFieldFlows?.stop?.();const button=$('#logout');if(button.disabled)return;button.disabled=true;const attempt=++authRevision;try{await api('/auth/logout',{method:'POST'})}catch{}finally{button.disabled=false}if(attempt!==authRevision)return;sessionStorage.removeItem('mobile_token');sessionStorage.removeItem('workspace_id');window.Workspace?.reset();user=null;showAuth()};
  const params=new URLSearchParams(location.search);
  if(/^[a-f0-9-]{36}$/.test(params.get('share')||'')){
    try{sessionStorage.setItem('smetra.pendingShare',params.get('share'))}catch{}
  }
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
    let pendingShare='';
    try{pendingShare=sessionStorage.getItem('smetra.pendingShare')||''}catch{}
    if(params.has('share')||/^[a-f0-9-]{36}$/.test(pendingShare)){tab='inbox';}
    const bootRevision=authRevision;
    const boot=async()=>{
      const label=$('#app-startup-label');
      if(label)label.textContent='Проверяем сессию…';
      if($('#app-startup-retry'))$('#app-startup-retry').hidden=true;
      await verificationTask;
      if(bootRevision!==authRevision)return;
      let result;
      try{result=await api('/me')}
      catch(error){
        if(bootRevision!==authRevision)return;
        if(error.status===401||error.status===403){user=null;showAuth();return}
        showBootError('Соединение не удалось. Повторите попытку.');
        return;
      }
      if(bootRevision!==authRevision)return;
      user=result.user;
      if(params.has('payment')){tab='billing';history.replaceState({},'',location.pathname+location.search+'#billing')}
      await showApp();
    };
    $('#app-startup-retry')?.addEventListener('click',()=>{void boot()});
    void boot();
  }
}
document.addEventListener('DOMContentLoaded',()=>{const params=new URLSearchParams(location.search),intake=params.get('intake'),quote=params.get('quote');if(intake&&document.querySelector('#public-quote'))window.Workspace.intakePage(intake);else if(quote&&document.querySelector('#public-quote'))window.Workspace.publicPage(quote)});
