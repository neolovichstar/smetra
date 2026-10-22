'use strict';

window.SmetraAssistantContext=function(value){
  if(!value||!['clients','quotes','projects','files','documents'].includes(value.entity)||typeof value.id!=='string')return;
  sessionStorage.setItem('smetra.assistant.context',JSON.stringify({entity:value.entity,id:value.id,label:String(value.label||'').slice(0,120),workspace_id:value.workspace_id||''}));
  sessionStorage.removeItem('smetra.assistant.conversation');
};

function assistantEditValue(field,value,currency='RUB'){
  if(value===null||value===undefined||value==='')return '—';
  if(['optional','included'].includes(field))return value?'Да':'Нет';
  if(['amount','amount_kopecks','unit_price','price'].includes(field)){
    try{return new Intl.NumberFormat('ru-RU',{style:'currency',currency}).format(Number(value)/100)}catch{return String(value)}
  }
  if(Array.isArray(value))return value.map(item=>item.name||'Позиция').join(', ');
  if(typeof value==='object')return 'Данные записи';
  return String(value);
}
function assistantEditPreview(preview){
  const labels={text:'Текст',attachment:'Привязка',document:'Документ',source:'Источник',template:'Шаблон',amount_kopecks:'Сумма',due_date:'Срок',status:'Статус',unit_price:'Цена',quantity:'Количество',coefficient:'Коэффициент',markup:'Наценка, %',discount:'Скидка, %',tax:'Налог, %',unit:'Единица',category:'Категория',optional:'Опциональная позиция',included:'Включена в расчёт',name:'Название',title:'Название',notes:'Заметки',description:'Описание',amount:'Сумма',items:'Позиции',phone:'Телефон',email:'Почта'};
  const structure=preview.kind==='quote_structure';
  const itemText=(item,position)=>item?`Строка ${position} · ${item.quantity} ${item.unit} × ${assistantEditValue('unit_price',item.unit_price,preview.currency)} · ${assistantEditValue('amount',item.subtotal,preview.currency)}${item.optional?(item.included?' · опция включена':' · опция исключена'):''}`:'—';
  const rows=(preview.rows||[]).map(row=>structure?`<div class="assistant-diff-row"><span>${escapeHtml(({insert:'Добавить',remove:'Удалить',move:'Переместить'})[row.change]||'Изменить')} · ${escapeHtml((row.after||row.before)?.name||'Позиция')}</span><div><del>${escapeHtml(itemText(row.before,row.before_row))}</del><span aria-label="станет">${escapeHtml(itemText(row.after,row.after_row))}</span></div></div>`:`<div class="assistant-diff-row"><span>${row.row?escapeHtml(row.row)+'. '+escapeHtml(row.name)+' · ':''}${escapeHtml(labels[row.field]||row.field)}</span><div><del>${escapeHtml(assistantEditValue(row.field,row.before,preview.currency))}</del><span aria-label="станет">${escapeHtml(assistantEditValue(row.field,row.after,preview.currency))}</span></div></div>`);
  const totals=['quote_items','quote_structure'].includes(preview.kind)?`${structure?`<p class="muted">Позиций: ${escapeHtml(preview.before_count)} → ${escapeHtml(preview.after_count)}</p>`:''}<div class="assistant-diff-total"><span>Итого по смете</span><div><del>${escapeHtml(assistantEditValue('amount',preview.before_total,preview.currency))}</del><strong>${escapeHtml(assistantEditValue('amount',preview.after_total,preview.currency))}</strong></div></div>`:'';
  return `<div class="assistant-edit-diff">${rows.slice(0,5).join('')}${rows.length>5?`<details><summary>Ещё ${rows.length-5} изменений</summary>${rows.slice(5).join('')}</details>`:''}${totals}</div>`;
}
let assistantRenderRevision=0;
window.SmetraAssistant=async function(parentActive=()=>true){
  const mine=++assistantRenderRevision,owner=user,workspaceId=sessionStorage.getItem('workspace_id');
  const active=()=>parentActive()&&mine===assistantRenderRevision&&owner===user&&tab==='assistant'&&workspaceId===sessionStorage.getItem('workspace_id');
  const [data,threadIndex]=await Promise.all([api('/assistant'),api('/assistant/conversations')]);
  if(!active())return;
  const maxUpload=Math.min(5000000,data.file_upload_max_bytes||3000000),maxUploadLabel=Math.floor(maxUpload/1000000)+' МБ';
  let activeConversation=sessionStorage.getItem('smetra.assistant.conversation')||'';
  if(activeConversation&&!threadIndex.items.some(item=>item.id===activeConversation))activeConversation='';
  const thread=activeConversation?await api('/assistant/conversations/'+encodeURIComponent(activeConversation)):data;
  if(!active())return;
  document.querySelector('.contextual-upgrade')?.remove();
  const collapsedTools=(()=>{try{return localStorage.getItem('smetra.assistant.tools-collapsed')==='true'}catch{return false}})();
  const historyExpanded=Boolean(document.querySelector('.assistant-studio.is-history-expanded'));
  view(`<section class="assistant-page assistant-refined assistant-studio${collapsedTools?' assistant-tools-collapsed':''}${historyExpanded?' is-history-expanded':''}">
    <div class="assistant-main-column">
      <header class="assistant-header" aria-label="Лимит ассистента"><span id="assistant-quota" class="assistant-quota"></span></header>
      <dialog id="assistant-knowledge-panel" class="assistant-knowledge-dialog hidden" aria-label="Знания ассистента"></dialog>
      <div class="assistant-content"><div id="assistant-messages" class="assistant-thread" role="log" aria-live="off"></div><div id="assistant-actions"></div></div>
      <div class="assistant-composer"><div id="assistant-context" class="assistant-context hidden"><span>Контекст</span><strong id="assistant-context-label"></strong><button id="assistant-context-remove" type="button" aria-label="Убрать контекст">×</button></div>
        <form id="assistant-form"><label class="visually-hidden" for="assistant-input">Сообщение ассистенту</label><textarea id="assistant-input" placeholder="Опишите задачу для Сметры…" rows="1" maxlength="3000" required></textarea><button class="assistant-action-button is-voice" id="assistant-send" type="button" aria-label="Ввести сообщение голосом" title="Голосовой ввод" data-ui-icon="microphone" data-ui-icon-only="true"><span class="visually-hidden">Голосовой ввод</span></button><button class="btn" id="assistant-stop" type="button" aria-label="Остановить ответ" title="Остановить ответ" hidden>Стоп</button></form>
        <div class="assistant-composer-foot"><span id="assistant-status" role="status"></span><span id="assistant-delivery-hint">Enter — отправить · Shift+Enter — новая строка</span></div><a id="assistant-upgrade" class="assistant-upgrade hidden" href="/app#billing">Лимит исчерпан. Посмотреть тариф Про ↗</a>
      </div>
    </div>
    <aside class="assistant-toolrail" aria-label="История и инструменты ассистента">
      <button class="assistant-toolrail-toggle" id="assistant-toolrail-toggle" type="button" aria-expanded="${!collapsedTools}" aria-controls="assistant-workbar" aria-label="${collapsedTools?'Развернуть панель диалога':'Свернуть панель диалога'}" title="${collapsedTools?'Развернуть панель':'Свернуть панель'}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="${collapsedTools?'M15 8l-4 4 4 4':'M9 8l4 4-4 4'}"/><path d="M7 4v16"/></svg></button>
      <div class="assistant-toolrail-body">
        <div class="assistant-workbar" id="assistant-workbar">
          <button class="btn small assistant-tool-new" id="assistant-new-thread" type="button" aria-label="Новый диалог" title="Новый диалог"><span class="icon assistant-tool-icon assistant-icon-plus" aria-hidden="true"></span><span class="assistant-tool-label">Новый диалог</span></button>
          <button class="btn small assistant-history-toggle" id="assistant-history-toggle" type="button" aria-label="Показать историю диалогов" title="История диалогов" aria-expanded="false" aria-controls="assistant-history-panel"><span class="icon assistant-tool-icon assistant-icon-chat" aria-hidden="true"></span><span class="assistant-tool-label">История</span></button>
          <button class="btn small assistant-tool-knowledge" id="assistant-knowledge" type="button" aria-label="База знаний" title="База знаний" aria-expanded="false" aria-controls="assistant-knowledge-panel"><span class="icon assistant-tool-icon assistant-icon-knowledge" aria-hidden="true"></span><span class="assistant-tool-label">Знания</span></button>
        </div>
        <section class="assistant-history-panel" id="assistant-history-panel" aria-label="История диалогов">
          <div class="assistant-history-heading" id="assistant-history-heading"><span>ИСТОРИЯ</span><span class="assistant-history-count">${threadIndex.items.length}</span></div>
          <div class="assistant-history-list" id="assistant-history-list" role="list" aria-label="История диалогов">
            <div class="assistant-conversation-row assistant-conversation-general${!activeConversation?' is-active':''}" data-thread-row data-thread-id="" data-pinned="0" role="listitem">
              <button class="assistant-conversation-open" type="button" data-conversation="" aria-pressed="${!activeConversation}" title="Общий диалог">
                <span class="icon assistant-conversation-leading assistant-icon-chat" aria-hidden="true"></span><span class="assistant-conversation-title">Общий диалог</span>
              </button>
              <div class="assistant-conversation-actions">
                <button class="assistant-conversation-icon-button assistant-conversation-delete" type="button" data-thread-delete aria-label="Очистить общий диалог" title="Очистить общий диалог"><span class="assistant-trash-mark" aria-hidden="true"></span></button>
              </div>
            </div>
            ${threadIndex.items.map(item=>`<div class="assistant-conversation-row${item.id===activeConversation?' is-active':''}" data-thread-row data-thread-id="${escapeHtml(item.id)}" data-pinned="${item.pinned?'1':'0'}" role="listitem">
              <button class="assistant-conversation-open" type="button" data-conversation="${escapeHtml(item.id)}" aria-pressed="${item.id===activeConversation}" title="${escapeHtml(item.title)}">
                <span class="icon assistant-conversation-leading assistant-icon-chat" aria-hidden="true"></span><span class="assistant-conversation-title">${escapeHtml(item.title)}</span>${item.pinned?'<span class="assistant-conversation-pinned" aria-label="Закреплён" title="Закреплён"></span>':''}
              </button>
              <div class="assistant-conversation-actions">
                <button class="assistant-conversation-icon-button assistant-conversation-more" type="button" data-thread-menu aria-expanded="false" aria-label="Действия для диалога «${escapeHtml(item.title)}»" title="Действия"><span class="assistant-more-mark" aria-hidden="true"></span></button>
                <button class="assistant-conversation-icon-button assistant-conversation-delete" type="button" data-thread-delete aria-label="Удалить диалог «${escapeHtml(item.title)}»" title="Удалить диалог"><span class="assistant-trash-mark" aria-hidden="true"></span></button>
              </div>
              <div class="assistant-conversation-menu" data-thread-menu-panel hidden>
                <div class="assistant-conversation-menu-actions">
                  <button type="button" data-thread-rename><span class="icon assistant-menu-icon assistant-icon-pencil" aria-hidden="true"></span>Переименовать</button>
                  <button type="button" data-thread-pin><span class="icon assistant-menu-icon assistant-icon-pin" aria-hidden="true"></span>${item.pinned?'Открепить':'Закрепить'}</button>
                </div>
                <form class="assistant-history-rename-form" data-thread-rename-form hidden>
                  <label class="visually-hidden" for="assistant-history-name-${escapeHtml(item.id)}">Название диалога</label>
                  <input id="assistant-history-name-${escapeHtml(item.id)}" data-thread-rename-input maxlength="120" required aria-label="Название диалога" value="${escapeHtml(item.title)}">
                  <div class="assistant-history-rename-actions"><button type="submit" class="is-primary">Сохранить</button><button type="button" data-thread-rename-cancel>Отмена</button></div>
                </form>
              </div>
            </div>`).join('')}
            ${threadIndex.items.length===0?'<div class="assistant-history-empty">Созданные диалоги будут здесь</div>':''}
          </div>
        </section>
        <label class="visually-hidden" for="assistant-thread-select">Диалог</label><select id="assistant-thread-select" hidden><option value="">Общий диалог</option>${threadIndex.items.map(item=>`<option value="${escapeHtml(item.id)}" ${item.id===activeConversation?'selected':''}>${escapeHtml(item.title)}</option>`).join('')}</select>
      </div>
    </aside>
  </section>`);
  const assistantStudioRoot=document.querySelector('.assistant-studio');
  const assistantMainColumn=assistantStudioRoot?.querySelector('.assistant-main-column');
  const assistantToolRail=assistantStudioRoot?.querySelector('.assistant-toolrail');
  const assistantContentHost=assistantStudioRoot?.querySelector('.assistant-content');
  const assistantAppShell=document.querySelector('.app-shell');
  const assistantMainHost=document.querySelector('#content.main');
  const positionAssistantToolRail=()=>{
    if(!assistantStudioRoot?.isConnected||!assistantToolRail?.isConnected)return;
    const compact=window.matchMedia?window.matchMedia('(max-width:800px)').matches:window.innerWidth<=800;
    if(compact){
      if(assistantMainColumn&&assistantContentHost&&assistantToolRail.parentElement!==assistantMainColumn)assistantMainColumn.insertBefore(assistantToolRail,assistantContentHost);
    }else if(assistantAppShell&&assistantMainHost&&assistantToolRail.parentElement!==assistantAppShell){
      assistantAppShell.insertBefore(assistantToolRail,assistantMainHost);
    }
  };
  const cleanupAssistantToolRail=()=>{
    window.removeEventListener('resize',positionAssistantToolRail);
    document.removeEventListener('smetra:before-view',cleanupAssistantToolRail);
  };
  document.addEventListener('smetra:before-view',cleanupAssistantToolRail,{once:true});
  window.addEventListener('resize',positionAssistantToolRail,{passive:true});
  positionAssistantToolRail();
  const messages=document.querySelector('#assistant-messages');
  const actions=document.querySelector('#assistant-actions');
  const input=document.querySelector('#assistant-input');
  const composer=document.querySelector('.assistant-composer');
  const content=document.querySelector('.assistant-content');
  const syncAssistantConversationState=()=>{
    if(!assistantStudioRoot||!messages?.isConnected)return;
    assistantStudioRoot.classList.toggle('has-conversation',Boolean(messages.querySelector('.assistant-message.user')));
  };
  const conversationObserver=new MutationObserver(syncAssistantConversationState);
  conversationObserver.observe(messages,{childList:true,subtree:true});
  syncAssistantConversationState();
  const attachmentBar=document.createElement('div');attachmentBar.className='assistant-attachment-bar';
  attachmentBar.innerHTML='<button type="button" id="assistant-attach" aria-label="Прикрепить документ" title="Прикрепить файл">Прикрепить файл</button><input type="file" id="assistant-attach-input" accept=".pdf,.txt,.md,.docx,.xlsx,.csv" hidden><span></span>';
  attachmentBar.querySelector('span').textContent='PDF, DOCX, XLSX, CSV, TXT, MD · до '+maxUploadLabel;
  composer.insertBefore(attachmentBar,document.querySelector('#assistant-form'));
  const jobBar=document.createElement('div');jobBar.className='assistant-jobbar';
  const backgroundButton=document.createElement('button');backgroundButton.type='button';backgroundButton.id='assistant-background';backgroundButton.textContent='В фоне';backgroundButton.hidden=true;backgroundButton.disabled=true;
  backgroundButton.setAttribute('aria-pressed','false');backgroundButton.setAttribute('aria-describedby','assistant-delivery-hint');
  backgroundButton.title='Сохранить задачу на сервере и открыть ответ позже';
  let backgroundEnabled=false,backgroundMode=false;
  const jobList=document.createElement('div');jobList.className='assistant-jobs';jobList.setAttribute('aria-live','polite');
  jobBar.append(backgroundButton);composer.insertBefore(jobBar,document.querySelector('#assistant-form'));
  const composeTools=document.createElement('div');composeTools.className='assistant-compose-tools';
  composeTools.append(attachmentBar,jobBar,document.querySelector('#assistant-send'),document.querySelector('#assistant-stop'));
  const assistantForm=document.querySelector('#assistant-form');
  assistantForm.append(composeTools);
  // Background jobs belong to the composer surface directly above the message field.
  assistantForm.insertBefore(jobList,input);
  const send=document.querySelector('#assistant-send');
  const status=document.querySelector('#assistant-status');
  const SpeechRecognitionAPI=window.SpeechRecognition||window.webkitSpeechRecognition;
  let voiceRecognition=null,voiceListening=false,voiceStarting=false,voiceText='',voiceInterim='',voiceError=false;
  const syncSendButton=()=>{
    const hasText=Boolean(input.value.trim()),icon=hasText?'arrow-up':'microphone';
    send.type=hasText?'submit':'button';
    send.dataset.uiIcon=icon;
    send.style.setProperty('--ui-icon',"url('/assets/icons/"+icon+".svg')");
    send.classList.toggle('is-voice',!hasText);
    send.classList.toggle('has-message',hasText);
    send.classList.toggle('is-recording',voiceListening||voiceStarting);
    send.setAttribute('aria-label',hasText?'Отправить сообщение':voiceListening?'Остановить голосовой ввод':'Ввести сообщение голосом');
    send.title=hasText?'Отправить сообщение':voiceListening?'Остановить голосовой ввод':'Голосовой ввод';
    send.setAttribute('aria-pressed',String(!hasText&&voiceListening));
  };
  const startVoiceInput=async()=>{
    if(voiceListening){try{voiceRecognition?.stop()}catch{};return}
    if(voiceStarting)return;
    if(!SpeechRecognitionAPI){status.textContent='Голосовой ввод не поддерживается этим браузером. Откройте Сметру в актуальном Chrome.';return}
    voiceStarting=true;voiceError=false;voiceText='';voiceInterim='';syncSendButton();
    status.textContent='Запускаем распознавание речи…';
    try{
      // Start the permission request in the click gesture, but do not await it before
      // recognition.start(): Chromium can consume transient activation across await.
      // Release the temporary stream as soon as the permission prompt resolves.
      if(navigator.mediaDevices?.getUserMedia){
        try{
          const permissionRequest=navigator.mediaDevices.getUserMedia({audio:true});
          permissionRequest.then(stream=>stream?.getTracks?.().forEach(track=>track.stop())).catch(()=>{});
        }catch{}
      }
      if(!voiceRecognition){
        voiceRecognition=new SpeechRecognitionAPI();
        voiceRecognition.lang='ru-RU';voiceRecognition.interimResults=true;voiceRecognition.continuous=true;voiceRecognition.maxAlternatives=1;
        voiceRecognition.onstart=()=>{
          voiceStarting=false;voiceListening=true;voiceText='';voiceInterim='';voiceError=false;syncSendButton();
          status.textContent='Слушаю… Нажмите микрофон, чтобы закончить.';
        };
        voiceRecognition.onresult=event=>{
          const finalParts=[],interimParts=[];
          for(let i=0;i<event.results.length;i++){
            const result=event.results[i],transcript=result[0]?.transcript?.trim();
            if(transcript&&result.isFinal)finalParts.push(transcript);
            else if(transcript&&!result.isFinal)interimParts.push(transcript);
          }
          voiceText=finalParts.join(' ').replace(/\s+/g,' ').trim();
          voiceInterim=interimParts.join(' ').replace(/\s+/g,' ').trim();
          status.textContent=voiceInterim?'Распознаю: '+voiceInterim:'Слушаю… Нажмите микрофон, чтобы закончить.';
        };
        voiceRecognition.onerror=event=>{
          voiceError=true;voiceStarting=false;voiceListening=false;syncSendButton();
          const errors={
            'not-allowed':'Нет доступа к микрофону. Разрешите его для сайта в настройках браузера.',
            'aborted':'Голосовой ввод остановлен.',
            'service-not-allowed':'Браузер заблокировал распознавание речи. Проверьте разрешения микрофона.',
            'no-speech':'Не услышал речь. Проверьте микрофон и попробуйте ещё раз.',
            'audio-capture':'Не найден микрофон. Проверьте подключение устройства.',
            'network':'Сервис распознавания речи недоступен. Проверьте подключение к интернету.'
          };
          status.textContent=errors[event.error]||'Голосовой ввод прерван. Нажмите микрофон и повторите попытку.';
        };
        voiceRecognition.onend=()=>{
          const transcript=(voiceText||voiceInterim).trim();voiceListening=false;voiceStarting=false;
          if(transcript){
            const current=input.value.trim();
            input.value=[current,transcript].filter(Boolean).join(current?' ':'');
            input.dispatchEvent(new Event('input',{bubbles:true}));
            input.focus({preventScroll:true});
          }
          if(!voiceError)status.textContent=transcript?'Текст распознан — проверьте его и отправьте.':'Голосовой ввод завершён.';
          syncSendButton();syncAssistantConversationState();
        };
      }
      try{voiceRecognition.start()}catch(startError){voiceStarting=false;voiceListening=false;syncSendButton();throw startError}
    }catch(error){
      voiceStarting=false;voiceListening=false;syncSendButton();
      const denied=error?.name==='NotAllowedError'||error?.name==='SecurityError';
      const missing=error?.name==='NotFoundError'||error?.name==='DevicesNotFoundError';
      status.textContent=denied?'Нет доступа к микрофону. Разрешите его в адресной строке браузера и повторите попытку.':
        missing?'Микрофон не найден. Подключите устройство и попробуйте ещё раз.':
        'Не удалось включить микрофон. Проверьте разрешения сайта и повторите попытку.';
    }
  };
  send.addEventListener('click',()=>{if(send.type==='button')startVoiceInput()});
  const quotaLabel=document.querySelector('#assistant-quota');
  const upgrade=document.querySelector('#assistant-upgrade');
  const selectedThread=threadIndex.items.find(item=>item.id===activeConversation);
  let threadPath=activeConversation?'/assistant/conversations/'+encodeURIComponent(activeConversation):'';
  const clearLocalDraft=()=>{try{sessionStorage.removeItem(draftSlot())}catch{}};
  document.querySelector('#assistant-thread-select').onchange=event=>{sessionStorage.removeItem('smetra.assistant.context');sessionStorage.setItem('smetra.assistant.conversation',event.target.value);window.SmetraAssistant()};
  const toolrail=document.querySelector('.assistant-studio'),toolrailToggle=document.querySelector('#assistant-toolrail-toggle');
  const historyToggle=document.querySelector('#assistant-history-toggle');
  const closeConversationMenus=(exceptRow=null)=>{
    document.querySelectorAll('.assistant-conversation-menu:not([hidden])').forEach(menu=>{
      const row=menu.closest('.assistant-conversation-row');
      if(row===exceptRow)return;
      menu.hidden=true;row?.classList.remove('is-menu-open','is-renaming');
      row?.querySelector('[data-thread-menu]')?.setAttribute('aria-expanded','false');
      const actions=menu.querySelector('.assistant-conversation-menu-actions');if(actions)actions.hidden=false;
      const form=menu.querySelector('[data-thread-rename-form]');if(form)form.hidden=true;
    });
  };
  const closeHistoryPanel=()=>{toolrail.classList.remove('is-history-expanded');historyToggle.setAttribute('aria-expanded','false')};
  historyToggle.onclick=event=>{event.stopPropagation();const open=toolrail.classList.toggle('is-history-expanded');historyToggle.setAttribute('aria-expanded',String(open));if(open)closeConversationMenus()};
  toolrailToggle.onclick=()=>{const collapsed=toolrail.classList.toggle('assistant-tools-collapsed');closeHistoryPanel();toolrailToggle.setAttribute('aria-expanded',String(!collapsed));toolrailToggle.setAttribute('aria-label',collapsed?'Развернуть панель диалога':'Свернуть панель диалога');toolrailToggle.title=collapsed?'Развернуть панель':'Свернуть панель';toolrailToggle.innerHTML=collapsed?'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m9 8 4 4-4 4M7 4v16"/></svg>':'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m15 8-4 4 4 4M7 4v16"/></svg>';try{localStorage.setItem('smetra.assistant.tools-collapsed',String(collapsed))}catch{}};
  document.querySelectorAll('[data-conversation]').forEach(button=>{button.onclick=()=>{
    const select=document.querySelector('#assistant-thread-select');select.value=button.dataset.conversation||'';select.dispatchEvent(new Event('change'));
  }});
  async function threadAction(button,action){
    if(button.disabled||!active()||working||threadBusy)return;threadBusy=true;
    setThreadBusy(true);
    try{await action();}catch(error){if(active())notify(error.message);}
    finally{threadBusy=false;if(active())setThreadBusy(working);}
  }
  document.querySelectorAll('.assistant-conversation-row').forEach(row=>{
    const id=row.dataset.threadId||'',path=id?'/assistant/conversations/'+encodeURIComponent(id):'/assistant/conversations/general';
    const more=row.querySelector('[data-thread-menu]'),menu=row.querySelector('[data-thread-menu-panel]');
    const closeRowMenu=()=>{if(!menu)return;menu.hidden=true;more?.setAttribute('aria-expanded','false');row.classList.remove('is-menu-open','is-renaming');const actions=menu.querySelector('.assistant-conversation-menu-actions');if(actions)actions.hidden=false;const form=menu.querySelector('[data-thread-rename-form]');if(form)form.hidden=true};
    more?.addEventListener('click',event=>{
      event.stopPropagation();if(working||threadBusy)return;
      const open=menu.hidden;closeConversationMenus(row);
      menu.hidden=!open;more.setAttribute('aria-expanded',String(open));row.classList.toggle('is-menu-open',open);
    });
    row.querySelector('[data-thread-rename]')?.addEventListener('click',event=>{
      event.stopPropagation();if(working||threadBusy)return;
      closeConversationMenus(row);
      menu.hidden=false;more.setAttribute('aria-expanded','true');row.classList.add('is-menu-open','is-renaming');
      menu.querySelector('.assistant-conversation-menu-actions').hidden=true;
      const form=menu.querySelector('[data-thread-rename-form]');form.hidden=false;
      const input=form.querySelector('[data-thread-rename-input]');input.value=row.querySelector('.assistant-conversation-title').textContent;input.focus();input.select();
    });
    row.querySelector('[data-thread-rename-cancel]')?.addEventListener('click',event=>{
      event.preventDefault();event.stopPropagation();closeRowMenu();more?.focus();
    });
    row.querySelector('[data-thread-rename-form]')?.addEventListener('submit',event=>{
      event.preventDefault();event.stopPropagation();const title=event.currentTarget.querySelector('[data-thread-rename-input]').value.trim();
      if(!title){notify('Введите название диалога');return}
      return threadAction(event.currentTarget.querySelector('button[type=submit]'),async()=>{
        await api(path,{method:'PATCH',body:JSON.stringify({title})});
        if(active())await window.SmetraAssistant();
      });
    });
    row.querySelector('[data-thread-pin]')?.addEventListener('click',event=>{
      event.preventDefault();event.stopPropagation();const pinned=row.dataset.pinned==='1';
      return threadAction(event.currentTarget,async()=>{
        await api(path,{method:'PATCH',body:JSON.stringify({pinned:pinned?0:1})});
        if(active())await window.SmetraAssistant();
      });
    });
    row.querySelector('[data-thread-delete]')?.addEventListener('click',event=>{
      event.preventDefault();event.stopPropagation();
      if(working||threadBusy)return;
      const general=!id;
      const message=general?'Очистить сообщения общего диалога? Остальные диалоги сохранятся.':'Удалить этот диалог и его сообщения?';
      if(!confirm(message))return;
      return threadAction(event.currentTarget,async()=>{
        await api(path,{method:'DELETE'});
        if(!active())return;
        const deletingActive=general?!activeConversation:id===activeConversation;
        if(deletingActive){clearLocalDraft();sessionStorage.removeItem('smetra.assistant.conversation');}
        await window.SmetraAssistant();
      });
    });
    row.addEventListener('keydown',event=>{
      if(event.key==='Escape'&&menu&&!menu.hidden){event.preventDefault();closeRowMenu();more?.focus();}
    });
  });
  document.querySelector('.assistant-page').addEventListener('click',event=>{
    if(!event.target.closest('.assistant-conversation-row-actions,.assistant-conversation-menu'))closeConversationMenus();
    if(!event.target.closest('.assistant-history-panel,#assistant-history-toggle')&&toolrail.classList.contains('is-history-expanded'))closeHistoryPanel();
  });
  document.querySelector('.assistant-page').addEventListener('keydown',event=>{
    if(event.key!=='Escape')return;
    if(toolrail.classList.contains('is-history-expanded')){event.preventDefault();closeHistoryPanel();historyToggle.focus();}
  });
  document.querySelector('#assistant-new-thread').onclick=event=>threadAction(event.currentTarget,async()=>{const created=await api('/assistant/conversations',{method:'POST',body:JSON.stringify({title:'Новый диалог',...(context?{context_entity:context.entity,context_id:context.id}:{})})});if(!active())return;sessionStorage.setItem('smetra.assistant.conversation',created.conversation.id);await window.SmetraAssistant()});
  document.querySelector('#assistant-knowledge').onclick=event=>threadAction(event.currentTarget,async()=>{const panel=document.querySelector('#assistant-knowledge-panel'),button=document.querySelector('#assistant-knowledge');await window.SmetraKnowledgePanel(panel);if(!active())return;closeHistoryPanel();panel.classList.remove('hidden');panel.showModal();button.setAttribute('aria-expanded','true')});
  let context=null,fileBlocking=false,filePollTimer=null,filePollSeq=0;
  try{context=JSON.parse(sessionStorage.getItem('smetra.assistant.context')||'null')}catch{}
  const currentWorkspace=window.Workspace?.currentWorkspaceId?.()||sessionStorage.getItem('workspace_id')||'';
  if(context&&(!['clients','quotes','projects','files','documents'].includes(context.entity)||typeof context.id!=='string'||currentWorkspace&&context.workspace_id!==currentWorkspace))context=null;
  if(activeConversation){
    context=selectedThread.context_entity?{entity:selectedThread.context_entity,id:selectedThread.context_id,workspace_id:currentWorkspace}:null;
    if(context){try{const record=await api('/'+context.entity+'/'+encodeURIComponent(context.id)+(context.entity==='files'?'/metadata':''));const item=record.quote||record.item||record.file;context.label=item?.title||item?.name||context.id}catch{context.label='Запись недоступна — уберите контекст'}}
  }
  if(!active())return;
  const contextBar=document.querySelector('#assistant-context');
  const fileStatus=document.createElement('div');fileStatus.className='assistant-file-status';fileStatus.hidden=true;fileStatus.setAttribute('role','status');contextBar.after(fileStatus);
  const renderContext=()=>{
    contextBar.classList.toggle('hidden',!context);
    if(context)document.querySelector('#assistant-context-label').textContent=({clients:'Клиент',quotes:'Смета',projects:'Заказ',files:'Файл',documents:'Документ'})[context.entity]+': '+(context.label||context.id);
    else sessionStorage.removeItem('smetra.assistant.context');
  };
  renderContext();
  const draftUser=user.id;
  const draftSlot=()=>`smetra.assistant.draft:${draftUser}:${currentWorkspace}:${activeConversation|| (context?context.entity+':'+context.id:'global')}`;
  const saveDraft=()=>{try{if(input.value)sessionStorage.setItem(draftSlot(),input.value.slice(0,3000));else sessionStorage.removeItem(draftSlot())}catch{}};
  const clearSentDraft=prompt=>{try{if((sessionStorage.getItem(draftSlot())||'').trim()===prompt)sessionStorage.removeItem(draftSlot())}catch{}};
  try{input.value=sessionStorage.getItem(draftSlot())||''}catch{}
  try{const prefill=JSON.parse(sessionStorage.getItem('smetra.assistant.prefill')||'null');if(prefill&&context&&context.entity==='files'&&prefill.file_id===context.id&&prefill.workspace_id===currentWorkspace&&typeof prefill.text==='string'){input.value=prefill.text.slice(0,3000);input.focus();input.style.height=Math.min(input.scrollHeight,180)+'px'}sessionStorage.removeItem('smetra.assistant.prefill')}catch{sessionStorage.removeItem('smetra.assistant.prefill')}
  saveDraft();
  document.querySelector('#assistant-context-remove').onclick=async()=>{try{if(activeConversation)await api(threadPath,{method:'PATCH',body:JSON.stringify({context_entity:'',context_id:''})});context=null;renderContext();saveDraft();refreshFile();input.focus()}catch(error){notify(error.message)}};
  const fileInput=document.querySelector('#assistant-attach-input');
  const attachButton=document.querySelector('#assistant-attach');
  attachButton.onclick=()=>fileInput.click();
  const uploadAttachment=async file=>{
    if(!file||attachButton.disabled)return;
    const extension=file.name.toLowerCase().split('.').pop();
    if(!['pdf','txt','md','docx','xlsx','csv'].includes(extension)||file.size<1||file.size>maxUpload){status.textContent='Выберите PDF, DOCX, XLSX, CSV, TXT или MD до '+maxUploadLabel;return}
    attachButton.disabled=true;status.textContent='Прикрепляю файл…';
    const retrySlot='smetra.assistant.attachment:'+user.id+':'+currentWorkspace+':'+activeConversation;
    try{
      const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
      const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(value=>value.toString(16).padStart(2,'0')).join('');
      const fingerprint=JSON.stringify([file.name,file.size,digest]);let pending=null;
      try{pending=JSON.parse(sessionStorage.getItem(retrySlot)||'null')}catch{}
      if(!pending||pending.fingerprint!==fingerprint||typeof pending.key!=='string'){pending={fingerprint,key:crypto.randomUUID()};sessionStorage.setItem(retrySlot,JSON.stringify(pending))}
      for(let index=0;index<bytes.length;index+=32768)binary+=String.fromCharCode(...bytes.subarray(index,index+32768));
      const result=await api('/files',{method:'POST',headers:{'Idempotency-Key':pending.key},body:JSON.stringify({assistant_upload:true,name:file.name,content:btoa(binary)})});
      const attached={entity:'files',id:result.file.id,label:result.file.name,workspace_id:currentWorkspace||sessionStorage.getItem('workspace_id')||''};
      if(activeConversation)await api(threadPath,{method:'PATCH',body:JSON.stringify({context_entity:attached.entity,context_id:attached.id})});
      context=attached;saveDraft();sessionStorage.removeItem(retrySlot);
      sessionStorage.setItem('smetra.assistant.context',JSON.stringify(context));renderContext();refreshFile();refreshJobs();
      status.textContent='Файл прикреплён. Задайте вопрос по его содержимому.';input.focus();
    }catch(error){if(error.status===409)sessionStorage.removeItem(retrySlot);status.textContent=error.message}
    finally{attachButton.disabled=false;fileInput.value=''}
  };
  fileInput.onchange=()=>uploadAttachment(fileInput.files[0]);
  composer.addEventListener('dragover',event=>{if([...event.dataTransfer.types].includes('Files'))event.preventDefault()});
  composer.addEventListener('drop',event=>{if(event.dataTransfer.files.length){event.preventDefault();uploadAttachment(event.dataTransfer.files[0])}});
  let quota=data.quota,working=false,threadBusy=false,requestController=null;
  const setThreadBusy=blocked=>{
    document.querySelectorAll('.assistant-workbar button,.assistant-history-list button,.assistant-history-rename-form input,.assistant-history-rename-form button').forEach(button=>button.disabled=blocked);
    document.querySelectorAll('.assistant-workbar summary').forEach(summary=>summary.setAttribute('aria-disabled',String(blocked)));
    if(blocked)closeConversationMenus();
  };
  const stop=document.querySelector('#assistant-stop');
  stop.onclick=()=>requestController?.abort();
  const renderQuota=value=>{
    quota=value;
    quotaLabel.textContent=`Осталось ${value.remaining} из ${value.limit} · ${value.plan==='free'?'Старт':'Про'}`;
    quotaLabel.title=`Лимит обновится ${new Date(value.resets_at*1000).toLocaleDateString('ru-RU')}`;
    upgrade.classList.toggle('hidden',value.remaining>0||value.plan==='pro');
    if(value.remaining<1&&value.plan!=='pro'){upgrade.onclick=()=>sessionStorage.setItem('smetra.paywall.source','ai_limit');Promise.resolve(window.SmetraLoadFeature?.('growth')).then(()=>{if(active())window.SmetraGrowth?.paywall('ai_limit')}).catch(()=>{});}
    const quotaBlocked=value.remaining<1&&value.plan!=='pro';
    const blocked=working||fileBlocking||!data.available||quotaBlocked;
    document.querySelectorAll('.assistant-regenerate').forEach(button=>{button.disabled=blocked||!button.dataset.prompt});
    // The empty composer button is a microphone, not an AI request: dictation remains available at zero quota.
    const canRecordVoice=send.type==='button'&&!input.value.trim();
    send.disabled=working||fileBlocking||!data.available||(!canRecordVoice&&(quotaBlocked||!input.value.trim()||(backgroundMode&&!backgroundEnabled)));
    backgroundButton.disabled=working||fileBlocking||!data.available||!backgroundEnabled;
    send.title=quotaBlocked?'Месячный лимит исчерпан. Черновик останется доступен.':backgroundMode?'Отправить задачу в фон':'Отправить сообщение';
    backgroundButton.title=!backgroundEnabled?'Фоновая обработка не подключена на сервере':quotaBlocked?'Фоновая задача использует тот же месячный лимит сообщений.':'Сохранить задачу на сервере и открыть ответ позже';
    input.disabled=working||!data.available;
    input.title=quotaBlocked?'Черновик можно редактировать; отправка откроется после обновления лимита или перехода на Про.':'';
    setThreadBusy(working||threadBusy);
  };
  const copyText=async(text,button)=>{if(button.disabled)return;const original=button.getAttribute('aria-label')||'Скопировать ответ';button.disabled=true;try{if(typeof window.SmetraCopyText==='function')await window.SmetraCopyText(text);else await navigator.clipboard.writeText(text);button.classList.add('is-copied');button.dataset.copied='true';button.title='Скопировано';button.setAttribute('aria-label','Скопировано');setTimeout(()=>{if(!button.isConnected)return;button.classList.remove('is-copied');delete button.dataset.copied;button.title=original;button.setAttribute('aria-label',original)},1600)}catch{notify('Не удалось скопировать. Выделите текст и скопируйте вручную.')}finally{button.disabled=false;button.focus({preventScroll:true})}};
  const nearBottom=()=>content.scrollHeight-content.scrollTop-content.clientHeight<100;
  const scrollBottom=()=>{content.scrollTop=content.scrollHeight};
  const messageIcons={
    copy:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>',
    refresh:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M20 7v5h-5"/><path d="M19 12a7 7 0 0 0-12-4L4 11"/><path d="M4 17v-5h5"/><path d="M5 12a7 7 0 0 0 12 4l3-3"/></svg>',
    up:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M7 10v11H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z"/><path d="M7 10l5-7a3 3 0 0 1 2 3l-1 4h6a3 3 0 0 1 3 4l-2 6a2 2 0 0 1-2 1H7"/></svg>',
    down:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M7 14V3H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2z"/><path d="M7 14l5 7a3 3 0 0 0 2-3l-1-4h6a3 3 0 0 0 3-4l-2-6a2 2 0 0 0-2-1H7"/></svg>',
    branch:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="6" cy="5" r="2.5"/><circle cx="18" cy="19" r="2.5"/><circle cx="18" cy="5" r="2.5"/><path d="M6 7.5v5a6.5 6.5 0 0 0 6.5 6.5H15.5M15.5 5H12a6 6 0 0 0-6 6"/></svg>'
  };
  const messageButton=(name,label)=>{const button=document.createElement('button');button.type='button';button.className='assistant-message-action assistant-action-'+name;button.title=label;button.setAttribute('aria-label',label);button.innerHTML=messageIcons[name];return button};
  const feedbackKey=(messageId,text)=>{const hash=Array.from(String(text)).reduce((value,char)=>Math.imul(value,31)+char.charCodeAt(0)>>>0,2166136261).toString(36);return 'smetra.assistant.feedback:'+user.id+':'+(activeConversation||'general')+':'+(messageId||hash)};
  const addMessage=(role,text,messageId)=>{
    const item=document.createElement('article');item.className='assistant-message '+role;
    const label=document.createElement('small');label.textContent=role==='user'?'ВЫ':'СМЕТРА';
    const body=document.createElement('div');body.className='assistant-markdown';
    body.dataset.source=text;
    body.innerHTML=role==='user'?`<p>${escapeHtml(text).replace(/\n/g,'<br>')}</p>`:assistantMarkdown(text);
    item.append(label,body);
    if(role==='assistant'){
      const toolbar=document.createElement('div');toolbar.className='assistant-message-actions';toolbar.setAttribute('role','group');toolbar.setAttribute('aria-label','Действия с ответом');
      const copy=messageButton('copy','Скопировать ответ');copy.classList.add('assistant-copy');copy.onclick=()=>copyText(body.dataset.source,copy);toolbar.append(copy);
      const previous=messages.lastElementChild;
      const previousPrompt=previous?.classList.contains('user')?previous.querySelector('.assistant-markdown')?.dataset.source||'':'';
      const regenerate=messageButton('refresh','Перегенерировать ответ');regenerate.classList.add('assistant-regenerate');regenerate.dataset.prompt=previousPrompt;regenerate.disabled=!previousPrompt||!data.available||(quota.remaining<1&&quota.plan!=='pro');
      regenerate.onclick=()=>{const prompt=regenerate.dataset.prompt;if(!prompt||working||threadBusy||!data.available||quota.remaining<1&&quota.plan!=='pro')return;input.value=prompt;saveDraft();resize();renderQuota(quota);document.querySelector('#assistant-form').requestSubmit()};
      toolbar.append(regenerate);
      const key=feedbackKey(messageId,previousPrompt||text);
      let vote='';try{vote=localStorage.getItem(key)||''}catch{}
      const applyVote=value=>{vote=vote===value?'':value;up.setAttribute('aria-pressed',String(vote==='up'));down.setAttribute('aria-pressed',String(vote==='down'));try{if(vote)localStorage.setItem(key,vote);else localStorage.removeItem(key)}catch{}};
      const up=messageButton('up','Полезный ответ');up.setAttribute('aria-pressed',String(vote==='up'));up.onclick=()=>applyVote('up');toolbar.append(up);
      const down=messageButton('down','Неполезный ответ');down.setAttribute('aria-pressed',String(vote==='down'));down.onclick=()=>applyVote('down');toolbar.append(down);
      if(activeConversation&&messageId){
        const fork=messageButton('branch','Продолжить диалог с этого сообщения отдельно');fork.classList.add('assistant-fork');fork.onclick=async()=>{if(fork.disabled||!active()||working||threadBusy)return;fork.disabled=true;try{
          const result=await api('/assistant/conversations/'+encodeURIComponent(activeConversation)+'/fork',{method:'POST',body:JSON.stringify({message_id:messageId})});
          if(!active())return;
          sessionStorage.setItem('smetra.assistant.conversation',result.conversation.id);await window.SmetraAssistant();
        }catch(error){if(active()){fork.disabled=false;notify(error.message)}}};
        toolbar.append(fork);
      }
      item.append(toolbar);
    }
    messages.append(item);return {item,body};
  };
  const addAction=action=>{
    const item=document.createElement('section');item.className='assistant-proposal';
    const markdownEdit=action.tool==='replace_markdown_text';
    const detail=action.preview?assistantEditPreview(action.preview):markdownEdit?`<div class="assistant-text-diff"><span>Было</span><pre>${escapeHtml(action.arguments.old_text)}</pre><span>Станет</span><pre>${escapeHtml(action.arguments.new_text)}</pre></div><p class="muted">После применения предыдущий текст останется в истории документа.</p>`:proposalFields(action.arguments);
    item.innerHTML=`<span class="overline">Предложение · ещё не сохранено</span><h3>${escapeHtml(action.summary)}</h3><div class="proposal-fields">${detail}</div><div class="row"><button class="btn primary" data-confirm>${markdownEdit?'Применить правку':'Применить'}</button><button class="btn ghost" data-dismiss>Не сейчас</button></div>`;
    actions.append(item);
    if(action.tool==='create_document'){
      const preview=document.createElement('button');preview.type='button';preview.className='btn ghost';preview.textContent='Предпросмотр PDF';item.querySelector('.row').prepend(preview);
      preview.onclick=async()=>{preview.disabled=true;try{await Workspace.download('/assistant/actions/'+encodeURIComponent(action.id)+'/preview.pdf','smetra-preview.pdf')}catch(error){notify(error.message)}finally{preview.disabled=false}};
    }
    item.querySelector('[data-confirm]').onclick=async()=>{const buttons=item.querySelectorAll('button');buttons.forEach(button=>button.disabled=true);try{const result=await api('/assistant/confirm',{method:'POST',body:JSON.stringify({id:action.id})});renderSavedAction(item,action,result.undoable,result.result?.document?.id);notify('Изменения сохранены')}catch(error){notify(error.message);buttons.forEach(button=>button.disabled=false)}};
    item.querySelector('[data-dismiss]').onclick=async()=>{try{await api('/assistant/dismiss',{method:'POST',body:JSON.stringify({id:action.id})});item.remove()}catch(error){notify(error.message)}};
  };
  const renderSavedAction=(item,action,undoable,documentId)=>{
    item.replaceChildren();const title=document.createElement('p');title.textContent='Сохранено · '+action.summary;item.append(title);
    if(documentId){const pdf=document.createElement('button');pdf.type='button';pdf.className='btn ghost';pdf.textContent='Скачать PDF';pdf.onclick=()=>Workspace.download('/documents/'+encodeURIComponent(documentId)+'/pdf','smetra-document.pdf').catch(error=>notify(error.message));item.append(pdf)}
    if(!undoable)return;
    const button=document.createElement('button');button.type='button';button.className='btn ghost';button.textContent='Отменить изменение';item.append(button);
    button.onclick=async()=>{button.disabled=true;try{await api('/assistant/undo',{method:'POST',body:JSON.stringify({id:action.id})});item.replaceChildren(title);title.textContent='Изменение отменено · '+action.summary;notify('Изменение отменено')}catch(error){button.disabled=false;notify(error.message)}};
  };
  renderQuota(quota);
  let jobRequest=null,jobPollTimer=null,jobLoadSeq=0;
  const dismissedJobsKey='smetra.assistant.dismissedJobs:'+user.id+':'+currentWorkspace;
  const dismissedJobIds=new Set();
  try{for(const id of JSON.parse(sessionStorage.getItem(dismissedJobsKey)||'[]'))dismissedJobIds.add(String(id))}catch{}
  const rememberDismissedJob=id=>{dismissedJobIds.add(String(id));try{sessionStorage.setItem(dismissedJobsKey,JSON.stringify([...dismissedJobIds].slice(-100)))}catch{}};
  const refreshJobs=async()=>{
    clearTimeout(jobPollTimer);const sequence=++jobLoadSeq;
    if(!jobList.isConnected)return;
    try{
      if(document.hidden){jobPollTimer=setTimeout(refreshJobs,15000);return}
      const result=await api('/assistant/jobs');
      if(!active()||!jobList.isConnected||sequence!==jobLoadSeq)return;
      backgroundEnabled=!!result.enabled;
      backgroundButton.hidden=!result.enabled;
      if(!backgroundEnabled&&backgroundMode){backgroundMode=false;renderDelivery()}
      renderQuota(quota);
      jobList.replaceChildren();
      const labels={queued:'В очереди',running:'В работе',retry:'Повторю позже',completed:'Готово',failed:'Не удалось завершить',cancelled:'Отменено'};
      const now=Date.now()/1000;
      result.jobs.filter(job=>{
        if(!job?.id||dismissedJobIds.has(String(job.id))||job.status==='cancelled')return false;
        if(['queued','running','retry'].includes(job.status))return true;
        return ['completed','failed'].includes(job.status)&&now-Number(job.updated_at||job.created_at||0)<86400;
      }).slice(0,5).forEach(job=>{
        const row=document.createElement('div');row.className='assistant-job';row.dataset.status=job.status;
        const description=document.createElement('div'),title=document.createElement('strong'),detail=document.createElement('span');
        title.textContent=job.prompt;
        const stalled=job.status==='queued'&&Date.now()/1000-Number(job.updated_at||job.created_at||0)>90;
        detail.textContent=job.error||(stalled?'Долго ожидает запуска. Задача сохранена, но обработчик ещё не забрал её.':job.progress||labels[job.status]);
        if(stalled)row.dataset.stalled='true';
        detail.setAttribute('role','status');description.append(title,detail);row.append(description);
        const active=['queued','running','retry'].includes(job.status);
        if(active||job.status==='completed'){
          const button=document.createElement('button');button.type='button';button.textContent=active?'Отменить':['file_index','file_ocr'].includes(job.kind)?'Открыть документ':'Открыть ответ';button.disabled=!!job.cancel_requested;
          button.onclick=async()=>{button.disabled=true;try{
            if(active){const cancelled=await api('/assistant/jobs/'+encodeURIComponent(job.id),{method:'DELETE'});rememberDismissedJob(job.id);row.classList.add('assistant-job-removing');row.setAttribute('aria-hidden','true');row.remove();renderQuota(cancelled.quota);refreshJobs();refreshFile()}
            else if(['file_index','file_ocr'].includes(job.kind)){window.SmetraAssistantContext({entity:'files',id:job.file_id,workspace_id:currentWorkspace,label:job.prompt.replace(/^(Подготовка|Распознавание) · /,'')});window.SmetraAssistant()}
            else{sessionStorage.removeItem('smetra.assistant.context');sessionStorage.setItem('smetra.assistant.conversation',job.conversation_id||'');window.SmetraAssistant()}
          }catch(error){button.disabled=false;notify(error.message)}};row.append(button);
        }
        jobList.append(row);
      });
      if(result.jobs.some(job=>['queued','running','retry'].includes(job.status)))jobPollTimer=setTimeout(refreshJobs,5000);
    }catch{if(active()&&jobList.isConnected&&sequence===jobLoadSeq)jobPollTimer=setTimeout(refreshJobs,15000)}
  };
  const renderDelivery=()=>{
    backgroundButton.setAttribute('aria-pressed',String(backgroundMode));
    composer.classList.toggle('background-mode',backgroundMode);
    send.setAttribute('aria-label',backgroundMode?'Отправить задачу в фон':'Отправить сообщение');
    const quotaBlocked=quota.remaining<1&&quota.plan!=='pro';
    send.title=quotaBlocked?'Месячный лимит исчерпан. Черновик останется доступен.':backgroundMode?'Отправить задачу в фон':'Отправить сообщение';
    document.querySelector('#assistant-delivery-hint').textContent=quotaBlocked?'Лимит исчерпан — фон также расходует сообщения.':backgroundMode?'Ответ сохранится в диалоге. Можно закрыть страницу.':'Enter — отправить · Shift+Enter — новая строка';
  };
  backgroundButton.onclick=()=>{
    if(!backgroundEnabled||working||fileBlocking)return;
    backgroundMode=!backgroundMode;renderDelivery();renderQuota(quota);input.focus();
  };
  const submitBackground=async()=>{
    const text=input.value.trim();if(!text||working||fileBlocking||quota.remaining<1||!backgroundEnabled||!data.available)return;
    const body=JSON.stringify({text,context:context?{entity:context.entity,id:context.id}:null,...(activeConversation?{conversation_id:activeConversation}:{})});
    if(!jobRequest||jobRequest.body!==body)jobRequest={body,key:crypto.randomUUID()};
    working=true;renderQuota(quota);status.textContent='Сохраняю фоновую задачу…';
    try{
      const result=await api('/assistant/jobs',{method:'POST',headers:{'Idempotency-Key':jobRequest.key},body});
      clearSentDraft(text);jobRequest=null;
      if(!active())return;
      renderQuota(result.quota);input.value='';resize();syncSendButton();status.textContent='В очереди · можно закрыть страницу';refreshJobs();
    }catch(error){if(active()){status.textContent=error.message;notify(error.message)}}
    finally{working=false;if(active()){renderQuota(quota);if(!input.disabled)input.focus()}}
  };
  renderDelivery();
  refreshJobs();
  const refreshFile=async()=>{
    clearTimeout(filePollTimer);const sequence=++filePollSeq;
    if(!fileStatus.isConnected)return;
    fileStatus.replaceChildren();fileStatus.hidden=context?.entity!=='files';fileBlocking=false;
    if(fileStatus.hidden){renderQuota(quota);return}
    const id=context.id;fileBlocking=true;renderQuota(quota);
    try{
      const result=await api('/files/'+encodeURIComponent(id)+'/metadata');
      if(!fileStatus.isConnected||sequence!==filePollSeq||context?.id!==id)return;
      const info=result.processing,active=['queued','running','retry'].includes(info.state);
      fileBlocking=active||['failed','deferred','cancelled','needs_ocr'].includes(info.state)||result.file.size>2000000&&info.state!=='ready';
      const labels={queued:'Документ в очереди',running:'Подготавливаю текст…',retry:'Повторю подготовку позже',ready:'Текст готов',needs_ocr:'В PDF есть страницы без текста. Для них нужен OCR.',failed:info.error||'Не удалось подготовить документ',cancelled:'Подготовка отменена',deferred:'Подготовьте документ перед вопросом',legacy:'Документ ещё не подготовлен'};
      const label=document.createElement('span');label.textContent=(labels[info.state]||labels.legacy)+(info.state==='ready'?(info.pages?' · '+info.pages+' стр.':'')+(info.truncated?' · подготовлена часть текста':'')+(info.method==='ocr'?' · OCR: проверьте суммы по оригиналу':''):'');fileStatus.append(label);
      if(['ready','needs_ocr'].includes(info.state)&&info.missing_text_pages?.length){const gaps=document.createElement('span');gaps.textContent='Без текста: стр. '+info.missing_text_pages.slice(0,6).join(', ')+(info.missing_text_pages.length>6?'…':'');fileStatus.append(gaps)}
      if(info.ocr_supported){const budget=document.createElement('span');budget.textContent=`OCR: ${info.ocr_quota.used} из ${info.ocr_quota.limit} в месяц · первые ${info.ocr_page_limit} страницы`;fileStatus.append(budget)}
      if(info.supported&&(active&&info.can_cancel||['failed','cancelled','deferred','legacy','needs_ocr'].includes(info.state))){
        const ocr=info.ocr_supported;const button=document.createElement('button');button.type='button';button.className='btn small';button.textContent=active?'Отменить подготовку':ocr?'Распознать скан':info.state==='failed'?'Повторить':'Подготовить документ';button.disabled=!!info.cancel_requested||!active&&ocr&&info.ocr_quota.used>=info.ocr_quota.limit;
        button.onclick=async()=>{button.disabled=true;try{await api('/files/'+encodeURIComponent(id)+'/'+(ocr?'ocr':'processing'),{method:active?'DELETE':'POST',...(active?{}:{headers:{'Idempotency-Key':crypto.randomUUID()}})});refreshFile();refreshJobs()}catch(error){button.disabled=false;notify(error.message)}};fileStatus.append(button);
      }
      renderQuota(quota);
      if(active)filePollTimer=setTimeout(refreshFile,document.hidden?15000:4000);
    }catch(error){if(fileStatus.isConnected&&sequence===filePollSeq){fileStatus.textContent=error.message;filePollTimer=setTimeout(refreshFile,15000)}}
  };
  refreshFile();
  if(!thread.messages.length){
    messages.innerHTML='<div class="assistant-welcome"><span class="assistant-welcome-line" aria-hidden="true"></span><h2>С чего начнём?</h2><p>Помогу со сметами, проектами и оплатами.</p><div class="assistant-suggestions"><button type="button" data-prompt="Помоги составить новую смету. Спроси необходимые детали." data-ui-icon="file-text">Составить смету</button><button type="button" data-prompt="Какие сметы ожидают согласования?" data-ui-icon="check-square">Проверить согласования</button><button type="button" data-prompt="Покажи поступления и остатки по заказам." data-ui-icon="wallet">Разобраться в оплатах</button></div></div>';
    messages.querySelectorAll('[data-prompt]').forEach(button=>button.onclick=()=>{input.value=button.dataset.prompt;saveDraft();input.focus();resize();syncSendButton();renderQuota(quota)});
  }
  thread.messages.forEach(message=>addMessage(message.role,message.content,message.id));
  data.actions.forEach(addAction);
  (data.recent_actions||[]).forEach(action=>{const item=document.createElement('section');item.className='assistant-proposal assistant-saved';actions.append(item);renderSavedAction(item,action,true,action.document_id)});
  if(!data.available)status.textContent='Ассистент пока не подключён.';
  else if(quota.remaining<1)status.textContent='Лимит исчерпан: обычные и фоновые сообщения используют общий месячный лимит. Черновик можно редактировать.';
  const resize=()=>{input.style.height='auto';input.style.height=Math.min(input.scrollHeight,180)+'px'};
  input.addEventListener('input',()=>{resize();saveDraft();renderQuota(quota);syncSendButton()});resize();syncSendButton();
  input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&event.keyCode!==229){event.preventDefault();document.querySelector('#assistant-form').requestSubmit()}});
  document.querySelector('#assistant-form').onsubmit=async event=>{
    event.preventDefault();const prompt=input.value.trim();if(!prompt||working||threadBusy||fileBlocking||quota.remaining<1||!data.available)return;
    if(backgroundMode){await submitBackground();return}
    working=true;renderQuota(quota);stop.hidden=false;requestController=new AbortController();status.textContent='Подключаюсь к модели…';
    messages.querySelector('.assistant-welcome')?.remove();
    const userMessage=addMessage('user',prompt);
    const assistantMessage=addMessage('assistant','');
    assistantMessage.item.classList.add('streaming');
    scrollBottom();
    let generated='',paintPending=false,completed=false;
    const paint=()=>{const follow=nearBottom();paintPending=false;assistantMessage.body.dataset.source=generated;assistantMessage.body.innerHTML=assistantMarkdown(generated);if(follow)scrollBottom()};
    const schedule=()=>{if(!paintPending){paintPending=true;requestAnimationFrame(paint)}};
    try{
      const response=await fetch('/api/assistant/stream',{method:'POST',credentials:'same-origin',signal:requestController.signal,headers:{'Content-Type':'application/json',...(sessionStorage.getItem('workspace_id')?{'X-Workspace-Id':sessionStorage.getItem('workspace_id')}:{})},body:JSON.stringify({text:prompt,...(context?{context:{entity:context.entity,id:context.id}}:{}),...(activeConversation?{conversation_id:activeConversation}:{})})});
      if(!response.ok){let error;try{error=(await response.json()).error}catch{}throw Error(error||`Ошибка ${response.status}`)}
      if(!response.body)throw Error('Браузер не поддерживает потоковый ответ');
      const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
      const eventBlock=block=>{
        const lines=block.split(/\r?\n/);const kind=lines.find(line=>line.startsWith('event:'))?.slice(6).trim();
        const raw=lines.filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');
        if(!kind||!raw)return;
        const payload=JSON.parse(raw);
        if(kind==='ready'){renderQuota(payload.quota);status.textContent='Формулирую ответ…'}
        if(kind==='delta'){generated+=payload.text;schedule();status.textContent='Пишу ответ…'}
        if(kind==='status')status.textContent=payload.text;
        if(kind==='done'){generated=payload.answer;paint();payload.actions.forEach(addAction);renderQuota(payload.quota);completed=true;status.textContent=''}
        if(kind==='error'){renderQuota(payload.quota);throw Error(payload.error)}
      };
      while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let match;while((match=buffer.match(/\r?\n\r?\n/))){const block=buffer.slice(0,match.index);buffer=buffer.slice(match.index+match[0].length);eventBlock(block)}}
      if(!completed)throw Error('Ответ оборвался. Попробуйте ещё раз.');
      assistantMessage.item.classList.remove('streaming');input.value='';clearSentDraft(prompt);resize();syncSendButton();
    }catch(error){
      if(error.name==='AbortError'){assistantMessage.item.classList.remove('streaming');if(!generated){assistantMessage.item.remove();userMessage.item.remove()}status.textContent='Ответ остановлен.'}
      else{userMessage.item.remove();assistantMessage.item.remove();status.textContent=error.message}
      try{renderQuota((await api('/assistant')).quota)}catch{}
    }finally{working=false;requestController=null;stop.hidden=true;renderQuota(quota);input.disabled=!data.available;if(!input.disabled)input.focus()}
  };
};
