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
function assistantQuoteDraftPreview(host, args){
  const rows=Array.isArray(args.items)?args.items:[];
  if(!rows.length)return;
  const wrapper=document.createElement('div');wrapper.className='assistant-quote-draft';
  const heading=document.createElement('div');heading.className='assistant-quote-draft-heading';
  const title=document.createElement('strong');title.textContent='Работы и материалы';
  const count=document.createElement('span');count.textContent=rows.length+' позиций';
  heading.append(title,count);wrapper.append(heading);
  if(args.client){const client=document.createElement('p');client.className='assistant-quote-draft-meta';client.textContent='Клиент: '+String(args.client);wrapper.append(client);}
  const buildRows=(subset,offset)=>{
    const list=document.createElement('ol');list.className='assistant-quote-draft-list';
    subset.forEach((record,index)=>{
      const row=document.createElement('li');row.className='assistant-quote-draft-item';
      const main=document.createElement('div');main.className='assistant-quote-draft-main';
      const label=document.createElement('span');label.className='assistant-quote-draft-name';label.textContent=(offset+index+1)+'. '+String(record.name||'Работа');
      const quantity=document.createElement('span');quantity.className='assistant-quote-draft-quantity';
      quantity.textContent=String(record.quantity??1)+' '+String(record.unit||'шт.');
      main.append(label,quantity);
      const price=document.createElement('span');price.className='assistant-quote-draft-price';
      const kopecks=Number(record.unit_price);
      const specified=Number.isFinite(kopecks)&&kopecks>0;
      price.textContent=specified?assistantEditValue('unit_price',kopecks,args.currency||'RUB')+' / ед.':'Цена не указана';
      if(!specified)price.classList.add('is-unpriced');
      row.append(main,price);list.append(row);
    });
    return list;
  };
  wrapper.append(buildRows(rows.slice(0,5),0));
  if(rows.length>5){
    const more=document.createElement('details');more.className='assistant-quote-draft-more';
    const summary=document.createElement('summary');summary.textContent='Показать ещё '+(rows.length-5)+' позиций';
    more.append(summary,buildRows(rows.slice(5),5));wrapper.append(more);
  }
  const note=document.createElement('p');note.className='assistant-quote-draft-note';
  note.textContent='Черновик. Количество и цены необходимо проверить перед отправкой клиенту.';
  wrapper.append(note);host.append(wrapper);
}

