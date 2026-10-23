/* Activation and paid value. Pricing and entitlements always come from the API. */
(() => {
 const e=escapeHtml;
 const syncRequests=new Map();
 const sessionRevision=()=>typeof authRevision==='number'?authRevision:0;
 function synchronize(key){
  if(syncRequests.has(key))return syncRequests.get(key);
  const request=api('/billing/sync',{method:'POST'});
  syncRequests.set(key,request);
  request.finally(()=>{if(syncRequests.get(key)===request)syncRequests.delete(key)}).catch(()=>{});
  return request;
 }
 const track=(name,source)=>api('/billing/events',{method:'POST',body:JSON.stringify({name,source})}).catch(()=>{});
 const starterNames={repair:'Ремонт',building:'Строительство',installation:'Монтаж',design:'Дизайн',equipment:'Ремонт техники',services:'Услуги',other:'Другое'};
 const starters={repair:['Подготовительные работы','Отделочные работы','Материалы'],building:['Подготовка площадки','Основные работы','Материалы'],installation:['Подготовка к монтажу','Монтаж','Проверка и запуск'],design:['Концепция','Разработка проекта','Подготовка материалов'],equipment:['Диагностика','Ремонт','Запасные части'],services:['Подготовка','Основная работа','Передача результата'],other:['Работа']};
 function start(goal='estimate'){
  const owner=user;
  view(`<section class="activation-page"><span class="overline">Первая полезная смета</span><h1>Что нужно рассчитать?</h1><p class="muted">Выберите основу. Останется указать клиента, объёмы и ваши цены.</p><div class="activation-starters">${Object.keys(starters).map(key=>`<button class="btn" type="button" data-starter="${key}"><img class="icon" src="/assets/icons/file-text.svg" alt="">${starterNames[key]}<span aria-hidden="true">↗</span></button>`).join('')}</div><button class="btn" id="activation-blank" type="button">Начать с пустой сметы</button><button class="btn" id="activation-back" type="button">Назад</button><p class="note">Заготовки не содержат рыночных цен. Итог рассчитаете по своим условиям.</p></section>`);
  document.querySelector('#activation-back').onclick=()=>render();
  document.querySelector('#activation-blank').onclick=()=>Workspace.editor();
  document.querySelectorAll('[data-starter]').forEach(button=>button.onclick=()=>{if(user!==owner)return;const key=button.dataset.starter;Workspace.editor({title:(goal==='proposal'?'Предложение · ':goal==='order'?'Заказ · ':'')+starterNames[key],description:'',items:starters[key].map(name=>({name,quantity:'1',unit:'усл.',unit_price:0,cost_price:0,included:true,optional:false}))})});
 }
 function onboarding(host){
  if(!host||user.quote_count>0||host.querySelector('.activation-intro'))return;
  host.insertAdjacentHTML('afterbegin',`<section class="activation-intro"><span class="overline">Начните с результата</span><h2>Что хотите сделать?</h2><div class="row wrap"><button class="btn primary" data-activation="estimate">Создать смету</button><button class="btn" data-activation="order">Рассчитать заказ</button><button class="btn" data-activation="proposal">Подготовить предложение</button></div><p class="note">Первая смета бесплатно. Ссылку и PDF можно отправить клиенту.</p></section>`);
  host.querySelectorAll('[data-activation]').forEach(button=>button.onclick=()=>start(button.dataset.activation));
 }
 async function paywall(source='other'){
  if(!user||user.plan==='pro')return;
  const key='smetra.paywall.'+user.id+'.'+source;
  if(Date.now()-Number(sessionStorage.getItem(key)||0)<1800000)return;
  sessionStorage.setItem(key,String(Date.now()));
  // Keep the user's draft and working page intact. Never interrupt with a modal.
  const old=document.querySelector('.contextual-upgrade');old?.remove();
  track('paywall_viewed',source);
  // The assistant already has an inline quota link; don't push its transcript down with a banner.
  if(tab==='assistant')return;
  const notice=document.createElement('section');notice.className='contextual-upgrade';notice.setAttribute('role','status');
  notice.innerHTML='<div><strong>Продолжите работу в Про</strong><p>Больше смет и помощи ассистента. Ваши данные и черновик сохранятся.</p></div><button class="btn primary" type="button">Посмотреть Про</button><button class="icon-button" type="button" aria-label="Закрыть предложение">×</button>';
  document.querySelector('#content')?.prepend(notice);
  notice.querySelector('.icon-button').onclick=()=>notice.remove();notice.querySelector('.primary').onclick=()=>{document.querySelector('#local-draft')?.click();sessionStorage.setItem('smetra.checkout.return.'+user.id,tab);sessionStorage.setItem('smetra.paywall.source',source);track('upgrade_clicked',source);tab='billing';location.hash='billing';render()};
 }
 async function billing(active){
  const owner=user,revision=sessionRevision(),[b,space]=await Promise.all([api('/billing'),api('/workspace')]);if(!active()||sessionRevision()!==revision)return;
  const pricing=b.pricing;
  if(!pricing)throw Error('Не удалось получить условия тарифа. Повторите загрузку.');
  const source=sessionStorage.getItem('smetra.paywall.source')||'pricing_page';
  const pro=owner.plan==='pro'&&owner.entitlement_until>Date.now()/1000;
  const ready=b.email_verified&&['test','live'].includes(b.checkout_mode);
  const ownSpace=space.workspace?.owner_id===owner.id;
  const note=b.checkout_mode==='off'?'Оплата временно недоступна. Ваш текущий доступ сохраняется.':!b.email_verified?'Для оплаты нужна подтверждённая почта аккаунта.':b.checkout_mode==='test'?'Тестовый режим: деньги не списываются.':'Защищённая оплата через ЮKassa. Без автоматических списаний.';
  const pending=b.payments.find(p=>p.status==='pending');
  const recent=b.payments[0];
  const paymentNames={pending:'Ожидает оплаты',succeeded:'Оплачено',canceled:'Отменено',refunded:'Возврат'};
  const monthlyPrice=pricing.plans.pro_month.amount_kopecks;
  const annualSaving=pricing.annual_saving_kopecks;
  const annualSavingPct=Math.round(annualSaving/(monthlyPrice*12)*100);
  const monthlyPurchaseBonus=Number(pricing.purchase_bonus?.pro_month||0);
  const annualPurchaseBonus=Number(pricing.purchase_bonus?.pro_year||0);
  const paymentHistory=b.payments.length?b.payments.map(p=>'<div class="record-line billing-history-row"><div><strong>Про · '+(p.plan==='pro_year'?'год':'31 день')+'</strong><small>'+date(p.created_at)+' · '+e(paymentNames[p.status]||p.status)+'</small></div><b>'+rub(p.amount_kopecks)+'</b></div>').join(''):'<p class="muted">Здесь появятся ваши оплаты подписки.</p>';
  view(`<section class="revenue-billing billing-v2">
   <header class="billing-hero">
    <div class="billing-hero-copy"><span class="overline billing-eyebrow">СМЕТРА / PRO</span><div class="billing-plan-status"><span class="billing-status-dot" aria-hidden="true"></span>${pro?'Подписка активна': 'План Старт · '+pricing.limits.free_quotes+' смет бесплатно'}</div>
     <h1>${pro?'Продолжайте работать без лишних шагов.':'Больше сделанной работы.<br><span>Меньше рутины.</span>'}</h1>
     <p class="billing-hero-lead">Сметы, документы, клиенты и помощь ИИ — в одном рабочем пространстве. Понятный тариф без автосписаний и сюрпризов.</p>
     <div class="billing-trust-row"><span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8 12h8"/></svg>Без автопродления</span><span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 1 1 8 0v3"/></svg>Оплата через ЮKassa</span><span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 8h10M7 12h6M7 16h8"/></svg>Сайт и Android</span></div>
    </div>
    <aside class="billing-hero-stats" aria-label="Возможности Сметра Про">
     <div class="billing-hero-stat"><strong>${pricing.limits.pro_quotes.toLocaleString('ru-RU')}</strong><span>смет и предложений</span></div>
     <div class="billing-hero-stat"><strong>${pricing.limits.pro_ai}</strong><span>сообщений ИИ каждый месяц</span></div>
     <div class="billing-hero-stat-note">Один профиль.<br>Все рабочие процессы.</div>
    </aside>
   </header>
   <section class="payment-recovery" ${pending||recent?.status==='canceled'||new URLSearchParams(location.search).has('payment')?'':'hidden'}><div><strong>${pending?'Оплата не завершена':pro?'Про активирован':'Оплата не завершена'}</strong><p class="muted">${pending?'Вы можете продолжить оплату или проверить её статус.':pro?'Доступ уже действует на всех устройствах.':'Повторная попытка не изменит ваш текущий тариф.'}</p></div><div class="row wrap">${pending&&ready?'<button class="btn primary" id="checkout-resume" type="button">Продолжить оплату</button>':''}<button class="btn" id="payment-continue" type="button">Продолжить работу</button></div></section>
   <section class="billing-purchase" aria-labelledby="billing-purchase-title">
    <div class="billing-section-heading"><div><span class="overline">ТАРИФ И ОПЛАТА</span><h2 id="billing-purchase-title">${pro?'Продлите Сметра Про':'Выберите удобный срок'}</h2><p>Оплачиваете выбранный период один раз. Автоматического списания не будет.</p></div><span class="billing-secure-mark"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3 20 6v5c0 5-3.4 8.3-8 10-4.6-1.7-8-5-8-10V6z"/><path d="m9 12 2 2 4-4"/></svg>Прозрачная цена</span></div>
    <div class="billing-audience-switch" role="tablist" aria-label="Категория тарифов">
      <button type="button" role="tab" aria-selected="true" aria-controls="billing-plan-carousel" data-plan-audience="personal"><strong>Для себя</strong><small>Для индивидуальной работы</small></button>
      <button type="button" role="tab" aria-selected="false" aria-controls="billing-plan-carousel" data-plan-audience="business"><strong>Бизнес</strong><small>Для снабжения и команды</small></button>
     </div>
     <p class="billing-audience-description" id="billing-audience-description">Профессиональные инструменты для одного специалиста без лишних расходов.</p>
     <div class="billing-plan-carousel" id="billing-plan-carousel" role="region" aria-roledescription="карусель" aria-label="Тарифы для себя">
      <div class="billing-carousel-toolbar"><button type="button" class="billing-carousel-arrow" data-carousel-move="-1" aria-label="Предыдущий тариф">←</button><span id="billing-carousel-position" aria-live="polite">1 из 2</span><button type="button" class="billing-carousel-arrow" data-carousel-move="1" aria-label="Следующий тариф">→</button></div>
      <div class="billing-carousel-viewport"><div class="billing-carousel-track" id="billing-plan-track"></div></div>
      <div class="billing-carousel-dots" id="billing-carousel-dots" aria-label="Выбрать тариф"></div>
     </div>
     <p class="billing-payment-note billing-carousel-payment-note">${e(note)}</p><p id="checkout-error" role="alert" aria-live="polite"></p>
     <div class="billing-guarantee-line"><span aria-hidden="true">✓</span><span>Оплата после подтверждения платёжным провайдером. Без автоматических списаний.</span></div>
     <div class="billing-branding-row" id="billing-branding-row"></div>
   </section>
   <section class="billing-history"><div class="billing-section-heading billing-history-heading"><div><span class="overline">ИСТОРИЯ</span><h2>Ваши оплаты</h2></div><button class="btn small" id="sync" type="button">Проверить статус</button></div>${paymentHistory}</section>
   <section class="billing-referral"><div class="billing-section-heading"><div><span class="overline">ДЕЛИТЕСЬ С КОЛЛЕГАМИ</span><h2>Пригласите коллегу</h2><p class="muted">Вы получите 3 дополнительных сообщения ассистенту, когда коллега создаст первую смету. До 30 бонусных сообщений в месяц.</p></div><button class="btn billing-referral-button" type="button" id="referral-copy"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>Скопировать приглашение</button></div><span id="referral-status" role="status"></span></section>
   <p class="note billing-legal">Оплату принимает самозанятый МУРАВЬЕВ КОНСТАНТИН АЛЕКСЕЕВИЧ · ИНН 713304603876. <a href="/terms">Условия оплаты и возврата</a> · <a href="/contacts">Контакты</a></p></section>`);
  const launchOffer=document.querySelector('#billing-launch-offer');
  if(pricing.launch_offer&&launchOffer){launchOffer.hidden=false;launchOffer.textContent=e(pricing.launch_offer.label)+' · до '+date(pricing.launch_offer.until);}
  const checkoutError=document.querySelector("#checkout-error");
  const carousel=document.querySelector("#billing-plan-carousel");
  const carouselTrack=document.querySelector("#billing-plan-track");
  const carouselDots=document.querySelector("#billing-carousel-dots");
  const carouselPosition=document.querySelector("#billing-carousel-position");
  const audienceDescription=document.querySelector("#billing-audience-description");
  const audiencePlans={personal:["pro_month","pro_year"],business:["pro_plus_month","pro_team_month","pro_team_year"]};
  let audience="personal",activeSlide=0;
  const planByCode=Object.fromEntries(pricing.catalog.map(item=>[item.code,item]));
  const plansForAudience=()=>audiencePlans[audience].map(code=>planByCode[code]).filter(Boolean);
  function renderPlanCard(item,index,total){
   const yearly=item.period==="year",team=item.tier==="team",plus=item.tier==="plus";
   const monthlyEquivalent=yearly?Math.round(item.amount_kopecks/12):item.amount_kopecks;
   const saving=item.code==="pro_year"?annualSaving:item.code==="pro_team_year"?pricing.team_annual_saving_kopecks:0;
   const badge=team?"До 5 участников":plus?"Учёт финансов и фирменные бланки":yearly?"Оплата за год со скидкой":"Для одного специалиста";
   const bonus=Number(pricing.purchase_bonus?.[item.code]||0);
   return '<article class="billing-carousel-slide" role="group" aria-roledescription="слайд" aria-label="'+(index+1)+' из '+total+'">'+
    '<div class="billing-carousel-card '+(team?'is-business':'')+(yearly?' is-annual':'')+'">'+
     '<div class="billing-carousel-card-top"><span class="billing-plan-kicker">'+(team?"СМЕТРА / TEAM":plus?"СМЕТРА / PRO ПЛЮС":"СМЕТРА / PRO SOLO")+'</span><span class="billing-plan-badge">'+e(badge)+'</span></div>'+
     '<h3>'+e(item.title)+'</h3>'+
     '<div class="billing-carousel-price"><strong>'+rub(item.amount_kopecks)+'</strong><span>/ '+(yearly?"год":"месяц")+'</span></div>'+
     '<p class="billing-carousel-term">'+(yearly?"Годовой доступ · "+rub(monthlyEquivalent)+" в месяц в пересчёте":"Один платёж · доступ на 31 день")+'</p>'+
     (saving>0?'<p class="billing-carousel-saving">Экономия за год — '+rub(saving)+'</p>':'')+
     '<ul class="billing-carousel-features">'+item.features.map(feature=>'<li>'+e(feature)+'</li>').join('')+'</ul>'+
     (bonus>0?'<div class="billing-carousel-bonus">+'+bonus+' бонусных сообщений ассистента после подтверждения оплаты</div>':'')+
     '<button type="button" class="btn primary billing-carousel-checkout" data-plan-choice="'+e(item.code)+'" '+(ready?'':'disabled')+'><span>'+(ready?'Выбрать тариф':'Оплата недоступна')+'</span><span aria-hidden="true">↗</span></button>'+
     '<p class="billing-carousel-trust">Без автоматического продления. Цена фиксируется до перехода к оплате.</p>'+
    '</div></article>';
  }
  function renderCarousel(requestedCode){
   const items=plansForAudience();
   if(requestedCode){const idx=items.findIndex(item=>item.code===requestedCode);if(idx>=0)activeSlide=idx}
   activeSlide=Math.max(0,Math.min(activeSlide,items.length-1));
   if(!items.length){carouselTrack.innerHTML='<p class="muted">Тарифы не найдены.</p>';carouselDots.innerHTML="";carouselPosition.textContent="0 из 0";return}
   carouselTrack.innerHTML=items.map((item,index)=>renderPlanCard(item,index,items.length)).join("");
   carouselTrack.style.transform="translateX(-"+(activeSlide*100)+"%)";
   carouselDots.innerHTML=items.map((item,index)=>'<button type="button" class="billing-carousel-dot" data-carousel-index="'+index+'" aria-label="Тариф: '+e(item.title)+'" aria-current="'+(index===activeSlide?'true':'false')+'"></button>').join("");
   carouselPosition.textContent=(activeSlide+1)+" из "+items.length;
   carousel.setAttribute("aria-label",audience==="business"?"Бизнес-тарифы":"Тарифы для себя");
   audienceDescription.textContent=audience==="business"?"PRO Плюс добавляет финансы и шаблоны, а TEAM объединяет владельца и до четырёх сотрудников.":"Выберите месячную или годовую подписку PRO Solo с чистым экспортом и приоритетом ИИ.";
   document.querySelectorAll("[data-plan-audience]").forEach(button=>{const isActive=button.dataset.planAudience===audience;button.setAttribute("aria-selected",String(isActive));button.tabIndex=isActive?0:-1});
   carousel.querySelectorAll("[data-carousel-move]").forEach(button=>{button.disabled=items.length<2||(button.dataset.carouselMove==="-1"&&activeSlide===0)||(button.dataset.carouselMove==="1"&&activeSlide===items.length-1)});
   carouselDots.querySelectorAll("[data-carousel-index]").forEach(button=>button.onclick=()=>{activeSlide=Number(button.dataset.carouselIndex);renderCarousel()});
   carousel.querySelectorAll("[data-plan-choice]").forEach(button=>button.onclick=()=>startCheckout(button.dataset.planChoice,button));
  }
  async function startCheckout(selected,button){
   if(button.disabled)return;
   const option=pricing.plans[selected];
   if(!option){checkoutError.textContent="Тариф больше недоступен. Обновите страницу.";return}
   button.disabled=true;
   const keyName="smetra.checkout."+owner.id+"."+selected;
   let key=sessionStorage.getItem(keyName);if(!key){key=crypto.randomUUID();sessionStorage.setItem(keyName,key)}
   track("upgrade_clicked",source);
   if(!sessionStorage.getItem("smetra.checkout.return."+owner.id))sessionStorage.setItem("smetra.checkout.return."+owner.id,"dashboard");
   try{
    const result=await api("/billing/checkout",{method:"POST",headers:{"Idempotency-Key":key},body:JSON.stringify({plan:selected,source,expected_amount_kopecks:option.amount_kopecks})});
    if(!active()||sessionRevision()!==revision)return;
    if(result.status==="canceled"||result.status==="refunded"){sessionStorage.removeItem(keyName);throw Error("Предыдущая оплата завершена отменой или возвратом. Нажмите ещё раз для новой попытки.")}
    if(result.status==="succeeded"){await sync();return}
    if(!result.url||!result.url.startsWith("https://"))throw Error("Платёжный провайдер не вернул безопасную ссылку для оплаты.");
    location.href=result.url;
   }catch(error){if(active()&&sessionRevision()===revision){if(error.status===409){sessionStorage.removeItem(keyName);button.textContent="Обновить условия";button.onclick=()=>render()}checkoutError.textContent=error.message}}
   finally{if(button.isConnected)button.disabled=false}
  }
  document.querySelectorAll("[data-plan-audience]").forEach(button=>button.onclick=()=>{audience=button.dataset.planAudience;activeSlide=0;renderCarousel()});
  carousel.querySelectorAll("[data-carousel-move]").forEach(button=>button.onclick=()=>{activeSlide=Math.max(0,Math.min(plansForAudience().length-1,activeSlide+Number(button.dataset.carouselMove)));renderCarousel()});
  const keyHandler=event=>{if(!carousel.isConnected||!carousel.matches(":hover,:focus-within"))return;if(event.key==="ArrowRight"&&activeSlide<plansForAudience().length-1){activeSlide++;renderCarousel()}else if(event.key==="ArrowLeft"&&activeSlide>0){activeSlide--;renderCarousel()}};
  carousel.addEventListener("keydown",keyHandler);
  let touchStartX=0;
  carousel.addEventListener("touchstart",event=>{touchStartX=event.changedTouches[0]?.clientX??0},{passive:true});
  carousel.addEventListener("touchend",event=>{const endX=event.changedTouches[0]?.clientX??touchStartX,delta=endX-touchStartX;if(Math.abs(delta)>40){const next=activeSlide+(delta<0?1:-1);if(next>=0&&next<plansForAudience().length){activeSlide=next;renderCarousel()}}},{passive:true});
  const retryCancelled=recent&&["canceled","refunded"].includes(recent.status);if(retryCancelled)for(const value of Object.keys(pricing.plans))sessionStorage.removeItem("smetra.checkout."+owner.id+"."+value);
  renderCarousel();
    async function sync(){
   const button=document.querySelector('#sync');if(!active()||sessionRevision()!==revision||!button||button.disabled)return;
   button.disabled=true;
   try{
    const result=await synchronize(owner.id+':'+revision);
    if(!active()||user!==owner||sessionRevision()!==revision)return;
    user=result.user;
    if(user.plan==='pro'&&!result.payments?.some(p=>p.status==='pending'))for(const value of ['pro_month','pro_year'])sessionStorage.removeItem('smetra.checkout.'+owner.id+'.'+value);
    await render();
    if(tab==='billing'&&user?.id===owner.id&&sessionRevision()===revision)notify(result.payments?.some(p=>p.status==='pending')?'Оплата пока не завершена. Текущий доступ сохранён.':user.plan==='pro'?'Про активен. Можно продолжать работу.':'Оплата пока не подтверждена. Доступ остаётся на тарифе Старт.');
   }catch(error){if(active()&&user===owner&&sessionRevision()===revision)notify(error.message)}
   finally{if(button.isConnected)button.disabled=false}
  }
  document.querySelector('#sync').onclick=sync;
  const brandingRow=document.querySelector('#billing-branding-row');
  if(ownSpace&&brandingRow){const hidden=space.workspace.settings?.hide_branding===true;brandingRow.innerHTML='<div class="billing-branding-copy"><strong>Управление брендингом</strong><span>'+(pro?'Настройте оформление новых PDF и клиентских страниц.':'Без отметки Сметры — один из бонусов Pro.')+'</span></div><button class="btn small" id="billing-branding-toggle" type="button" '+(pro?'':'disabled')+'>'+(pro?(hidden?'Вернуть отметку Сметры':'Убрать отметку Сметры'):'Доступно в Pro')+'</button>';const branding=brandingRow.querySelector('button');branding.setAttribute('aria-pressed',String(hidden));branding.onclick=async()=>{if(branding.disabled)return;branding.disabled=true;try{await api('/workspace',{method:'PATCH',body:JSON.stringify({settings:{hide_branding:!hidden}})});if(active())await render();notify('Оформление новых PDF и клиентских страниц обновлено')}catch(error){if(active())notify(error.message)}finally{if(branding.isConnected)branding.disabled=false}};}else if(brandingRow)brandingRow.remove();
  const resume=document.querySelector('#checkout-resume');if(resume)resume.onclick=()=>{if(pending.confirmation_url?.startsWith('https://'))location.href=pending.confirmation_url};
  document.querySelector('#payment-continue').onclick=()=>{const previous=sessionStorage.getItem('smetra.checkout.return.'+owner.id)||'dashboard';tab=['quotes','projects','assistant','documents','files','dashboard'].includes(previous)?previous:'dashboard';history.replaceState({},'','/app#'+tab);render()};
  document.querySelector('#referral-copy').onclick=async event=>{const button=event.currentTarget;if(button.disabled)return;button.disabled=true;try{const result=await api('/billing/referral');if(!active())return;await navigator.clipboard.writeText(location.origin+'/app?register=1&ref='+encodeURIComponent(result.code));document.querySelector('#referral-status').textContent='Приглашение скопировано'}catch(error){if(active())document.querySelector('#referral-status').textContent=error.message}finally{button.disabled=false}};
  track('paywall_viewed',source);
  if(pending&&new URLSearchParams(location.search).has('payment')){const pollKey='smetra.payment.poll.'+owner.id+'.'+pending.id,count=Number(sessionStorage.getItem(pollKey)||0);if(count<3){setTimeout(()=>{if(active()&&sessionRevision()===revision&&document.visibilityState==='visible'){sessionStorage.setItem(pollKey,String(count+1));sync()}},count===0?0:10000)}}
 }
 window.SmetraGrowth={billing,onboarding,start,paywall};
})();
