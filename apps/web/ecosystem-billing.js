/* Four server-priced products; payment callbacks remain the only grant authority. */
window.SmetraBillingCatalog=async function(active,b,space,owner,revision){
 const alive=()=>active()&&user===owner&&(typeof authRevision!=='number'||authRevision===revision);
 const e=escapeHtml,pricing=b.pricing,workspace=space.workspace,access=space.entitlements||{};
 const owns=workspace?.owner_id===owner.id;
 const available=b.email_verified&&['live','test'].includes(b.checkout_mode)&&owns;
 const names={starter:'Старт',pro_solo:'PRO Solo',pro_plus:'PRO Плюс',team:'TEAM'};
 const features={
  starter:['10 бесплатных смет','Согласование по клиентской ссылке','История ваших документов'],
  pro_solo:['Безлимитные сметы','PDF и Excel без отметки Сметры','500 МБ для рабочих файлов','Ассистент: 100 сообщений в месяц'],
  pro_plus:['Всё из PRO Solo','Учёт поступлений и расходов','Предупреждения о кассовом разрыве','Визуальные позиции и мониторинг материалов','5 ГБ для рабочих файлов'],
  team:['Всё из PRO Плюс','Владелец и до 4 сотрудников','Общая база клиентов и объектов','Закрытые чаты объектов','5 ГБ на рабочее пространство']
 };
 let period='month',selected='pro_solo',busy=false;
 const codes={pro_solo:{month:'pro_month',year:'pro_year'},pro_plus:{month:'pro_plus_month'},team:{month:'team_month',year:'team_year'}};
 const history=b.payments.map(p=>'<div class="record-line"><div><strong>'+e((p.plan.startsWith('team')?'TEAM':p.plan.startsWith('pro_plus')?'PRO Плюс':'PRO Solo')+(p.plan.endsWith('year')?' · год':' · месяц'))+'</strong><small>'+e(date(p.created_at))+' · '+e(({pending:'Ожидает оплаты',succeeded:'Оплачено',canceled:'Отменено',refunded:'Возврат'})[p.status]||p.status)+'</small></div><b>'+e(rub(p.amount_kopecks))+'</b></div>').join('');
 view('<section class="catalog-billing"><div class="section-top"><div><span class="overline">РАБОЧЕЕ ПРОСТРАНСТВО</span><h1>Тариф под вашу работу</h1><p class="muted">Сметы, деньги и команда. Одна подписка, без покупки отдельных функций.</p></div><span class="pill">'+e(names[access.tier]||'Старт')+'</span></div><div class="row wrap" role="group" aria-label="Период оплаты"><button class="btn" data-period="month" aria-pressed="true">Месяц</button><button class="btn" data-period="year" aria-pressed="false">Год · 2 месяца в подарок</button></div><div class="catalog-plan-grid" id="plan-cards"></div><p id="catalog-period-note" class="note"></p><p id="catalog-checkout-note" role="status"></p><p class="note">'+(!owns?'Тарифом управляет владелец этого пространства.':!b.email_verified?'Для оплаты подтвердите почту.':b.checkout_mode==='off'?'Оплата временно недоступна. Ваш текущий доступ сохраняется.':b.checkout_mode==='test'?'Тестовый режим оплаты.':'Разовая оплата выбранного периода через ЮKassa. Автоматических списаний нет.')+'</p><section class="panel"><div class="section-top"><h2>История оплат</h2><button class="btn small" id="catalog-sync">Проверить оплату</button></div>'+(history||'<p class="muted">Здесь появятся подтверждённые оплаты.</p>')+'</section><p class="note"><a href="/terms">Условия оплаты и возврата</a> · <a href="/contacts">Контакты</a></p></section>');
 function paint(){
  if(!alive())return;
  document.querySelector('#plan-cards').innerHTML=Object.entries(pricing.catalog).map(([tier,product])=>{
   const code=codes[tier]?.[period]||codes[tier]?.month,option=pricing.plans[code],current=access.tier===tier;
   const chosenPeriod=code?.endsWith('year')?'год':'месяц';
   return '<article class="catalog-plan '+(tier===selected?'selected':'')+'"><span class="overline">'+(tier==='starter'?'БАЗОВЫЙ ДОСТУП':tier==='team'?'ДЛЯ КОМПАНИИ':'ДЛЯ СПЕЦИАЛИСТА')+'</span><h2>'+e(names[tier])+'</h2><div class="catalog-plan-price"><strong>'+e(rub(option?.amount_kopecks||0))+'</strong><span>'+(option?' / '+chosenPeriod:'')+'</span></div><ul>'+features[tier].map(text=>'<li>'+e(text)+'</li>').join('')+'</ul>'+(tier==='starter'?'<p class="note">'+(current?'Ваш текущий тариф':'Бесплатный доступ')+'</p>':'<button class="btn '+(tier===selected?'primary':'')+'" data-product="'+tier+'" '+(available&&!busy?'':'disabled')+'>'+(current?'Продлить':'Выбрать')+'</button>')+'</article>';
  }).join('');
  document.querySelector('#catalog-period-note').textContent=period==='year'?'Для PRO Плюс доступна ежемесячная оплата. Месяц — 31 день, год — 366 дней.':'Все цены указаны за 31 день. TEAM включает пять участников вместе с владельцем.';
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
 if(new URLSearchParams(location.search).has('payment')&&b.payments.some(p=>p.status==='pending'))await synchronize();
};