let assistantRenderRevision=0;
let assistantVoiceCleanup=null;
const assistantIcon=(name,size=18)=>window.SmetraIcons?window.SmetraIcons.svg(name,size):'';
window.SmetraAssistant=async function(parentActive=()=>true){
  // Starting another conversation must release the previous microphone first.
  assistantVoiceCleanup?.();
  const mine=++assistantRenderRevision,owner=user,workspaceId=sessionStorage.getItem('workspace_id');
  const active=()=>parentActive()&&mine===assistantRenderRevision&&owner===user&&tab==='assistant'&&workspaceId===sessionStorage.getItem('workspace_id');
  const [data,threadIndex]=await Promise.all([api('/assistant'),api('/assistant/conversations')]);
  if(!active())return;
  const maxUpload=Math.min(5000000,data.file_upload_max_bytes||3000000),maxUploadLabel=Math.floor(maxUpload/1000000)+' МБ';
  const requestWorkspace=data.workspace_id||workspaceId||window.Workspace?.currentWorkspaceId?.()||'';
  const scopeHeaders=requestWorkspace?{'X-Workspace-Id':requestWorkspace}:{};
  let activeConversation=sessionStorage.getItem('smetra.assistant.conversation')||'';
  if(activeConversation&&!threadIndex.items.some(item=>item.id===activeConversation))activeConversation='';
  const thread=activeConversation?await api('/assistant/conversations/'+encodeURIComponent(activeConversation)):data;
  if(!active())return;
  document.querySelector('.contextual-upgrade')?.remove();
  const collapsedTools=(()=>{try{return localStorage.getItem('smetra.assistant.tools-collapsed')==='true'}catch{return false}})();
  const historyExpanded=Boolean(document.querySelector('.assistant-studio.is-history-expanded'));
  view(`<section class="assistant-page assistant-refined assistant-studio${collapsedTools?' assistant-tools-collapsed':''}${historyExpanded?' is-history-expanded':''}">
    <div class="assistant-main-column">
      <header class="assistant-header" hidden><span id="assistant-quota" class="assistant-quota"></span></header>
      <dialog id="assistant-knowledge-panel" class="assistant-knowledge-dialog hidden" aria-label="Знания ассистента"></dialog>
      <div class="assistant-content"><div id="assistant-messages" class="assistant-thread" role="log" aria-live="off"></div><div id="assistant-actions"></div></div>
      <div class="assistant-composer"><div id="assistant-decision-slot" class="assistant-decision-slot" aria-live="polite"></div><div id="assistant-context" class="assistant-context hidden"><span>Контекст</span><strong id="assistant-context-label"></strong><button id="assistant-context-remove" class="icon-button" type="button" aria-label="Убрать контекст">${assistantIcon('x',16)}</button></div>
        <form id="assistant-form"><label class="visually-hidden" for="assistant-input">Сообщение ассистенту</label><textarea id="assistant-input" placeholder="Опишите задачу для Сметры…" rows="1" maxlength="3000" required></textarea><button class="assistant-action-button assistant-voice" id="assistant-voice" type="button" aria-label="Ввести сообщение голосом" title="Голосовой ввод" aria-pressed="false">${assistantIcon('microphone',18)}</button><button class="assistant-action-button assistant-send" id="assistant-send" type="submit" aria-label="Отправить сообщение" title="Отправить сообщение" disabled>${assistantIcon('arrow-up',18)}</button><button class="assistant-action-button assistant-stop" id="assistant-stop" type="button" aria-label="Остановить ответ" title="Остановить ответ" hidden>${assistantIcon('stop',16)}</button></form>
        <div class="assistant-composer-foot"><span id="assistant-status" role="status"></span><span id="assistant-delivery-hint">Enter — отправить · Shift+Enter — новая строка</span></div><a id="assistant-upgrade" class="assistant-upgrade hidden" href="/app#billing">Токены закончились — купить токены или перейти на Про</a>
      </div>
    </div>
    <aside class="assistant-toolrail" aria-label="История и инструменты ассистента">
      <button class="assistant-toolrail-toggle" id="assistant-toolrail-toggle" type="button" aria-expanded="${!collapsedTools}" aria-controls="assistant-workbar" aria-label="${collapsedTools?'Развернуть панель диалога':'Свернуть панель диалога'}" title="${collapsedTools?'Развернуть панель':'Свернуть панель'}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="${collapsedTools?'M12 9l3 3-3 3':'M15 9l-3 3 3 3'}"/><path d="M7 4v16"/></svg></button>
      <div class="assistant-toolrail-body">
        <div class="assistant-workbar" id="assistant-workbar">
          <button class="btn small assistant-tool-new" id="assistant-new-thread" type="button" aria-label="Новый диалог" title="Новый диалог">${assistantIcon('plus')}<span class="assistant-tool-label">Новый диалог</span></button>
          <button class="btn small assistant-history-toggle" id="assistant-history-toggle" type="button" aria-label="Показать историю диалогов" title="История диалогов" aria-expanded="false" aria-controls="assistant-history-panel">${assistantIcon('chat')}<span class="assistant-tool-label">История</span></button>
          <button class="btn small assistant-tool-quotes" id="assistant-quotes" type="button" aria-label="Сметы" title="Сметы" aria-expanded="false" aria-controls="smetra-quote-preview">${assistantIcon('file-text')}<span class="assistant-tool-label">Сметы</span></button>
          <button class="btn small assistant-tool-knowledge" id="assistant-knowledge" type="button" aria-label="База знаний" title="База знаний" aria-expanded="false" aria-controls="assistant-knowledge-panel">${assistantIcon('book')}<span class="assistant-tool-label">Знания</span></button>
        </div>
        <section class="assistant-history-panel" id="assistant-history-panel" aria-label="История диалогов">
          <div class="assistant-history-heading" id="assistant-history-heading"><span>Диалоги</span><span class="assistant-history-count">${threadIndex.items.length}</span></div>
          <div class="assistant-history-list" id="assistant-history-list" role="list" aria-label="История диалогов">
            <div class="assistant-conversation-row assistant-conversation-general${!activeConversation?' is-active':''}" data-thread-row data-thread-id="" data-pinned="0" role="listitem"${data.messages?.length?'':' hidden'}>
              <button class="assistant-conversation-open" type="button" data-conversation="" aria-pressed="${!activeConversation}" title="Общий диалог">
                ${assistantIcon('chat',16)}<span class="assistant-conversation-title">Общий диалог</span>
              </button>
              <div class="assistant-conversation-actions">
                <button class="assistant-conversation-icon-button assistant-conversation-delete" type="button" data-thread-delete aria-label="Удалить общий диалог" title="Удалить диалог">${assistantIcon('trash',16)}</button>
              </div>
            </div>
            ${threadIndex.items.map(item=>`<div class="assistant-conversation-row${item.id===activeConversation?' is-active':''}" data-thread-row data-thread-id="${escapeHtml(item.id)}" data-pinned="${item.pinned?'1':'0'}" role="listitem">
              <button class="assistant-conversation-open" type="button" data-conversation="${escapeHtml(item.id)}" aria-pressed="${item.id===activeConversation}" title="${escapeHtml(item.title)}">
                ${assistantIcon('chat',16)}<span class="assistant-conversation-title">${escapeHtml(item.title)}</span>${item.pinned?`<span class="assistant-conversation-pinned" aria-label="Закреплён" title="Закреплён">${assistantIcon('pin',14)}</span>`:''}
              </button>
              <div class="assistant-conversation-actions">
                <button class="assistant-conversation-icon-button assistant-conversation-more" type="button" data-thread-menu aria-expanded="false" aria-label="Действия для диалога «${escapeHtml(item.title)}»" title="Действия">${assistantIcon('more',16)}</button>
                <button class="assistant-conversation-icon-button assistant-conversation-delete" type="button" data-thread-delete aria-label="Удалить диалог «${escapeHtml(item.title)}»" title="Удалить диалог">${assistantIcon('trash',16)}</button>
              </div>
              <div class="assistant-conversation-menu" data-thread-menu-panel hidden>
                <div class="assistant-conversation-menu-actions">
                  <button type="button" data-thread-rename>${assistantIcon('pencil',16)}Переименовать</button>
                  <button type="button" data-thread-pin>${assistantIcon('pin',16)}${item.pinned?'Открепить':'Закрепить'}</button>
                </div>
                <form class="assistant-history-rename-form" data-thread-rename-form hidden>
                  <label class="visually-hidden" for="assistant-history-name-${escapeHtml(item.id)}">Название диалога</label>
                  <input id="assistant-history-name-${escapeHtml(item.id)}" data-thread-rename-input maxlength="120" required aria-label="Название диалога" value="${escapeHtml(item.title)}">
                  <div class="assistant-history-rename-actions"><button type="submit" class="is-primary">Сохранить</button><button type="button" data-thread-rename-cancel>Отмена</button></div>
                </form>
              </div>
            </div>`).join('')}
            
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
  // Keep the rail in the same grid as the composer. Reparenting it to
  // #shell produced competing grid tracks, detached sidebars and overflow.
  const positionAssistantToolRail=()=>{
    if(!assistantStudioRoot?.isConnected||!assistantToolRail?.isConnected)return;
    if(assistantToolRail.parentElement!==assistantStudioRoot)
      assistantStudioRoot.appendChild(assistantToolRail);
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
  // Existing estimate engine and the chat share one revision-safe quote source.
  const openQuoteEditor=async id=>{
    try{
      const {quote}=await api('/quotes/'+encodeURIComponent(id));
      tab='quotes';location.hash='quotes';
      await window.render();
      if(tab==='quotes')await window.Workspace.editor(quote);
    }catch(error){notify(error.message)}
  };
  const quotePreview=window.SmetraQuoteVisuals?.mountAssistant({
    host:assistantStudioRoot,
    getUserId:()=>user?.id,
    fetchQuote:id=>api('/quotes/'+encodeURIComponent(id)),
    listQuotes:async()=>(await api('/quotes'))?.quotes||[],
    onToggle:open=>{const button=document.querySelector('#assistant-quotes');if(button){button.setAttribute('aria-expanded',String(open));button.classList.toggle('is-active',open)}},
    onOpenEditor:openQuoteEditor,
  });
  const syncAssistantConversationState=()=>{
    if(!assistantStudioRoot||!messages?.isConnected)return;
    const next=Boolean(messages.querySelector('.assistant-message.user'));
    if(next&&!activeConversation)assistantStudioRoot.querySelector('.assistant-conversation-general')?.removeAttribute('hidden');
    if(next===assistantStudioRoot.classList.contains('has-conversation'))return;
    const dock=assistantStudioRoot.querySelector('.assistant-composer');
    const before=dock?.getBoundingClientRect().top;
    assistantStudioRoot.classList.toggle('has-conversation',next);
    if(!dock||before===undefined||window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches!==false||typeof dock.animate!=='function')return;
    const delta=before-dock.getBoundingClientRect().top;
    if(Math.abs(delta)>2)dock.animate([{transform:`translateY(${delta}px)`},{transform:'none'}],{duration:420,easing:'cubic-bezier(.2,.7,.2,1)'});
  };
  const conversationObserver=new MutationObserver(syncAssistantConversationState);
  conversationObserver.observe(messages,{childList:true,subtree:true});
  syncAssistantConversationState();
  const attachmentBar=document.createElement('div');attachmentBar.className='assistant-attachment-bar';
  attachmentBar.innerHTML='<button type="button" id="assistant-attach" class="assistant-action-button" aria-label="Прикрепить файл или фото" title="Прикрепить файл или фото">'+assistantIcon('paperclip',18)+'</button><input type="file" id="assistant-attach-input" accept="image/png,image/jpeg,.png,.jpg,.jpeg,.pdf,.txt,.md,.docx,.xlsx,.csv" multiple hidden><span></span>';
  attachmentBar.querySelector('span').textContent='Фото PNG/JPG до 2 МБ · PDF, DOCX, XLSX, CSV, TXT, MD до '+maxUploadLabel;
  composer.insertBefore(attachmentBar,document.querySelector('#assistant-form'));
  let backgroundEnabled=null;
  const jobList=document.createElement('div');jobList.className='assistant-jobs';jobList.setAttribute('aria-live','polite');
  const composeTools=document.createElement('div');composeTools.className='assistant-compose-tools';
  composeTools.append(attachmentBar,document.querySelector('#assistant-voice'),document.querySelector('#assistant-send'),document.querySelector('#assistant-stop'));
  const assistantForm=document.querySelector('#assistant-form');
  assistantForm.append(composeTools);
  // Background jobs belong to the composer surface directly above the message field.
  assistantForm.insertBefore(jobList,input);
  const send=document.querySelector('#assistant-send');
  const voiceButton=document.querySelector('#assistant-voice');
  const status=document.querySelector('#assistant-status');
  const SpeechRecognitionAPI=window.SpeechRecognition||window.webkitSpeechRecognition;
  let voiceRecognition=null,voiceListening=false,voiceStarting=false,voiceText='',voiceInterim='',voiceError=false;
  let voicePreview='',voicePreviewAt=0;
  const stopVoiceInput=()=>{
    const recognition=voiceRecognition;
    voiceRecognition=null;
    voiceListening=false;voiceStarting=false;
    if(!recognition)return;
    // Do not let a late browser callback write into a submitted or replaced composer.
    recognition.onstart=null;recognition.onresult=null;
    recognition.onerror=null;recognition.onend=null;
    try{recognition.abort()}catch{}
  };
  const cleanupVoice=()=>{
    document.removeEventListener('smetra:before-view',cleanupVoice);
    if(assistantVoiceCleanup===cleanupVoice)assistantVoiceCleanup=null;
    stopVoiceInput();
  };
  assistantVoiceCleanup=cleanupVoice;
  document.addEventListener('smetra:before-view',cleanupVoice,{once:true});
  const renderVoiceToInput=()=>{
    // Reconcile interim/final segments in one composer range. Each new
    // SpeechRecognition result replaces that range, rather than appending
    // the same words again when the microphone stops.
    const spoken=[voiceText,voiceInterim].filter(Boolean).join(' ').replace(/\s+/g,' ').trim();
    if(!spoken)return;
    const current=input.value;
    if(voicePreview&&current.slice(voicePreviewAt,voicePreviewAt+voicePreview.length)!==voicePreview){
      // Preserve a draft edited during dictation; the previous preview may
      // have shifted or been removed by the user.
      const shifted=current.lastIndexOf(voicePreview);
      if(shifted>=0)voicePreviewAt=shifted;
      else{voicePreviewAt=current.length;voicePreview=''}
    }
    const prefix=current.slice(0,voicePreviewAt);
    const suffix=current.slice(voicePreviewAt+voicePreview.length);
    const separator=prefix&&!/\s$/.test(prefix)?' ':'';
    const limit=input.maxLength>0?input.maxLength:Infinity;
    const nextPreview=(separator+spoken).slice(0,Math.max(0,limit-prefix.length-suffix.length));
    const nextValue=prefix+nextPreview+suffix;
    voicePreview=nextPreview;
    if(nextValue!==current){
      input.value=nextValue;
      // Update composer height, draft persistence and send state immediately.
      input.dispatchEvent(new Event('input',{bubbles:true}));
    }
  };
  const syncSendButton=()=>{
    const canSend=Boolean(input.value.trim()||pendingPhotos.length);
    const quotaBlocked=quota.remaining<1&&quota.plan!=='pro';
    send.disabled=!canSend||working||threadBusy||attachingCount>0||fileBlocking||!data.available||quotaBlocked||backgroundEnabled===false;
    voiceButton.disabled=working||threadBusy||fileBlocking||!data.available;
    send.classList.toggle('has-message',canSend);
    voiceButton.classList.toggle('is-recording',voiceListening||voiceStarting);
    voiceButton.setAttribute('aria-label',voiceListening?'Остановить голосовой ввод':'Ввести сообщение голосом');
    voiceButton.title=voiceListening?'Остановить голосовой ввод':'Голосовой ввод';
    voiceButton.setAttribute('aria-pressed',String(voiceListening));
  };
  const startVoiceInput=async()=>{
    if(voiceListening){try{voiceRecognition?.stop()}catch{};return}
    if(voiceStarting)return;
    // In the Android app the system recognizer is used; WebView has no SpeechRecognition.
    if(!SpeechRecognitionAPI&&window.SmetraShell?.available){
      await window.SmetraShell.ready;
      // A delayed Android bridge handshake must not open the system recorder
      // after the assistant view or account has changed.
      if(!active()||!input.isConnected)return;
      if(!window.SmetraShell.has('speech')){status.textContent='Распознавание речи недоступно на этом телефоне. Включите голосовой ввод Google или Яндекс-клавиатуры.';return}
      voiceStarting=true;syncSendButton();status.textContent='Говорите…';
      try{const result=await window.SmetraShell.call('speech.recognize',{},{timeout:0});if(!active()||!input.isConnected)return;const heard=String(result.text||'').trim();if(heard){input.value=(input.value.trim()?input.value.trim()+' ':'')+heard;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus()}status.textContent=heard?'Текст добавлен — проверьте и отправьте.':''}
      catch(error){if(active()&&input.isConnected)status.textContent=error.code==='cancelled'?'':error.message}
      finally{if(active()&&input.isConnected){voiceStarting=false;syncSendButton()}}
      return;
    }
    if(!SpeechRecognitionAPI){status.textContent='Голосовой ввод не поддерживается этим браузером. Откройте Сметру в актуальном Chrome.';return}
    voiceStarting=true;voiceError=false;voiceText='';voiceInterim='';voicePreview='';voicePreviewAt=input.value.length;syncSendButton();
    status.textContent='Запускаем распознавание речи…';
    try{
      // SpeechRecognition requests microphone permission itself. Do not start a second
      // getUserMedia prompt in parallel: two simultaneous microphone requests can stall
      // recognition in Chromium/WebView. Start directly from this explicit button gesture.
      if(!voiceRecognition){
        voiceRecognition=new SpeechRecognitionAPI();
        voiceRecognition.lang='ru-RU';voiceRecognition.interimResults=true;voiceRecognition.continuous=true;voiceRecognition.maxAlternatives=1;
        voiceRecognition.onstart=()=>{
          voiceStarting=false;voiceListening=true;voiceText='';voiceInterim='';voicePreview='';voicePreviewAt=input.value.length;voiceError=false;syncSendButton();
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
          renderVoiceToInput();
          status.textContent='Слушаю… Нажмите микрофон, чтобы закончить.';
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
          const transcript=[voiceText,voiceInterim].filter(Boolean).join(' ').trim();voiceListening=false;voiceStarting=false;
          // Speech recognition already put the live text in the textarea.
          // Do not append again here (would duplicate the message).
          if(transcript&&document.activeElement!==input)input.focus({preventScroll:true});
          voicePreview='';voicePreviewAt=input.value.length;
          if(!voiceError)status.textContent=transcript?'Текст в поле сообщения — проверьте и отправьте.':'Голосовой ввод завершён.';
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
  voiceButton.addEventListener('click',startVoiceInput);
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
  toolrailToggle.onclick=()=>{const collapsed=toolrail.classList.toggle('assistant-tools-collapsed');closeHistoryPanel();toolrailToggle.setAttribute('aria-expanded',String(!collapsed));toolrailToggle.setAttribute('aria-label',collapsed?'Развернуть панель диалога':'Свернуть панель диалога');toolrailToggle.title=collapsed?'Развернуть панель':'Свернуть панель';const arrow=toolrailToggle.querySelector('svg path');if(arrow)arrow.setAttribute('d',collapsed?'M12 9l3 3-3 3':'M15 9l-3 3 3 3');try{localStorage.setItem('smetra.assistant.tools-collapsed',String(collapsed))}catch{}};
  document.querySelectorAll('[data-conversation]').forEach(button=>{button.onclick=()=>{
    const select=document.querySelector('#assistant-thread-select');select.value=button.dataset.conversation||'';select.dispatchEvent(new Event('change'));
  }});
  async function threadAction(button,action){
    if(button.disabled||!active()||threadBusy)return;threadBusy=true;
    setThreadBusy(true);
    try{await action();}catch(error){if(active())notify(error.message);}
    finally{threadBusy=false;if(active())setThreadBusy(false);}
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
      const button=event.currentTarget;
      const message=general?'Сообщения общего диалога будут удалены. Остальные диалоги сохранятся.':'Диалог и все его сообщения будут удалены.';
      return (async()=>{
        if(!(await window.SmetraDialog.confirm({title:'Удалить диалог?',message,confirmLabel:'Удалить',danger:true})))return;
        // A refresh started by the previous action may still hold the rail; wait for it briefly.
        for(let attempt=0;attempt<50&&active()&&(working||threadBusy||button.disabled);attempt++)await new Promise(resolve=>setTimeout(resolve,100));
        if(!active())return;
        await threadAction(button,async()=>{
          await api(path,{method:'DELETE'});
          if(!active())return;
          const deletingActive=general?!activeConversation:id===activeConversation;
          if(deletingActive){clearLocalDraft();sessionStorage.removeItem('smetra.assistant.conversation');}
          await window.SmetraAssistant();
        });
      })();
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
  document.querySelector('#assistant-quotes').onclick=()=>{if(!quotePreview){notify('Предпросмотр смет недоступен');return}closeHistoryPanel();if(!quotePreview.visible&&!quotePreview.currentId&&context?.entity==='quotes'&&context.id)quotePreview.load(context.id).catch(()=>{});else quotePreview.toggle()};
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
    if(context?.entity==='quotes'&&context.id)quotePreview?.load(context.id).catch(()=>{});
    if(context)document.querySelector('#assistant-context-label').textContent=({clients:'Клиент',quotes:'Смета',projects:'Заказ',files:'Файл',documents:'Документ'})[context.entity]+': '+(context.label||context.id);
    else sessionStorage.removeItem('smetra.assistant.context');
  };
  renderContext();
  const draftUser=user.id;
  const draftSlot=()=>`smetra.assistant.draft:${draftUser}:${currentWorkspace}:${activeConversation|| (context?context.entity+':'+context.id:'global')}`;
  const saveDraft=()=>{try{if(input.value)sessionStorage.setItem(draftSlot(),input.value.slice(0,3000));else sessionStorage.removeItem(draftSlot())}catch{}};
  const clearSentDraft=(prompt,slot=draftSlot())=>{try{if((sessionStorage.getItem(slot)||'').trim()===prompt)sessionStorage.removeItem(slot)}catch{}};
  try{input.value=sessionStorage.getItem(draftSlot())||''}catch{}
  // Text shared from another Android app arrives as a ready draft.
  try{const shared=sessionStorage.getItem('smetra.shared.text');if(shared){sessionStorage.removeItem('smetra.shared.text');input.value=(input.value?input.value+'\n\n':'')+shared.slice(0,3000)}}catch{}
  try{const prefill=JSON.parse(sessionStorage.getItem('smetra.assistant.prefill')||'null');if(prefill&&context&&context.entity==='files'&&prefill.file_id===context.id&&prefill.workspace_id===currentWorkspace&&typeof prefill.text==='string'){input.value=prefill.text.slice(0,3000);input.focus();input.style.height=Math.min(input.scrollHeight,180)+'px'}sessionStorage.removeItem('smetra.assistant.prefill')}catch{sessionStorage.removeItem('smetra.assistant.prefill')}
  saveDraft();
  document.querySelector('#assistant-context-remove').onclick=async()=>{try{if(activeConversation)await api(threadPath,{method:'PATCH',body:JSON.stringify({context_entity:'',context_id:''})});context=null;renderContext();renderPhoto();saveDraft();refreshFile();input.focus()}catch(error){notify(error.message)}};
  const fileInput=document.querySelector('#assistant-attach-input');
  const attachButton=document.querySelector('#assistant-attach');
  const attachmentInfo=attachmentBar.querySelector('span');
  const previewTray=document.createElement('div');previewTray.className='assistant-attachment-preview';previewTray.hidden=true;
  composer.insertBefore(previewTray,document.querySelector('#assistant-form'));
  let pendingPhotos=[],attachingCount=0;
  const renderPhoto=()=>{
    previewTray.replaceChildren();
    const hasFiles=pendingPhotos.length>0;
    input.required=!hasFiles;
    for(const entry of pendingPhotos){
      const card=document.createElement('div');card.className='assistant-attachment-tile';
      const image=document.createElement('img');image.src=entry.url;image.alt='Предпросмотр '+entry.file.name;
      const name=document.createElement('span');name.className='assistant-attachment-name';name.textContent=entry.file.name;
      const remove=document.createElement('button');remove.type='button';remove.className='assistant-attachment-remove';
      remove.innerHTML=assistantIcon('x',14);remove.title='Убрать изображение';remove.setAttribute('aria-label','Убрать изображение '+entry.file.name);
      remove.onclick=()=>{URL.revokeObjectURL(entry.url);pendingPhotos=pendingPhotos.filter(item=>item!==entry);renderPhoto();syncSendButton()};
      card.append(image,name,remove);previewTray.append(card);
    }
    if(context?.entity==='files'){
      const chip=document.createElement('div');chip.className='assistant-attachment-tile assistant-attachment-document';
      const icon=document.createElement('span');icon.className='assistant-document-glyph';icon.textContent='PDF';icon.setAttribute('aria-hidden','true');
      const name=document.createElement('span');name.className='assistant-attachment-name';name.textContent=context.label||'Документ';
      const remove=document.createElement('button');remove.type='button';remove.className='assistant-attachment-remove';
      remove.innerHTML=assistantIcon('x',14);remove.setAttribute('aria-label','Убрать файл из контекста');
      remove.onclick=()=>document.querySelector('#assistant-context-remove')?.click();
      chip.append(icon,name,remove);previewTray.append(chip);
    }
    previewTray.hidden=!previewTray.children.length;
    attachmentInfo.textContent=hasFiles?pendingPhotos.length+' фото выбрано · до 3, общим размером до 1,5 МБ':'Файлы и фото';
    if(typeof renderQuota==='function')renderQuota(quota);
    syncSendButton();
  };
  const clearPhoto=()=>{
    for(const entry of pendingPhotos)URL.revokeObjectURL(entry.url);
    pendingPhotos=[];renderPhoto();
  };
  const compressPhoto=async file=>{
    if(file.size<=420_000)return file;
    if(typeof createImageBitmap!=='function')throw Error('Браузер не поддерживает уменьшение фотографий');
    let bitmap;
    try{
      bitmap=await createImageBitmap(file);
      const scale=Math.min(1,1280/Math.max(bitmap.width,bitmap.height));
      const canvas=document.createElement('canvas');
      canvas.width=Math.max(1,Math.round(bitmap.width*scale));
      canvas.height=Math.max(1,Math.round(bitmap.height*scale));
      const ctx=canvas.getContext('2d',{alpha:false});
      if(!ctx)throw Error('Не удалось обработать фотографию');
      ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);
      ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);
      let blob=null;
      for(const quality of [.78,.68,.56,.45]){
        blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',quality));
        if(blob&&blob.size<=470_000)break;
      }
      if(!blob||blob.size>500_000)throw Error('Изображение слишком сложное для отправки — выберите фото меньшего размера');
      const base=file.name.replace(/\.[^.]+$/,'').slice(0,140);
      return new File([blob],base+'.jpg',{type:'image/jpeg',lastModified:file.lastModified});
    }finally{bitmap?.close?.()}
  };
  const encodePhoto=async file=>{
    const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
    for(let offset=0;offset<bytes.length;offset+=32768)binary+=String.fromCharCode(...bytes.subarray(offset,offset+32768));
    const extension=file.name.toLowerCase().split('.').pop();
    return {name:file.name,mime:file.type||(extension==='png'?'image/png':'image/jpeg'),content:btoa(binary)};
  };
  attachButton.onclick=()=>fileInput.click();
  // Sent photos become durable workspace files before invoking the assistant.
  // A stable per-File key prevents duplicate uploads when retrying a failed chat turn.
  const photoStorageKeys=new WeakMap();
  const persistChatPhoto=async file=>{
    let key=photoStorageKeys.get(file);
    if(!key){key=crypto.randomUUID();photoStorageKeys.set(file,key)}
    const bytes=new Uint8Array(await file.arrayBuffer());
    let binary='';
    for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
    if(owner!==user)throw new DOMException('Сеанс изменился','AbortError');
    const saved=await api('/files',{method:'POST',headers:{'Idempotency-Key':key,...scopeHeaders},
      body:JSON.stringify({assistant_upload:true,name:file.name,content:btoa(binary)})});
    return saved.file?.id;
  };
  const uploadAttachment=async file=>{
    if(!file||attachButton.disabled||working||threadBusy||!active())return;
    attachingCount++;renderQuota(quota);
    try{
    const extension=file.name.toLowerCase().split('.').pop();
    if(['png','jpg','jpeg'].includes(extension)){
      const expected=extension==='png'?'image/png':'image/jpeg';
      if(file.size<1||file.size>15_000_000||file.type&&file.type!==expected){
        status.textContent='Прикрепите корректную фотографию PNG/JPG размером до 15 МБ';fileInput.value='';return;
      }
      let optimized;
      try{optimized=await compressPhoto(file)}catch(error){status.textContent=error.message;fileInput.value='';return}
      if(!active())return;
      const currentBytes=pendingPhotos.reduce((sum,item)=>sum+item.file.size,0);
      if(pendingPhotos.length>=3||currentBytes+optimized.size>1_500_000){
        status.textContent='Максимум 3 изображения общим размером до 1,5 МБ после сжатия';fileInput.value='';return;
      }
      pendingPhotos.push({file:optimized,url:URL.createObjectURL(optimized)});renderPhoto();
      status.textContent='Фото готовы к отправке вместе с сообщением.';
      input.focus();return;
    }
    if(!['pdf','txt','md','docx','xlsx','csv'].includes(extension)||file.size<1||file.size>maxUpload){status.textContent='Выберите фото PNG/JPG до 2 МБ или документ до '+maxUploadLabel;return}
    attachButton.disabled=true;status.textContent='Прикрепляю файл…';
    const retrySlot='smetra.assistant.attachment:'+user.id+':'+currentWorkspace+':'+activeConversation;
    try{
      const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
      const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(value=>value.toString(16).padStart(2,'0')).join('');
      const fingerprint=JSON.stringify([file.name,file.size,digest]);let pending=null;
      try{pending=JSON.parse(sessionStorage.getItem(retrySlot)||'null')}catch{}
      if(!pending||pending.fingerprint!==fingerprint||typeof pending.key!=='string'){pending={fingerprint,key:crypto.randomUUID()};sessionStorage.setItem(retrySlot,JSON.stringify(pending))}
      for(let index=0;index<bytes.length;index+=32768)binary+=String.fromCharCode(...bytes.subarray(index,index+32768));
      const result=await api('/files',{method:'POST',headers:{'Idempotency-Key':pending.key,...scopeHeaders},body:JSON.stringify({assistant_upload:true,name:file.name,content:btoa(binary)})});
      if(!active())return;
      const attached={entity:'files',id:result.file.id,label:result.file.name,workspace_id:currentWorkspace||sessionStorage.getItem('workspace_id')||''};
      if(activeConversation)await api(threadPath,{method:'PATCH',body:JSON.stringify({context_entity:attached.entity,context_id:attached.id})});
      context=attached;saveDraft();sessionStorage.removeItem(retrySlot);
      sessionStorage.setItem('smetra.assistant.context',JSON.stringify(context));renderContext();renderPhoto();refreshFile();refreshJobs();
      status.textContent='Файл прикреплён. Задайте вопрос по его содержимому.';input.focus();
    }catch(error){if(error.status===409)sessionStorage.removeItem(retrySlot);status.textContent=error.message}
    finally{fileInput.value=''}
    }finally{attachingCount--;if(active())renderQuota(quota)}
  };
  fileInput.onchange=async()=>{const files=[...fileInput.files];for(const file of files){await uploadAttachment(file)}fileInput.value=''};

  composer.addEventListener('dragover',event=>{if([...event.dataTransfer.types].includes('Files'))event.preventDefault()});
  composer.addEventListener('drop',async event=>{if(event.dataTransfer.files.length){event.preventDefault();for(const file of [...event.dataTransfer.files])await uploadAttachment(file)}});
  let quota=data.quota,working=false,threadBusy=false,requestController=null,currentJobId=null,cancelRequested=false;
  const setThreadBusy=blocked=>{
    document.querySelectorAll('.assistant-workbar button,.assistant-history-list button,.assistant-history-rename-form input,.assistant-history-rename-form button').forEach(button=>button.disabled=blocked);
    document.querySelectorAll('.assistant-workbar summary').forEach(summary=>summary.setAttribute('aria-disabled',String(blocked)));
    if(blocked)closeConversationMenus();
  };
  const stop=document.querySelector('#assistant-stop');
  stop.onclick=async()=>{
    if(!active()||stop.disabled)return;
    cancelRequested=true;stop.disabled=true;requestController?.abort();
    if(currentJobId){
      try{await api('/assistant/jobs/'+encodeURIComponent(currentJobId),{method:'DELETE',headers:{...scopeHeaders}})}
      catch(error){if(active())notify(error.message)}
    }
  };
  const renderQuota=value=>{
    if(!value||typeof value.remaining!=='number'||!active()||!composer.isConnected)return;
    quota=value;
    // Usage is metered in model tokens; a reply needs a small reserve to start.
    const tokens=value.unit==='tokens',minimum=tokens?1500:1,empty=value.remaining<minimum;
    const short=n=>{n=Number(n||0);return n>=1e6?(n/1e6).toLocaleString('ru-RU',{maximumFractionDigits:1})+' млн':n>=1e4?Math.round(n/1e3).toLocaleString('ru-RU')+' тыс.':n.toLocaleString('ru-RU')};
    quotaLabel.textContent=tokens?`Токены: ${short(value.remaining)} · ${value.plan==='free'?'Старт':'Про'}`:`Осталось ${value.remaining} из ${value.limit} · ${value.plan==='free'?'Старт':'Про'}`;
    quotaLabel.title=tokens?`За месяц: ${short(value.monthly_used)} из ${short(value.monthly_limit)}${value.wallet?` · на балансе ${short(value.wallet)}`:''} · обновится ${new Date(value.resets_at*1000).toLocaleDateString('ru-RU')}`:`Лимит обновится ${new Date(value.resets_at*1000).toLocaleDateString('ru-RU')}`;
    quotaLabel.classList.toggle('is-low',tokens&&value.remaining<Math.max(minimum*4,(value.monthly_limit||0)*.1));
    upgrade.classList.toggle('hidden',!empty||(value.plan==='pro'&&!tokens));
    if(empty&&value.plan!=='pro'){upgrade.onclick=()=>{sessionStorage.setItem('smetra.paywall.source','ai_limit');if(tokens)try{sessionStorage.setItem('smetra.billing.view','tokens')}catch{}};if(!tokens)Promise.resolve(window.SmetraLoadFeature?.('growth')).then(()=>{if(active())window.SmetraGrowth?.paywall('ai_limit')}).catch(()=>{});}
    // In the Android app a free account can watch a rewarded video for tokens.
    let reward=document.querySelector('#assistant-reward');
    if(!reward&&window.SmetraShell?.available){
      reward=document.createElement('button');reward.type='button';reward.id='assistant-reward';reward.className='btn small assistant-reward';reward.hidden=true;
      reward.textContent='Посмотреть видео · +45 тыс. токенов';upgrade.after(reward);
      reward.onclick=async()=>{reward.disabled=true;try{const result=await window.SmetraShell.call('ads.rewarded.show',{},{timeout:0});if(result.quota)renderQuota(result.quota);notify('Начислено '+Number(result.granted||0).toLocaleString('ru-RU')+' токенов')}catch(error){if(error.code!=='not_completed'&&error.code!=='cancelled')notify(error.message);else status.textContent=error.message}finally{reward.disabled=false}};
    }
    if(reward)window.SmetraShell.ready.then(()=>{reward.hidden=!(empty&&value.plan==='free'&&window.SmetraShell.has('ads'))});
    const quotaBlocked=empty;
    const blocked=working||fileBlocking||!data.available||quotaBlocked;
    document.querySelectorAll('.assistant-regenerate').forEach(button=>{button.disabled=blocked||!button.dataset.prompt});
    syncSendButton();
    send.title=quotaBlocked?'Токены ассистента закончились. Черновик останется доступен.':'Отправить сообщение';
    attachButton.disabled=working||threadBusy||attachingCount>0||!data.available;
    input.disabled=!data.available;
    input.title=quotaBlocked?'Черновик можно редактировать; отправка откроется после обновления лимита или перехода на Про.':'';
    setThreadBusy(threadBusy);
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
    const label=document.createElement('small');label.className='visually-hidden';label.textContent=role==='user'?'Вы':'Сметра';
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
  const decisionSlot=document.getElementById('assistant-decision-slot');
  const proposalQueue=[];
  const updateDecisions=()=>{
    if(!decisionSlot?.isConnected)return;
    decisionSlot.replaceChildren();
    const next=proposalQueue.find(item=>item.isConnected&&item.dataset.proposalState==='pending');
    if(!next)return;
    const heading=document.createElement('div');heading.className='assistant-decision-heading';
    const kicker=document.createElement('span');kicker.textContent='Подтвердите действие';
    const summary=document.createElement('strong');summary.textContent=next.querySelector('h3')?.textContent||'Предложение ИИ';
    heading.append(kicker,summary);
    const controls=document.createElement('div');controls.className='assistant-decision-buttons';
    const yes=document.createElement('button');yes.type='button';yes.className='btn primary';yes.textContent='Принять';yes.onclick=()=>next.querySelector('[data-confirm]')?.click();
    const no=document.createElement('button');no.type='button';no.className='btn ghost';no.textContent='Отклонить';no.onclick=()=>next.querySelector('[data-dismiss]')?.click();
    controls.append(yes,no);decisionSlot.append(heading,controls);
  };
  const showQuestion=(question)=>{
    if(!decisionSlot?.isConnected||!question||typeof question.question!=='string')return;
    const options=Array.isArray(question.options)?question.options.slice(0,4):[];
    if(options.length<2)return;
    decisionSlot.replaceChildren();
    const group=document.createElement('div');group.className='assistant-decision-heading';
    const tag=document.createElement('span');tag.textContent='Ассистент уточняет';
    const title=document.createElement('strong');title.textContent=question.question;
    title.style.whiteSpace='normal';group.append(tag,title);
    const choices=document.createElement('div');choices.className='assistant-question-choice';
    const reply=value=>{
      if(working||!active()||!value.trim())return;
      decisionSlot.replaceChildren();input.value=value.trim();input.dispatchEvent(new Event('input',{bubbles:true}));
      document.querySelector('#assistant-form')?.requestSubmit();
    };
    for(const value of options){
      if(typeof value!=='string'||!value.trim())continue;
      const button=document.createElement('button');button.type='button';button.textContent=value;button.onclick=()=>reply(value);
      choices.append(button);
    }
    const custom=document.createElement('form');custom.className='assistant-question-custom';
    const field=document.createElement('input');field.type='text';field.maxLength=300;field.placeholder='Свой вариант ответа';field.setAttribute('aria-label','Свой вариант ответа');field.required=true;
    const sendChoice=document.createElement('button');sendChoice.type='submit';sendChoice.textContent='Отправить';
    custom.append(field,sendChoice);
    custom.addEventListener('submit',event=>{event.preventDefault();reply(field.value)});
    decisionSlot.append(group,choices,custom);
  };
  const renderedProposalIds=new Set();
  const addAction=action=>{
    if(!active()||!actions.isConnected||!action || !action.id || renderedProposalIds.has(action.id))return;
    renderedProposalIds.add(action.id);
    if(action?.tool&&/quote/.test(action.tool))quotePreview?.propose(action).catch(()=>{});
    const item=document.createElement('section');item.className='assistant-proposal';item.dataset.proposalState='pending';
    const markdownEdit=action.tool==='replace_markdown_text';
    const quoteDraft=action.tool==='create_quotes'&&Array.isArray(action.arguments?.items)&&action.arguments.items.length>0;
    const detail=quoteDraft?'':action.preview?assistantEditPreview(action.preview):markdownEdit?`<div class="assistant-text-diff"><span>Было</span><pre>${escapeHtml(action.arguments.old_text)}</pre><span>Станет</span><pre>${escapeHtml(action.arguments.new_text)}</pre></div><p class="muted">После применения предыдущий текст останется в истории документа.</p>`:proposalFields(action.arguments);
    item.innerHTML=`<span class="assistant-proposal-state">Требует подтверждения · ещё не сохранено</span><h3>${escapeHtml(action.summary)}</h3><div class="proposal-fields">${detail}</div><div class="row"><button class="btn primary" data-confirm>${markdownEdit?'Применить правку':'Применить'}</button><button class="btn ghost" data-dismiss>Не сейчас</button></div>`;
    actions.append(item);proposalQueue.push(item);updateDecisions();
    if(quoteDraft)assistantQuoteDraftPreview(item.querySelector('.proposal-fields'),action.arguments);
    if(action.tool==='create_document'){
      const preview=document.createElement('button');preview.type='button';preview.className='btn ghost';preview.textContent='Предпросмотр PDF';item.querySelector('.row').prepend(preview);
      preview.onclick=async()=>{preview.disabled=true;try{await Workspace.download('/assistant/actions/'+encodeURIComponent(action.id)+'/preview.pdf','smetra-preview.pdf')}catch(error){notify(error.message)}finally{preview.disabled=false}};
    }
    item.querySelector('[data-confirm]').onclick=async()=>{
      const confirm=item.querySelector('[data-confirm]');
      if(!active()||!item.isConnected||confirm.disabled)return;
      const buttons=item.querySelectorAll('button');buttons.forEach(button=>button.disabled=true);
      try{
        if(action.tool?.startsWith('delete_')){
          const accepted=window.SmetraDialog?.confirm
            ?await window.SmetraDialog.confirm({title:'Удалить запись?',message:action.summary+' — удаление нельзя отменить.',confirmLabel:'Удалить',danger:true})
            :window.confirm(action.summary+'? Это действие нельзя отменить.');
          if(!accepted||!active()||!item.isConnected)return;
        }
        if(action.tool==='publish_quote'&&window.SmetraEstimateSafety&&!(await window.SmetraEstimateSafety.confirmReview()))return;
        if(!active()||!item.isConnected)return;
        const result=await api('/assistant/confirm',{method:'POST',headers:{...scopeHeaders},body:JSON.stringify({id:action.id})});
        if(!active()||!item.isConnected)return;
        item.dataset.proposalState='applied';updateDecisions();quotePreview?.clearProposal?.(action.id);
        renderSavedAction(item,action,result.undoable,result.result?.document?.id,result.result?.quote?.id);
        quotePreview?.refresh().catch(()=>{});
        notify(result.result?.quote?.id?'Смета создана. Откройте черновик для проверки.':'Изменения сохранены');
      }catch(error){
        if(!active()||!item.isConnected)return;
        const state=item.querySelector('.assistant-proposal-state');
        if(state){state.textContent='Не удалось сохранить: '+error.message;state.classList.add('is-error');state.setAttribute('role','alert')}
        notify(error.message);
      }finally{if(active()&&item.isConnected&&item.dataset.proposalState==='pending')buttons.forEach(button=>button.disabled=false)}
    };
    item.querySelector('[data-dismiss]').onclick=async()=>{
      const dismiss=item.querySelector('[data-dismiss]');
      if(dismiss.disabled||!active()||!item.isConnected)return;
      dismiss.disabled=true;
      try{
        await api('/assistant/dismiss',{method:'POST',body:JSON.stringify({id:action.id})});
        if(!active()||!item.isConnected)return;
        item.dataset.proposalState='dismissed';quotePreview?.clearProposal?.(action.id);
        item.remove();updateDecisions();
      }catch(error){dismiss.disabled=false;notify(error.message)}
    };
  };
  // Like ChatGPT's "Memory updated": a quiet note under the answer with a way to review it.
  const showMemoryNote=(item,updates)=>{
    if(!item||!Array.isArray(updates)||!updates.length)return;
    const saved=updates.filter(update=>update.kind==='saved').map(update=>update.title);
    const forgotten=updates.filter(update=>update.kind==='forgotten').map(update=>update.title);
    const note=document.createElement('div');note.className='assistant-memory-note';
    const text=document.createElement('span');
    text.textContent=[saved.length?'Память обновлена: '+saved.join(', '):'',forgotten.length?'Удалено из памяти: '+forgotten.join(', '):''].filter(Boolean).join(' · ');
    const manage=document.createElement('button');manage.type='button';manage.textContent='Управлять';
    manage.onclick=()=>{const panel=document.querySelector('#assistant-knowledge-panel');if(panel)panel.dataset.scope='personal';document.querySelector('#assistant-knowledge')?.click()};
    note.innerHTML=assistantIcon('book',14);note.append(text,manage);item.append(note);
  };
  const renderSavedAction=(item,action,undoable,documentId,quoteId)=>{
    item.replaceChildren();item.classList.add('is-saved');const title=document.createElement('p');title.className='assistant-saved-title';
    title.textContent=(quoteId?'Черновик создан · ':'Сохранено · ')+action.summary;item.append(title);
    if(quoteId){
      const open=document.createElement('button');open.type='button';open.className='btn small primary assistant-saved-open-quote';
      open.textContent='Открыть смету';open.setAttribute('aria-label','Открыть созданную смету');
      open.onclick=()=>openQuoteEditor(quoteId);item.append(open);
      const hint=document.createElement('small');hint.className='assistant-saved-hint';
      hint.textContent='Сохранено в разделе «Сметы». Клиенту ещё не отправлено.';
      item.append(hint);
    }
    if(documentId){const pdf=document.createElement('button');pdf.type='button';pdf.className='btn ghost';pdf.textContent='Скачать PDF';pdf.onclick=()=>Workspace.download('/documents/'+encodeURIComponent(documentId)+'/pdf','smetra-document.pdf').catch(error=>notify(error.message));item.append(pdf)}
    if(!undoable)return;
    const button=document.createElement('button');button.type='button';button.className='btn ghost';button.textContent='Отменить изменение';item.append(button);
    button.onclick=async()=>{button.disabled=true;try{await api('/assistant/undo',{method:'POST',body:JSON.stringify({id:action.id})});item.replaceChildren(title);title.textContent='Изменение отменено · '+action.summary;notify('Изменение отменено')}catch(error){button.disabled=false;notify(error.message)}};
  };
  renderQuota(quota);
  let jobRequest=null,jobPollTimer=null,jobLoadSeq=0;
  const observedChatJobs=new Set();
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
      renderDelivery();
      for(const job of result.jobs){
        if(job.kind==='chat'&&(job.conversation_id||'')===activeConversation){
          if(['queued','running','retry'].includes(job.status))observedChatJobs.add(job.id);
          else if(job.status==='completed'&&observedChatJobs.has(job.id)&&!(working&&currentJobId===job.id)){
            observedChatJobs.delete(job.id);await window.SmetraAssistant();return;
          }
        }
      }
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
      if(result.jobs.some(job=>['queued','running','retry'].includes(job.status)))jobPollTimer=setTimeout(refreshJobs,2000);
    }catch{if(active()&&jobList.isConnected&&sequence===jobLoadSeq)jobPollTimer=setTimeout(refreshJobs,15000)}
  };
  const renderDelivery=()=>{
    if(!active()||!composer.isConnected)return;
    send.setAttribute('aria-label','Отправить сообщение');
    const quotaBlocked=quota.remaining<1&&quota.plan!=='pro';
    send.title=quotaBlocked?'Токены ассистента закончились. Черновик останется доступен.':'Отправить сообщение';
    document.querySelector('#assistant-delivery-hint').textContent=backgroundEnabled===false
      ?'Ассистент временно недоступен. Черновик останется в этом чате.'
      :quotaBlocked?'Токены закончились — черновик останется доступен.'
      :'Ответ сохранится в диалоге · Enter — отправить';
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
    messages.innerHTML='<div class="assistant-welcome"><h2>С чего начнём?</h2><p>Опишите работы словами или прикрепите фото объекта — ассистент предложит позиции сметы. Суммы считает Сметра, а изменения сохраняются только после вашего подтверждения.</p><div class="assistant-suggestions"><button type="button" data-prompt="Помоги составить новую смету. Спроси необходимые детали.">'+assistantIcon('file-text',16)+'<span>Составить смету</span></button><button type="button" data-prompt="Какие сметы ожидают согласования?">'+assistantIcon('check',16)+'<span>Проверить согласования</span></button><button type="button" data-prompt="Покажи поступления и остатки по заказам.">'+assistantIcon('wallet',16)+'<span>Разобраться в оплатах</span></button></div></div>';
    messages.querySelectorAll('[data-prompt]').forEach(button=>button.onclick=()=>{input.value=button.dataset.prompt;saveDraft();input.focus();resize();syncSendButton();renderQuota(quota)});
  }
  thread.messages.forEach(message=>addMessage(message.role,message.content,message.id));
  data.actions.filter(action=>(action.conversation_id||'')===activeConversation).forEach(addAction);
  (data.recent_actions||[]).filter(action=>action.undo_until&&(action.conversation_id||'')===activeConversation).forEach(action=>{const item=document.createElement('section');item.className='assistant-proposal assistant-saved';actions.append(item);renderSavedAction(item,action,!!action.undo_until,action.document_id,action.quote_id)});
  if(!data.available)status.textContent='Ассистент пока не подключён.';
  else if(quota.remaining<(quota.unit==='tokens'?1500:1))status.textContent='Токены закончились: обычные и фоновые ответы расходуют общий баланс. Черновик можно редактировать.';
  const resize=()=>{input.style.height='auto';input.style.height=Math.min(input.scrollHeight,180)+'px'};
  const takeSubmittedDraft=()=>{
    const submitted={text:input.value,prompt:input.value.trim(),photos:pendingPhotos.map(entry=>entry.file),context,slot:draftSlot()};
    clearSentDraft(submitted.prompt,submitted.slot);
    input.value='';fileInput.value='';
    if(context&&['files','documents'].includes(context.entity)){
      context=null;renderContext();clearTimeout(filePollTimer);filePollSeq++;
      fileStatus.hidden=true;fileStatus.replaceChildren();fileBlocking=false;
    }
    submitted.remainingContext=context;
    clearSentDraft(submitted.prompt);
    clearPhoto();resize();syncSendButton();
    return submitted;
  };
  const restoreSubmittedDraft=submitted=>{
    if(!active()||!input.isConnected||input.value||pendingPhotos.length||context!==submitted.remainingContext)return;
    context=submitted.context;
    if(context)sessionStorage.setItem('smetra.assistant.context',JSON.stringify(context));
    pendingPhotos=submitted.photos.map(file=>({file,url:URL.createObjectURL(file)}));
    input.value=submitted.text;renderContext();renderPhoto();saveDraft();resize();syncSendButton();
    if(context?.entity==='files')refreshFile();
  };
  const clearSentFileContext=async submitted=>{
    if(context!==submitted.remainingContext)return;
    if(!active()||!activeConversation||!submitted.context||!['files','documents'].includes(submitted.context.entity))return;
    // The sent request owns a context snapshot. It no longer belongs to the next draft.
    try{await api(threadPath,{method:'PATCH',body:JSON.stringify({context_entity:'',context_id:''})})}catch{}
  };
  input.addEventListener('input',()=>{resize();saveDraft();renderQuota(quota);syncSendButton()});resize();syncSendButton();
  input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&event.keyCode!==229){event.preventDefault();document.querySelector('#assistant-form').requestSubmit()}});
  document.querySelector('#assistant-form').onsubmit=async event=>{
    event.preventDefault();
    // The displayed transcript is the source of truth at submit time.
    // Abort recognition before clearing the composer so late results cannot reappear.
    if(voiceListening||voiceStarting){stopVoiceInput();syncSendButton()}
    let prompt=input.value.trim();if((!prompt&&!pendingPhotos.length)||working||threadBusy||attachingCount||fileBlocking||quota.remaining<(quota.unit==='tokens'?1500:1)||!data.available||backgroundEnabled===false)return;
    if(window.SmetraEstimateSafety){try{if(!(await window.SmetraEstimateSafety.ensureConsent()))return}catch(error){status.textContent=error.message;return}}
    if(!active()||working||threadBusy||attachingCount)return;
    prompt=input.value.trim();if(!prompt&&!pendingPhotos.length)return;
    const submitted=takeSubmittedDraft();
    working=true;cancelRequested=false;currentJobId=null;renderQuota(quota);stop.hidden=false;stop.disabled=false;requestController=new AbortController();status.textContent='Подключаюсь к модели…';
    messages.querySelector('.assistant-welcome')?.remove();messages.querySelectorAll('.assistant-error').forEach(node=>node.remove());
    const sentPhotos=submitted.photos;
    const userMessage=addMessage('user',prompt||(sentPhotos.length?'Посмотри прикреплённые фотографии.':''));
    if(sentPhotos.length){const attached=document.createElement('small');attached.className='assistant-message-attachment';attached.textContent='Фото: '+sentPhotos.map(file=>file.name).join(', ');userMessage.body.append(attached)}
    const assistantMessage=addMessage('assistant','');
    assistantMessage.item.classList.add('streaming');
    const activity=document.createElement('div');activity.className='assistant-activity';activity.setAttribute('role','status');
    const pulse=document.createElement('span');pulse.className='assistant-activity-indicator';pulse.setAttribute('aria-hidden','true');
    const activityLabel=document.createElement('span');activityLabel.className='assistant-activity-label';activityLabel.textContent='Думаю…';
    const sources=document.createElement('div');sources.className='assistant-activity-sources';
    activity.append(pulse,activityLabel,sources);assistantMessage.item.prepend(activity);
    const setActivity=value=>{activityLabel.textContent=String(value||'Думаю…').slice(0,100)};
    const showSource=item=>{
      if(!item||typeof item.url!=='string'||sources.children.length>=3)return;
      let url;try{url=new URL(item.url)}catch{return}
      if(!['http:','https:'].includes(url.protocol)||!url.hostname||url.username||url.password)return;
      if([...sources.querySelectorAll('a')].some(a=>a.href===url.href))return;
      const chip=document.createElement('a');chip.className='assistant-source';chip.href=url.href;chip.target='_blank';chip.rel='noopener noreferrer';
      const icon=document.createElement('img');icon.alt='';icon.loading='lazy';
      icon.src='https://www.google.com/s2/favicons?domain='+encodeURIComponent(url.hostname)+'&sz=32';
      icon.onerror=()=>{const fallback=document.createElement('span');fallback.className='assistant-source-fallback';fallback.textContent=url.hostname[0].toUpperCase();icon.replaceWith(fallback)};
      const name=document.createElement('span');name.className='assistant-source-name';name.textContent=url.hostname;
      chip.append(icon,name);sources.append(chip);
    };
    scrollBottom();
    let generated='',paintPending=false,completed=false,queued=false,delegated=false,terminalFailure=false,paintFrame=0,lastPaint=0;
    const paint=()=>{if(!active()||!assistantMessage.item.isConnected)return;const follow=nearBottom();paintPending=false;lastPaint=performance.now();assistantMessage.body.dataset.source=generated;assistantMessage.body.innerHTML=assistantMarkdown(generated);if(follow)scrollBottom()};
    const schedule=()=>{if(!paintPending){paintPending=true;const frame=()=>{if(performance.now()-lastPaint<32)paintFrame=requestAnimationFrame(frame);else paint()};paintFrame=requestAnimationFrame(frame)}};
    try{
      let savedIds=[];
      if(sentPhotos.length){
        status.textContent='Сохраняю фотографии в хранилище…';
        savedIds=await Promise.all(sentPhotos.map(persistChatPhoto));
        if(savedIds.some(id=>!id))throw Error('Не удалось сохранить все изображения в рабочем пространстве');
        if(active()){
          const notice=document.createElement('a');notice.href='#files';notice.textContent='Фотографии сохранены в хранилище';notice.className='assistant-storage-link';
          notice.onclick=event=>{event.preventDefault();location.hash='files'};userMessage.body.append(notice);
        }
      }
      if(owner!==user||cancelRequested)throw new DOMException('Ответ остановлен','AbortError');
      const body=JSON.stringify({text:prompt,context:submitted.context?{entity:submitted.context.entity,id:submitted.context.id}:null,...(savedIds.length?{file_ids:savedIds}:{}),...(activeConversation?{conversation_id:activeConversation}:{})});
      if(!jobRequest||jobRequest.body!==body)jobRequest={body,key:crypto.randomUUID()};
      const accepted=await api('/assistant/jobs',{method:'POST',headers:{'Idempotency-Key':jobRequest.key,...scopeHeaders},body});
      currentJobId=accepted.job.id;queued=true;jobRequest=null;observedChatJobs.add(currentJobId);
      if(cancelRequested){
        await api('/assistant/jobs/'+encodeURIComponent(currentJobId),{method:'DELETE',headers:{...scopeHeaders}});
        throw new DOMException('Ответ остановлен','AbortError');
      }
      if(owner!==user)return;
      if(active()){renderQuota(accepted.quota);await clearSentFileContext(submitted);refreshJobs()}
      const response=await fetch('/api/assistant/stream',{method:'POST',credentials:'same-origin',signal:requestController.signal,headers:{'Content-Type':'application/json',...scopeHeaders},body:JSON.stringify({job_id:currentJobId})});
      if(!response.ok){let error;try{error=(await response.json()).error}catch{}throw Error(error||`Ошибка ${response.status}`)}
      if(!response.body)throw Error('Браузер не поддерживает потоковый ответ');
      const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
      let hasModelProgress=false;
      const eventBlock=block=>{
        const lines=block.split(/\r?\n/);const kind=lines.find(line=>line.startsWith('event:'))?.slice(6).trim();
        const raw=lines.filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');
        if(!kind||!raw)return;
        const payload=JSON.parse(raw);
        if(kind==='done'){completed=true;observedChatJobs.delete(currentJobId);jobLoadSeq++}
        if(kind==='background')delegated=true;
        if(kind==='error'){terminalFailure=true;if(payload.cancelled){const error=new DOMException('Ответ остановлен','AbortError');throw error}}
        if(!active()||!messages.isConnected)return;
        if(kind==='ready'){renderQuota(payload.quota);if(!hasModelProgress){setActivity('Анализирую запрос…');status.textContent='Анализирую запрос…'}}
        if(kind==='delta'&&typeof payload.text==='string'){generated+=payload.text;schedule();if(!hasModelProgress){setActivity('Формирую ответ…');status.textContent='Формирую ответ…'}}
        if(kind==='status'&&typeof payload.text==='string'&&payload.text.trim()){hasModelProgress=true;setActivity(payload.text.trim());status.textContent=payload.text.trim()}
        if(kind==='web_source'){showSource(payload);if(!hasModelProgress)setActivity('Проверяю источники…')}
        if(kind==='quote_design'){quotePreview?.design(payload).catch(()=>{});if(!hasModelProgress)setActivity('Конструирую смету…')}
        if(kind==='done'){if(activeConversation&&typeof payload.conversation_title==='string'){
          const title=payload.conversation_title.trim();
          if(title){
            const row=[...document.querySelectorAll('[data-thread-row]')].find(node=>node.dataset.threadId===activeConversation);
            if(row){
              const label=row.querySelector('.assistant-conversation-title'),open=row.querySelector('.assistant-conversation-open');
              if(label)label.textContent=title;
              if(open)open.title=title;
              const rename=row.querySelector('[data-thread-rename-input]');if(rename)rename.value=title;
            }
            const index=threadIndex.items.find(item=>item.id===activeConversation);if(index)index.title=title;
            const option=[...document.querySelector('#assistant-thread-select').options].find(item=>item.value===activeConversation);
            if(option)option.textContent=title;
          }
        }if(typeof payload.answer==='string')generated=payload.answer;cancelAnimationFrame(paintFrame);paint();(payload.actions||[]).forEach(addAction);if(Array.isArray(payload.questions)&&payload.questions.length)showQuestion(payload.questions[0]);(payload.designs||[]).forEach(design=>quotePreview?.design(design).catch(()=>{}));showMemoryNote(assistantMessage.item,payload.memory);renderQuota(payload.quota);completed=true;status.textContent='';activity.classList.add('is-complete');if(sources.children.length)setActivity('Источники');else activity.remove()}
        if(kind==='background'){setActivity('Выполняю запрос…');status.textContent='Запрос сохранён. Ответ появится в этом диалоге.';refreshJobs()}
        if(kind==='error'){renderQuota(payload.quota);throw Error(payload.error||'Не удалось завершить ответ')}
      };
      try{
        while(!completed&&!delegated){
          const {value,done}=await reader.read();
          if(done){buffer+=decoder.decode();break}
          buffer+=decoder.decode(value,{stream:true});
          let match;
          while(!completed&&!delegated&&(match=buffer.match(/\r?\n\r?\n/))){
            const block=buffer.slice(0,match.index);buffer=buffer.slice(match.index+match[0].length);eventBlock(block);
          }
        }
        if(!completed&&!delegated){
          if(buffer.trim())eventBlock(buffer.trim());
          if(!completed&&!delegated)throw Error('Соединение прервалось. Запрос сохранён на сервере.');
        }
      }finally{
        await reader.cancel().catch(()=>{});
        reader.releaseLock();
      }
      assistantMessage.item.classList.remove('streaming');
    }catch(error){
      if(!active()||!messages.isConnected)return;
      if(completed)return;
      if(queued&&!terminalFailure&&!cancelRequested){
        cancelAnimationFrame(paintFrame);assistantMessage.item.classList.remove('streaming');
        activity.classList.add('is-complete');setActivity('Продолжаю выполнение…');
        status.textContent='Запрос сохранён. Ответ появится в этом диалоге.';refreshJobs();return;
      }
      restoreSubmittedDraft(submitted);
      cancelAnimationFrame(paintFrame);
      assistantMessage.item.classList.remove('streaming');
      if(error.name!=='AbortError'&&generated&&assistantMessage.item.isConnected)paint();
      if(error.name==='AbortError'){
        assistantMessage.item.remove();
        status.textContent='Ответ остановлен.';
      }else{
        activity.classList.add('is-complete');
        setActivity('Генерация прервана');
        if(!generated)assistantMessage.item.remove();
        status.textContent=(generated?'Ответ прервался: ':'')+error.message;
        // Restore the submitted draft for retry without overwriting a newer view or draft.
        const failure=document.createElement('div');failure.className='assistant-error';failure.setAttribute('role','alert');
        const text=document.createElement('p');text.textContent=(generated?'Ответ прервался. ':'Не удалось получить ответ. ')+error.message+' Текст сообщения сохранён.';
        const retry=document.createElement('button');retry.type='button';retry.className='btn small';retry.innerHTML=assistantIcon('refresh',15)+'<span>Повторить</span>';
        retry.onclick=()=>{if(working)return;failure.remove();if(!generated)userMessage.item.remove();if(!input.value.trim()&&prompt){input.value=prompt;resize()}syncSendButton();renderQuota(quota);document.querySelector('#assistant-form').requestSubmit()};
        failure.append(text,retry);messages.append(failure);
        requestAnimationFrame(scrollBottom);
      }
      try{renderQuota((await api('/assistant')).quota)}catch{}
    }finally{working=false;requestController=null;if(active()&&composer.isConnected){stop.hidden=true;renderQuota(quota);input.disabled=!data.available;if(!input.disabled)input.focus();if(queued)refreshJobs()}}
  };
  // Initialize the tray after quota/state callbacks are constructed.
  renderPhoto();
  // A different route destroys this view. Release observers, preview listeners,
  // and object URLs instead of retaining whole conversations in memory.
  const disposeAssistantView=()=>{
    conversationObserver.disconnect();
    clearTimeout(jobPollTimer);clearTimeout(filePollTimer);jobLoadSeq++;filePollSeq++;
    quotePreview?.destroy();
    for(const entry of pendingPhotos)URL.revokeObjectURL(entry.url);
    pendingPhotos=[];
    document.removeEventListener('smetra:before-view',disposeAssistantView);
  };
  document.addEventListener('smetra:before-view',disposeAssistantView,{once:true});
};
