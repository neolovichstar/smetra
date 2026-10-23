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
    <div class="billing-section-heading"><div><span class="overline">ТАРИФ И ОПЛАТА</span><h2 id="billing-purchase-title">${pro?'Управляйте подпиской':'Выберите рабочий набор'}</h2><p>Четыре понятных тарифа. Оплата за выбранный срок — без скрытых списаний и доплат за отдельные функции.</p></div><span class="billing-secure-mark"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3 20 6v5c0 5-3.4 8.3-8 10-4.6-1.7-8-5-8-10V6z"/><path d="m9 12 2 2 4-4"/></svg>Прозрачная цена</span></div>
    <div class="billing-tier-selector" role="group" aria-label="Выбор тарифа">${(pricing.catalog||[]).map(tier=>'<button class="billing-tier-option" type="button" data-tier="'+e(tier.id)+'" aria-pressed="'+String(tier.id==='pro_solo')+'"><span>'+e(tier.name)+'</span><strong>'+rub(tier.price_kopecks)+'</strong><small>в месяц</small></button>').join('')}</div>
    <div class="billing-plan-grid">
     <div class="billing-plan-card">
      <div class="billing-plan-card-head"><div><span class="billing-plan-kicker">СМЕТРА PRO</span><h3>Полный рабочий набор</h3></div><span class="billing-plan-badge">Без автосписаний</span></div>
      <div class="billing-periods" role="group" aria-label="Срок доступа">
       <button class="billing-period-option" type="button" data-period="pro_month" aria-pressed="true"><span>31 день</span><small>Оплата на месяц</small></button>
       <button class="billing-period-option billing-period-annual" type="button" data-period="pro_year" aria-pressed="false"><span>366 дней</span><small>Годовой доступ</small><b>Выгоднее</b></button>
      </div>
      <p class="launch-offer billing-launch-offer" id="billing-launch-offer" hidden></p>
      <div class="billing-price-block"><div class="billing-price-caption">Стоимость выбранного периода</div><div class="billing-price-line"><strong class="open-price" id="offer-price"></strong><span class="billing-price-currency">RUB</span></div><p class="note" id="offer-saving"></p></div>
      <div class="billing-annual-bonus" id="billing-annual-bonus"><span class="billing-bonus-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 3 2.2 5.7L20 11l-5.8 2.3L12 19l-2.2-5.7L4 11l5.8-2.3z"/><path d="m19 16 1.1 2.1L22 19l-1.9.9L19 22l-.9-2.1L16 19l2.1-.9z"/></svg></span><span id="billing-annual-bonus-text">Подарок при покупке: +${monthlyPurchaseBonus} сообщений ИИ</span><span class="billing-bonus-arrow" aria-hidden="true">↗</span></div>
      <button class="btn primary billing-checkout-button" data-plan="pro_month" id="upgrade-checkout" type="button" ${ready?'':'disabled'}>${pro?'Продлить Сметра Про':'Подключить Сметра Про'}<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>
      <p class="billing-payment-note">${e(note)}</p><p id="checkout-error" role="alert"></p>
      <div class="billing-guarantee-line"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3 20 6v5c0 5-3.4 8.3-8 10-4.6-1.7-8-5-8-10V6z"/><path d="m9 12 2 2 4-4"/></svg><span>Без автоматического продления. Условия оплаты и возврата доступны до покупки.</span></div>
     </div>
     <aside class="billing-bundle-card"><div class="billing-bundle-top"><span class="overline">ВКЛЮЧЕНО В PRO</span><span class="billing-bundle-orbit" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L15 18l2.2-.8z"/></svg></span></div><h3>Больше, чем лимит</h3><p class="billing-bundle-intro">Инструменты, которые помогают доводить работу до оплаты.</p>
      <div class="billing-perk-list">
       <article class="billing-perk"><span class="billing-perk-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h9l5 5v13H6z"/><path d="M14 3v6h6M9 13h7M9 17h7"/></svg></span><div><strong>Документы без бренда Сметры</strong><p>Клиенту уходит документ с вашим оформлением.</p></div><span class="billing-perk-tag">Pro</span></article>
       <article class="billing-perk"><span class="billing-perk-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3 13.8 8.2 19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L15 18l2.2-.8z"/></svg></span><div><strong>100 сообщений ассистента в месяц</strong><p>Подготовка смет, разбор данных и рабочие подсказки.</p></div><span class="billing-perk-tag">/мес</span></article>
       <article class="billing-perk"><span class="billing-perk-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 8h10M7 12h6M7 16h8"/></svg></span><div><strong>До 10 000 смет и предложений</strong><p>Не упирайтесь в лимит, когда клиентов становится больше.</p></div><span class="billing-perk-tag">Лимит</span></article>
       <article class="billing-perk"><span class="billing-perk-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="8" height="18" rx="2"/><rect x="14" y="3" width="7" height="12" rx="2"/><path d="M15 19h5"/></svg></span><div><strong>Один профиль на всех устройствах</strong><p>Сметы и работа остаются рядом на сайте и Android.</p></div><span class="billing-perk-tag">Включено</span></article>
      </div>
      <div class="billing-year-savings"><span>Подарок за годовую оплату</span><strong id="billing-year-savings">+${annualPurchaseBonus} сообщений ИИ</strong><small id="billing-year-savings-note">Бонус начисляется после подтверждения оплаты и действует до окончания оплаченного доступа. Экономия относительно 12 месячных периодов — ${rub(annualSaving)}.</small></div>
      <div class="billing-branding-row" id="billing-branding-row"></div>
     </aside>
    </div>
   </section>
   <section class="billing-history"><div class="billing-section-heading billing-history-heading"><div><span class="overline">ИСТОРИЯ</span><h2>Ваши оплаты</h2></div><button class="btn small" id="sync" type="button">Проверить статус</button></div>${paymentHistory}</section>
   <section class="billing-referral"><div class="billing-section-heading"><div><span class="overline">ДЕЛИТЕСЬ С КОЛЛЕГАМИ</span><h2>Пригласите коллегу</h2><p class="muted">Вы получите 3 дополнительных сообщения ассистенту, когда коллега создаст первую смету. До 30 бонусных сообщений в месяц.</p></div><button class="btn billing-referral-button" type="button" id="referral-copy"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>Скопировать приглашение</button></div><span id="referral-status" role="status"></span></section>
   <p class="note billing-legal">Оплату принимает самозанятый МУРАВЬЕВ КОНСТАНТИН АЛЕКСЕЕВИЧ · ИНН 713304603876. <a href="/terms">Условия оплаты и возврата</a> · <a href="/contacts">Контакты</a></p></section>`);
  const launchOffer=document.querySelector('#billing-launch-offer');
  if(pricing.launch_offer&&launchOffer){launchOffer.hidden=false;launchOffer.textContent=e(pricing.launch_offer.label)+' · до '+date(pricing.launch_offer.until);}
  const tiers=pricing.catalog||[];
  let tierId=tiers[0]?.id||'pro_solo',annual=false;
  const checkout=document.querySelector('#upgrade-checkout');
  const tierPlan=(entry,period)=>entry?.[period==='year'?'annual_plan':'plan']||'pro_month';
  let plan=tierPlan(tiers.find(t=>t.id===tierId),'month');
  const paint=()=>{
   const tier=tiers.find(t=>t.id===tierId)||tiers[0];
   if(!tier)return;
   plan=tierPlan(tier,annual?'year':'month');
   const monthlyAmount=pricing.plans[tierPlan(tier,'month')]?.amount_kopecks||tier.price_kopecks;
   const yearlyPlan=tier.annual_plan;
   const yearlyAmount=yearlyPlan?pricing.plans[yearlyPlan]?.amount_kopecks:0;
   const saving=yearlyAmount?monthlyAmount*12-yearlyAmount:0;
   const savingPct=saving?Math.round(saving/(monthlyAmount*12)*100):0;
   const amount=pricing.plans[plan]?.amount_kopecks||monthlyAmount;
   const monthlyBonus=Number(pricing.purchase_bonus?.[tierPlan(tier,'month')]||0);
   const annualBonus=Number(pricing.purchase_bonus?.[yearlyPlan]||0);
   checkout.dataset.plan=plan;
   checkout.innerHTML=(pro?'Продлить ':'Подключить ')+e(tier.name)+'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';
   document.querySelector('#offer-price').textContent=rub(amount);
   document.querySelector('#offer-saving').textContent=annual?rub(Math.round(amount/12))+' в месяц в пересчёте · доступ на 366 дней':'Один платёж за 31 день';
   document.querySelector('#billing-annual-bonus-text').textContent=monthlyBonus||annualBonus?(annual?'Подарок за год: +'+annualBonus+' сообщений ИИ':'Подарок за покупку: +'+monthlyBonus+' сообщений ИИ'):'Весь набор тарифа включён. Доплаты за отдельные функции не нужны.';
   document.querySelector('#billing-year-savings').textContent=annualBonus?'+'+annualBonus+' сообщений ИИ':saving?rub(saving)+' экономии':'Без доплат за функции';
   document.querySelector('#billing-year-savings-note').textContent=saving?'Годовой платёж без автопродления. Экономия против 12 месячных оплат — '+rub(saving)+' ('+savingPct+'%).':'Один понятный платёж за весь выбранный период без микротранзакций.';
   document.querySelector('#billing-annual-bonus').classList.toggle('is-active',annual);
   document.querySelector('#billing-year-savings').closest('.billing-year-savings').querySelector('span').textContent=annual?'Выгода годовой оплаты':'Понятная стоимость';
   document.querySelectorAll('[data-period]').forEach(button=>{button.setAttribute('aria-pressed',String((button.dataset.period==='pro_year')===annual));button.disabled=annual&&!yearlyPlan});
   document.querySelectorAll('[data-tier]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.tier===tierId)));
   document.querySelector('#billing-purchase-title').textContent=pro?'Управляйте подпиской':tier.name+' — выберите срок';
   document.querySelector('.billing-plan-card-head h3').textContent=tier.name;
   const perks=document.querySelector('.billing-perk-list');
   if(perks)perks.innerHTML=tier.features.map((feature,index)=>'<article class="billing-perk"><span class="billing-perk-icon" aria-hidden="true">'+(index+1)+'</span><div><strong>'+e(feature)+'</strong><p>Включено в выбранный тариф.</p></div><span class="billing-perk-tag">Включено</span></article>').join('');
   const seatText=(tier.seat_limit||1)===1?'1 пользователь':(tier.seat_limit||1)+' участников';
   document.querySelector('.billing-hero-stat strong').textContent=seatText;
   document.querySelector('.billing-hero-stat:nth-child(2) strong').textContent=pricing.limits.pro_ai;
   document.querySelector('.billing-hero-stat-note').textContent=tier.name+' · без доплат';
  };
  paint();
  document.querySelectorAll('[data-tier]').forEach(button=>button.addEventListener('click',()=>{tierId=button.dataset.tier;annual=false;paint()}));
  document.querySelectorAll('[data-period]').forEach(button=>button.onclick=()=>{annual=button.dataset.period==='pro_year';paint()});
  const retryCancelled=recent&&['canceled','refunded'].includes(recent.status);if(retryCancelled)for(const value of ['pro_month','pro_year'])sessionStorage.removeItem('smetra.checkout.'+owner.id+'.'+value);
  checkout.onclick=async()=>{if(checkout.disabled)return;checkout.disabled=true;const selected=plan,keyName='smetra.checkout.'+owner.id+'.'+selected;let key=sessionStorage.getItem(keyName);if(!key){key=crypto.randomUUID();sessionStorage.setItem(keyName,key)}track('upgrade_clicked',source);if(!sessionStorage.getItem('smetra.checkout.return.'+owner.id))sessionStorage.setItem('smetra.checkout.return.'+owner.id,'dashboard');try{const result=await api('/billing/checkout',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({plan:selected,source,expected_amount_kopecks:pricing.plans[selected].amount_kopecks})});if(!active()||sessionRevision()!==revision)return;if(result.status==='canceled'||result.status==='refunded'){sessionStorage.removeItem(keyName);throw Error('Предыдущая оплата завершена отменой или возвратом. Нажмите ещё раз для новой попытки.')}if(result.status==='succeeded'){await sync();return}location.href=result.url}catch(error){if(active()&&sessionRevision()===revision){if(error.status===409){sessionStorage.removeItem(keyName);checkout.disabled=true;checkout.textContent='Обновить условия';checkout.onclick=()=>render()}document.querySelector('#checkout-error').textContent=error.message}}finally{if(checkout.isConnected)checkout.disabled=false}};
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
