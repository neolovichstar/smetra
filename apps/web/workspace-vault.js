/* Workspace storage and release notes. No local persistence of file contents. */
(function () {
  'use strict';
  const esc = value => escapeHtml(value);
  const human = bytes => bytes >= 1e9 ? (bytes / 1e9).toFixed(2) + ' ГБ' : bytes >= 1e6 ? (bytes / 1e6).toFixed(1) + ' МБ' : Math.max(0, Math.ceil(bytes / 1024)) + ' КБ';
  const when = seconds => new Date(seconds * 1000).toLocaleDateString('ru-RU', {day:'numeric',month:'long',year:'numeric'});
  const teaser = value => String(value || '').replace(/!\[[^\]]*\]\([^)]*\)/g,' ').replace(/\[([^\]]+)\]\([^)]*\)/g,'$1').replace(/[#*_`>|~]/g,' ').replace(/\s+/g,' ').trim().slice(0,190);
  const thumbs = {
    up:'<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v11H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3Zm0 11h9.4a3 3 0 0 0 2.9-2.2l2-7a2 2 0 0 0-1.9-2.5H14l.8-4.4a2.1 2.1 0 0 0-3.9-1.4L7 10"/></svg>',
    down:'<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M7 14V3H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3Zm0-11h9.4a3 3 0 0 1 2.9 2.2l2 7a2 2 0 0 1-1.9 2.5H14l.8 4.4a2.1 2.1 0 0 1-3.9 1.4L7 14"/></svg>'
  };
  const fileSymbol = file => {
    const ext = (file.name.split('.').pop() || 'FILE').toUpperCase().slice(0,5);
    return '<span class="vault-file-icon" aria-hidden="true"><svg viewBox="0 0 42 50" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M7 2h18l10 10v35H7z"/><path d="M25 2v11h10"/><path d="M13 22h16M13 27h16"/></svg><b>' + esc(ext) + '</b></span>';
  };
  const head = (title,description) => '<header class="vault-head"><span class="vault-eyebrow">СМЕТРА / РАБОЧЕЕ ПРОСТРАНСТВО</span><h1>' + title + '</h1><p>' + description + '</p></header>';
  let epoch = 0, thumbAbort = null, thumbUrls = [];
  function cleanup() {
    ++epoch;
    if (thumbAbort) thumbAbort.abort();
    thumbAbort = null;
    for (const url of thumbUrls) URL.revokeObjectURL(url);
    thumbUrls = [];
  }
  // A hashchange into this page must not cancel its own in-flight render.
  window.addEventListener('hashchange', () => {
    const section=location.hash.slice(1);
    if(section!=='files' && section!=='changelog') cleanup();
  });
  const state = {filter:'images',search:'',offset:0,files:[],result:null,canWrite:false,wid:''};
  let listRequest=0;
  const activePage = mine => epoch === mine && tab === 'files' && document.querySelector('#vault-root');

  async function thumbLoad(mine) {
    if (!activePage(mine)) return;
    if (thumbAbort) thumbAbort.abort();
    for (const url of thumbUrls) URL.revokeObjectURL(url);
    thumbUrls = [];
    thumbAbort = new AbortController();
    const images = Array.from(document.querySelectorAll('#vault-root img[data-thumb]'));
    const controller = thumbAbort;
    let next = 0;
    async function worker() {
      while (next < images.length && activePage(mine) && !controller.signal.aborted) {
        const node = images[next++];
        const id = node.dataset.thumb;
        try {
          const response = await fetch('/api/files/' + encodeURIComponent(id) + '/thumbnail', {
            credentials:'same-origin', signal:controller.signal,
            headers:state.wid ? {'X-Workspace-Id':state.wid} : {}
          });
          if (!response.ok) throw Error('thumb');
          const blob = await response.blob();
          if (!activePage(mine) || controller.signal.aborted) return;
          const url = URL.createObjectURL(blob);
          thumbUrls.push(url);
          node.src = url;
        } catch (err) {
          if (err.name === 'AbortError') return;
          node.classList.add('is-unavailable');
        }
      }
    }
    await Promise.all(Array.from({length:Math.min(4,images.length)},worker));
  }

  function fileCard(file) {
    const image = file.mime === 'image/jpeg' || file.mime === 'image/png';
    const controls = '<div class="vault-item-actions">' +
      '<button type="button" data-action="open" data-id="' + esc(file.id) + '" aria-label="Открыть">Открыть</button>' +
      '<button type="button" data-action="ask" data-id="' + esc(file.id) + '">Спросить ИИ</button>' +
      (state.canWrite ? '<button type="button" data-file-manage="' + esc(file.id) + '" data-action="manage" data-id="' + esc(file.id) + '">Данные</button><button type="button" data-action="archive" data-id="' + esc(file.id) + '">' + (file.archived ? 'Восстановить' : 'В архив') + '</button>' +
      '<button type="button" class="is-destructive" data-action="delete" data-id="' + esc(file.id) + '">Удалить</button>' : '') +
      '</div>';
    if (image) return '<article class="vault-image-tile"><button type="button" class="vault-image-preview" data-action="open" data-id="' + esc(file.id) + '" aria-label="Просмотреть ' + esc(file.name) + '"><img data-thumb="' + esc(file.id) + '" alt="' + esc(file.name) + '" loading="lazy" decoding="async"></button>' +
      '<div class="vault-image-info"><strong title="' + esc(file.name) + '">' + esc(file.name) + '</strong><small>' + human(file.size) + '</small></div>' + controls + '</article>';
    return '<article class="vault-file-tile file-center-row">' + fileSymbol(file) +
      '<div class="vault-file-details"><strong title="' + esc(file.name) + '">' + esc(file.name) + '</strong><small>' + human(file.size) + ' · ' + when(file.created_at) + '</small></div>' + controls + '</article>';
  }
  function paint(mine) {
    if (!activePage(mine)) return;
    const result = state.result;
    const used = result.used_bytes || 0, quota = result.quota_bytes || 100000000;
    document.querySelector('#vault-usage').textContent = human(used) + ' из ' + human(quota);
    const meter = document.querySelector('#vault-meter');
    meter.value = Math.min(100,Math.round(100 * used / quota));
    const root = document.querySelector('#vault-items');
    if (!root) return;
    const showingImages = state.filter === 'images';
    root.className = showingImages ? 'vault-gallery' : 'vault-file-grid';
    root.innerHTML = state.files.length ? state.files.map(fileCard).join('') :
      '<div class="vault-empty"><strong>Здесь пока пусто</strong><p>' +
      (state.search ? 'По запросу ничего не найдено.' : state.filter === 'archive' ? 'В архиве нет файлов.' : 'Загрузите файлы или прикрепите их в чате ассистента.') + '</p></div>';
    document.querySelector('#vault-total').textContent = state.files.length + ' из ' + (result.total || 0) + ' файлов';
    document.querySelector('#vault-more').hidden = state.files.length >= (result.total || 0);
    document.querySelectorAll('#vault-root [data-filter]').forEach(button => {
      const selected = button.dataset.filter === state.filter;
      button.classList.toggle('selected',selected);
      button.setAttribute('aria-selected',String(selected));
    });
    thumbLoad(mine);
  }
  async function loadFiles(mine,append=false) {
    const request=++listRequest;
    const query = new URLSearchParams({q:state.search,archived:state.filter==='archive'?'1':'0',type:state.filter==='images'?'images':state.filter==='files'?'documents':'all',offset:String(append?state.offset:0)});
    const result = await api('/files?' + query.toString());
    if (!activePage(mine) || request!==listRequest) return;
    state.result = result;
    state.files = append ? state.files.concat(result.items) : result.items;
    state.offset = state.files.length;
    paint(mine);
  }

  async function upload(files,mine) {
    if (!state.canWrite || !files.length) return;
    const max = state.result?.max_upload_bytes || 3000000;
    if (files.length > 10) { notify('За раз можно загрузить до 10 файлов'); return; }
    const progress = document.querySelector('#vault-progress');
    if (progress) progress.hidden = false;
    let count = 0;
    try {
      for (const file of files) {
        if (!activePage(mine)) return;
        if (file.size < 1 || file.size > max) throw Error('Файл «' + file.name + '» превышает допустимый размер: ' + human(max));
        const bytes = new Uint8Array(await file.arrayBuffer());
        let binary = '';
        for (let i=0; i<bytes.length; i+=32768) binary += String.fromCharCode(...bytes.subarray(i,i+32768));
        await api('/files', {method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},
          body:JSON.stringify({assistant_upload:true,name:file.name,content:btoa(binary)})});
        count++;
        if (progress) progress.textContent = 'Загружено ' + count + ' из ' + files.length;
      }
      if (activePage(mine)) { notify('Файлы сохранены в рабочем пространстве'); await loadFiles(mine); }
    } catch(err) {
      notify(err.message);
      if (count && activePage(mine)) await loadFiles(mine);
    } finally { if (progress) progress.hidden = true; }
  }
  async function ask(file) {
    await window.SmetraLoadFeature('assistant');
    window.SmetraAssistantContext({entity:'files',id:file.id,label:file.name,workspace_id:state.wid});
    sessionStorage.setItem('smetra.assistant.prefill',JSON.stringify({
      file_id:file.id,workspace_id:state.wid,text:'Помоги разобраться с файлом «' + file.name + '».'
    }));
    tab = 'assistant'; location.hash = 'assistant';
    await window.render();
  }
  async function renderFiles(active=()=>true) {
    cleanup();
    const mine = epoch;
    ++listRequest;
    const owner = user;
    const preserving = !!document.querySelector('#vault-root');
    const filter = preserving ? state.filter : 'images';
    const search = preserving ? state.search : '';
    const params = new URLSearchParams({q:search,archived:filter==='archive'?'1':'0',type:filter==='images'?'images':filter==='files'?'documents':'all'});
    const [workspaceResult,result] = await Promise.all([api('/workspace'),api('/files?' + params)]);
    if (!active() || epoch !== mine || owner !== user || tab !== 'files') return;
    state.wid = workspaceResult.workspace?.id || sessionStorage.getItem('workspace_id') || '';
    state.canWrite = workspaceResult.workspace?.role !== 'viewer';
    state.filter=filter; state.search=search; state.files=result.items; state.result=result; state.offset=result.items.length;
    view('<section id="vault-root" class="vault-root">' +
      head('Хранилище','Все изображения, документы и вложения рабочего пространства в одном месте.') +
      '<div class="vault-tools"><div class="vault-space"><span>Использовано места</span><strong id="vault-usage"></strong><progress id="vault-meter" max="100" value="0" aria-label="Использование хранилища"></progress></div>' +
      (state.canWrite ? '<label for="vault-upload" class="btn primary vault-upload">+ Загрузить<input id="vault-upload" type="file" accept=".png,.jpg,.jpeg,.pdf,.txt,.md,.docx,.xlsx,.csv" multiple hidden></label>':'') + '</div>' +
      '<div class="vault-bar"><div role="tablist" class="vault-tabs" aria-label="Тип файлов"><button type="button" data-filter="images" role="tab">Изображения</button><button type="button" data-filter="files" role="tab">Файлы</button><button type="button" data-filter="archive" role="tab">Архив</button></div><input id="vault-search" type="search" aria-label="Поиск файлов" placeholder="Поиск по названию"></div>' +
      '<p id="vault-progress" class="vault-progress" hidden role="status"></p><div id="vault-items" aria-live="polite" aria-relevant="additions text"></div>' +
      '<footer class="vault-footer"><span id="vault-total"></span><button class="btn small" id="vault-more" type="button">Показать ещё</button></footer>' +
      '</section>');
    paint(mine);
    const root = document.querySelector('#vault-root');
    root.querySelector('#vault-search').value = search;
    let searchTimer,sequence=0;
    root.querySelector('#vault-search').oninput = event => {
      state.search = event.target.value.trim(); state.offset=0;
      const request = ++sequence;
      clearTimeout(searchTimer);
      searchTimer=setTimeout(()=>{if(request===sequence)loadFiles(mine).catch(err=>notify(err.message));},240);
    };
    root.querySelector('#vault-more').onclick = () => loadFiles(mine,true).catch(err=>notify(err.message));
    root.querySelector('#vault-upload')?.addEventListener('change',event => {
      upload(Array.from(event.target.files),mine).catch(err=>notify(err.message));
      event.target.value='';
    });
    root.addEventListener('click',async event => {
      const filter = event.target.closest('[data-filter]');
      if (filter) { state.filter=filter.dataset.filter; state.offset=0; await loadFiles(mine).catch(err=>notify(err.message)); return; }
      const button = event.target.closest('[data-action]');
      if (!button) return;
      const file = state.files.find(item=>item.id===button.dataset.id);
      if (!file) return;
      const action = button.dataset.action;
      if (action === 'open') return window.SmetraFilePreview?.open(file,state.wid);
      if (action === 'ask') return ask(file).catch(err=>notify(err.message));
      if (action === 'manage') return window.Workspace.manageFile(file.id).catch(err=>notify(err.message));
      if (!state.canWrite) return;
      if (action === 'delete' && !confirm('Удалить «' + file.name + '» без возможности восстановления?')) return;
      button.disabled = true;
      try {
        if (action === 'archive') await api('/files/'+encodeURIComponent(file.id)+'/archive',{method:'PATCH',body:JSON.stringify({archived:file.archived?0:1})});
        else if (action === 'delete') await api('/files/'+encodeURIComponent(file.id),{method:'DELETE'});
        await loadFiles(mine);
      } catch(err) {notify(err.message);button.disabled=false;}
    });
  }

  let notes=[],canPublish=false,openedNote='';
  const activeNews = mine => epoch===mine && tab==='changelog' && document.querySelector('#changelog-root');
  async function noteMarkup(body) {
    await window.SmetraLoadFeature('markdown');
    return window.SmetraMarkdown?.render(body) ?? '<pre>' + esc(body) + '</pre>';
  }
  async function paintNews(mine) {
    if (!activeNews(mine)) return;
    const list=document.querySelector('#changelog-list');
    list.innerHTML=notes.length ? notes.map((item,index) =>
      '<article class="changelog-entry'+(openedNote===item.id?' is-open':'')+'" data-id="'+esc(item.id)+'">' +
      '<button type="button" class="changelog-open" data-note="'+esc(item.id)+'" aria-controls="changelog-content-'+esc(item.id)+'" aria-expanded="'+(openedNote===item.id)+'">' +
      '<span class="changelog-date">'+when(item.published_at)+'</span><span class="changelog-copy">' +
      '<span class="changelog-title">'+esc(item.title)+'</span>' +
      (openedNote===item.id?'':'<span class="changelog-excerpt">'+esc(teaser(item.body))+'</span>') +
      '</span><span class="changelog-meta">'+(item.version?'<span class="changelog-version">'+esc(item.version)+'</span>':index===0&&item.published?'<span class="changelog-version">Последнее</span>':'') +
      '<svg class="changelog-chevron" aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.65"><path d="m7 5 5 5-5 5"/></svg></span></button>' +
      (openedNote===item.id?'<div class="changelog-body assistant-markdown" id="changelog-content-'+esc(item.id)+'"></div>':'') +
      '<div class="changelog-footer"><span class="changelog-views">'+Number(item.view_count||0).toLocaleString('ru-RU')+' просмотров</span>' +
      (item.published?'<div class="changelog-reactions">' +
      '<button type="button" data-react="like" data-id="'+esc(item.id)+'" aria-label="Нравится, '+Number(item.likes||0)+'" aria-pressed="'+(item.my_reaction==='like')+'">'+thumbs.up+'<span>'+Number(item.likes||0).toLocaleString('ru-RU')+'</span></button>' +
      '<button type="button" data-react="dislike" data-id="'+esc(item.id)+'" aria-label="Не нравится, '+Number(item.dislikes||0)+'" aria-pressed="'+(item.my_reaction==='dislike')+'">'+thumbs.down+'<span>'+Number(item.dislikes||0).toLocaleString('ru-RU')+'</span></button></div>':'') +
      (canPublish?'<button type="button" class="changelog-edit" data-edit="'+esc(item.id)+'">Редактировать</button>':'') +
      (!item.published?'<span class="changelog-draft">Черновик</span>':'')+'</div></article>').join('') :
      '<div class="vault-empty"><strong>Пока нет обновлений</strong><p>Здесь появятся новости о новых функциях Сметры.</p></div>';
    if (openedNote) {
      const entry=notes.find(item=>item.id===openedNote);
      if (entry) {
        const body=await noteMarkup(entry.body);
        if (activeNews(mine)) {
          const container=document.getElementById('changelog-content-'+entry.id);
          if(container) container.innerHTML=body;
        }
      }
    }
  }
  async function refreshNotes(mine) {
    const result=await api('/changelog');
    if(!activeNews(mine))return;
    notes=result.items;canPublish=result.can_publish;
    await paintNews(mine);
  }
  function editor(note,mine) {
    const dialog=document.createElement('dialog');dialog.className='changelog-editor';
    dialog.innerHTML='<form class="changelog-form"><h2>'+(note?'Редактировать обновление':'Новая публикация')+'</h2>'+
      '<label>Заголовок<input name="title" required maxlength="160" value="'+esc(note?.title||'')+'"></label>'+
      '<label>Версия<input name="version" maxlength="32" placeholder="Например, 2.1" value="'+esc(note?.version||'')+'"></label>'+
      '<div class="changelog-editor-toolbar"><span>Содержимое Markdown</span><button type="button" data-preview-toggle aria-pressed="false">Предпросмотр</button></div>' +
      '<textarea name="body" aria-label="Содержимое Markdown" required rows="12" maxlength="30000" spellcheck="true"></textarea>' +
      '<div class="changelog-preview assistant-markdown" data-preview-pane hidden></div>' +
      '<label class="changelog-published"><input type="checkbox" name="published" '+(!note||note.published?'checked':'')+'> Опубликовать</label>'+
      '<p class="changelog-error" role="alert"></p>'+
      '<div class="changelog-form-actions"><button type="button" data-cancel>Отмена</button><button class="btn primary" type="submit">Сохранить</button></div></form>';
    document.body.append(dialog);dialog.querySelector('textarea').value=note?.body||'';
    const textarea=dialog.querySelector('textarea[name=body]');
    const toggle=dialog.querySelector('[data-preview-toggle]');
    const pane=dialog.querySelector('[data-preview-pane]');
    let previewActive=false;
    let previewTimer=null;
    const preview=async()=>{
      if(!previewActive)return;
      try {
        await window.SmetraLoadFeature('markdown');
        if(!dialog.isConnected || !previewActive)return;
        pane.innerHTML=window.SmetraMarkdown.render(textarea.value||'*Напишите текст обновления, чтобы увидеть предпросмотр.*');
      }catch(error){if(dialog.isConnected)pane.textContent='Не удалось загрузить предпросмотр: '+error.message;}
    };
    toggle.onclick=()=>{
      previewActive=!previewActive;
      pane.hidden=!previewActive;
      toggle.setAttribute('aria-pressed',String(previewActive));
      toggle.textContent=previewActive?'К редактированию':'Предпросмотр';
      textarea.hidden=previewActive;
      if(previewActive)void preview();
      else textarea.focus();
    };
    textarea.addEventListener('input',()=>{if(previewActive){clearTimeout(previewTimer);previewTimer=setTimeout(()=>void preview(),250);}});
    const close=()=>dialog.close();dialog.querySelector('[data-cancel]').onclick=close;
    dialog.addEventListener('close',()=>{clearTimeout(previewTimer);dialog.remove();},{once:true});
    dialog.querySelector('form').onsubmit=async event=>{
      event.preventDefault();
      const form=event.currentTarget,button=form.querySelector('[type=submit]');
      button.disabled=true;
      const body=JSON.stringify({title:form.elements.title.value,version:form.elements.version.value,body:form.elements.body.value,published:form.elements.published.checked?1:0});
      try{
        await api(note?'/changelog/'+encodeURIComponent(note.id):'/changelog',{method:note?'PATCH':'POST',body});
        close(); if(activeNews(mine))await refreshNotes(mine);
      }catch(err){form.querySelector('[role=alert]').textContent=err.message;button.disabled=false;}
    };
    dialog.showModal();
  }
  async function renderNews(active=()=>true) {
    cleanup();
    const mine=epoch,owner=user;
    const result=await api('/changelog');
    if(!active()||epoch!==mine||owner!==user||tab!=='changelog')return;
    notes=result.items;canPublish=result.can_publish;openedNote='';
    view('<section id="changelog-root" class="vault-root">'+head('Что нового','История изменений Сметры. Оценивайте обновления, чтобы помогать нам делать сервис лучше.')+
      '<div class="changelog-toolbar"><span>Обновления продукта</span>'+(canPublish?'<button class="btn primary" id="changelog-publish">+ Опубликовать</button>':'')+'</div>'+
      '<div id="changelog-list" class="changelog-list"></div></section>');
    await paintNews(mine);
    const root=document.querySelector('#changelog-root');
    root.querySelector('#changelog-publish')?.addEventListener('click',()=>editor(null,mine));
    root.addEventListener('click',async event=>{
      const edit=event.target.closest('[data-edit]');
      if(edit){editor(notes.find(item=>item.id===edit.dataset.edit),mine);return;}
      const react=event.target.closest('[data-react]');
      if(react){
        const note=notes.find(item=>item.id===react.dataset.id);
        if(!note)return;
        const old=note.my_reaction||'none',desired=old===react.dataset.react?'none':react.dataset.react;
        react.disabled=true;
        try{await api('/changelog/'+encodeURIComponent(note.id)+'/reaction',{method:'POST',body:JSON.stringify({reaction:desired})});await refreshNotes(mine);}
        catch(err){notify(err.message);react.disabled=false;}
        return;
      }
      const open=event.target.closest('[data-note]');
      if(open){
        const note=notes.find(item=>item.id===open.dataset.note);
        openedNote=openedNote===note.id?'':note.id;
        await paintNews(mine);
        if(openedNote&&note.published){
          try{await api('/changelog/'+encodeURIComponent(note.id)+'/view',{method:'POST',body:'{}'});await refreshNotes(mine);}
          catch(err){notify(err.message);}
        }
      }
    });
  }
  window.SmetraVault={render:renderFiles,renderNews,cleanup};
})();