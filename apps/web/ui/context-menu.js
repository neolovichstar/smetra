/* Target-aware desktop right-click menus for the Smetra cabinet.
   All mutations reuse the source UI's existing authorization / confirmation handlers. */
(() => {
  const icon = name => window.SmetraIcons?.svg(name,16) || '';
  const fine = () => window.matchMedia?.('(pointer:fine)')?.matches !== false;
  let menu=null,focusBefore=null,closeTimer=null,openTimer=null,serial=0;
  const toast = message => { if(typeof notify==='function')notify(message); };
  const copy = async value => {
    try { await navigator.clipboard.writeText(String(value));toast('Скопировано');return true; }
    catch { toast('Не удалось скопировать. Используйте Ctrl+C.');return false; }
  };
  const action = (label,iconName,run,key) => ({label,icon:iconName,run,key});
  const textOf = el => String(el?.textContent || '').trim().replace(/\s+/g,' ').slice(0,160);
  const clickable = (root,selector) => root?.querySelector(selector);
  const trigger = button => { if(button && !button.disabled && button.isConnected) button.click(); };
  const go = section => {
    const button=document.querySelector('#sidebar [data-tab="'+section+'"],.app-nav [data-tab="'+section+'"],[data-tab="'+section+'"]');
    if(button){button.click();return;}
    if(typeof tab!=='undefined' && typeof render==='function'){
      tab=section;history.pushState({},'',location.pathname+location.search+'#'+section);return render();
    }
  };
  const askAbout = async (entity,id,label) => {
    if(!['quotes','clients','projects','documents','files'].includes(entity)||!id)return;
    if(typeof window.SmetraLoadFeature==='function')await window.SmetraLoadFeature('assistant');
    const workspaceId=window.Workspace?.currentWorkspaceId?.()||sessionStorage.getItem('workspace_id')||'';
    if(typeof window.SmetraAssistantContext!=='function')throw Error('Контекст ассистента недоступен');
    window.SmetraAssistantContext({entity,id,label,workspace_id:workspaceId});
    await go('assistant');
  };
  const askText = async value => {
    await go('assistant');
    let field=document.querySelector('#assistant-input');
    for(let i=0;!field&&i<25;i++){
      await new Promise(resolve=>setTimeout(resolve,80));
      field=document.querySelector('#assistant-input');
    }
    if(!field)throw Error('Не удалось открыть поле ассистента');
    field.value=(field.value?field.value+'\n\n':'')+value;
    field.dispatchEvent(new Event('input',{bubbles:true}));field.focus();
  };
  const editable = el => el?.closest?.('input:not([type=checkbox]):not([type=radio]):not([type=file]):not([type=range]):not([type=color]),textarea,[contenteditable=""],[contenteditable="true"]');
  const editableSelection = field => field && typeof field.selectionStart==='number'
    ? String(field.value).slice(field.selectionStart,field.selectionEnd) : pageSelection(field);
  const pageSelection = target => {
    const selection=window.getSelection?.();
    if(!selection || selection.isCollapsed)return '';
    const range=selection.rangeCount ? selection.getRangeAt(0) : null;
    const node=range?.commonAncestorContainer;
    if(!node || !(node===target||node.contains?.(target)||target.contains?.(node)))return '';
    return String(selection).trim().slice(0,3000);
  };
  const nativePaste = async field => {
    try {
      const value=await navigator.clipboard.readText();
      field.focus();
      if(typeof field.setRangeText==='function'){
        field.setRangeText(value,field.selectionStart,field.selectionEnd,'end');
        field.dispatchEvent(new Event('input',{bubbles:true}));
      }else document.execCommand?.('insertText',false,value);
    }catch{toast('Используйте Ctrl+V для вставки');}
  };
  const recordTarget = target => {
    // Only the object under the pointer; do not inspect arbitrary neighbouring records.
    const match=target.closest?.('[data-work="quote"][data-id],[data-work="ask-document"][data-id],[data-work="entity"][data-kind][data-id]');
    if(match){
      const entity=match.dataset.work==='quote'?'quotes':match.dataset.work==='ask-document'?'documents':match.dataset.kind;
      if(['quotes','clients','projects','documents','tasks','leads','catalog'].includes(entity))return {entity,id:match.dataset.id,button:match};
    }
    const row=target.closest?.('.quote-row,.quotes-document-row,.record-line,.kanban-card,.catalog-row,.task-group,.today-action,.agenda-day');
    if(!row)return null;
    const button=row.querySelector('[data-work="quote"][data-id],[data-work="ask-document"][data-id],[data-work="entity"][data-kind][data-id]');
    if(!button)return null;
    const entity=button.dataset.work==='quote'?'quotes':button.dataset.work==='ask-document'?'documents':button.dataset.kind;
    return ['quotes','clients','projects','documents','tasks','leads','catalog'].includes(entity)
      ? {entity,id:button.dataset.id,button} : null;
  };
  const itemName = (target,button) => {
    const source=button?.querySelector('strong')||target.closest?.('.record-line,.quote-row,.kanban-card')?.querySelector('strong')||button;
    return textOf(source)||'Запись';
  };
  const build = target => {
    const field=editable(target);
    if(field){
      const selected=editableSelection(field);
      const list=[];
      if(selected){
        if(!field.readOnly&&!field.disabled)list.push(action('Вырезать','x',async()=>{
          // Clipboard permission can be denied; never delete the text until copy succeeded.
          if(!await copy(selected))return;
          field.focus();
          if(typeof field.setRangeText==='function')field.setRangeText('');
          else document.execCommand?.('delete',false);
          field.dispatchEvent(new Event('input',{bubbles:true}));
        },'Ctrl+X'));
        list.push(action('Копировать','copy',()=>copy(selected),'Ctrl+C'));
        list.push(action('Спросить ИИ о выделенном','sparkle',()=>askText(selected)));
      }
      if(!field.disabled&&!field.readOnly){
        list.push(action('Вставить','file-text',()=>nativePaste(field),'Ctrl+V'));
        list.push(action('Выделить всё','check',()=>{
          field.focus();
          if(field.select)field.select();
          else if(field.isContentEditable){
            const range=document.createRange();range.selectNodeContents(field);
            const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
          }
        },'Ctrl+A'));
      }
      return {heading:'Редактирование',items:list};
    }
    const selected=pageSelection(target);
    if(selected)return {heading:'Выделенный текст',items:[
      action('Копировать выделенное','copy',()=>copy(selected),'Ctrl+C'),
      action('Спросить ассистента','sparkle',()=>askText(selected))
    ]};

    const file=target.closest?.('.vault-file-tile,.vault-image-tile');
    if(file){
      const filename=textOf(file.querySelector('.vault-file-details strong,.vault-image-info strong'))||'Файл';
      const list=[];
      const add=(selector,label,symbol)=>{const button=clickable(file,selector);if(button&&!button.disabled)list.push(action(label,symbol,()=>trigger(button)));};
      add('[data-action="open"]','Открыть','image');
      add('[data-action="ask"]','Спросить ИИ о файле','sparkle');
      add('[data-action="manage"]','Сведения о файле','info');
      const archive=clickable(file,'[data-action="archive"]');
      if(archive)list.push(action(document.querySelector('#vault-root [data-filter="archive"][aria-selected="true"]')?'Восстановить':'В архив','folder',()=>trigger(archive)));
      add('[data-action="delete"]','Удалить…','trash');
      list.push(action('Скопировать название','copy',()=>copy(filename)));
      return {heading:filename,items:list};
    }
    const fileCenter=target.closest?.('.file-center-row');
    if(fileCenter && fileCenter.querySelector('[data-file-open]')){
      const filename=textOf(fileCenter.querySelector('.file-description strong'))||'Файл';
      const list=[];
      for(const [selector,label,symbol] of [
        ['[data-file-open]','Открыть','file-text'],
        ['[data-file-edit]','Редактировать','pencil'],
        ['[data-file-ask]','Спросить ИИ о файле','sparkle'],
        ['[data-file-manage]','Сведения о файле','info']
      ]){
        const button=fileCenter.querySelector(selector);
        if(button)list.push(action(label,symbol,()=>trigger(button)));
      }
      list.push(action('Скопировать название','copy',()=>copy(filename)));
      return {heading:filename,items:list};
    }
    const estimateLine=target.closest?.('.estimate-table tbody tr');
    if(estimateLine){
      const name=textOf(estimateLine.querySelector('td:first-child strong'))||textOf(estimateLine.querySelector('td:first-child'))||'Позиция';
      return {heading:'Позиция сметы · '+name,items:[
        action('Копировать позицию','copy',()=>copy(textOf(estimateLine))),
        action('Спросить ИИ о позиции','sparkle',()=>askText('Проверь эту позицию сметы: '+textOf(estimateLine)))
      ]};
    }
    const syncedFolder=target.closest?.('.premium-folder');
    if(syncedFolder){
      const label=textOf(syncedFolder.querySelector('strong'))||'Папка';
      const remove=syncedFolder.querySelector('[data-premium-disable-folder]');
      const list=[action('Скопировать название','copy',()=>copy(label))];
      if(remove)list.push(action('Убрать из синхронизации…','trash',()=>trigger(remove)));
      return {heading:label,items:list};
    }
    const cloudFolder=target.closest?.('.premium-folder-entry');
    if(cloudFolder){
      const name=textOf(cloudFolder.querySelector('.premium-folder-select'))||'Папка';
      return {heading:name,items:[
        action('Выбрать для синхронизации','check',()=>trigger(cloudFolder.querySelector('.premium-folder-select'))),
        action('Открыть вложенные папки','folder',()=>trigger(cloudFolder.querySelector('.premium-folder-enter'))),
        action('Скопировать название','copy',()=>copy(name.replace(/^▱\s*/,'')))
      ]};
    }
    const cloudFile=target.closest?.('.premium-cloud-file');
    if(cloudFile){
      const filename=textOf(cloudFile.querySelector('.premium-cloud-file-name'))||'Файл';
      return {heading:filename,items:[action('Скопировать название','copy',()=>copy(filename))]};
    }
    const cloudCard=target.closest?.('[data-cloud-card]');
    if(cloudCard){
      const name=textOf(cloudCard.querySelector('.premium-connect-copy strong'))||'Облако';
      const choice=cloudCard.querySelector('[data-premium-select]');
      const link=cloudCard.querySelector('[data-premium-connect],[data-premium-disconnect]');
      const list=[action('Показать папки','folder',()=>trigger(choice))];
      if(link)list.push(action(link.dataset.premiumDisconnect?'Отключить…':'Подключить','link',()=>trigger(link)));
      return {heading:name,items:list};
    }
    const conversation=target.closest?.('.assistant-conversation-row');
    if(conversation){
      const label=textOf(conversation.querySelector('.assistant-conversation-title'))||'Диалог';
      const isGeneral=!conversation.dataset.threadId;
      const list=[action('Открыть диалог','chat',()=>trigger(conversation.querySelector('[data-conversation]')))];
      if(!isGeneral){
        list.push(action('Переименовать','pencil',()=>trigger(conversation.querySelector('[data-thread-rename]'))));
        list.push(action(conversation.dataset.pinned==='1'?'Открепить':'Закрепить','pin',()=>trigger(conversation.querySelector('[data-thread-pin]'))));
      }
      const del=conversation.querySelector('[data-thread-delete]');
      if(del)list.push(action('Удалить диалог…','trash',()=>trigger(del)));
      return {heading:label,items:list};
    }
    const message=target.closest?.('.assistant-message,.tg-msg');
    if(message){
      const txt=textOf(message.querySelector('.assistant-markdown,.tg-text')||message);
      const content=String((message.querySelector('.assistant-markdown,.tg-text')||message).innerText||txt).trim();
      const list=[];
      if(content){list.push(action('Копировать сообщение','copy',()=>copy(content)));
        list.push(action('Ответить с помощью ИИ','sparkle',()=>askText(content.slice(0,3000))));}
      return {heading:'Сообщение',items:list};
    }
    const documentRow=target.closest?.('.document-row');
    if(documentRow){
      const label=textOf(documentRow.querySelector('strong'))||'Документ';
      const ask=documentRow.querySelector('[data-work="ask-document"]');
      const pdf=documentRow.querySelector('[data-work="download-document"]');
      const list=[];
      if(pdf)list.push(action('Скачать PDF','download',()=>trigger(pdf)));
      if(ask)list.push(action('Спросить ИИ о документе','sparkle',()=>trigger(ask)));
      list.push(action('Скопировать название','copy',()=>copy(label)));
      return {heading:'Документ · '+label,items:list};
    }
    const entity=recordTarget(target);
    if(entity){
      const name=itemName(target,entity.button);
      const titles={quotes:'Смета',clients:'Клиент',projects:'Проект',documents:'Документ',tasks:'Задача',leads:'Лид',catalog:'Расценка'};
      const list=[action('Открыть','arrow-up-right',()=>trigger(entity.button))];
      if(['quotes','clients','projects'].includes(entity.entity))
        list.push(action('Спросить ИИ об этом','sparkle',()=>askAbout(entity.entity,entity.id,name)));
      const row=entity.button.closest('.record-line');
      if(entity.entity==='tasks'){
        const toggle=row?.querySelector('[data-work="task-toggle"]');
        if(toggle)list.push(action(toggle.getAttribute('aria-checked')==='true'?'Вернуть в работу':'Отметить выполненной','check',()=>trigger(toggle)));
      }
      if(entity.entity==='catalog'){
        const favorite=row?.querySelector('[data-work="catalog-favorite"]');
        if(favorite)list.push(action(favorite.getAttribute('aria-pressed')==='true'?'Убрать из избранного':'В избранное','pin',()=>trigger(favorite)));
      }
      list.push(action('Скопировать название','copy',()=>copy(name)));
      return {heading:(titles[entity.entity]||'Запись')+' · '+name,items:list};
    }
    const link=target.closest?.('a[href]');
    if(link){
      const href=link.href;
      if(!/^https?:/.test(href))return null;
      return {heading:'Ссылка',items:[
        action('Открыть в новой вкладке','arrow-up-right',()=>window.open(href,'_blank','noopener,noreferrer')),
        action('Скопировать адрес','link',()=>copy(href))
      ]};
    }
    const nav=target.closest?.('[data-tab]');
    if(nav && nav.dataset.tab){
      const label=textOf(nav)||nav.dataset.tab;
      return {heading:label,items:[action('Открыть раздел','arrow-up-right',()=>trigger(nav))]};
    }
    const newQuote=target.closest?.('#records,.workspace-home,.workspace-main,#content')?.querySelector('[data-work="quote-new"]');
    if(typeof tab!=='undefined' && tab==='quotes' && newQuote)return {heading:'Сметы',items:[
      action('Создать смету','plus',()=>trigger(newQuote)),
      action('Поиск','search',()=>trigger(document.querySelector('#command-open')),'Ctrl+K')
    ]};
    // No generic commands over every element: right-click on blank areas
    // should not invent a relationship with an unrelated object.
    return {heading:'Рабочее пространство',items:[
      action('Поиск по Сметре','search',()=>trigger(document.querySelector('#command-open')),'Ctrl+K')
    ]};
  };

  const close = (restore=true) => {
    if(!menu)return;
    const node=menu;menu=null;serial++;
    clearTimeout(openTimer);clearTimeout(closeTimer);
    document.removeEventListener('pointerdown',outside,true);
    window.removeEventListener('blur',blurClose);
    window.removeEventListener('resize',blurClose);
    document.removeEventListener('scroll',blurClose,true);
    if(node.matches?.(':popover-open'))try{node.hidePopover();}catch{}
    node.remove();
    if(restore&&focusBefore?.isConnected)focusBefore.focus?.({preventScroll:true});
  };
  const outside=event=>{if(menu && !menu.contains(event.target))close(false)};
  const blurClose=()=>close(false);
  const open=(event,group)=>{
    close(false);
    if(!group?.items?.length)return;
    focusBefore=document.activeElement;
    menu=document.createElement('div');menu.className='sm-context';menu.setAttribute('role','menu');
    menu.setAttribute('aria-label',group.heading||'Действия');
    const heading=document.createElement('div');heading.className='sm-context-heading';heading.textContent=group.heading||'Действия';
    menu.append(heading);
    for(const entry of group.items.slice(0,6)){
      const button=document.createElement('button');button.type='button';button.className='sm-context-item';button.setAttribute('role','menuitem');button.tabIndex=-1;
      const symbol=document.createElement('span');symbol.className='sm-context-symbol';symbol.innerHTML=icon(entry.icon);
      const name=document.createElement('span');name.textContent=entry.label;button.append(symbol,name);
      if(entry.key){const kbd=document.createElement('kbd');kbd.textContent=entry.key;button.append(kbd);}
      button.addEventListener('click',()=>{close(false);try{Promise.resolve(entry.run()).catch(error=>toast(error?.message||'Не удалось выполнить действие'))}catch(error){toast(error?.message||'Не удалось выполнить действие')}});
      menu.append(button);
    }
    document.body.append(menu);
    if(typeof menu.showPopover==='function'){
      menu.setAttribute('popover','manual');
      try{menu.showPopover()}catch{}
    }
    const rect=menu.getBoundingClientRect(),margin=8;
    menu.style.left=Math.max(margin,Math.min(event.clientX,innerWidth-rect.width-margin))+'px';
    menu.style.top=Math.max(margin,Math.min(event.clientY,innerHeight-rect.height-margin))+'px';
    menu.querySelector('.sm-context-item')?.focus({preventScroll:true});
    menu.addEventListener('keydown',event=>{
      const buttons=[...menu.querySelectorAll('.sm-context-item')],i=buttons.indexOf(document.activeElement);
      if(event.key==='Escape'){event.preventDefault();close();}
      else if(event.key==='ArrowDown'||event.key==='ArrowUp'){
        event.preventDefault();buttons[(i+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();
      }else if(event.key==='Home'||event.key==='End'){
        event.preventDefault();buttons[event.key==='Home'?0:buttons.length-1]?.focus();
      }else if(event.key==='Tab'){close(false);}
    });
    const token=serial;
    openTimer=setTimeout(()=>{
      if(!menu||serial!==token)return;
      document.addEventListener('pointerdown',outside,true);
      window.addEventListener('blur',blurClose);
      window.addEventListener('resize',blurClose);
      document.addEventListener('scroll',blurClose,true);
    },0);
  };
  document.addEventListener('contextmenu',event=>{
    if(event.shiftKey||!fine()||event.defaultPrevented)return;
    const target=event.target instanceof Element?event.target:event.target?.parentElement;
    if(!target||target.closest('.sm-context,[data-native-context],input[type=password],input[type=hidden]'))return;
    if(!target.closest('#shell,.app-nav,#communication-center,dialog[open]'))return;
    const group=build(target);
    if(!group?.items?.length)return;
    event.preventDefault();
    open(event,group);
  });
  window.SmetraContextMenu=Object.freeze({close,describe:build});
})();