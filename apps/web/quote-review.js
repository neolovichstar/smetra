/* Private, read-only comparison. Publishing still requires explicit consent. */
window.SmetraQuoteReview=(()=>{
 let generation=0;
 const labels={name:'Название',description:'Описание',category:'Категория',quantity:'Количество',unit:'Единица',unit_price:'Цена',cost_price:'Себестоимость',coefficient:'Коэффициент',markup:'Наценка',discount:'Скидка',tax:'Налог',optional:'Дополнительная',included:'Включена в итог',title:'Название сметы',client:'Клиент',terms:'Условия',due_date:'Срок работ',expires_at:'Срок предложения',custom_fields:'Дополнительные поля',currency:'Валюта'};
 const kinds={added:'Добавлено',removed:'Удалено',changed:'Изменено',moved:'Перемещено'};
 const e=escapeHtml;
 const money=(amount,currency)=>new Intl.NumberFormat('ru-RU',{style:'currency',currency,maximumFractionDigits:2}).format(amount/100);
 const format=(value,key,currency)=>{
  if(value===null||value===undefined||value==='')return 'Не указано';
  if(key==='unit_price'||key==='cost_price')return money(value,currency);
  if(key==='expires_at')return date(value);
  if(typeof value==='boolean')return value?'Да':'Нет';
  if(typeof value==='object')return Object.values(value).map(item=>Array.isArray(item)?item.join(', '):String(item)).join(' · ')||'Не указано';
  return String(value);
 };
 function report(result){
  const t=result.totals,s=result.summary;
  return `<div class="review-total"><div><span>Было</span><strong>${e(money(t.before,t.before_currency))}</strong></div><div><span>Стало</span><strong>${e(money(t.after,t.after_currency))}</strong></div><div><span>Изменение суммы</span><strong>${t.delta_kopecks===null?'Разные валюты':e((t.delta_kopecks>0?'+':'')+money(t.delta_kopecks,t.after_currency))}</strong></div></div>
   <p class="review-counts">${Object.keys(kinds).map(kind=>`${kinds[kind]}: ${s[kind]}`).join(' · ')} · Без изменений: ${s.unchanged}</p>
   ${!result.has_changes?'<div class="review-empty"><h2>Условия совпадают</h2><p class="muted">Состав, стоимость и условия остались прежними.</p></div>':''}
   ${result.fields.length?`<section class="review-section"><h2>Условия сметы</h2>${result.fields.map(field=>`<div class="review-field"><strong>${e(labels[field.field]||field.field)}</strong><div><span>Было</span><p>${e(format(field.before,field.field,t.before_currency))}</p></div><div><span>Стало</span><p>${e(format(field.after,field.field,t.after_currency))}</p></div></div>`).join('')}</section>`:''}
   ${result.items.length?`<section class="review-section"><h2>Изменения в позициях</h2>${result.items.map(item=>{
     const row=item.after||item.before;
     return `<article class="review-item"><header><span class="review-kind review-${item.kind}">${kinds[item.kind]}</span><h3>${e(row.name)}</h3>${item.moved?`<small>Позиция ${item.before_position} → ${item.after_position}</small>`:''}</header>${item.kind==='added'||item.kind==='removed'?`<p class="muted">${e(row.quantity)} ${e(row.unit)} · ${e(money(row.unit_price,item.after?t.after_currency:t.before_currency))}</p>`:''}${item.fields.map(key=>`<div class="review-field"><strong>${e(labels[key])}</strong><div><span>Было</span><p>${e(format(item.before[key],key,t.before_currency))}</p></div><div><span>Стало</span><p>${e(format(item.after[key],key,t.after_currency))}</p></div></div>`).join('')}<footer><span>Влияние на итог</span><strong>${item.delta_kopecks===null?'Разные валюты':e((item.delta_kopecks>0?'+':'')+money(item.delta_kopecks,t.after_currency))}</strong></footer></article>`;
   }).join('')}</section>`:''}`;
 }
 async function open(quote,versions,{publish=false,source=String(quote.published_version)}={}){
  const mine=++generation,owner=user,section=tab,space=sessionStorage.getItem('workspace_id'),revision=renderRevision;
  const active=()=>mine===generation&&owner===user&&section===tab&&space===sessionStorage.getItem('workspace_id')&&revision===renderRevision&&root.isConnected;
  view(`<section class="quote-review"><button class="review-back" id="review-back" type="button">← К смете</button><header class="review-heading"><span class="overline">${publish?'Перед отправкой клиенту':'История сметы'}</span><h1>${publish?'Проверьте, что изменилось.':'Сравнение версий.'}</h1><p class="muted" id="review-title">${e(quote.title)}</p><p class="review-private">Только для команды · себестоимость скрыта от клиента</p></header><div class="review-selectors"><label>Было<select id="review-source">${versions.map(v=>`<option value="${v.version}" ${String(v.version)===source?'selected':''}>Версия ${v.version} · ${e(date(v.created_at))}</option>`).join('')}</select></label><label>Стало<select id="review-target"><option value="current">Текущий черновик</option>${versions.map(v=>`<option value="${v.version}">Версия ${v.version} · ${e(date(v.created_at))}</option>`).join('')}</select></label></div><div id="review-report" aria-live="polite"></div>${publish?'<form id="review-publish"><label for="review-comment">Комментарий для команды</label><textarea id="review-comment" rows="2" maxlength="1000" placeholder="Например: добавили доставку и уточнили срок"></textarea><p class="muted">После отправки клиентская ссылка откроет новую зафиксированную версию.</p><button class="btn primary" type="submit" disabled>Зафиксировать и отправить</button><p id="review-publish-status" role="status"></p></form>':''}</section>`);
  const root=document.querySelector('.quote-review'),sourceInput=root.querySelector('#review-source'),targetInput=root.querySelector('#review-target'),body=root.querySelector('#review-report'),form=root.querySelector('#review-publish');
  let request=0,checked=null;
  root.querySelector('#review-back').onclick=()=>window.Workspace.openQuote(quote.id);
  const load=async()=>{
   const current=++request;checked=null;if(form)form.querySelector('button').disabled=true;
   body.innerHTML='<p class="muted" role="status">Сравниваем версии…</p>';
   try{
    const result=await api('/quotes/'+encodeURIComponent(quote.id)+'/compare?'+new URLSearchParams({from:sourceInput.value,to:targetInput.value}));
    if(!active()||current!==request)return;
    checked=result;body.innerHTML=report(result);root.querySelector('#review-title').textContent=result.title;
    if(form){form.querySelector('button').disabled=!result.can_publish;if(result.target==='current'&&!result.can_publish)form.querySelector('#review-publish-status').textContent='Эту смету сейчас нельзя отправить повторно. Вернитесь к смете и проверьте её статус.';}
   }catch(error){if(!active()||current!==request)return;body.innerHTML='<p class="form-error" role="alert">'+e(error.message)+'</p><button class="btn" type="button" id="review-retry">Повторить</button>';body.querySelector('button').onclick=load}
  };
  sourceInput.onchange=load;targetInput.onchange=load;
  if(form)form.onsubmit=async event=>{
   event.preventDefault();const button=form.querySelector('button');if(button.disabled||!checked||checked.target!=='current'||!active())return;
   button.disabled=true;sourceInput.disabled=true;targetInput.disabled=true;const status=form.querySelector('#review-publish-status');status.textContent='Отправляем новую версию…';
   try{await api('/quotes/'+encodeURIComponent(quote.id)+'/publish',{method:'POST',body:JSON.stringify({revision:checked.revision,comment:form.querySelector('textarea').value})});if(!active())return;await window.Workspace.openQuote(quote.id);notify('Новая версия отправлена. Клиентская ссылка обновлена.')}
   catch(error){if(active())status.textContent=error.message+' Проверьте сравнение повторно перед отправкой.';checked=null;}
   finally{if(active()){sourceInput.disabled=false;targetInput.disabled=false;if(!checked){await load();}}}
  };
  await load();
 }
 return {open,report};
})();
