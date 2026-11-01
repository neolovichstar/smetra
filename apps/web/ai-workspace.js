'use strict';

/* Memory and knowledge: personal facts the assistant remembers (by request or
   on its own, like ChatGPT memory) and the team's verified rules/references. */
window.SmetraKnowledgePanel=async function(root){
  const [shared,personal]=await Promise.all([api('/assistant/knowledge'),api('/assistant/memory')]);
  if(!root.isConnected)return;
  const scope=root.dataset.scope||'personal',isPersonal=scope==='personal',items=isPersonal?personal.items:shared.items,canEdit=isPersonal||shared.can_edit;
  const endpoint='/assistant/'+(isPersonal?'memory':'knowledge'),limit=personal.limit||50;
  const icon=(name,size=18)=>window.SmetraIcons?window.SmetraIcons.svg(name,size):'';
  const date=value=>value?new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short'}).format(new Date(Number(value)*1000)):'';
  const badge=item=>!item.enabled?['is-off','Не используется']:item.source==='assistant'?['is-auto','Запомнил ассистент']:isPersonal?['','Добавлено вами']:item.kind==='rule'?['','Правило']:['','Справочник'];
  const card=item=>{const [tone,label]=badge(item);return `<button class="knowledge-item${item.enabled?'':' is-disabled'}" type="button" data-id="${escapeHtml(item.id)}" aria-pressed="false"><span class="knowledge-item-top"><strong>${escapeHtml(item.title)}</strong><time>${escapeHtml(date(item.updated_at||item.created_at))}</time></span><small>${escapeHtml(item.content.slice(0,160))}</small><span class="knowledge-badge ${tone}">${label}</span></button>`};
  const empty=isPersonal
    ?`<div class="knowledge-empty"><span class="knowledge-empty-mark" aria-hidden="true">${icon('book',22)}</span><h3>Память пока пуста</h3><p>Расскажите ассистенту о своей работе — специализацию, город, любимые материалы, обычную наценку. Он запомнит сам или по просьбе «запомни…».</p></div>`
    :`<div class="knowledge-empty"><span class="knowledge-empty-mark" aria-hidden="true">${icon('book',22)}</span><h3>Знаний команды пока нет</h3><p>Добавьте правила работы и проверенные справочники — ассистент будет опираться на них во всех диалогах команды.</p></div>`;

  root.innerHTML=`<section class="knowledge-window${isPersonal?' is-personal':''}">
    <header class="knowledge-window-head">
      <span class="knowledge-mark" aria-hidden="true">${icon('book',20)}</span>
      <div><h2>Память и знания</h2><p>${isPersonal?'Что ассистент помнит о вас и вашей работе. Видите только вы.':'Общие правила и справочники рабочего пространства.'}</p></div>
      <button id="knowledge-close" type="button" aria-label="Закрыть знания">${icon('x')}</button>
    </header>
    <nav class="knowledge-tabs" aria-label="Хранилище знаний">
      <button type="button" data-knowledge-scope="personal" aria-pressed="${isPersonal}">Память<span>${personal.items.length}</span></button>
      <button type="button" data-knowledge-scope="workspace" aria-pressed="${!isPersonal}">Знания команды<span>${shared.items.length}</span></button>
    </nav>
    ${isPersonal?`<div class="knowledge-memory-bar">
      <div><strong>Ассистент запоминает сам</strong><small>Сохраняет полезные факты из разговоров и использует их в ответах. Просьба «забудь…» удаляет запись.</small></div>
      <label class="knowledge-switch"><input type="checkbox" id="knowledge-memory-toggle" ${personal.enabled?'checked':''} aria-label="Автоматическая память"><span aria-hidden="true"></span></label>
    </div>`:''}
    <div class="knowledge-window-body">
      <aside class="knowledge-side">
        <label class="knowledge-search">${icon('search',16)}<span class="visually-hidden">Поиск по записям</span><input id="knowledge-search" type="search" placeholder="Поиск" autocomplete="off"></label>
        <div class="knowledge-list-head"><span>${isPersonal?'Записей: '+items.length+' из '+limit:items.length+' '+(items.length%10===1&&items.length%100!==11?'запись':[2,3,4].includes(items.length%10)&&![12,13,14].includes(items.length%100)?'записи':'записей')}</span>${canEdit?`<button id="knowledge-add" type="button">${icon('plus',14)}Добавить</button>`:''}</div>
        <div class="knowledge-list">${items.map(card).join('')||empty}</div>
        ${isPersonal&&items.length?`<button class="knowledge-clear" id="knowledge-clear" type="button">${icon('trash',14)}Очистить память</button>`:''}
      </aside>
      <div class="knowledge-editor">
        <button class="knowledge-back" id="knowledge-back" type="button">${icon('arrow-left',16)}К списку</button>
        ${isPersonal&&!personal.enabled?'<p class="knowledge-paused">Автоматическая память выключена. Записи сохранены, ассистент их не использует, пока вы не включите её снова.</p>':''}
        ${canEdit?`<form id="knowledge-form">
          <div class="knowledge-form-head"><h3 id="knowledge-form-title">Новая запись</h3><p id="knowledge-form-hint">${isPersonal?'Короткая тема и один факт — так ассистенту проще ими пользоваться.':'Правила ассистент соблюдает всегда, справочники — читает по необходимости.'}</p></div>
          <label>Тема<input name="title" maxlength="120" placeholder="${isPersonal?'Например, специализация':'Например, стандартная наценка'}" required></label>
          ${isPersonal?'<input name="kind" type="hidden" value="reference">':'<label>Тип<select name="kind"><option value="reference">Справочник</option><option value="rule">Правило ассистента</option></select></label>'}
          <label>Содержание<textarea name="content" maxlength="${isPersonal?1500:12000}" rows="7" placeholder="${isPersonal?'Например, делаю ремонт квартир под ключ в Казани':'Добавьте правило или справочные данные…'}" required></textarea><span class="knowledge-counter" id="knowledge-counter">0 / ${isPersonal?1500:12000}</span></label>
          <label class="knowledge-enabled"><input name="enabled" type="checkbox" checked> Использовать в ответах</label>
          <div class="knowledge-form-actions"><button class="btn primary" type="submit">${icon('check',16)}Сохранить</button><button class="btn" id="knowledge-reset" type="button">Новая запись</button><button class="btn danger hidden" id="knowledge-delete" type="button">${icon('trash',16)}Удалить</button></div>
          <p id="knowledge-status" role="status"></p>
        </form>`:'<div class="knowledge-readonly"><h3>Знания команды</h3><p>Выберите запись, чтобы прочитать её. Изменять записи может руководитель пространства.</p><div id="knowledge-read-content"></div></div>'}
      </div>
    </div>
  </section>`;

  const windowNode=root.querySelector('.knowledge-window');
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
    if(button.disabled||root.dataset.saving==='true'||button.getAttribute('aria-pressed')==='true')return;
    button.disabled=true;root.dataset.scope=button.dataset.knowledgeScope;
    try{await window.SmetraKnowledgePanel(root)}catch(error){button.disabled=false;notify(error.message)}
  });
  root.querySelector('#knowledge-search').oninput=event=>{
    const query=event.target.value.trim().toLocaleLowerCase('ru');
    root.querySelectorAll('.knowledge-item').forEach(item=>item.hidden=Boolean(query)&&!item.textContent.toLocaleLowerCase('ru').includes(query));
  };
  root.querySelector('#knowledge-back').onclick=()=>windowNode.classList.remove('is-editing');
  root.querySelector('#knowledge-memory-toggle')?.addEventListener('change',async event=>{
    const toggle=event.target;toggle.disabled=true;
    try{await api('/profile',{method:'PATCH',body:JSON.stringify({memory_enabled:toggle.checked?1:0})});notify(toggle.checked?'Автоматическая память включена':'Автоматическая память выключена');await window.SmetraKnowledgePanel(root)}
    catch(error){toggle.checked=!toggle.checked;toggle.disabled=false;notify(error.message)}
  });
  root.querySelector('#knowledge-clear')?.addEventListener('click',async()=>{
    if(root.dataset.saving==='true')return;
    if(!(await window.SmetraDialog.confirm({title:'Очистить всю память?',message:'Ассистент забудет всё, что запомнил о вас. Знания команды останутся.',confirmLabel:'Очистить',danger:true})))return;
    try{await api('/assistant/memory',{method:'DELETE'});notify('Память очищена');await window.SmetraKnowledgePanel(root)}catch(error){notify(error.message)}
  });
  if(!canEdit){root.querySelectorAll('[data-id]').forEach(button=>button.onclick=()=>{const item=items.find(value=>value.id===button.dataset.id);const content=root.querySelector('#knowledge-read-content');content.innerHTML='<h4>'+escapeHtml(item.title)+'</h4>';const text=document.createElement('p');text.textContent=item.content;content.append(text);root.querySelectorAll('[data-id]').forEach(value=>value.setAttribute('aria-pressed',String(value===button)));windowNode.classList.add('is-editing')});return}
  const form=root.querySelector('#knowledge-form'),status=root.querySelector('#knowledge-status'),counter=root.querySelector('#knowledge-counter');let selected='';
  const count=()=>{counter.textContent=form.elements.content.value.length+' / '+form.elements.content.maxLength};
  form.elements.content.addEventListener('input',count);
  const reset=()=>{selected='';form.reset();form.elements.enabled.checked=true;root.querySelector('#knowledge-form-title').textContent='Новая запись';root.querySelector('#knowledge-delete').classList.add('hidden');status.textContent='';count();root.querySelectorAll('[data-id]').forEach(item=>item.setAttribute('aria-pressed','false'));windowNode.classList.add('is-editing');form.elements.title.focus()};
  root.querySelector('#knowledge-reset').onclick=reset;root.querySelector('#knowledge-add').onclick=reset;
  root.querySelectorAll('[data-id]').forEach(button=>button.onclick=()=>{
    if(root.dataset.saving==='true')return;const item=items.find(value=>value.id===button.dataset.id);if(!item)return;
    selected=item.id;form.elements.title.value=item.title;form.elements.kind.value=item.kind||'reference';form.elements.content.value=item.content;form.elements.enabled.checked=Boolean(item.enabled);count();
    root.querySelector('#knowledge-form-title').textContent=item.source==='assistant'?'Запомнил ассистент':'Запись';root.querySelector('#knowledge-delete').classList.remove('hidden');root.querySelectorAll('[data-id]').forEach(value=>value.setAttribute('aria-pressed',String(value===button)));
    windowNode.classList.add('is-editing');form.elements.title.focus({preventScroll:true});
  });
  const save=async action=>{
    if(root.dataset.saving==='true')return;root.dataset.saving='true';root.querySelectorAll('button,input,textarea,select').forEach(control=>{if(control.id!=='knowledge-close')control.disabled=true});status.textContent='Сохраняем…';
    try{await action();await window.SmetraKnowledgePanel(root)}catch(error){status.textContent=error.message}
    finally{delete root.dataset.saving;root.querySelectorAll('button,input,textarea,select').forEach(control=>control.disabled=false)}
  };
  form.onsubmit=event=>{event.preventDefault();const payload={title:form.elements.title.value.trim(),content:form.elements.content.value.trim(),enabled:form.elements.enabled.checked?1:0};if(!payload.title||!payload.content){status.textContent='Заполните тему и содержание';return}if(!isPersonal)payload.kind=form.elements.kind.value;return save(()=>api(endpoint+(selected?'/'+encodeURIComponent(selected):''),{method:selected?'PATCH':'POST',body:JSON.stringify(payload)}))};
  root.querySelector('#knowledge-delete').onclick=async()=>{if(!selected||root.dataset.saving==='true'||!(await window.SmetraDialog.confirm({title:'Удалить запись?',message:'Ассистент перестанет учитывать её в ответах.',confirmLabel:'Удалить',danger:true})))return;return save(()=>api(endpoint+'/'+encodeURIComponent(selected),{method:'DELETE'}))};
};
