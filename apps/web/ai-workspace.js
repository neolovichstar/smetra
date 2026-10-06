'use strict';

window.SmetraKnowledgePanel=async function(root){
  const [shared,personal]=await Promise.all([api('/assistant/knowledge'),api('/assistant/memory')]);
  if(!root.isConnected)return;
  const scope=root.dataset.scope||'personal',isPersonal=scope==='personal',items=isPersonal?personal.items:shared.items,canEdit=isPersonal||shared.can_edit;
  const endpoint='/assistant/'+(isPersonal?'memory':'knowledge');
  root.innerHTML=`<section class="knowledge-window"><header class="knowledge-window-head"><div><h2>Знания</h2><p>То, что помогает ассистенту понимать вашу работу.</p></div><button id="knowledge-close" type="button" aria-label="Закрыть знания">×</button></header>
    <nav class="knowledge-tabs" aria-label="Хранилище знаний"><button type="button" data-knowledge-scope="personal" aria-pressed="${isPersonal}">Личная память</button><button type="button" data-knowledge-scope="workspace" aria-pressed="${!isPersonal}">Знания команды</button></nav>
    <div class="knowledge-window-body"><aside><div class="knowledge-list-head"><span>${items.length} записей</span>${canEdit?'<button id="knowledge-add" type="button">Добавить</button>':''}</div><div class="knowledge-list">${items.map(item=>`<button class="knowledge-item" type="button" data-id="${escapeHtml(item.id)}"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.content.slice(0,110))}</small><span>${!item.enabled?'Не используется':item.source==='assistant'?'Запомнил ассистент':isPersonal?'Добавлено вами':item.kind==='rule'?'Правило команды':'Справочник'}</span></button>`).join('')||`<div class="knowledge-empty"><span></span><h3>Пока ничего нет</h3><p>${isPersonal?'Ассистент запоминает полезные факты из разговора. Можно добавить запись самостоятельно.':'Добавьте правила работы и проверенные справочники для команды.'}</p></div>`}</div></aside>
    <div class="knowledge-editor">${isPersonal&&!personal.enabled?'<p class="knowledge-paused">Автоматическая память выключена в настройках. Записи сохранены.</p>':''}${canEdit?`<form id="knowledge-form"><h3 id="knowledge-form-title">Новая запись</h3><label>Название<input name="title" maxlength="120" placeholder="Например, моя специализация" required></label>${isPersonal?'<input name="kind" type="hidden" value="reference">':'<label>Тип<select name="kind"><option value="reference">Справочник</option><option value="rule">Правило ассистента</option></select></label>'}<label>Содержание<textarea name="content" maxlength="${isPersonal?1500:12000}" rows="6" placeholder="Добавьте факты или предпочтения…" required></textarea></label><label class="knowledge-enabled"><input name="enabled" type="checkbox" checked> Использовать в ответах</label><div class="knowledge-form-actions"><button class="btn primary" type="submit">Сохранить</button><button class="btn hidden" id="knowledge-delete" type="button">Удалить</button><button class="btn" id="knowledge-reset" type="button">Новая запись</button></div><p id="knowledge-status" role="status"></p></form>`:'<div class="knowledge-readonly"><h3>Знания команды</h3><p>Выберите запись, чтобы прочитать её. Изменять записи может руководитель пространства.</p><div id="knowledge-read-content"></div></div>'}</div></div><footer class="knowledge-window-foot">${isPersonal?'Личная память доступна только вам. Её можно изменить или удалить.':'Эти записи доступны участникам текущего рабочего пространства.'}</footer></section>`;
  const close=()=>{
    document.querySelector('#assistant-knowledge')?.setAttribute('aria-expanded','false');
    root.classList.add('is-closing');
    const finish=()=>{if(root.open)root.close();root.classList.remove('is-closing');root.classList.add('hidden');document.querySelector('#assistant-knowledge')?.focus()};
    if(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)finish();else setTimeout(finish,150);
  };
  root.querySelector('#knowledge-close').onclick=close;root.oncancel=event=>{event.preventDefault();close()};
  root.onclick=event=>{if(event.target===root)close()};
  root.onclose=()=>document.querySelector('#assistant-knowledge')?.setAttribute('aria-expanded','false');
  root.querySelectorAll('[data-knowledge-scope]').forEach(button=>button.onclick=async()=>{
    if(button.disabled||root.dataset.saving==='true')return;
    button.disabled=true;root.dataset.scope=button.dataset.knowledgeScope;
    try{await window.SmetraKnowledgePanel(root)}catch(error){button.disabled=false;notify(error.message)}
  });
  if(!canEdit){root.querySelectorAll('[data-id]').forEach(button=>button.onclick=()=>{const item=items.find(value=>value.id===button.dataset.id);const content=root.querySelector('#knowledge-read-content');content.innerHTML='<h4>'+escapeHtml(item.title)+'</h4>';const text=document.createElement('p');text.textContent=item.content;content.append(text)});return}
  const form=root.querySelector('#knowledge-form'),status=root.querySelector('#knowledge-status');let selected='';
  const reset=()=>{selected='';form.reset();form.elements.enabled.checked=true;root.querySelector('#knowledge-form-title').textContent='Новая запись';root.querySelector('#knowledge-delete').classList.add('hidden');status.textContent='';root.querySelectorAll('[data-id]').forEach(item=>item.setAttribute('aria-pressed','false'));form.elements.title.focus()};
  root.querySelector('#knowledge-reset').onclick=reset;root.querySelector('#knowledge-add').onclick=reset;
  root.querySelectorAll('[data-id]').forEach(button=>button.onclick=()=>{
    if(root.dataset.saving==='true')return;const item=items.find(value=>value.id===button.dataset.id);if(!item)return;
    selected=item.id;form.elements.title.value=item.title;form.elements.kind.value=item.kind||'reference';form.elements.content.value=item.content;form.elements.enabled.checked=Boolean(item.enabled);
    root.querySelector('#knowledge-form-title').textContent='Редактировать запись';root.querySelector('#knowledge-delete').classList.remove('hidden');root.querySelectorAll('[data-id]').forEach(value=>value.setAttribute('aria-pressed',String(value===button)));form.elements.title.focus({preventScroll:true});
  });
  const save=async action=>{
    if(root.dataset.saving==='true')return;root.dataset.saving='true';root.querySelectorAll('button,input,textarea,select').forEach(control=>{if(control.id!=='knowledge-close')control.disabled=true});status.textContent='Сохраняем…';
    try{await action();await window.SmetraKnowledgePanel(root)}catch(error){status.textContent=error.message}
    finally{delete root.dataset.saving;root.querySelectorAll('button,input,textarea,select').forEach(control=>control.disabled=false)}
  };
  form.onsubmit=event=>{event.preventDefault();const payload={title:form.elements.title.value.trim(),content:form.elements.content.value.trim(),enabled:form.elements.enabled.checked?1:0};if(!payload.title||!payload.content){status.textContent='Заполните название и содержание';return}if(!isPersonal)payload.kind=form.elements.kind.value;return save(()=>api(endpoint+(selected?'/'+encodeURIComponent(selected):''),{method:selected?'PATCH':'POST',body:JSON.stringify(payload)}))};
  root.querySelector('#knowledge-delete').onclick=()=>{if(!selected||root.dataset.saving==='true'||!confirm('Удалить запись из знаний?'))return;return save(()=>api(endpoint+'/'+encodeURIComponent(selected),{method:'DELETE'}))};
};
