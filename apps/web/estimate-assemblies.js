/* Private editor tools; public documents receive only explicit scope notes. */
(() => {
  'use strict';
  const labels={included:'Включено в стоимость',excluded:'Не включено в стоимость',customer:'Обеспечивает заказчик',clarifications:'Требует уточнения'};
  const e=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const scopeFields=(value={})=>`<details class="editor-section assembly-scope"><summary>Границы предложения</summary><p class="muted">Эти условия увидит заказчик. Один пункт на строку. Укажите, кто покупает материалы, оплачивает доставку, подъём и вывоз мусора.</p><div class="form-grid">${Object.entries(labels).map(([key,label])=>`<label>${label}<textarea name="scope_${key}" rows="3" maxlength="10000" placeholder="Один пункт на строку">${e((value[key]||[]).join('\n'))}</textarea></label>`).join('')}</div></details>`;
  const readScope=form=>Object.fromEntries(Object.keys(labels).map(key=>[key,(form.elements['scope_'+key]?.value||'').split('\n').map(text=>text.trim()).filter(Boolean)]));
  const scopeHTML=(value={})=>Object.entries(labels).filter(([key])=>value[key]?.length).map(([key,label])=>`<section class="assembly-document-scope"><h3>${label}</h3><ul>${value[key].map(text=>`<li>${e(text)}</li>`).join('')}</ul></section>`).join('');
  const mergeScope=(before,extra)=>Object.fromEntries(Object.keys(labels).map(key=>[key,[...new Set([...(before[key]||[]),...(extra[key]||[])])]]));
  function mount(host,o){
    let definitions=[],destroyed=false;
    const live=()=>!destroyed&&host.isConnected&&o.active();
    const cleanRows=()=>o.rows().map(({_raw,...row})=>structuredClone(row));
    const fingerprint=()=>JSON.stringify(o.snapshot());
    const call=(path,data,method='POST')=>o.api('/assemblies'+path,{method,body:JSON.stringify(data)});
    function refresh(){
      if(!live())return;
      const groups=new Map();for(const row of o.rows())if(row.assembly)groups.set(row.assembly.instance_id,row.assembly);
      host.innerHTML=`<details class="editor-bulk assembly-panel"><summary>Технологические сборки</summary><p class="muted">Связанные работы и материалы с пересчётом по объёму. Нормы расхода и цены — из ваших данных.</p><div class="assembly-actions"><button type="button" class="btn small" data-assembly="add">Добавить сборку</button><button type="button" class="btn small" data-assembly="create">Сохранить выбранные позиции как сборку</button></div><div class="assembly-instances">${[...groups].map(([id,source])=>`<div class="assembly-instance"><div><strong>${e(source.title)}</strong><small>${e(Object.entries(source.parameters).map(([key,value])=>key+' = '+value).join(' · '))} · версия ${e(source.template_revision)}</small></div><button type="button" class="btn small" data-recalculate="${e(id)}">Изменить параметры</button><button type="button" class="editor-tool" data-detach="${e(id)}">Отключить связь</button></div>`).join('')}</div><p class="form-error" role="alert"></p></details>`;
      host.querySelector('[data-assembly="add"]').onclick=()=>add();
      host.querySelector('[data-assembly="create"]').onclick=()=>create();
      host.querySelectorAll('[data-recalculate]').forEach(button=>button.onclick=()=>recalculate(groups.get(button.dataset.recalculate)));
      host.querySelectorAll('[data-detach]').forEach(button=>button.onclick=()=>{o.replace(o.rows().map(row=>{if(row.assembly?.instance_id!==button.dataset.detach)return row;const copy={...row};delete copy.assembly;return copy}));o.notify('Связь отключена. Количества сохранены и доступны для ручного изменения.')});
    }
    const fail=error=>{if(live())host.querySelector('[role=alert]').textContent=error.message};
    async function load(){const response=await o.api('/assemblies');if(live())definitions=response.items;return definitions}
    function dialog(title,subtitle,body){
      const root=o.modal(title,subtitle,`<form class="assembly-form">${body}<p class="form-error" role="alert"></p><div class="form-actions"><button type="submit" class="btn primary">Рассчитать</button><button type="button" class="btn" data-cancel>Отмена</button></div></form>`);
      root.querySelector('[data-cancel]').onclick=o.close;
      return {root,form:root.querySelector('form')};
    }
    function inputs(definition){return `<div class="form-grid">${Object.entries(definition.parameters).map(([key,value])=>`<label>${e(definition.labels?.[key]||key)}<input data-param="${e(key)}" type="number" min="0" max="1000000" step="any" required value="${e(value)}"></label>`).join('')}</div>`}
    const values=form=>Object.fromEntries([...form.querySelectorAll('[data-param]')].map(input=>[input.dataset.param,input.value]));
    function preview(form,result,apply,label='Добавить в смету'){
      let box=form.querySelector('.assembly-preview');if(!box){box=document.createElement('section');box.className='assembly-preview';form.querySelector('.form-actions').before(box)}
      const currency=o.currency();
      box.innerHTML=`<h3>Проверьте расчёт</h3><div class="assembly-preview-scroll"><table><thead><tr><th>Позиция</th><th>Количество</th><th>Стоимость</th></tr></thead><tbody>${result.items.map(row=>`<tr><td>${e(row.name)}${row.assembly?`<small>${e(row.assembly.expression)}</small>`:''}</td><td>${e(row.quantity)} ${e(row.unit)}</td><td>${e(o.money(row.subtotal,currency))}</td></tr>`).join('')}</tbody></table></div><strong>${e(o.money(result.amount_kopecks,currency))}</strong>${scopeHTML(result.scope)}<p class="muted">${e(result.note||'Цены и остальные позиции сохранены. Проверьте исходные размеры и нормы.')}</p><button type="button" class="btn primary" data-apply-assembly>${label}</button>`;
      const button=box.querySelector('[data-apply-assembly]');button.onclick=apply;
      form.addEventListener('input',()=>{button.disabled=true;box.setAttribute('aria-label','Данные изменились. Рассчитайте заново')},{once:true});
    }
    function submit(form,fn){form.onsubmit=async event=>{event.preventDefault();if(!form.reportValidity())return;const button=form.querySelector('[type=submit]');if(button.disabled)return;button.disabled=true;form.querySelector('[role=alert]').textContent='';try{await fn()}catch(error){if(form.isConnected)form.querySelector('[role=alert]').textContent=error.message}finally{if(button.isConnected)button.disabled=false}}}
    async function add(){
      try{await load();if(!live())return;if(!definitions.length){o.notify('Сначала выберите позиции своей сметы и сохраните их как сборку.');return}
        const {form}=dialog('Добавить сборку','Расценки из вашей библиотеки. После расчёта проверьте состав перед добавлением.',`<label>Сборка<select name="assembly">${definitions.map(d=>`<option value="${e(d.id)}">${e(d.title)} · версия ${d.revision}</option>`).join('')}</select></label><div data-parameters></div><div class="assembly-actions"><button type="button" class="btn small" data-edit>Изменить шаблон</button><button type="button" class="btn small" data-delete>Удалить шаблон</button></div>`);
        const select=form.elements.assembly,render=()=>{form.querySelector('[data-parameters]').innerHTML=inputs(definitions.find(d=>d.id===select.value));form.querySelector('.assembly-preview')?.remove()};select.onchange=render;render();
        form.querySelector('[data-edit]').onclick=()=>create(definitions.find(d=>d.id===select.value));
        form.querySelector('[data-delete]').onclick=async()=>{const definition=definitions.find(d=>d.id===select.value);if(!await window.SmetraDialog.confirm({title:"Удалить сборку?",message:"Применённые расчёты в сметах сохранятся.",confirmLabel:"Удалить",danger:true}))return;try{await call("/"+definition.id,{},"DELETE");if(live()){o.close();o.notify("Сборка удалена")}}catch(error){if(form.isConnected)form.querySelector("[role=alert]").textContent=error.message}};
        submit(form,async()=>{const before=fingerprint(),definition=definitions.find(d=>d.id===select.value),result=await call('/preview',{id:definition.id,revision:definition.revision,currency:o.currency(),parameters:values(form)});if(!live()||!form.isConnected)return;preview(form,result,()=>{if(!live())return;if(before!==fingerprint()){form.querySelector('[role=alert]').textContent='Смета изменилась. Рассчитайте сборку заново.';return}const current=cleanRows(),rows=current.length===1&&!current[0].name.trim()?[]:current;if(rows.length+result.items.length>200){form.querySelector('[role=alert]').textContent='В смете может быть до 200 позиций';return}o.scope(mergeScope(readScope(o.form),result.scope));o.replace([...rows,...result.items]);o.close();o.notify('Сборка добавлена в черновик. Проверьте технологию и цены перед публикацией.')})});
      }catch(error){fail(error)}
    }
    function recalculate(source){
      const {form}=dialog('Параметры сборки',source.title+' · пересчёт изменит только связанные количества в текущем черновике.',inputs(source));
      submit(form,async()=>{const before=fingerprint(),result=await call('/recalculate',{items:cleanRows(),instance_id:source.instance_id,parameters:values(form)});if(!live()||!form.isConnected)return;preview(form,result,()=>{if(!live())return;if(before!==fingerprint()){form.querySelector('[role=alert]').textContent='Смета изменилась. Повторите расчёт.';return}o.replace(result.items);o.close();o.notify('Количество пересчитано. Опубликованная версия сохранена.')},'Применить пересчёт')});
    }
    function create(existing=null){
      const selected=[...o.selected()].sort((a,b)=>a-b),rows=existing?structuredClone(existing.items):(selected.length?selected.map(index=>cleanRows()[index]):cleanRows()).filter(row=>row.name.trim());
      if(!rows.length||rows.length>50){o.notify('Выберите от 1 до 50 заполненных позиций сметы.');return}
      const {form}=dialog('Сохранить технологическую сборку','Укажите исходный объём, которому соответствуют выбранные количества. Формулы можно уточнить до сохранения.',`<label>Название сборки<input name="title" maxlength="120" required placeholder="Например, облицовка стен"></label><div class="form-grid"><label>Исходный объём<input name="base" type="number" min="0.0001" max="1000000" step="any" value="1" required></label><label>Название параметра<input name="label" maxlength="80" value="Объём, м²" required></label></div><p class="muted">volume — объём. Например, volume * 0.3 — расход 0,3 на единицу объёма. Здесь нет готовых нормативов: проверьте расход по технологии и производителю.</p><div class="assembly-formulas">${rows.map((row,index)=>`<label>${e(row.name)} · ${e(row.quantity)} ${e(row.unit)}<select data-kind="${index}" aria-label="Тип позиции ${index+1}">${[['work','Работа'],['material','Материал'],['service','Услуга'],['equipment','Оборудование'],['other','Прочее']].map(([key,label])=>`<option value="${key}" ${(row.kind||'work')===key?'selected':''}>${label}</option>`).join('')}</select><input data-formula="${index}" aria-label="Формула позиции ${index+1}" value="${e(existing?row.expression:'volume * '+row.quantity)}" maxlength="160" required></label>`).join('')}</div>${scopeFields(existing?.scope||readScope(o.form))}`);
      if(existing){form.elements.title.value=existing.title;form.elements.base.closest('.form-grid').innerHTML=inputs(existing);form.querySelector('[data-cancel]').before(Object.assign(document.createElement('p'),{className:'muted',textContent:'Изменение шаблона не меняет ранее применённые сборки.'}))}
      rows.forEach((row,index)=>{const label=form.querySelector(`[data-formula="${index}"]`).closest('label');label.insertAdjacentHTML('beforeend',`<span>Цена за единицу, ${e(existing?.currency||o.currency())}</span><input data-rate="${index}" type="number" min="0" step="0.01" required value="${e(row.unit_price/100)}" aria-label="Цена позиции ${index+1}">`)});
      if(!existing)form.elements.base.oninput=()=>{form.querySelectorAll('[data-formula]').forEach((input,index)=>input.value='volume * '+rows[index].quantity+' / ('+(form.elements.base.value||'1')+')')};
      form.querySelector('[type=submit]').textContent='Сохранить сборку';
      submit(form,async()=>{const data={title:form.elements.title.value,currency:existing?.currency||o.currency(),parameters:existing?values(form):{volume:form.elements.base.value},labels:existing?existing.labels:{volume:form.elements.label.value},scope:readScope(form),items:rows.map((row,index)=>({...row,unit_price:o.amount(form.querySelector(`[data-rate="${index}"]`).value),kind:form.querySelector(`[data-kind="${index}"]`).value,expression:form.querySelector(`[data-formula="${index}"]`).value}))};await call(existing?'/'+existing.id:'',{...data,...(existing?{revision:existing.revision}:{})},existing?'PATCH':'POST');if(live()&&form.isConnected){o.close();o.notify('Сборка сохранена. Теперь её можно добавить в эту или другую смету.')}});
    }
    refresh();
    return {refresh,destroy(){destroyed=true}};
  }
  window.SmetraAssemblies={mount,scopeFields,readScope,scopeHTML};
})();
