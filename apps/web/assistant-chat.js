'use strict';

// Render a deliberately small Markdown subset. User/model text is escaped first;
// only http(s) links are made clickable, so chat content cannot inject HTML.
function assistantInline(source) {
  const links=[];
  const segments=String(source).split(/(`[^`\n]+`)/g);
  return segments.map(segment=>{
    if(segment.startsWith('`')&&segment.endsWith('`'))return `<code>${escapeHtml(segment.slice(1,-1))}</code>`;
    const withLinks=segment.replace(/[\uE000\uE001]/g,'').replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g,(match,label,href)=>{
      try{
        const url=new URL(href);
        if(!['http:','https:'].includes(url.protocol))return match;
        const index=links.push(`<a href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`)-1;
        return `\uE000${index}\uE001`;
      }catch{return match}
    });
    return escapeHtml(withLinks)
      .replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g,'$1<em>$2</em>')
      .replace(/\uE000(\d+)\uE001/g,(_,index)=>links[Number(index)]||'');
  }).join('');
}

function assistantMarkdown(source) {
  const lines=String(source||'').replace(/\r\n?/g,'\n').split('\n');
  const html=[];let index=0;
  const isBlock=line=>/^\s*$|^```|^#{1,3}\s|^>\s?|^\s*[-*]\s+|^\s*\d+\.\s+|^---+\s*$/.test(line);
  while(index<lines.length){
    const line=lines[index];
    if(!line.trim()){index++;continue}
    if(line.startsWith('```')){
      const language=line.slice(3).trim().replace(/[^a-z0-9+#-]/gi,'').slice(0,24);
      const code=[];index++;
      while(index<lines.length&&!lines[index].startsWith('```'))code.push(lines[index++]);
      if(index<lines.length)index++;
      html.push(`<pre><span class="code-language">${escapeHtml(language||'Код')}</span><code>${escapeHtml(code.join('\n'))}</code></pre>`);
      continue;
    }
    const heading=line.match(/^(#{1,3})\s+(.+)$/);
    if(heading){const level=Math.min(heading[1].length+2,4);html.push(`<h${level}>${assistantInline(heading[2])}</h${level}>`);index++;continue}
    if(/^---+\s*$/.test(line)){html.push('<hr>');index++;continue}
    if(/^>\s?/.test(line)){
      const quote=[];
      while(index<lines.length&&/^>\s?/.test(lines[index]))quote.push(lines[index++].replace(/^>\s?/,''));
      html.push(`<blockquote>${quote.map(assistantInline).join('<br>')}</blockquote>`);continue;
    }
    const unordered=/^\s*[-*]\s+/.test(line),ordered=/^\s*\d+\.\s+/.test(line);
    if(unordered||ordered){
      const tag=ordered?'ol':'ul',pattern=ordered?/^\s*\d+\.\s+/:/^\s*[-*]\s+/;
      const items=[];
      while(index<lines.length&&pattern.test(lines[index]))items.push(`<li>${assistantInline(lines[index++].replace(pattern,''))}</li>`);
      html.push(`<${tag}>${items.join('')}</${tag}>`);continue;
    }
    const paragraph=[line];index++;
    while(index<lines.length&&!isBlock(lines[index]))paragraph.push(lines[index++]);
    html.push(`<p>${paragraph.map(assistantInline).join('<br>')}</p>`);
  }
  return html.join('');
}

window.SmetraAssistantContext=function(value){
  if(!value||!['clients','quotes','projects','files'].includes(value.entity)||typeof value.id!=='string')return;
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
  const labels={unit_price:'Цена',quantity:'Количество',coefficient:'Коэффициент',markup:'Наценка, %',discount:'Скидка, %',tax:'Налог, %',unit:'Единица',category:'Категория',optional:'Опциональная позиция',included:'Включена в расчёт',name:'Название',title:'Название',notes:'Заметки',description:'Описание',amount:'Сумма',items:'Позиции',phone:'Телефон',email:'Почта'};
  const structure=preview.kind==='quote_structure';
  const itemText=(item,position)=>item?`Строка ${position} · ${item.quantity} ${item.unit} × ${assistantEditValue('unit_price',item.unit_price,preview.currency)} · ${assistantEditValue('amount',item.subtotal,preview.currency)}${item.optional?(item.included?' · опция включена':' · опция исключена'):''}`:'—';
  const rows=(preview.rows||[]).map(row=>structure?`<div class="assistant-diff-row"><span>${escapeHtml(({insert:'Добавить',remove:'Удалить',move:'Переместить'})[row.change]||'Изменить')} · ${escapeHtml((row.after||row.before)?.name||'Позиция')}</span><div><del>${escapeHtml(itemText(row.before,row.before_row))}</del><span aria-label="станет">${escapeHtml(itemText(row.after,row.after_row))}</span></div></div>`:`<div class="assistant-diff-row"><span>${row.row?escapeHtml(row.row)+'. '+escapeHtml(row.name)+' · ':''}${escapeHtml(labels[row.field]||row.field)}</span><div><del>${escapeHtml(assistantEditValue(row.field,row.before,preview.currency))}</del><span aria-label="станет">${escapeHtml(assistantEditValue(row.field,row.after,preview.currency))}</span></div></div>`);
  const totals=['quote_items','quote_structure'].includes(preview.kind)?`${structure?`<p class="muted">Позиций: ${escapeHtml(preview.before_count)} → ${escapeHtml(preview.after_count)}</p>`:''}<div class="assistant-diff-total"><span>Итого по смете</span><div><del>${escapeHtml(assistantEditValue('amount',preview.before_total,preview.currency))}</del><strong>${escapeHtml(assistantEditValue('amount',preview.after_total,preview.currency))}</strong></div></div>`:'';
  return `<div class="assistant-edit-diff">${rows.slice(0,5).join('')}${rows.length>5?`<details><summary>Ещё ${rows.length-5} изменений</summary>${rows.slice(5).join('')}</details>`:''}${totals}</div>`;
}
window.SmetraAssistant=async function(){
  const [data,threadIndex]=await Promise.all([api('/assistant'),api('/assistant/conversations')]);
  const maxUpload=Math.min(5000000,data.file_upload_max_bytes||3000000),maxUploadLabel=Math.floor(maxUpload/1000000)+' МБ';
  let activeConversation=sessionStorage.getItem('smetra.assistant.conversation')||'';
  if(activeConversation&&!threadIndex.items.some(item=>item.id===activeConversation))activeConversation='';
  const thread=activeConversation?await api('/assistant/conversations/'+encodeURIComponent(activeConversation)):data;
  view(`<section class="assistant-page"><header class="assistant-header"><div><span class="overline"><span class="assistant-mark"></span>Сметра рядом</span><h1>Ассистент</h1></div><span id="assistant-quota" class="assistant-quota"></span></header><div class="assistant-workbar"><label class="visually-hidden" for="assistant-thread-select">Диалог</label><select id="assistant-thread-select"><option value="">Общий диалог</option>${threadIndex.items.map(item=>`<option value="${escapeHtml(item.id)}" ${item.id===activeConversation?'selected':''}>${item.pinned?'● ':''}${escapeHtml(item.title)}</option>`).join('')}</select><button class="btn small" id="assistant-new-thread" type="button">+ Диалог</button><button class="btn small" id="assistant-knowledge" type="button">Знания</button><button class="assistant-thread-action" id="assistant-rename" type="button" aria-label="Переименовать диалог" title="Переименовать" ${activeConversation?'':'disabled'}>✎</button><button class="assistant-thread-action" id="assistant-pin" type="button" aria-label="Закрепить диалог" title="Закрепить" ${activeConversation?'':'disabled'}>◇</button><button class="assistant-thread-action" id="assistant-delete" type="button" aria-label="Удалить диалог" title="Удалить" ${activeConversation?'':'disabled'}>×</button></div><form id="assistant-thread-edit" class="assistant-thread-edit hidden"><input id="assistant-thread-name" maxlength="120" aria-label="Название диалога"><button class="btn small" type="submit">Сохранить</button><button class="btn small" type="button" id="assistant-thread-cancel">Отмена</button></form><div id="assistant-knowledge-panel" class="hidden"></div><div id="assistant-messages" class="assistant-thread" role="log" aria-live="off"></div><div id="assistant-actions"></div><div class="assistant-composer"><div id="assistant-context" class="assistant-context hidden"><span>Контекст</span><strong id="assistant-context-label"></strong><button id="assistant-context-remove" type="button" aria-label="Убрать контекст">×</button></div><form id="assistant-form"><label class="visually-hidden" for="assistant-input">Сообщение ассистенту</label><textarea id="assistant-input" placeholder="Спросите или поручите задачу…" rows="1" maxlength="3000" required></textarea><button class="btn primary" id="assistant-send" type="submit" aria-label="Отправить сообщение">↗</button><button class="btn" id="assistant-stop" type="button" hidden>Стоп</button></form><div class="assistant-composer-foot"><span id="assistant-status" role="status"></span><span>Enter — отправить · Shift+Enter — новая строка</span></div><a id="assistant-upgrade" class="assistant-upgrade hidden" href="/app#billing">Лимит исчерпан. Посмотреть тариф Про ↗</a></div></section>`);
  const messages=document.querySelector('#assistant-messages');
  const actions=document.querySelector('#assistant-actions');
  const input=document.querySelector('#assistant-input');
  const composer=document.querySelector('.assistant-composer');
  const attachmentBar=document.createElement('div');attachmentBar.className='assistant-attachment-bar';
  attachmentBar.innerHTML='<button type="button" id="assistant-attach">+ Файл</button><input type="file" id="assistant-attach-input" accept=".pdf,.txt,.md" hidden><span>PDF, TXT или Markdown · до 5 МБ</span>';
  attachmentBar.querySelector('span').textContent='PDF, TXT или Markdown · до '+maxUploadLabel;
  composer.insertBefore(attachmentBar,document.querySelector('#assistant-form'));
  const jobBar=document.createElement('div');jobBar.className='assistant-jobbar';
  const backgroundButton=document.createElement('button');backgroundButton.type='button';backgroundButton.textContent='Выполнить в фоне';backgroundButton.hidden=true;
  const jobList=document.createElement('div');jobList.className='assistant-jobs';jobList.setAttribute('aria-live','polite');
  jobBar.append(backgroundButton);composer.insertBefore(jobBar,document.querySelector('#assistant-form'));actions.after(jobList);
  const send=document.querySelector('#assistant-send');
  const status=document.querySelector('#assistant-status');
  const quotaLabel=document.querySelector('#assistant-quota');
  const upgrade=document.querySelector('#assistant-upgrade');
  const selectedThread=threadIndex.items.find(item=>item.id===activeConversation);
  const threadPath=activeConversation?'/assistant/conversations/'+encodeURIComponent(activeConversation):'';
  document.querySelector('#assistant-thread-select').onchange=event=>{sessionStorage.removeItem('smetra.assistant.context');sessionStorage.setItem('smetra.assistant.conversation',event.target.value);window.SmetraAssistant()};
  document.querySelector('#assistant-new-thread').onclick=async()=>{try{const created=await api('/assistant/conversations',{method:'POST',body:JSON.stringify({title:'Новый диалог',...(context?{context_entity:context.entity,context_id:context.id}:{})})});sessionStorage.setItem('smetra.assistant.conversation',created.conversation.id);window.SmetraAssistant()}catch(error){notify(error.message)}};
  document.querySelector('#assistant-knowledge').onclick=async()=>{const panel=document.querySelector('#assistant-knowledge-panel');if(!panel.classList.contains('hidden')){panel.classList.add('hidden');return}await window.SmetraKnowledgePanel?.(panel);panel.classList.remove('hidden')};
  document.querySelector('#assistant-rename').onclick=()=>{const form=document.querySelector('#assistant-thread-edit');form.classList.remove('hidden');const name=document.querySelector('#assistant-thread-name');name.value=selectedThread.title;name.focus();name.select()};
  document.querySelector('#assistant-thread-cancel').onclick=()=>document.querySelector('#assistant-thread-edit').classList.add('hidden');
  document.querySelector('#assistant-thread-edit').onsubmit=async event=>{event.preventDefault();try{await api(threadPath,{method:'PATCH',body:JSON.stringify({title:document.querySelector('#assistant-thread-name').value.trim()})});window.SmetraAssistant()}catch(error){notify(error.message)}};
  document.querySelector('#assistant-pin').onclick=async()=>{try{await api(threadPath,{method:'PATCH',body:JSON.stringify({pinned:selectedThread.pinned?0:1})});window.SmetraAssistant()}catch(error){notify(error.message)}};
  document.querySelector('#assistant-delete').onclick=async()=>{if(!confirm('Удалить этот диалог и его сообщения?'))return;try{await api(threadPath,{method:'DELETE'});sessionStorage.removeItem('smetra.assistant.conversation');window.SmetraAssistant()}catch(error){notify(error.message)}};
  let context=null,fileBlocking=false,filePollTimer=null,filePollSeq=0;
  try{context=JSON.parse(sessionStorage.getItem('smetra.assistant.context')||'null')}catch{}
  const currentWorkspace=window.Workspace?.currentWorkspaceId?.()||sessionStorage.getItem('workspace_id')||'';
  if(context&&(!['clients','quotes','projects','files'].includes(context.entity)||typeof context.id!=='string'||currentWorkspace&&context.workspace_id!==currentWorkspace))context=null;
  if(activeConversation){
    context=selectedThread.context_entity?{entity:selectedThread.context_entity,id:selectedThread.context_id,workspace_id:currentWorkspace}:null;
    if(context){try{const record=await api('/'+context.entity+'/'+encodeURIComponent(context.id)+(context.entity==='files'?'/metadata':''));const item=record.quote||record.item||record.file;context.label=item?.title||item?.name||context.id}catch{context.label='Запись недоступна — уберите контекст'}}
  }
  const contextBar=document.querySelector('#assistant-context');
  const fileStatus=document.createElement('div');fileStatus.className='assistant-file-status';fileStatus.hidden=true;fileStatus.setAttribute('role','status');contextBar.after(fileStatus);
  const renderContext=()=>{
    contextBar.classList.toggle('hidden',!context);
    if(context)document.querySelector('#assistant-context-label').textContent=({clients:'Клиент',quotes:'Смета',projects:'Заказ',files:'Файл'})[context.entity]+': '+(context.label||context.id);
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
    if(!['pdf','txt','md'].includes(extension)||file.size<1||file.size>maxUpload){status.textContent='Выберите PDF, TXT или MD до '+maxUploadLabel;return}
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
  let quota=data.quota,working=false,requestController=null;
  const stop=document.querySelector('#assistant-stop');
  stop.onclick=()=>requestController?.abort();
  const renderQuota=value=>{
    quota=value;
    quotaLabel.textContent=`${value.remaining} из ${value.limit} сообщений · ${value.plan==='free'?'Старт':'Про'}`;
    quotaLabel.title=`Лимит обновится ${new Date(value.resets_at*1000).toLocaleDateString('ru-RU')}`;
    upgrade.classList.toggle('hidden',value.remaining>0||value.plan==='pro');
    send.disabled=working||fileBlocking||!data.available||value.remaining<1;
    backgroundButton.disabled=working||fileBlocking||!data.available||value.remaining<1;
    input.disabled=!data.available||value.remaining<1;
  };
  const scrollBottom=()=>{if(window.innerHeight+window.scrollY>=document.documentElement.scrollHeight-260)window.scrollTo({top:document.documentElement.scrollHeight,behavior:'instant'})};
  const addMessage=(role,text,messageId)=>{
    const item=document.createElement('article');item.className='assistant-message '+role;
    const label=document.createElement('small');label.textContent=role==='user'?'ВЫ':'СМЕТРА';
    const body=document.createElement('div');body.className='assistant-markdown';
    body.innerHTML=assistantMarkdown(text);
    item.append(label,body);
    if(role==='assistant'){
      const copy=document.createElement('button');copy.type='button';copy.className='assistant-copy';copy.textContent='Копировать';copy.onclick=async()=>{await navigator.clipboard.writeText(body.innerText);copy.textContent='Скопировано';setTimeout(()=>copy.textContent='Копировать',1800)};
      item.append(copy);
    }
    if(activeConversation&&messageId){
      const fork=document.createElement('button');fork.type='button';fork.className='assistant-fork';fork.textContent='Новая ветка';
      fork.title='Продолжить диалог с этого сообщения отдельно';
      fork.onclick=async()=>{fork.disabled=true;try{
        const result=await api('/assistant/conversations/'+encodeURIComponent(activeConversation)+'/fork',{method:'POST',body:JSON.stringify({message_id:messageId})});
        sessionStorage.setItem('smetra.assistant.conversation',result.conversation.id);window.SmetraAssistant();
      }catch(error){fork.disabled=false;notify(error.message)}};
      item.append(fork);
    }
    messages.append(item);return {item,body};
  };
  const addAction=action=>{
    const item=document.createElement('section');item.className='assistant-proposal';
    const markdownEdit=action.tool==='replace_markdown_text';
    const detail=action.preview?assistantEditPreview(action.preview):markdownEdit?`<div class="assistant-text-diff"><span>Было</span><pre>${escapeHtml(action.arguments.old_text)}</pre><span>Станет</span><pre>${escapeHtml(action.arguments.new_text)}</pre></div><p class="muted">После применения предыдущий текст останется в истории документа.</p>`:proposalFields(action.arguments);
    item.innerHTML=`<span class="overline">Предложение · ещё не сохранено</span><h3>${escapeHtml(action.summary)}</h3><div class="proposal-fields">${detail}</div><div class="row"><button class="btn primary" data-confirm>${markdownEdit?'Применить правку':'Применить'}</button><button class="btn ghost" data-dismiss>Не сейчас</button></div>`;
    actions.append(item);
    item.querySelector('[data-confirm]').onclick=async()=>{const buttons=item.querySelectorAll('button');buttons.forEach(button=>button.disabled=true);try{const result=await api('/assistant/confirm',{method:'POST',body:JSON.stringify({id:action.id})});renderSavedAction(item,action,result.undoable);notify('Изменения сохранены')}catch(error){notify(error.message);buttons.forEach(button=>button.disabled=false)}};
    item.querySelector('[data-dismiss]').onclick=async()=>{try{await api('/assistant/dismiss',{method:'POST',body:JSON.stringify({id:action.id})});item.remove()}catch(error){notify(error.message)}};
  };
  const renderSavedAction=(item,action,undoable)=>{
    item.replaceChildren();const title=document.createElement('p');title.textContent='Сохранено · '+action.summary;item.append(title);
    if(!undoable)return;
    const button=document.createElement('button');button.type='button';button.className='btn ghost';button.textContent='Отменить изменение';item.append(button);
    button.onclick=async()=>{button.disabled=true;try{await api('/assistant/undo',{method:'POST',body:JSON.stringify({id:action.id})});title.textContent='Изменение отменено · '+action.summary;button.remove();notify('Предыдущие значения восстановлены')}catch(error){button.disabled=false;notify(error.message)}};
  };
  renderQuota(quota);
  let jobRequest=null,jobPollTimer=null,jobLoadSeq=0;
  const refreshJobs=async()=>{
    clearTimeout(jobPollTimer);const sequence=++jobLoadSeq;
    if(!jobList.isConnected)return;
    try{
      if(document.hidden){jobPollTimer=setTimeout(refreshJobs,15000);return}
      const result=await api('/assistant/jobs');
      if(!jobList.isConnected||sequence!==jobLoadSeq)return;
      backgroundButton.hidden=!result.enabled;
      backgroundButton.disabled=working||fileBlocking||quota.remaining<1||!data.available;
      jobList.replaceChildren();
      const labels={queued:'В очереди',running:'В работе',retry:'Повторю позже',completed:'Готово',failed:'Не удалось завершить',cancelled:'Отменено'};
      result.jobs.filter(job=>['queued','running','retry'].includes(job.status)||Date.now()/1000-job.updated_at<86400).slice(0,5).forEach(job=>{
        const row=document.createElement('div');row.className='assistant-job';
        const description=document.createElement('div'),title=document.createElement('strong'),detail=document.createElement('span');
        title.textContent=job.prompt;detail.textContent=job.error||job.progress||labels[job.status];description.append(title,detail);row.append(description);
        const active=['queued','running','retry'].includes(job.status);
        if(active||job.status==='completed'){
          const button=document.createElement('button');button.type='button';button.textContent=active?'Отменить':['file_index','file_ocr'].includes(job.kind)?'Открыть документ':'Открыть ответ';button.disabled=!!job.cancel_requested;
          button.onclick=async()=>{button.disabled=true;try{
            if(active){const cancelled=await api('/assistant/jobs/'+encodeURIComponent(job.id),{method:'DELETE'});renderQuota(cancelled.quota);refreshJobs();refreshFile()}
            else if(['file_index','file_ocr'].includes(job.kind)){window.SmetraAssistantContext({entity:'files',id:job.file_id,workspace_id:currentWorkspace,label:job.prompt.replace(/^(Подготовка|Распознавание) · /,'')});window.SmetraAssistant()}
            else{sessionStorage.removeItem('smetra.assistant.context');sessionStorage.setItem('smetra.assistant.conversation',job.conversation_id||'');window.SmetraAssistant()}
          }catch(error){button.disabled=false;notify(error.message)}};row.append(button);
        }
        jobList.append(row);
      });
      if(result.jobs.some(job=>['queued','running','retry'].includes(job.status)))jobPollTimer=setTimeout(refreshJobs,5000);
    }catch{if(jobList.isConnected&&sequence===jobLoadSeq)jobPollTimer=setTimeout(refreshJobs,15000)}
  };
  backgroundButton.onclick=async()=>{
    const text=input.value.trim();if(!text||working||fileBlocking||quota.remaining<1)return;
    const body=JSON.stringify({text,context:context?{entity:context.entity,id:context.id}:null,...(activeConversation?{conversation_id:activeConversation}:{})});
    if(!jobRequest||jobRequest.body!==body)jobRequest={body,key:crypto.randomUUID()};
    working=true;backgroundButton.disabled=true;renderQuota(quota);
    try{const result=await api('/assistant/jobs',{method:'POST',headers:{'Idempotency-Key':jobRequest.key},body});renderQuota(result.quota);input.value='';clearSentDraft(text);resize();jobRequest=null;status.textContent='Задача сохранена. Можно закрыть экран.';refreshJobs()}
    catch(error){notify(error.message)}finally{working=false;backgroundButton.disabled=false;renderQuota(quota)}
  };
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
    messages.innerHTML='<div class="assistant-welcome"><span class="assistant-welcome-line"></span><h2>Что сделаем сегодня?</h2><p>Спросите о сметах и заказах или поручите подготовить изменение. Сохранение всегда остаётся за вами.</p><div class="assistant-suggestions"><button type="button" data-prompt="Какие сметы ожидают согласования?">Что ждёт согласования?</button><button type="button" data-prompt="Помоги составить новую смету. Спроси необходимые детали.">Составить смету</button><button type="button" data-prompt="Покажи поступления и остатки по заказам.">Разобраться в оплатах</button></div></div>';
    messages.querySelectorAll('[data-prompt]').forEach(button=>button.onclick=()=>{input.value=button.dataset.prompt;saveDraft();input.focus();resize()});
  }
  thread.messages.forEach(message=>addMessage(message.role,message.content,message.id));
  data.actions.forEach(addAction);
  (data.recent_actions||[]).forEach(action=>{const item=document.createElement('section');item.className='assistant-proposal assistant-saved';actions.append(item);renderSavedAction(item,action,true)});
  if(!data.available)status.textContent='Ассистент пока не подключён.';
  else if(quota.remaining<1)status.textContent='Лимит сообщений на этот месяц исчерпан.';
  const resize=()=>{input.style.height='auto';input.style.height=Math.min(input.scrollHeight,180)+'px'};
  input.addEventListener('input',()=>{resize();saveDraft()});resize();
  input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();document.querySelector('#assistant-form').requestSubmit()}});
  document.querySelector('#assistant-form').onsubmit=async event=>{
    event.preventDefault();const prompt=input.value.trim();if(!prompt||working||fileBlocking||quota.remaining<1)return;
    working=true;send.disabled=true;input.disabled=true;stop.hidden=false;requestController=new AbortController();status.textContent='Подключаюсь к модели…';
    messages.querySelector('.assistant-welcome')?.remove();
    const userMessage=addMessage('user',prompt);
    const assistantMessage=addMessage('assistant','');
    assistantMessage.item.classList.add('streaming');
    let generated='',paintPending=false,completed=false;
    const paint=()=>{paintPending=false;assistantMessage.body.innerHTML=assistantMarkdown(generated);scrollBottom()};
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
      assistantMessage.item.classList.remove('streaming');input.value='';clearSentDraft(prompt);resize();
    }catch(error){
      if(error.name==='AbortError'){assistantMessage.item.classList.remove('streaming');if(!generated){assistantMessage.item.remove();userMessage.item.remove()}status.textContent='Ответ остановлен.'}
      else{userMessage.item.remove();assistantMessage.item.remove();status.textContent=error.message}
      try{renderQuota((await api('/assistant')).quota)}catch{}
    }finally{working=false;requestController=null;stop.hidden=true;renderQuota(quota);input.disabled=!data.available||quota.remaining<1;if(!input.disabled)input.focus()}
  };
};
