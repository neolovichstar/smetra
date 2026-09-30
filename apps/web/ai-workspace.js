'use strict';

window.SmetraKnowledgePanel=async function(root){
  const data=await api('/assistant/knowledge');
  const items=data.items;
  root.innerHTML=`<section class="assistant-knowledge"><div class="assistant-knowledge-head"><div><span class="overline">Контекст пространства</span><h2>База знаний</h2><p>Правила применяются ко всем диалогам; справочные записи ассистент находит по запросу.</p></div><button class="assistant-thread-action" id="knowledge-close" type="button" aria-label="Закрыть">×</button></div><div class="knowledge-list">${items.map(item=>`<button class="knowledge-item" type="button" data-id="${escapeHtml(item.id)}"><span>${item.kind==='rule'?'Правило':'Источник'} · ${item.enabled?'Активно':'Выключено'}</span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.content.slice(0,160))}</small></button>`).join('')||'<p class="muted">Здесь пока пусто. Добавьте правила работы или проверенный справочник.</p>'}</div>${data.can_edit?`<form id="knowledge-form"><h3 id="knowledge-form-title">Новая запись</h3><label>Название<input name="title" maxlength="120" required></label><label>Тип<select name="kind"><option value="reference">Справочник</option><option value="rule">Правило ассистента</option></select></label><label>Содержание<textarea name="content" maxlength="12000" rows="5" required></textarea></label><label class="knowledge-enabled"><input name="enabled" type="checkbox" checked> Использовать в ассистенте</label><div class="row"><button class="btn primary" type="submit">Сохранить</button><button class="btn small hidden" id="knowledge-delete" type="button">Удалить</button><button class="btn small" id="knowledge-reset" type="button">Сбросить</button></div><p id="knowledge-status" role="status"></p></form>`:''}</section>`;
  root.querySelector('#knowledge-close').onclick=()=>root.classList.add('hidden');
  if(!data.can_edit)return;
  const form=root.querySelector('#knowledge-form'),status=root.querySelector('#knowledge-status');
  let selected='';
  const reset=()=>{selected='';form.reset();form.elements.enabled.checked=true;root.querySelector('#knowledge-form-title').textContent='Новая запись';root.querySelector('#knowledge-delete').classList.add('hidden');status.textContent=''};
  root.querySelector('#knowledge-reset').onclick=reset;
  root.querySelectorAll('[data-id]').forEach(button=>button.onclick=()=>{
    const item=items.find(value=>value.id===button.dataset.id);if(!item)return;
    selected=item.id;form.elements.title.value=item.title;form.elements.kind.value=item.kind;form.elements.content.value=item.content;form.elements.enabled.checked=Boolean(item.enabled);
    root.querySelector('#knowledge-form-title').textContent='Редактировать запись';root.querySelector('#knowledge-delete').classList.remove('hidden');form.elements.title.focus();
  });
  form.onsubmit=async event=>{event.preventDefault();const payload={title:form.elements.title.value.trim(),kind:form.elements.kind.value,content:form.elements.content.value.trim(),enabled:form.elements.enabled.checked?1:0};const button=form.querySelector('[type=submit]');button.disabled=true;status.textContent='Сохраняем…';try{await api('/assistant/knowledge'+(selected?'/'+encodeURIComponent(selected):''),{method:selected?'PATCH':'POST',body:JSON.stringify(payload)});await window.SmetraKnowledgePanel(root)}catch(error){status.textContent=error.message}finally{button.disabled=false}};
  root.querySelector('#knowledge-delete').onclick=async()=>{if(!selected||!confirm('Удалить запись из базы знаний?'))return;try{await api('/assistant/knowledge/'+encodeURIComponent(selected),{method:'DELETE'});await window.SmetraKnowledgePanel(root)}catch(error){status.textContent=error.message}};
};
