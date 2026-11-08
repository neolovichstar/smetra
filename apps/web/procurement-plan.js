/* Consolidated quantities and server-calculated, read-only purchase scenarios. */
(() => {
  'use strict';
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const quantity=value=>Number(value).toLocaleString('ru-RU',{maximumFractionDigits:4});
  const money=value=>value==null?'Не указано':new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB'}).format(value/100);
  const sourceLabel={purchase:'Последняя указанная цена закупки',planned:'Средняя плановая себестоимость',unknown:'Закупочная цена не указана'};


  const toKopecks=value=>{
    const raw=String(value??'').trim();
    if(!/^\d+(?:[.,]\d{1,2})?$/.test(raw))return null;
    const parts=raw.replace(',','.').split('.');
    const result=Number(parts[0])*100+Number((parts[1]||'').padEnd(2,'0'));
    return Number.isSafeInteger(result)?result:null;
  };
  const textOrUnknown=value=>value===null||value===undefined||value===''?'Не указано':String(value);
  function quoteComparison(item, editable){
    const comparison=item.supplier_comparison,quotes=item.supplier_quotes||[];
    if(!comparison&&!quotes.length)return '';
    let bestHtml='<p class="procurement-warning">Полную стоимость рассчитать нельзя: проверьте остатки, доставку и сроки.</p>';
    if(comparison?.best){
      const best=comparison.best,parts=best.suppliers.map(line=>
        '<span>'+escape(line.supplier)+': '+escape(quantity(line.quantity))+' '+escape(item.unit)+
        ' · товар '+escape(money(line.material_kopecks))+' + доставка '+escape(money(line.delivery_kopecks))+'</span>'
      ).join('');
      bestHtml='<div class="procurement-best"><p class="procurement-best-title">Выгоднее по полной стоимости: <strong>'+escape(money(best.total_kopecks))+'</strong></p>'+
        '<p>'+(best.kind==='split'?'Заказ у двух поставщиков':'Заказ у одного поставщика')+' · товары '+escape(money(best.products_kopecks))+
        ' · доставка '+escape(money(best.delivery_kopecks))+
        (best.delivery_days==null?' · срок неизвестен':' · до '+escape(best.delivery_days)+' дн.')+'</p>'+
        '<div class="procurement-best-parts">'+parts+'</div>'+
        (comparison.saving_vs_next_kopecks!=null?'<p>Разница со следующим более дорогим вариантом: '+escape(money(comparison.saving_vs_next_kopecks))+'</p>':'')+'</div>';
    }
    const offers=quotes.map(offer=>'<div class="procurement-offer-line"><div><strong>'+escape(offer.supplier_name)+'</strong><p>'+
      escape(money(offer.unit_price_kopecks))+' / '+escape(item.unit)+' · остаток '+escape(textOrUnknown(offer.stock_quantity))+
      ' · доставка '+escape(money(offer.delivery_kopecks))+
      ' · срок '+escape(offer.delivery_days==null?'не указан':offer.delivery_days+' дн.')+
      (offer.delivery_city?' · '+escape(offer.delivery_city):'')+
      (offer.expires_on?' · до '+escape(offer.expires_on):'')+
      '</p></div>'+(editable?'<button class="btn small" type="button" data-procurement-quote-remove="'+escape(offer.id)+'">Удалить</button>':'')+'</div>').join('');
    return '<section class="procurement-comparison" aria-label="Сравнение поставщиков"><h4>Сравнение предложений поставщиков</h4>'+bestHtml+
      (comparison?.excluded?.length?'<p class="procurement-note">Не участвуют в рейтинге: '+comparison.excluded.map(v=>escape(v.supplier)+' — '+escape(v.reason)).join('; ')+'</p>':'')+
      (comparison?.quotes_truncated?'<p class="procurement-warning">Для сравнения взяты последние 20 предложений этой группы.</p>':'')+
      '<div class="procurement-offer-lines">'+offers+'</div>'+
      '<p class="procurement-note">Цены и наличие введены вручную. Доставка рассчитана отдельно для каждой позиции; комиссии партнёрской программы не учитываются. Заказ автоматически не размещается.</p></section>';
  }

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
          ${b?`<div class="procurement-price"><span>${escape(sourceLabel[b.reference_source])}${b.reference_date?' · '+escape(b.reference_date):''}: ${escape(money(b.reference_unit_price_kopecks))} / ${escape(item.unit)}</span><strong>Прогноз: ${escape(money(b.forecast_kopecks))}</strong></div>${b.unknown_purchase_prices?'<p class="procurement-warning">В записанных закупках есть неуказанные цены.</p>':''}`:''}${quoteComparison(item,result.supplier_quotes_editable)}</article>`;
      }).join(''):'<p class="construction-empty">'+(result.materials.length?'Все материалы уже получены или заказаны.':'Добавьте материалы в ведомость объекта, чтобы составить список закупок.')+'</p>'}</div>`;
  }

  function mount(root, objectId, active){
    let sequence=0, current=null, onlyRemaining=false, disposed=false;
    const live=()=>!disposed&&root.isConnected&&active();
    const path='/construction/objects/'+encodeURIComponent(objectId)+'/procurement-plan';
    root.innerHTML=`<div class="procurement-toolbar"><div><h3>Общий список закупок</h3><p class="procurement-note">Одинаковые материалы объединены по помещениям с учётом единиц и примечаний.</p></div><button type="button" class="btn small" data-procurement-export>Список поставщику · XLSX</button></div>
      <form class="procurement-scenario" hidden><label>Изменение цены оставшихся закупок, %<input name="price_change" type="number" min="-100" max="1000" step="0.01" value="0" required inputmode="decimal"></label><label>Город объекта (для проверки доставки)<input name="site_city" type="text" maxlength="120" placeholder="Например, Москва"></label><label>Материалы нужны к дате<input name="needed_by" type="date"></label><button class="btn" type="submit">Рассчитать</button><button class="btn small" type="button" data-procurement-reset>Без изменения цен</button></form>
      <p class="procurement-note" data-scenario-note hidden>Сценарий меняет только расчёт будущих закупок. Полученное и заказанное считаются по записанным ценам. Это стоимость закупок, а не оплаченные расходы.</p>
      <label class="procurement-filter"><input type="checkbox" data-procurement-filter> Только то, что осталось докупить</label><div data-procurement-status role="status" aria-live="polite"></div><div data-procurement-report></div>
      <form class="procurement-quote-form" data-procurement-offer-form hidden>
        <div class="procurement-quote-head"><div><h4>Предложение поставщика</h4><p class="procurement-note">Добавьте полученную цену и условия поставки. Незаполненные доставка и остаток не считаются нулевыми.</p></div></div>
        <div class="procurement-quote-fields">
          <label>Материал<select name="material_id" required></select></label>
          <label>Поставщик<input name="supplier_name" type="text" maxlength="200" placeholder="Название компании" required></label>
          <label>Цена за ед., ₽<input name="unit_price_rub" type="text" inputmode="decimal" placeholder="390,00" required></label>
          <label>Остаток на складе<input name="stock_quantity" type="number" min="0" max="1000000" step="0.0001" placeholder="Если известно"></label>
          <label>Минимальная партия<input name="min_order_quantity" type="number" min="0" max="1000000" step="0.0001" value="0" required></label>
          <label>Доставка за этот материал, ₽<input name="delivery_rub" type="text" inputmode="decimal" placeholder="0 — если бесплатно"></label>
          <label>Срок доставки, дней<input name="delivery_days" type="number" min="0" max="3650" step="1" placeholder="Если известно"></label>
          <label>Город доставки<input name="delivery_city" type="text" maxlength="120" placeholder="Например, Москва"></label>
          <label>Предложение действует до<input name="expires_on" type="date"></label>
        </div>
        <button class="btn" type="submit">Сохранить и сравнить</button>
      </form>`;
    const form=root.querySelector('.procurement-scenario'),status=root.querySelector('[data-procurement-status]'),body=root.querySelector('[data-procurement-report]'),exportButton=root.querySelector('[data-procurement-export]'),quoteForm=root.querySelector('[data-procurement-offer-form]');
    const paint=()=>{if(live()&&current)body.innerHTML=report(current,onlyRemaining);};
    async function load(){
      const mine=++sequence, value=form.elements.price_change.value;
      current=null;body.replaceChildren();status.textContent='Собираю список закупок…';exportButton.disabled=true;
      const submit=form.querySelector('[type=submit]');submit.disabled=true;
      try{
        const result=await api(path+'?'+new URLSearchParams({price_change:value,site_city:form.elements.site_city.value.trim(),needed_by:form.elements.needed_by.value}));
        if(!live()||mine!==sequence)return;
        current=result;paint();status.textContent='';
        const needOptions=result.materials.filter(item=>Number(item.to_buy_quantity)>0);
        const selector=quoteForm.elements.material_id,selected=selector.value;
        selector.innerHTML=needOptions.map(item=>'<option value="'+escape(item.material_ids[0])+'">'+escape(item.title)+' · '+escape(item.unit)+'</option>').join('');
        if(needOptions.some(item=>item.material_ids.includes(selected)))selector.value=selected;
        quoteForm.hidden=!result.supplier_quotes_editable||!needOptions.length;
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

    quoteForm.onsubmit=async event=>{
      event.preventDefault();
      if(!live()||!current||quoteForm.hidden||!quoteForm.reportValidity())return;
      const e=quoteForm.elements,price=toKopecks(e.unit_price_rub.value);
      const shipping=e.delivery_rub.value.trim()?toKopecks(e.delivery_rub.value):null;
      if(price==null||price<=0||e.delivery_rub.value.trim()&&shipping==null){
        status.textContent='Введите корректную цену в рублях (до двух знаков после запятой).';return;
      }
      const payload={
        material_id:e.material_id.value,supplier_name:e.supplier_name.value.trim(),
        unit_price_kopecks:price,
        stock_quantity:e.stock_quantity.value||null,
        min_order_quantity:e.min_order_quantity.value||'0',
        delivery_kopecks:shipping,delivery_days:e.delivery_days.value===''?null:Number(e.delivery_days.value),
        delivery_city:e.delivery_city.value.trim(),expires_on:e.expires_on.value,
      };
      const button=quoteForm.querySelector('[type=submit]');button.disabled=true;
      try{
        await api('/construction/objects/'+encodeURIComponent(objectId)+'/supplier-quotes',
          {method:'POST',body:JSON.stringify(payload)});
        if(!live())return;
        const material=payload.material_id;quoteForm.reset();quoteForm.elements.material_id.value=material;
        await load();
      }catch(error){if(live())status.textContent=error.message||'Не удалось сохранить предложение';}
      finally{if(live())button.disabled=false;}
    };
    root.addEventListener('click',async event=>{
      const button=event.target.closest('[data-procurement-quote-remove]');
      if(!button||!live()||button.disabled)return;
      if(window.SmetraDialog?.confirm){
        const ok=await window.SmetraDialog.confirm({title:'Удалить предложение поставщика?',confirmLabel:'Удалить',danger:true});
        if(!ok||!live())return;
      }else if(!window.confirm('Удалить предложение поставщика?'))return;
      button.disabled=true;
      try{
        await api('/construction/objects/'+encodeURIComponent(objectId)+'/supplier-quotes/'+encodeURIComponent(button.dataset.procurementQuoteRemove),{method:'DELETE'});
        if(live())await load();
      }catch(error){if(live()){status.textContent=error.message||'Не удалось удалить предложение';button.disabled=false;}}
    });
    load();
    return {destroy(){disposed=true;++sequence;}};
  }
  window.SmetraProcurementPlan=Object.freeze({report,mount});
})();
