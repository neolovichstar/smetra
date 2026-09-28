'use strict';
const steps=[...document.querySelectorAll('[data-step]')];
const documentHost=document.querySelector('#preview-document');
const prices=[35000,48000,15000];let selectedStep=0;
const format=value=>new Intl.NumberFormat('ru-RU').format(value)+' ₽';
const total=()=>prices.reduce((a,b)=>a+b,0);
const names=['Исследование и структура','Дизайн интерфейса','Подготовка к запуску'];
function renderPreview(step){selectedStep=step;steps.forEach((button,index)=>{button.setAttribute('aria-selected',String(index===step));button.tabIndex=index===step?0:-1});documentHost.setAttribute('aria-labelledby',steps[step].id);
 if(step===0){documentHost.innerHTML=`<div class="document-top"><div><span class="overline">Смета · 001</span><h3>Сайт для студии Север</h3><p>Клиент: Студия Север</p></div><span class="pill">Черновик</span></div><table class="preview-table"><thead><tr><th>Работа</th><th>Стоимость, ₽</th></tr></thead><tbody>${names.map((name,i)=>`<tr><td>${name}</td><td><input aria-label="Стоимость: ${name}" data-price="${i}" type="number" min="1" max="10000000" value="${prices[i]}"></td></tr>`).join('')}</tbody></table><div class="document-total"><span>Итого</span><strong id="preview-total">${format(total())}</strong></div><p class="document-note">Попробуйте изменить стоимость. Итог пересчитается сразу.</p>`;documentHost.querySelectorAll('[data-price]').forEach(input=>input.oninput=()=>{const value=Number(input.value);if(Number.isFinite(value)&&value>=0&&value<=10000000){prices[Number(input.dataset.price)]=value;document.querySelector('#preview-total').textContent=format(total())}})}
 else if(step===1){documentHost.innerHTML=`<div class="step-result"><span class="overline">Клиентская ссылка</span><h3>Договорённости на одной странице.</h3><p>Клиент видит работы, стоимость и условия. Может согласовать смету или предложить изменения без регистрации.</p><div class="link-preview">сметра / предложение / студия-север</div><div class="document-total"><span>К согласованию</span><strong>${format(total())}</strong></div><div class="hero-cta"><button class="btn primary" id="demo-approve">Согласовать смету</button></div></div>`;document.querySelector('#demo-approve').onclick=()=>renderPreview(2)}
 else if(step===2){documentHost.innerHTML=`<div class="step-result"><span class="status-line">Условия согласованы</span><h3>Теперь это заказ.</h3><p>Принятая версия сохраняется. Работы, сроки и клиент переходят в заказ — ничего не нужно переносить вручную.</p><table class="preview-table"><tbody><tr><td>Исследование</td><td>Готово</td></tr><tr><td>Дизайн интерфейса</td><td>В работе</td></tr><tr><td>Подготовка к запуску</td><td>Следующий этап</td></tr></tbody></table></div>`}
 else {documentHost.innerHTML=`<div class="step-result"><span class="overline">Поступления и остаток</span><h3>Суммы сходятся.</h3><p>Фиксируйте полученные оплаты и расходы. Сметра покажет, сколько уже оплачено и сколько осталось получить.</p><div class="document-total"><span>Получено · 40%</span><strong>${format(Math.round(total()*.4))}</strong></div><div class="progress-line"><span></span></div><div class="document-total"><span>Осталось</span><strong>${format(total()-Math.round(total()*.4))}</strong></div></div>`}
 documentHost.classList.remove('demo-enter');void documentHost.offsetWidth;documentHost.classList.add('demo-enter');
}
steps.forEach((button,index)=>{
 button.id='preview-tab-'+index;
 button.setAttribute('aria-controls','preview-document');
 button.onclick=()=>renderPreview(index);
 button.onkeydown=event=>{
  const next=event.key==='Home'?0:event.key==='End'?steps.length-1:event.key==='ArrowRight'?(index+1)%steps.length:event.key==='ArrowLeft'?(index+steps.length-1)%steps.length:-1;
  if(next<0)return;
  event.preventDefault();renderPreview(next);steps[next].focus();
 };
});renderPreview(0);
document.querySelector('#use-preview').onclick=()=>{const draft={title:'Сайт для студии Север',client:'Студия Север',items:names.map((name,i)=>({name,quantity:'1',unit:'усл.',unit_price:Math.round(prices[i]*100)}))};sessionStorage.setItem('smetra.previewDraft',JSON.stringify(draft));location.href='/app?register=1'};
const planButtons=[...document.querySelectorAll('[data-price-plan]')];
function selectPlan(button){planButtons.forEach(b=>{b.setAttribute('aria-selected',String(b===button));b.tabIndex=b===button?0:-1});const year=button.dataset.pricePlan==='year';document.querySelector('#plan-amount').textContent=year?'4 900 ₽':'490 ₽';document.querySelector('#plan-period').textContent=year?' / 366 дней':' / 31 день'}
planButtons.forEach((button,index)=>{button.onclick=()=>selectPlan(button);button.onkeydown=event=>{const next=event.key==='Home'?0:event.key==='End'?planButtons.length-1:event.key==='ArrowRight'?(index+1)%planButtons.length:event.key==='ArrowLeft'?(index+planButtons.length-1)%planButtons.length:-1;if(next<0)return;event.preventDefault();selectPlan(planButtons[next]);planButtons[next].focus()}});selectPlan(planButtons[0]);
fetch('/api/auth/providers').then(r=>r.json()).then(data=>{if(data.rustore_url&&/^https:\/\/(www\.)?rustore\.ru\//.test(data.rustore_url)){const button=document.querySelector('#rustore');button.href=data.rustore_url;button.textContent='Открыть в RuStore';button.removeAttribute('aria-disabled');document.querySelector('#mobile-note').textContent='Карточка приложения в RuStore. Доступность установки проверьте на странице магазина.'}}).catch(()=>{});
