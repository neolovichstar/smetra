/* Read-only price-change impact view, powered by existing monitored suppliers. */
(() => {
 'use strict';
 const escape=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
 const amount=(value,currency)=>value==null?'Не рассчитано':new Intl.NumberFormat('ru-RU',{style:'currency',currency:currency||'RUB',maximumFractionDigits:2}).format(Number(value)/100);
 const reasons={stale:'Нужно обновить цену',currency_mismatch:'Другая валюта',unit_mismatch:'Единицы не совпадают',ambiguous:'Несколько поставщиков',out_of_stock:'Нет в наличии',skipped:'Не учитывается в смете',invalid_price:'Нет достоверной цены',unavailable:'Нет подходящей цены'};
 function renderReport(result,target){
   const rows=Array.isArray(result.lines)?result.lines:[];
   const currency=result.currency||'RUB';
   const comparable=rows.filter(x=>x.status==='comparable');
   const excluded=rows.filter(x=>x.status!=='comparable');
   const total=result.indicative_total_kopecks;
   const signed=Number(result.comparable_delta_kopecks)||0;
   target.innerHTML=
    '<div class="spi-summary"><span>Смета без изменений</span><strong>'+escape(amount(result.original_total_kopecks,currency))+'</strong>'+
    '<span>Условная стоимость по проверенным товарам</span><strong>'+escape(amount(total,currency))+'</strong>'+
    '<span>Возможное изменение</span><b class="'+(signed>0?'spi-rise':signed<0?'spi-fall':'')+'">'+(signed>0?'+':'')+escape(amount(signed,currency))+'</b></div>'+
    '<div class="spi-coverage">Сопоставлено позиций: '+comparable.length+' · Исключено: '+excluded.length+'</div>'+
    (rows.length?'<div class="spi-lines">'+rows.map(row=>'<div class="spi-line">'+
      '<div><strong>'+escape(row.name||'Позиция')+'</strong><small>'+escape(row.quantity||'')+' '+escape(row.unit||'')+'</small></div>'+
      (row.status==='comparable'
       ?'<div class="spi-line-values"><strong>'+(Number(row.delta_kopecks)>0?'+':'')+escape(amount(row.delta_kopecks,currency))+'</strong><small>'+
         escape(amount(row.quote_unit_price_kopecks,currency))+' → '+escape(amount(row.supplier_unit_price_kopecks,currency))+
         (row.delta_percent!=null?' · '+escape(row.delta_percent)+'%':'')+'</small></div>'
       :'<span class="spi-reason">'+escape(reasons[row.status]||row.reason||'Невозможно сравнить')+'</span>')+
       '</div>').join('')+'</div>':'<p class="spi-empty">Связанных источников цен пока нет. Привяжите товары к позициям сметы в разделе выше.</p>')+
    '<p class="spi-disclaimer">Это ориентировочный прогноз только по сопоставимым позициям, а не общий индекс инфляции. Смета, цена договора и согласование заказчика не изменяются автоматически.</p>';
 }
 function mount(quotes,active=()=>true){
   const source=document.querySelector('.premium-tools-page > .premium-section');
   if(!source)return;
   const all=(Array.isArray(quotes)?quotes:[]).filter(q=>q&&q.id);
   source.insertAdjacentHTML('afterend','<section class="premium-section spi" id="spi-section">'+
     '<div class="premium-section-heading"><div><span class="premium-kicker">02 / СРАВНЕНИЕ СТОИМОСТИ</span>'+
     '<h2>Динамика бюджета</h2><p>Сравните сметные цены с проверенными предложениями поставщиков.</p></div></div>'+
     '<div class="spi-form"><label for="spi-quote">Смета<select id="spi-quote"><option value="">Выберите смету</option>'+
       all.map(q=>'<option value="'+escape(q.id)+'">'+escape(q.title||'Без названия')+'</option>').join('')+
     '</select></label><button type="button" class="btn primary" id="spi-check">Сравнить цены</button></div>'+
     '<div class="spi-report" id="spi-report" aria-live="polite"><p class="spi-empty">Выберите смету и запустите сравнение.</p></div></section>');
   const button=document.querySelector('#spi-check');
   const select=document.querySelector('#spi-quote');
   const result=document.querySelector('#spi-report');
   button.disabled=true;
   select.addEventListener('change',()=>{button.disabled=!select.value;result.innerHTML='<p class="spi-empty">Нажмите «Сравнить цены» для этой сметы.</p>'});
   button.addEventListener('click',async()=>{
     if(!select.value||button.disabled)return;
     button.disabled=true;result.textContent='Сопоставляем цены…';
     const requested=select.value;
     try{
       const data=await api('/premium/price-impact?quote_id='+encodeURIComponent(requested));
       if(active()&&result.isConnected&&select.value===requested)renderReport(data,result);
     }catch(error){
       if(active()&&result.isConnected&&select.value===requested)result.textContent=error.message||'Не удалось сравнить цены';
     }finally{if(button.isConnected)button.disabled=!select.value;}
   });
 }
 window.SmetraPriceImpact=Object.freeze({mount,renderReport});
})();
