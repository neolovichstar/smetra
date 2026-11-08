/* Consolidated quantities and server-calculated, read-only purchase scenarios. */
(() => {
  'use strict';
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const quantity=value=>Number(value).toLocaleString('ru-RU',{maximumFractionDigits:4});
  const money=value=>value==null?'Не указано':new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB'}).format(value/100);
  const sourceLabel={purchase:'Последняя указанная цена закупки',planned:'Средняя плановая себестоимость',unknown:'Закупочная цена не указана'};

  function report(result, onlyRemaining=false){
    const budget=result.procurement_budget, summary=result.summary;
    const items=onlyRemaining?result.materials.filter(item=>Number(item.to_buy_quantity)>0):result.materials;
    return `<div class="procurement-summary" role="status">${summary.groups} групп материалов из ${summary.source_rows} позиций · докупить: ${summary.to_buy_groups}${summary.surplus_groups?' · с избытком: '+summary.surplus_groups:''}</div>
      ${budget?`<div class="procurement-budget"><div><span>Плановая себестоимость</span><strong>${escape(money(budget.planned_kopecks))}</strong></div><div><span>Получено и заказано</span><strong>${escape(money(budget.recorded_kopecks))}</strong></div><div><span>Осталось закупить</span><strong>${escape(money(budget.remaining_kopecks))}</strong></div><div><span>Прогноз всех закупок</span><strong>${escape(money(budget.forecast_kopecks))}</strong></div></div>
      <p class="procurement-note">${budget.delta_kopecks==null?'Для сравнения с планом не хватает цен.':budget.delta_kopecks>0?'Выше плановой себестоимости на '+escape(money(budget.delta_kopecks))+'.':budget.delta_kopecks<0?'Ниже плановой себестоимости на '+escape(money(-budget.delta_kopecks))+'.':'Прогноз совпадает с плановой себестоимостью.'}${budget.unpriced_groups?' Не хватает закупочных цен: '+budget.unpriced_groups+' групп.':''}</p>`:''}
      <div class="procurement-materials">${items.length?items.map(item=>{
        const b=item.procurement_budget;
        return `<article class="procurement-material"><header><strong>${escape(item.title)}</strong><b>${Number(item.to_buy_quantity)>0?'Докупить '+escape(quantity(item.to_buy_quantity))+' '+escape(item.unit):'Потребность закрыта'}</b></header>
          ${item.notes?`<p>${escape(item.notes)}</p>`:''}${item.zones.length?`<p class="procurement-note">${item.zones.map(escape).join(' · ')}</p>`:''}
          <p>Нужно ${escape(quantity(item.required_quantity))} ${escape(item.unit)} · получено ${escape(quantity(item.received_quantity))} · заказано ${escape(quantity(item.ordered_quantity))}</p>
          ${Number(item.surplus_quantity)>0?`<p class="procurement-warning">Сверх потребности: ${escape(quantity(item.surplus_quantity))} ${escape(item.unit)}</p>`:''}
          ${Number(item.shortage_quantity)>0?`<p class="procurement-warning">Записанный расход превышает полученное на ${escape(quantity(item.shortage_quantity))} ${escape(item.unit)}. Проверьте поступления.</p>`:''}
          ${b?`<div class="procurement-price"><span>${escape(sourceLabel[b.reference_source])}${b.reference_date?' · '+escape(b.reference_date):''}: ${escape(money(b.reference_unit_price_kopecks))} / ${escape(item.unit)}</span><strong>Прогноз: ${escape(money(b.forecast_kopecks))}</strong></div>${b.unknown_purchase_prices?'<p class="procurement-warning">В записанных закупках есть неуказанные цены.</p>':''}`:''}</article>`;
      }).join(''):'<p class="construction-empty">'+(result.materials.length?'Все материалы уже получены или заказаны.':'Добавьте материалы в ведомость объекта, чтобы составить список закупок.')+'</p>'}</div>`;
  }

  function mount(root, objectId, active){
    let sequence=0, current=null, onlyRemaining=false, disposed=false;
    const live=()=>!disposed&&root.isConnected&&active();
    const path='/construction/objects/'+encodeURIComponent(objectId)+'/procurement-plan';
    root.innerHTML=`<div class="procurement-toolbar"><div><h3>Общий список закупок</h3><p class="procurement-note">Одинаковые материалы объединены по помещениям с учётом единиц и примечаний.</p></div><button type="button" class="btn small" data-procurement-export>Список поставщику · XLSX</button></div>
      <form class="procurement-scenario" hidden><label>Изменение цены оставшихся закупок, %<input name="price_change" type="number" min="-100" max="1000" step="0.01" value="0" required inputmode="decimal"></label><button class="btn" type="submit">Рассчитать</button><button class="btn small" type="button" data-procurement-reset>Без изменения цен</button></form>
      <p class="procurement-note" data-scenario-note hidden>Сценарий меняет только расчёт будущих закупок. Полученное и заказанное считаются по записанным ценам. Это стоимость закупок, а не оплаченные расходы.</p>
      <label class="procurement-filter"><input type="checkbox" data-procurement-filter> Только то, что осталось докупить</label><div data-procurement-status role="status" aria-live="polite"></div><div data-procurement-report></div>`;
    const form=root.querySelector('form'),status=root.querySelector('[data-procurement-status]'),body=root.querySelector('[data-procurement-report]'),exportButton=root.querySelector('[data-procurement-export]');
    const paint=()=>{if(live()&&current)body.innerHTML=report(current,onlyRemaining);};
    async function load(){
      const mine=++sequence, value=form.elements.price_change.value;
      current=null;body.replaceChildren();status.textContent='Собираю список закупок…';exportButton.disabled=true;
      const submit=form.querySelector('[type=submit]');submit.disabled=true;
      try{
        const result=await api(path+'?'+new URLSearchParams({price_change:value}));
        if(!live()||mine!==sequence)return;
        current=result;paint();status.textContent='';
        form.hidden=!result.procurement_budget;root.querySelector('[data-scenario-note]').hidden=!result.procurement_budget;
        exportButton.disabled=result.summary.to_buy_groups===0;
      }catch(error){if(live()&&mine===sequence){status.textContent=error.message;const retry=document.createElement('button');retry.type='button';retry.className='btn small';retry.textContent='Повторить';retry.onclick=load;status.append(' ',retry);}}
      finally{if(live()&&mine===sequence)submit.disabled=false;}
    }
    form.onsubmit=event=>{event.preventDefault();if(form.reportValidity())load();};
    form.elements.price_change.oninput=()=>{
      ++sequence;current=null;body.replaceChildren();exportButton.disabled=true;form.querySelector('[type=submit]').disabled=false;
      status.textContent='Нажмите «Рассчитать», чтобы обновить прогноз.';
    };
    root.querySelector('[data-procurement-reset]').onclick=()=>{form.elements.price_change.value='0';load();};
    root.querySelector('[data-procurement-filter]').onchange=event=>{onlyRemaining=event.target.checked;paint();};
    exportButton.onclick=async()=>{
      if(!current||!live()||exportButton.disabled)return;
      exportButton.disabled=true;
      try{
        const space=sessionStorage.getItem('workspace_id');
        const headers=space?{'X-Workspace-Id':space}:{};
        const response=await fetch('/api'+path+'.xlsx',{credentials:'same-origin',headers});
        if(!response.ok){const error=await response.json();throw Error(error.error||'Не удалось скачать список закупок.');}
        const blob=await response.blob();
        if(!live())return;
        const url=URL.createObjectURL(blob),anchor=document.createElement('a');anchor.href=url;anchor.download='smetra-procurement.xlsx';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),5000);
      }catch(error){if(live())status.textContent=error.message;}
      finally{if(live())exportButton.disabled=!current||current.summary.to_buy_groups===0;}
    };
    load();
    return {destroy(){disposed=true;++sequence;}};
  }
  window.SmetraProcurementPlan=Object.freeze({report,mount});
})();
