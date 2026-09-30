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
};

window.SmetraAssistant=async function(){
  const data=await api('/assistant');
  view(`<section class="assistant-page"><header class="assistant-header"><div><span class="overline"><span class="assistant-mark"></span>Сметра рядом</span><h1>Ассистент</h1></div><span id="assistant-quota" class="assistant-quota"></span></header><div id="assistant-messages" class="assistant-thread" role="log" aria-live="off"></div><div id="assistant-actions"></div><div class="assistant-composer"><div id="assistant-context" class="assistant-context hidden"><span>Контекст</span><strong id="assistant-context-label"></strong><button id="assistant-context-remove" type="button" aria-label="Убрать контекст">×</button></div><form id="assistant-form"><label class="visually-hidden" for="assistant-input">Сообщение ассистенту</label><textarea id="assistant-input" placeholder="Спросите или поручите задачу…" rows="1" maxlength="3000" required></textarea><button class="btn primary" id="assistant-send" type="submit" aria-label="Отправить сообщение">↗</button></form><div class="assistant-composer-foot"><span id="assistant-status" role="status"></span><span>Enter — отправить · Shift+Enter — новая строка</span></div><a id="assistant-upgrade" class="assistant-upgrade hidden" href="/app#billing">Лимит исчерпан. Посмотреть тариф Про ↗</a></div></section>`);
  const messages=document.querySelector('#assistant-messages');
  const actions=document.querySelector('#assistant-actions');
  const input=document.querySelector('#assistant-input');
  const send=document.querySelector('#assistant-send');
  const status=document.querySelector('#assistant-status');
  const quotaLabel=document.querySelector('#assistant-quota');
  const upgrade=document.querySelector('#assistant-upgrade');
  let context=null;
  try{context=JSON.parse(sessionStorage.getItem('smetra.assistant.context')||'null')}catch{}
  const currentWorkspace=window.Workspace?.currentWorkspaceId?.();
  if(context&&(!['clients','quotes','projects','files'].includes(context.entity)||typeof context.id!=='string'||currentWorkspace&&context.workspace_id!==currentWorkspace))context=null;
  const contextBar=document.querySelector('#assistant-context');
  const renderContext=()=>{
    contextBar.classList.toggle('hidden',!context);
    if(context)document.querySelector('#assistant-context-label').textContent=({clients:'Клиент',quotes:'Смета',projects:'Заказ',files:'Файл'})[context.entity]+': '+(context.label||context.id);
    else sessionStorage.removeItem('smetra.assistant.context');
  };
  renderContext();
  document.querySelector('#assistant-context-remove').onclick=()=>{context=null;renderContext();input.focus()};
  let quota=data.quota,working=false;
  const renderQuota=value=>{
    quota=value;
    quotaLabel.textContent=`${value.remaining} из ${value.limit} сообщений · ${value.plan==='free'?'Старт':'Про'}`;
    quotaLabel.title=`Лимит обновится ${new Date(value.resets_at*1000).toLocaleDateString('ru-RU')}`;
    upgrade.classList.toggle('hidden',value.remaining>0||value.plan==='pro');
    send.disabled=working||!data.available||value.remaining<1;
    input.disabled=!data.available||value.remaining<1;
  };
  const scrollBottom=()=>{if(window.innerHeight+window.scrollY>=document.documentElement.scrollHeight-260)window.scrollTo({top:document.documentElement.scrollHeight,behavior:'instant'})};
  const addMessage=(role,text)=>{
    const item=document.createElement('article');item.className='assistant-message '+role;
    const label=document.createElement('small');label.textContent=role==='user'?'ВЫ':'СМЕТРА';
    const body=document.createElement('div');body.className='assistant-markdown';
    body.innerHTML=assistantMarkdown(text);
    item.append(label,body);
    if(role==='assistant'){
      const copy=document.createElement('button');copy.type='button';copy.className='assistant-copy';copy.textContent='Копировать';copy.onclick=async()=>{await navigator.clipboard.writeText(body.innerText);copy.textContent='Скопировано';setTimeout(()=>copy.textContent='Копировать',1800)};
      item.append(copy);
    }
    messages.append(item);return {item,body};
  };
  const addAction=action=>{
    const item=document.createElement('section');item.className='assistant-proposal';
    item.innerHTML=`<span class="overline">Предложение · ещё не сохранено</span><h3>${escapeHtml(action.summary)}</h3><div class="proposal-fields">${proposalFields(action.arguments)}</div><div class="row"><button class="btn primary" data-confirm>Применить</button><button class="btn ghost" data-dismiss>Не сейчас</button></div>`;
    actions.append(item);
    item.querySelector('[data-confirm]').onclick=async()=>{const buttons=item.querySelectorAll('button');buttons.forEach(button=>button.disabled=true);try{await api('/assistant/confirm',{method:'POST',body:JSON.stringify({id:action.id})});item.replaceChildren();const result=document.createElement('p');result.textContent='Сохранено · '+action.summary;item.append(result);notify('Изменения сохранены')}catch(error){notify(error.message);buttons.forEach(button=>button.disabled=false)}};
    item.querySelector('[data-dismiss]').onclick=async()=>{try{await api('/assistant/dismiss',{method:'POST',body:JSON.stringify({id:action.id})});item.remove()}catch(error){notify(error.message)}};
  };
  renderQuota(quota);
  if(!data.messages.length){
    messages.innerHTML='<div class="assistant-welcome"><span class="assistant-welcome-line"></span><h2>Что сделаем сегодня?</h2><p>Спросите о сметах и заказах или поручите подготовить изменение. Сохранение всегда остаётся за вами.</p><div class="assistant-suggestions"><button type="button" data-prompt="Какие сметы ожидают согласования?">Что ждёт согласования?</button><button type="button" data-prompt="Помоги составить новую смету. Спроси необходимые детали.">Составить смету</button><button type="button" data-prompt="Покажи поступления и остатки по заказам.">Разобраться в оплатах</button></div></div>';
    messages.querySelectorAll('[data-prompt]').forEach(button=>button.onclick=()=>{input.value=button.dataset.prompt;input.focus();resize()});
  }
  data.messages.forEach(message=>addMessage(message.role,message.content));
  data.actions.forEach(addAction);
  if(!data.available)status.textContent='Ассистент пока не подключён.';
  else if(quota.remaining<1)status.textContent='Лимит сообщений на этот месяц исчерпан.';
  const resize=()=>{input.style.height='auto';input.style.height=Math.min(input.scrollHeight,180)+'px'};
  input.addEventListener('input',resize);
  input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();document.querySelector('#assistant-form').requestSubmit()}});
  document.querySelector('#assistant-form').onsubmit=async event=>{
    event.preventDefault();const prompt=input.value.trim();if(!prompt||working||quota.remaining<1)return;
    working=true;send.disabled=true;input.disabled=true;status.textContent='Подключаюсь к модели…';
    messages.querySelector('.assistant-welcome')?.remove();
    const userMessage=addMessage('user',prompt);
    const assistantMessage=addMessage('assistant','');
    assistantMessage.item.classList.add('streaming');
    let generated='',paintPending=false,completed=false;
    const paint=()=>{paintPending=false;assistantMessage.body.innerHTML=assistantMarkdown(generated);scrollBottom()};
    const schedule=()=>{if(!paintPending){paintPending=true;requestAnimationFrame(paint)}};
    try{
      const response=await fetch('/api/assistant/stream',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json',...(sessionStorage.getItem('workspace_id')?{'X-Workspace-Id':sessionStorage.getItem('workspace_id')}:{})},body:JSON.stringify({text:prompt,...(context?{context:{entity:context.entity,id:context.id}}:{})})});
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
        if(kind==='done'){generated=payload.answer;paint();payload.actions.forEach(addAction);renderQuota(payload.quota);completed=true;status.textContent=''}
        if(kind==='error'){renderQuota(payload.quota);throw Error(payload.error)}
      };
      while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let match;while((match=buffer.match(/\r?\n\r?\n/))){const block=buffer.slice(0,match.index);buffer=buffer.slice(match.index+match[0].length);eventBlock(block)}}
      if(!completed)throw Error('Ответ оборвался. Попробуйте ещё раз.');
      assistantMessage.item.classList.remove('streaming');input.value='';resize();
    }catch(error){
      userMessage.item.remove();assistantMessage.item.remove();
      status.textContent=error.message;
      try{renderQuota((await api('/assistant')).quota)}catch{}
    }finally{working=false;renderQuota(quota);input.disabled=!data.available||quota.remaining<1;if(!input.disabled)input.focus()}
  };
};
