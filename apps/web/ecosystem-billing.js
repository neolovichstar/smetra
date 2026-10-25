/* Four server-priced products; payment callbacks remain the only grant authority. */
window.SmetraBillingCatalog=async function(active,b,space,owner,revision){
 const alive=()=>active()&&user===owner&&(typeof authRevision!=='number'||authRevision===revision);
 const e=escapeHtml,pricing=b.pricing,workspace=space.workspace,access=space.entitlements||{};
 const owns=workspace?.owner_id===owner.id;
 const available=b.email_verified&&['live','test'].includes(b.checkout_mode)&&owns;
 const names={starter:'Старт',pro_solo:'PRO Solo',pro_plus:'PRO Плюс',team:'TEAM'};
 // Shared with the landing page (ui/plans.js); this copy is only a fallback.
 const features=window.SmetraPlanFeatures||{
  starter:['10 бесплатных смет','Согласование по клиентской ссылке','История ваших документов','Ассистент: 60 тыс. токенов в месяц'],
  pro_solo:['Безлимитные сметы','PDF и Excel без отметки Сметры','500 МБ для рабочих файлов','Gemini 3 Flash с анализом фотографий','Ассистент: 2 млн токенов в месяц'],
  pro_plus:['Всё из PRO Solo','Учёт поступлений и расходов','Предупреждения о кассовом разрыве','Визуальные позиции и мониторинг материалов','5 ГБ для рабочих файлов','Ассистент: 4 млн токенов в месяц'],
  team:['Всё из PRO Плюс','До 5 участников с отдельным доступом к ИИ','Общая база клиентов и объектов','Закрытые чаты объектов','5 ГБ на рабочее пространство','Ассистент: 8 млн токенов на пространство']
 };
 let period='month',selected='pro_solo',busy=false;
 const codes={pro_solo:{month:'pro_month',year:'pro_year'},pro_plus:{month:'pro_plus_month',year:'pro_plus_year'},team:{month:'team_month',year:'team_year'}};
 const tokenPack=plan=>{const m=/^tokens_(\d+)m$/.exec(plan);return m?Number(m[1]):0};
 const paymentName=p=>tokenPack(p.plan)?'Токены · '+tokenPack(p.plan)+' млн':(p.plan.startsWith('team')?'TEAM':p.plan.startsWith('pro_plus')?'PRO Плюс':'PRO Solo')+(p.plan.endsWith('year')?' · год':' · месяц');
 const history=b.payments.map(p=>'<div class="record-line"><div><strong>'+e(paymentName(p))+'</strong><small>'+e(date(p.created_at))+' · '+e(({pending:'Ожидает оплаты',succeeded:'Оплачено',canceled:'Отменено',refunded:'Возврат'})[p.status]||p.status)+'</small></div><b>'+e(rub(p.amount_kopecks))+'</b></div>').join('');
 const tokens=b.tokens,canBuyTokens=b.email_verified&&['live','test'].includes(b.checkout_mode);
 let tab=(()=>{try{const v=sessionStorage.getItem('smetra.billing.view');sessionStorage.removeItem('smetra.billing.view');return v==='tokens'&&tokens?'tokens':'plans'}catch{return 'plans'}})();
 view('<section class="catalog-billing"><div class="section-top"><div><span class="overline">РАБОЧЕЕ ПРОСТРАНСТВО</span><h1 id="billing-title">Тариф под вашу работу</h1><p class="muted" id="billing-lead">Сметы, деньги и команда. Одна подписка, без покупки отдельных функций.</p></div><span class="pill">'+e(names[access.tier]||'Старт')+'</span></div>'
  +(tokens?'<div class="billing-switch" role="tablist" aria-label="Что оплатить"><button type="button" role="tab" id="billing-tab-plans" data-billing-tab="plans" aria-controls="billing-plans">Тарифы</button><button type="button" role="tab" id="billing-tab-tokens" data-billing-tab="tokens" aria-controls="billing-tokens">Токены ИИ</button></div>':'')
  +'<div id="billing-plans" role="tabpanel" aria-labelledby="billing-tab-plans"><div class="row wrap" role="group" aria-label="Период оплаты"><button class="btn" data-period="month" aria-pressed="true">Месяц</button><button class="btn" data-period="year" aria-pressed="false">Год · 2 месяца в подарок</button></div><div class="catalog-plan-grid" id="plan-cards"></div><p id="catalog-period-note" class="note"></p></div>'+(tokens?'<div id="billing-tokens" role="tabpanel" aria-labelledby="billing-tab-tokens" hidden></div>':'')+'<p id="catalog-checkout-note" role="status"></p><p class="note">'+(!owns?'Тарифом управляет владелец этого пространства.':!b.email_verified?'Для оплаты подтвердите почту.':b.checkout_mode==='off'?'Оплата временно недоступна. Ваш текущий доступ сохраняется.':b.checkout_mode==='test'?'Тестовый режим оплаты.':'Разовая оплата через ЮKassa. Автоматических списаний нет.')+'</p><section class="panel"><div class="section-top"><h2>История оплат</h2><button class="btn small" id="catalog-sync">Проверить оплату</button></div>'+(history||'<p class="muted">Здесь появятся подтверждённые оплаты.</p>')+'</section><p class="note"><a href="/terms">Условия оплаты и возврата</a> · <a href="/contacts">Контакты</a></p></section>');
 const kilo=n=>{n=Number(n||0);return n>=1e6?(n/1e6).toLocaleString('ru-RU',{maximumFractionDigits:2})+' млн':n>=1e3?Math.round(n/1e3).toLocaleString('ru-RU')+' тыс.':n.toLocaleString('ru-RU')};
 // Mirrors the server's graduated bands; the server re-checks the amount at checkout.
 const tokenPrice=millions=>{let total=0,start=0;for(const band of tokens.bands){if(millions<=start)break;total+=(Math.min(millions,band.up_to_millions)-start)*band.kopecks_per_million;start=band.up_to_millions}return total};
 let custom=5,balance=null;
 function paintTokens(){
  const host=document.querySelector('#billing-tokens');if(!host||!alive())return;
  const base=tokens.bands[0].kopecks_per_million;
  const meter=balance&&balance.monthly_limit?Math.min(100,Math.round(balance.monthly_used/balance.monthly_limit*100)):0;
  host.innerHTML='<div class="token-hero"><div class="token-balance"><span class="overline">ДОСТУПНО СЕЙЧАС</span><strong>'+(balance?e(kilo(balance.remaining)):'—')+'</strong><span class="token-unit">токенов</span>'
   +(balance?'<div class="token-meter" aria-hidden="true"><span data-share="'+meter+'"></span></div><dl class="token-facts"><div><dt>Тариф в этом месяце</dt><dd>'+e(kilo(balance.monthly_used))+' из '+e(kilo(balance.monthly_limit))+'</dd></div><div><dt>Купленные</dt><dd>'+e(kilo(balance.wallet))+'</dd></div><div><dt>Обновление тарифа</dt><dd>'+e(date(balance.resets_at))+'</dd></div></dl>':'<p class="muted">Загружаем баланс…</p>')
   +'</div><div class="token-explain"><h2>Как считаются токены</h2><ul><li><b>1 ответ ассистента</b><span>≈ 10–20 тыс. токенов</span></li><li><b>1 млн токенов</b><span>≈ 50–100 ответов</span></li><li><b>Купленные токены</b><span>не сгорают</span></li></ul><p class="note">Сначала тратится месячный лимит тарифа, затем купленные токены. Неудачный ответ не списывается.</p></div></div>'
   +'<div class="token-packs">'+tokens.packs.map(pack=>{const per=Math.round(pack.amount_kopecks/pack.millions/100)*100;return '<article class="token-pack'+(pack.featured?' is-featured':'')+'">'+(pack.featured?'<span class="token-badge">Выгоднее всего</span>':'')+'<span class="overline">'+e(pack.label)+'</span><h3>'+e(pack.millions)+' млн <small>токенов</small></h3><div class="token-price"><strong>'+e(rub(pack.amount_kopecks))+'</strong><span>'+e(rub(per))+' за 1 млн</span></div>'+(pack.saving_kopecks>0?'<p class="token-saving">Экономия '+e(rub(pack.saving_kopecks))+'</p>':'<p class="token-saving is-muted">Базовая цена</p>')+'<button class="btn '+(pack.featured?'primary':'')+'" type="button" data-token-buy="'+pack.millions+'"'+(canBuyTokens?'':' disabled')+'>Купить</button></article>'}).join('')+'</div>'
   +'<section class="token-custom"><div><h2>Своё количество</h2><p class="muted">От '+tokens.min_millions+' до '+tokens.max_millions+' млн. Чем больше, тем ниже цена за миллион.</p></div><div class="token-custom-controls"><input type="range" id="token-range" min="'+tokens.min_millions+'" max="'+tokens.max_millions+'" step="1" value="'+custom+'" aria-label="Количество миллионов токенов"><label class="token-amount"><input type="number" id="token-amount" min="'+tokens.min_millions+'" max="'+tokens.max_millions+'" step="1" value="'+custom+'" inputmode="numeric"><span>млн</span></label></div><div class="token-custom-total"><div><strong id="token-total"></strong><span id="token-rate"></span></div><button class="btn primary" type="button" id="token-custom-buy"'+(canBuyTokens?'':' disabled')+'>Купить</button></div></section>';
  host.querySelectorAll('[data-share]').forEach(bar=>bar.style.setProperty('--share',bar.dataset.share+'%'));
  const range=host.querySelector('#token-range'),amount=host.querySelector('#token-amount');
  const sync=value=>{custom=Math.max(tokens.min_millions,Math.min(tokens.max_millions,Math.round(Number(value)||tokens.min_millions)));range.value=custom;if(document.activeElement!==amount)amount.value=custom;range.style.setProperty('--fill',((custom-tokens.min_millions)/(tokens.max_millions-tokens.min_millions)*100)+'%');const total=tokenPrice(custom);host.querySelector('#token-total').textContent=rub(total);host.querySelector('#token-rate').textContent=rub(Math.round(total/custom/100)*100)+' за 1 млн'+(base*custom>total?' · экономия '+rub(base*custom-total):'');host.querySelector('#token-custom-buy').textContent='Купить '+custom+' млн'};
  range.oninput=()=>sync(range.value);amount.oninput=()=>sync(amount.value);amount.onblur=()=>{amount.value=custom};sync(custom);
  host.querySelectorAll('[data-token-buy]').forEach(button=>button.onclick=()=>buyTokens(Number(button.dataset.tokenBuy),button));
  host.querySelector('#token-custom-buy').onclick=event=>buyTokens(custom,event.currentTarget);
 }
 async function loadBalance(){try{const data=await api('/assistant');if(!alive())return;balance=data.quota&&data.quota.unit==='tokens'?data.quota:null;paintTokens()}catch{}}
 async function buyTokens(millions,button){
  if(!alive()||!canBuyTokens||busy)return;busy=true;button.disabled=true;
  const keyName='smetra.tokens.'+owner.id+'.'+millions;let key=sessionStorage.getItem(keyName);if(!key){key=crypto.randomUUID();sessionStorage.setItem(keyName,key)}
  const note=document.querySelector('#catalog-checkout-note');note.textContent='Готовим защищённую оплату…';
  try{
   const result=await api('/billing/tokens/checkout',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({millions,expected_amount_kopecks:tokenPrice(millions),source:'pricing_page'})});
   if(!alive())return;
   if(['canceled','refunded','succeeded'].includes(result.status)){sessionStorage.removeItem(keyName)}
   if(result.status==='succeeded'){await synchronize();return}
   if(['canceled','refunded'].includes(result.status))throw Error('Предыдущая оплата закрыта. Нажмите ещё раз, чтобы начать новую.');
   const target=new URL(result.url);if(target.protocol!=='https:')throw Error('Некорректная ссылка оплаты');location.href=target.href;
  }catch(error){if(alive()){if(error.status===409)sessionStorage.removeItem(keyName);note.textContent=error.message}}
  finally{busy=false;if(button.isConnected)button.disabled=!canBuyTokens}
 }
 function showTab(next){
  if(!tokens)return;tab=next;
  document.querySelectorAll('[data-billing-tab]').forEach(button=>{const on=button.dataset.billingTab===tab;button.setAttribute('aria-selected',String(on));button.tabIndex=on?0:-1});
  document.querySelector('.billing-switch')?.classList.toggle('is-tokens',tab==='tokens');
  document.querySelector('#billing-plans').hidden=tab!=='plans';document.querySelector('#billing-tokens').hidden=tab!=='tokens';
  document.querySelector('#billing-title').textContent=tab==='tokens'?'Токены для ассистента':'Тариф под вашу работу';
  document.querySelector('#billing-lead').textContent=tab==='tokens'?'Пополните баланс разово, без подписки. Купленные токены не сгорают.':'Сметы, деньги и команда. Одна подписка, без покупки отдельных функций.';
  if(tab==='tokens'){paintTokens();if(!balance)loadBalance()}
 }
 function paint(){
  if(!alive())return;
  document.querySelector('#plan-cards').innerHTML=Object.entries(pricing.catalog).map(([tier,product])=>{
   const code=codes[tier]?.[period]||codes[tier]?.month,option=pricing.plans[code],current=access.tier===tier;
   const chosenPeriod=code?.endsWith('year')?'год':'месяц';
   return '<article class="catalog-plan '+(tier===selected?'selected':'')+'"><span class="overline">'+(tier==='starter'?'БАЗОВЫЙ ДОСТУП':tier==='team'?'ДЛЯ КОМПАНИИ':'ДЛЯ СПЕЦИАЛИСТА')+'</span><h2>'+e(names[tier])+'</h2><div class="catalog-plan-price"><strong>'+e(rub(option?.amount_kopecks||0))+'</strong><span>'+(option?' / '+chosenPeriod:'')+'</span></div><ul>'+features[tier].map(text=>'<li>'+e(text)+'</li>').join('')+'</ul>'+(tier==='starter'?'<p class="note">'+(current?'Ваш текущий тариф':'Бесплатный доступ')+'</p>':'<button class="btn '+(tier===selected?'primary':'')+'" data-product="'+tier+'" '+(available&&!busy?'':'disabled')+'>'+(current?'Продлить':'Выбрать')+'</button>')+'</article>';
  }).join('');
  document.querySelector('#catalog-period-note').textContent=period==='year'?'Годовой тариф на 366 дней. Экономия относительно помесячной оплаты.':'Цены за 31 день. TEAM включает пять участников вместе с владельцем.';
  document.querySelectorAll('[data-product]').forEach(button=>button.onclick=()=>checkout(button.dataset.product));
  document.querySelectorAll('[data-period]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.period===period)));
 }
 async function checkout(tier){
  if(!alive()||!available||busy)return;busy=true;selected=tier;paint();
  const code=codes[tier][period]||codes[tier].month,keyName='smetra.checkout.'+owner.id+'.'+workspace.id+'.'+code;
  let key=sessionStorage.getItem(keyName);if(!key){key=crypto.randomUUID();sessionStorage.setItem(keyName,key)}
  const note=document.querySelector('#catalog-checkout-note');note.textContent='Готовим защищённую оплату…';
  try{
   const result=await api('/billing/checkout',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({plan:code,workspace_id:workspace.id,expected_amount_kopecks:pricing.plans[code].amount_kopecks,source:'pricing_page'})});
   if(!alive())return;
   if(['canceled','refunded'].includes(result.status)){sessionStorage.removeItem(keyName);throw Error('Предыдущая оплата отменена. Повторите для создания новой.')}
   if(result.status==='succeeded'){await synchronize();return}
   const target=new URL(result.url);if(target.protocol!=='https:')throw Error('Некорректная ссылка оплаты');location.href=target.href;
  }catch(error){if(alive()){if(error.status===409)sessionStorage.removeItem(keyName);note.textContent=error.message}}
  finally{busy=false;if(alive())paint()}
 }
 async function synchronize(){
  const button=document.querySelector('#catalog-sync');if(!alive()||button.disabled)return;button.disabled=true;
  try{const result=await api('/billing/sync',{method:'POST'});if(!alive())return;user=result.user;await render()}
  catch(error){if(alive())document.querySelector('#catalog-checkout-note').textContent=error.message}
  finally{if(button.isConnected)button.disabled=false}
 }
 document.querySelectorAll('[data-period]').forEach(button=>button.onclick=()=>{if(busy)return;period=button.dataset.period;paint()});
 document.querySelector('#catalog-sync').onclick=synchronize;paint();
 if(tokens){document.querySelectorAll('[data-billing-tab]').forEach(button=>{button.onclick=()=>showTab(button.dataset.billingTab);button.onkeydown=event=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();showTab(tab==='plans'?'tokens':'plans');document.querySelector('[data-billing-tab="'+tab+'"]').focus()}}});showTab(tab)}
 if(new URLSearchParams(location.search).has('payment')&&b.payments.some(p=>p.status==='pending'))await synchronize();
};
