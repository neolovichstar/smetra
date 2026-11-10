/* Smetra quote visualization core — server-sourced monetary values only.
 * Preview calculations must NEVER infer quote totals from LLM output. */
(() => {
  'use strict';
  const doc = document;
  const el = (tag, className, text) => {
    const node = doc.createElement(tag);
    if(className) node.className = className;
    if(text !== undefined) node.textContent = String(text);
    return node;
  };
  const money = (kopecks, currency='RUB') => {
    const n = Number(kopecks);
    if (!Number.isSafeInteger(n)) return '—';
    try { return new Intl.NumberFormat('ru-RU', {style:'currency', currency}).format(n/100); }
    catch { return (n/100).toLocaleString('ru-RU') + ' ' + currency; }
  };
  const groupName = item => String(item.category||'Без раздела').trim().slice(0,80)||'Без раздела';
  const serverAmounts = items => {
    const groups = new Map();
    let total=0;
    for(const item of Array.isArray(items)?items:[]){
      // Only values returned by the server's calculate()/quote_view() may be charted.
      if(!item || item.included === false)continue;
      const amount=item.subtotal;
      if(!Number.isSafeInteger(amount) || amount<0)continue;
      const category=groupName(item);
      groups.set(category,(groups.get(category)||0)+amount);
      total+=amount;
    }
    return {groups:[...groups].sort((a,b)=>b[1]-a[1]), total};
  };
  const breakdown = (items,currency)=>{
    const node=el('section','smetra-visual-breakdown');
    const head=el('div','smetra-visual-heading');
    head.append(el('strong','','Структура стоимости'),el('small','','По рассчитанным позициям'));node.append(head);
    const data=serverAmounts(items);
    if(!data.groups.length){
      node.append(el('p','smetra-visual-empty','Для диаграммы нужны позиции с рассчитанной стоимостью.'));
      return node;
    }
    const bars=el('div','smetra-visual-bars');
    for(const [name,value] of data.groups.slice(0,10)){
      const row=el('div','smetra-visual-bar-row');
      const label=el('div','smetra-visual-bar-label');
      label.append(el('span','',name),el('span','',money(value,currency)));
      const track=el('div','smetra-visual-bar-track');
      const fill=el('span','smetra-visual-bar-fill');
      fill.style.width=(data.total>0?Math.min(100,value/data.total*100):0).toFixed(2)+'%';
      fill.setAttribute('aria-hidden','true');track.append(fill);
      row.append(label,track);bars.append(row);
    }
    node.append(bars);
    const footer=el('p','smetra-visual-footnote','Распределение по позициям с указанной стоимостью. Позиции без цены в диаграмму не включены.');
    node.append(footer);return node;
  };
  const svgNode=(tag,attrs={},text)=>{
    const node=doc.createElementNS('http://www.w3.org/2000/svg',tag);
    for(const [key,value] of Object.entries(attrs))node.setAttribute(key,String(value));
    if(text!==undefined)node.textContent=String(text);
    return node;
  };
  const roomDiagram=zone=>{
    const name=String(zone?.name||'Помещение').slice(0,100);
    const length=Number(zone?.length_m), width=Number(zone?.width_m);
    if(!(length>0&&width>0&&Number.isFinite(length)&&Number.isFinite(width)))return null;
    const tile=el('figure','smetra-room-card');
    const cap=el('figcaption','smetra-room-caption');
    const format=value=>Number(value).toLocaleString('ru-RU',{maximumFractionDigits:3});
    cap.append(el('strong','',name),el('span','',format(length*width)+' м²'));tile.append(cap);
    const svg=svgNode('svg',{viewBox:'0 0 270 170',role:'img','aria-label':name+', '+format(length)+' на '+format(width)+' метров',preserveAspectRatio:'xMidYMid meet'});
    const ratio=length/width;
    let w,h;
    if(ratio>1){w=174;h=Math.max(34,Math.min(108,w/ratio))}
    else{h=108;w=Math.max(34,Math.min(174,h*ratio))}
    const x=135-w/2,y=78-h/2;
    svg.append(svgNode('rect',{x,y,width:w,height:h,rx:2,fill:'var(--smetra-visual-room)',stroke:'var(--smetra-visual-outline)','stroke-width':2}));
    svg.append(svgNode('path',{d:`M ${x} 139 H ${x+w}`,stroke:'var(--smetra-visual-muted)','stroke-width':1}));
    svg.append(svgNode('text',{x:135,y:153,'text-anchor':'middle',fill:'currentColor','font-size':11},format(length)+' м'));
    svg.append(svgNode('text',{x:20,y:82,fill:'currentColor','font-size':11,'text-anchor':'middle',transform:'rotate(-90 20 82)'},format(width)+' м'));
    tile.append(svg);return tile;
  };
  const mountRooms=(container,zones)=>{
    if(!container)return;
    const list=(Array.isArray(zones)?zones:[]).map(roomDiagram).filter(Boolean).slice(0,18);
    container.replaceChildren();
    if(!list.length)return;
    const wrap=el('section','smetra-room-visuals');
    const heading=el('div','smetra-room-header');
    heading.append(el('h3','','Графическая смета · помещения'),el('small','','Размеры указаны в метрах'));
    wrap.append(heading);
    const cards=el('div','smetra-room-grid');list.forEach(node=>cards.append(node));wrap.append(cards);
    wrap.append(el('p','smetra-visual-footnote','Пропорции каждого помещения соблюдены. Расположение помещений условное — это не архитектурный план.'));
    container.append(wrap);
  };

  function mountAssistant({host,fetchQuote,onOpenEditor,getUserId,listQuotes,onToggle}){
    if(!host||typeof fetchQuote!=='function')throw Error('Quote preview requires an authorized quote fetcher');
    const panel=el('aside','smetra-quote-preview');
    panel.id='smetra-quote-preview';
    panel.setAttribute('aria-label','Предпросмотр сметы');
    panel.setAttribute('aria-hidden','true');
    panel.hidden=true;
    const header=el('header','smetra-quote-preview-header');
    const titleWrap=el('div','smetra-quote-preview-heading');
    const heading=el('h2','','Смета'),kicker=el('small','','Предпросмотр');
    titleWrap.append(kicker,heading);
    const close=el('button','smetra-quote-preview-close icon-button');close.innerHTML=window.SmetraIcons?window.SmetraIcons.svg('x',18):'×';
    close.type='button';close.setAttribute('aria-label','Закрыть предпросмотр');
    close.onclick=()=>setOpen(false);
    // «К списку» brings back the picker without closing the panel.
    const back=el('button','smetra-quote-preview-back icon-button');back.innerHTML=window.SmetraIcons?window.SmetraIcons.svg('arrow-left',18):'←';
    back.type='button';back.setAttribute('aria-label','К списку смет');back.title='К списку смет';back.hidden=true;
    back.onclick=()=>{closeAppearance(false);seq++;loading=false;current=null;pending=null;render()};
    const expand=el('button','smetra-quote-preview-expand icon-button');expand.type='button';
    expand.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>';
    expand.setAttribute('aria-label','Развернуть редактор');expand.title='Развернуть';expand.setAttribute('aria-pressed','false');
    header.append(back,titleWrap,expand,close);panel.append(header);
    // Desktop: drag the left edge to share space between chat and estimate.
    const grip=el('div','smetra-quote-preview-grip');grip.setAttribute('role','separator');grip.setAttribute('aria-orientation','vertical');
    grip.setAttribute('aria-label','Ширина редактора сметы');grip.tabIndex=0;panel.append(grip);
    const content=el('div','smetra-quote-preview-content');panel.append(content);
    const hostRoot=host.closest('.assistant-studio');
    host.append(panel);
    const WIDTH_KEY='smetra.preview.width';
    const applyWidth=px=>{if(!hostRoot)return px;const max=Math.max(360,(hostRoot.clientWidth||window.innerWidth)*.68);const value=Math.round(Math.min(max,Math.max(340,px)));hostRoot.style.setProperty('--preview-saved-w',value+'px');grip.setAttribute('aria-valuenow',String(value));return value};
    try{const saved=Number(localStorage.getItem(WIDTH_KEY));if(saved>0)applyWidth(saved)}catch{}
    grip.addEventListener('pointerdown',event=>{
      if(event.button!==0||!hostRoot)return;event.preventDefault();grip.setPointerCapture(event.pointerId);hostRoot.classList.add('is-resizing');
      const right=hostRoot.getBoundingClientRect().right;
      const move=e=>applyWidth(right-e.clientX);
      const up=e=>{grip.releasePointerCapture(e.pointerId);hostRoot.classList.remove('is-resizing');grip.removeEventListener('pointermove',move);grip.removeEventListener('pointerup',up);try{localStorage.setItem(WIDTH_KEY,String(applyWidth(right-e.clientX)))}catch{}};
      grip.addEventListener('pointermove',move);grip.addEventListener('pointerup',up);
    });
    grip.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();const now=panel.getBoundingClientRect().width;const value=applyWidth(now+(event.key==='ArrowLeft'?32:-32));try{localStorage.setItem(WIDTH_KEY,String(value))}catch{}});
    grip.addEventListener('dblclick',()=>{hostRoot?.style.removeProperty('--preview-saved-w');try{localStorage.removeItem(WIDTH_KEY)}catch{}});
    expand.onclick=()=>{const wide=!hostRoot?.classList.contains('is-preview-wide');hostRoot?.classList.toggle('is-preview-wide',wide);expand.setAttribute('aria-pressed',String(wide));expand.setAttribute('aria-label',wide?'Свернуть редактор':'Развернуть редактор');expand.title=wide?'Свернуть':'Развернуть'};
    let current=null,pending=null,visible=false,seq=0,loading=false,pickSeq=0;
    // New-estimate mode: an empty editor waits for the assistant; draft holds a
    // server-validated create_quotes proposal (sections and totals computed by the server).
    let mode=null,draft=null,progressText='',statusLine=null;
    const storageSpace=()=>sessionStorage.getItem('workspace_id')||'';
    const storageUser=()=>typeof getUserId==='function'?String(getUserId()||''):'';
    let layout=null,currentContext=null,documentNode=null,appearanceDialog=null,appearancePreview=null,appearanceOwner=null,appearanceGuard=null;
    const appearanceActive=()=>appearanceOwner&&visible&&!loading&&host.isConnected&&current===appearanceOwner.quote&&storageSpace()===appearanceOwner.space&&storageUser()===appearanceOwner.user;
    function closeAppearance(restoreFocus=true){
      const dialog=appearanceDialog;if(!dialog)return;
      appearanceDialog=null;appearancePreview=null;appearanceOwner=null;
      appearanceGuard?.disconnect();appearanceGuard=null;
      if(dialog.open)dialog.close();dialog.remove();
      if(restoreFocus&&visible)content.querySelector('.smetra-quote-preview-tune')?.focus({preventScroll:true});
    }
    function paintAppearance(){
      if(!appearanceDialog)return;
      if(!appearanceActive()){closeAppearance(false);return}
      appearancePreview.replaceChildren(window.SmetraQuoteLayout.render({quote:current,layout,pending}));
    }
    function openAppearance(){
      if(!visible||!host.isConnected||!current||loading||!window.SmetraQuoteLayout||currentContext?.user!==storageUser()||currentContext?.space!==storageSpace())return;
      if(appearanceDialog?.open){appearanceDialog.querySelector('button')?.focus();return}
      appearanceOwner={quote:current,space:storageSpace(),user:storageUser()};
      const dialog=el('dialog','smetra-appearance-dialog');appearanceDialog=dialog;
      dialog.setAttribute('aria-label','Оформление сметы');
      const top=el('header','smetra-appearance-header');
      const label=el('div');label.append(el('h2','','Оформление сметы'),el('p','',current.title||'Смета'));
      const done=el('button','smetra-appearance-close icon-button');done.type='button';done.autofocus=true;
      done.setAttribute('aria-label','Закрыть настройки оформления');done.textContent='×';done.onclick=()=>closeAppearance();
      top.append(label,done);
      const body=el('div','smetra-appearance-body');
      const preview=el('section','smetra-appearance-preview');preview.setAttribute('aria-label','Предпросмотр документа');
      appearancePreview=preview;
      const aside=el('aside','smetra-appearance-settings');aside.setAttribute('aria-label','Настройки оформления');
      const saveState=el('p','smetra-appearance-save-state','Изменения сохраняются автоматически');saveState.setAttribute('role','status');
      const controls=el('div','smetra-appearance-controls');aside.append(controls,saveState);body.append(preview,aside);dialog.append(top,body);
      window.SmetraQuoteLayout.configure({container:controls,value:layout,onChange:newLayout=>{
        if(!appearanceActive()){closeAppearance(false);return}
        layout=newLayout;
        const saved=window.SmetraQuoteLayout.save(appearanceOwner.space,appearanceOwner.user,current.id,layout);
        const next=window.SmetraQuoteLayout.render({quote:current,layout,pending});
        if(documentNode?.isConnected)documentNode.replaceWith(next);documentNode=next;
        paintAppearance();
        saveState.textContent=saved?'Изменения сохранены':'Предпросмотр обновлён. Не удалось сохранить оформление на устройстве.';
      }});
      dialog.addEventListener('cancel',event=>{event.preventDefault();closeAppearance()});
      dialog.addEventListener('close',()=>{if(appearanceDialog===dialog)closeAppearance()});
      dialog.addEventListener('click',event=>{
        if(event.target!==dialog)return;
        const box=dialog.getBoundingClientRect();
        if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)closeAppearance();
      });
      doc.body.append(dialog);paintAppearance();dialog.showModal();
      appearanceGuard=new MutationObserver(()=>{if(!appearanceActive())closeAppearance(false)});
      appearanceGuard.observe(doc.body,{childList:true,subtree:true});
    }
    const themeObserver=new MutationObserver(()=>{
      if(visible && (!layout || layout.appearance==='auto') && current)render();
    });
    themeObserver.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
    const render=()=>{
      if(!visible)return;
      content.replaceChildren();
      back.hidden=!current||typeof listQuotes!=='function';
      statusLine=null;
      if(draft){renderDraft();return}
      if(mode==='new'&&!current){renderNew();return}
      const listing=!current&&!loading&&typeof listQuotes==='function';
      kicker.hidden=false;
      heading.textContent=listing?'Сметы':'Смета';kicker.textContent=listing?'Выберите для предпросмотра':'Предпросмотр';
      if(!current){if(!loading)picker();return}
      const quote=current;
      if(!layout)layout=window.SmetraQuoteLayout?.load(storageSpace(),storageUser(),quote.id);
      const title=el('div','smetra-quote-preview-title');
      title.append(el('h3','',quote.title||'Смета'),el('span','smetra-quote-preview-state',pending?'Есть предложение ИИ':quote.approval_state==='draft'?'Черновик · сохранено':'Только просмотр'));
      if(pending)content.append(el('p','smetra-quote-preview-pending','Ниже показан вариант с изменениями ассистента. Итог пересчитан сервером; в смету он попадёт только после «Применить» в чате.'));
      content.append(title);
      const bar=el('div','smetra-quote-preview-controls');
      const tune=el('button','smetra-quote-preview-tune','Настроить вид');
      tune.type='button';tune.setAttribute('aria-haspopup','dialog');
      tune.onclick=openAppearance;
      bar.append(tune);content.append(bar);
      documentNode=window.SmetraQuoteLayout?.render({quote,layout,pending})||el('p','','Предпросмотр пока недоступен.');
      content.append(documentNode);paintAppearance();
      const foot=el('div','smetra-quote-preview-actions');
      const edit=el('button','smetra-quote-open-editor','Открыть полный редактор');
      edit.type='button';edit.onclick=()=>{if(quote.id)onOpenEditor?.(quote.id)};
      foot.append(edit);
      if(pending)foot.append(el('p','smetra-visual-footnote','Предложения по позициям применяются только после подтверждения в чате.'));
      content.append(foot);
    };
    const status=()=>{statusLine=el('p','smetra-draft-status');statusLine.setAttribute('role','status');statusLine.setAttribute('aria-live','polite');paintStatus();return statusLine};
    const paintStatus=()=>{if(!statusLine)return;statusLine.textContent=progressText;statusLine.hidden=!progressText;statusLine.classList.toggle('is-working',Boolean(progressText))};
    const renderNew=()=>{
      // Keep the workspace panel ready for the real AI draft, without a fake
      // empty document or canned example prompts. Progress is displayed only
      // when the assistant starts working.
      heading.textContent='Новая смета';
      kicker.textContent='';
      kicker.hidden=true;
      content.append(status());
    };
    const renderDraft=()=>{
      const p=draft.preview||{},currency=p.currency||'RUB',counts=p.counts||{};
      heading.textContent=p.title||'Новая смета';kicker.textContent='Черновик ИИ';kicker.hidden=false;
      const title=el('div','smetra-quote-preview-title');
      title.append(el('h3','',p.title||'Смета'),el('span','smetra-quote-preview-state','Ждёт подтверждения в чате'));
      content.append(title,status());
      content.append(el('p','smetra-draft-meta',[`${counts.lines||0} поз.`,`работы ${counts.works||0}`,`материалы ${counts.materials||0}`,p.region?'регион: '+p.region:''].filter(Boolean).join(' · ')));
      if(counts.estimated||counts.unknown){
        const warn=el('p','smetra-draft-warning');
        warn.textContent=[counts.estimated?`ориентировочных цен: ${counts.estimated}`:'',counts.unknown?`без цены: ${counts.unknown}`:''].filter(Boolean).join(', ')+' — проверьте перед отправкой клиенту.';
        content.append(warn);
      }
      (Array.isArray(p.sections)?p.sections:[]).forEach(section=>{
        const block=el('section','smetra-draft-section');
        const head=el('header','smetra-draft-section-head');head.append(el('h4','',section.name||'Раздел'),el('span','',money(section.subtotal,currency)));
        block.append(head);
        const rows=el('ol','smetra-draft-rows');
        (section.rows||[]).forEach(row=>{
          const li=el('li','smetra-draft-row'+(row.price_status==='unknown'?' is-unknown':''));
          const name=el('div','smetra-draft-name');name.append(el('strong','',row.name));
          const tags=el('span','smetra-draft-tags');
          if(row.kind==='material')tags.append(el('span','smetra-draft-tag','материал'));
          if(row.price_status==='estimate')tags.append(el('span','smetra-draft-tag is-estimate','оценка'));
          if(row.price_status==='unknown')tags.append(el('span','smetra-draft-tag is-unknown','нет цены'));
          if(tags.children.length)name.append(tags);
          li.append(name,el('span','smetra-draft-qty',`${String(row.quantity).replace('.',',')} ${row.unit} × ${money(row.unit_price,currency)}`),el('b','smetra-draft-sum',money(row.subtotal,currency)));
          rows.append(li);
        });
        block.append(rows);content.append(block);
      });
      if(Array.isArray(p.assumptions)&&p.assumptions.length){
        const box=el('details','smetra-draft-assumptions');box.open=true;box.append(el('summary','','Допущения ИИ · '+p.assumptions.length));
        const list=el('ul');p.assumptions.forEach(text=>list.append(el('li','',text)));box.append(list);content.append(box);
      }
      const total=el('div','smetra-draft-total');total.append(el('span','','Итого · рассчитано сервером'),el('strong','',money(p.total,currency)));
      content.append(total);
      content.append(el('p','smetra-visual-footnote','Смета сохранится после «Применить» в чате. Потом её можно править вручную — без токенов.'));
    };
    // Without a selected quote the panel lists recent ones; the server keeps
    // totals, so the list only shows what the quote endpoint returned.
    const picker=async()=>{
      if(typeof listQuotes!=='function'){content.append(el('p','smetra-visual-empty','Выберите смету для живого предпросмотра.'));return}
      const request=++pickSeq;
      content.replaceChildren(el('p','smetra-visual-empty','Загружаю сметы…'));
      try{
        const items=(await listQuotes())||[];
        if(request!==pickSeq||loading||!host.isConnected||current)return;
        content.replaceChildren();
        if(!items.length){content.append(el('p','smetra-visual-empty','Смет пока нет.'));return}
        const list=el('div','smetra-quote-picker');list.setAttribute('role','list');
        items.slice(0,30).forEach(quote=>{
          const row=el('button','smetra-quote-picker-row');row.type='button';row.setAttribute('role','listitem');
          const meta=[quote.client,quote.published_version?'Версия '+quote.published_version:'Черновик'].filter(Boolean).join(' · ');
          row.append(el('strong','',quote.title||'Смета'),el('small','',meta||'Смета'));
          if(quote.amount_kopecks!=null&&Number.isFinite(Number(quote.amount_kopecks)))row.append(el('span','smetra-quote-picker-sum',money(Number(quote.amount_kopecks),quote.currency||'RUB')));
          row.onclick=()=>load(quote.id);
          list.append(row);
        });
        content.append(list);
      }catch(error){
        if(request===pickSeq&&!loading&&!current)content.replaceChildren(el('p','smetra-visual-empty',error?.message||'Не удалось загрузить сметы'));
      }
    };
    let closeTimer=null;
    function setOpen(open){
      const next=Boolean(open);
      if(closeTimer!==null){clearTimeout(closeTimer);closeTimer=null}
      if(!next){
        const restoreFocus=panel.contains(document.activeElement)||Boolean(appearanceDialog?.contains(document.activeElement));
        closeAppearance(false);
        if(visible){
          // Invalidate async loads so an old response cannot reopen a
          // dismissed preview.
          ++seq;++pickSeq;loading=false;pending=null;
        }
        visible=false;
        // Collapse the grid track immediately; the CSS grid transition
        // smoothly returns the entire chat and composer to their full width.
        hostRoot?.classList.remove('has-quote-preview');
        panel.setAttribute('aria-hidden','true');
        panel.inert=true;
        const reducedMotion=window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches===true;
        if(!reducedMotion&&!panel.hidden){
          panel.classList.add('is-closing');
          closeTimer=setTimeout(()=>{
            closeTimer=null;
            if(!visible){panel.hidden=true;panel.classList.remove('is-closing')}
          },260);
        }else{
          panel.hidden=true;
          panel.classList.remove('is-closing');
        }
        onToggle?.(false);
        if(restoreFocus)hostRoot?.querySelector('#assistant-input')?.focus({preventScroll:true});
        return;
      }
      visible=true;
      panel.classList.remove('is-closing');
      panel.hidden=false;
      panel.inert=false;
      panel.setAttribute('aria-hidden','false');
      hostRoot?.classList.add('has-quote-preview');
      onToggle?.(true);
      render();
    }
    const load=async id=>{
      if(!id)return;
      closeAppearance(false);
      const requestUser=storageUser(),requestSpace=storageSpace();
      const request=++seq;loading=true;setOpen(true);
      content.replaceChildren(el('p','smetra-visual-empty','Загружаю смету…'));
      try{
        const response=await fetchQuote(id);
        if(request!==seq||!host.isConnected||storageUser()!==requestUser||storageSpace()!==requestSpace)return;
        loading=false;
        current=response?.quote||response;
        if(!current||current.id!==id)throw Error('Смета недоступна');
        currentContext={user:requestUser,space:requestSpace};
        pending=null;draft=null;mode=null;progressText='';layout=window.SmetraQuoteLayout?.load(storageSpace(),storageUser(),id)||null;render();
      }catch(error){
        if(request===seq){loading=false;content.replaceChildren(el('p','smetra-visual-empty',error?.message||'Не удалось загрузить смету'))}
      }
    };
    const clearProposal=(actionId)=>{
      if(pending && (!actionId||pending.id===actionId)){
        pending=null;
        if(visible)render();
      }
      if(draft && (!actionId||draft.id===actionId)){
        draft=null;
        if(visible)render();
      }
    };
    const propose=async action=>{
      if(!action||!action.tool||!action.arguments)return;
      const isQuote=/quote/.test(action.tool);
      if(!isQuote)return;
      if(action.tool==='create_quotes'){
        if(action.preview?.kind!=='quote_draft')return;
        // The same proposal arrives twice (live event, then the final answer): keep one.
        if(draft?.id===action.id)return;
        closeAppearance(false);++seq;loading=false;current=null;pending=null;draft=action;mode='new';setOpen(true);render();return;
      }
      const id=action.arguments.id;
      if(typeof id!=='string'||!id)return;
      if(!current||current.id!==id)await load(id);
      if(!current||current.id!==id)return;
      pending=action;setOpen(true);render();
    };
    const design=async payload=>{
      if(!payload||!payload.id||!window.SmetraQuoteLayout)return;
      const validated=window.SmetraQuoteLayout.safeLayout(payload.layout);
      if(!validated)return;
      if(!current||current.id!==payload.id)await load(payload.id);
      if(!current||current.id!==payload.id)return;
      closeAppearance(false);
      layout=validated;
      window.SmetraQuoteLayout.save(storageSpace(),storageUser(),payload.id,validated);
      setOpen(true);
    };
    const refresh=async()=>{
      if(!current)return;
      const id=current.id;await load(id);
    };
    const startNew=()=>{closeAppearance(false);++seq;loading=false;current=null;pending=null;draft=null;mode='new';progressText='';setOpen(true);render()};
    const progress=text=>{progressText=String(text||'').slice(0,120);if(visible&&(draft||mode==='new'))paintStatus()};
    return {load,propose,design,refresh,startNew,progress,close:()=>setOpen(false),open:()=>setOpen(true),toggle:()=>setOpen(!visible),get visible(){return visible},
      clearProposal,
      destroy:()=>{closeAppearance(false);if(closeTimer!==null)clearTimeout(closeTimer);seq++;pickSeq++;themeObserver.disconnect();hostRoot?.classList.remove('has-quote-preview','is-preview-wide','is-resizing');hostRoot?.style.removeProperty('--preview-saved-w');panel.remove()},
      get currentId(){return current?.id||''}};
  }
  window.SmetraQuoteVisuals={mountAssistant,mountRooms,breakdown,serverAmounts,roomDiagram,money};
})();
