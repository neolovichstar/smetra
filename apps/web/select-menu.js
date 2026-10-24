/* Accessible single-select enhancement. The original select owns form data. */
(() => {
  const instances=new WeakMap(),tracked=new Set();let opened=null;
  function close(focus=false){if(!opened)return;const current=opened;opened=null;current.trigger.setAttribute('aria-expanded','false');current.panel.classList.add('select-menu-closing');current.cleanup();setTimeout(()=>current.panel.remove(),matchMedia('(prefers-reduced-motion: reduce)').matches?0:140);if(focus&&current.trigger.isConnected)current.trigger.focus()}
  function enhance(root=document){
    const nodes=[...(root.matches?.('select')?[root]:[]),...root.querySelectorAll('select')];
    for(const select of nodes){if(select.multiple||select.hidden||select.closest('[hidden]'))continue;if(instances.has(select)){instances.get(select).sync();continue}
      const wrap=document.createElement('div');wrap.className='select-control';select.before(wrap);wrap.append(select);
      const trigger=document.createElement('button');trigger.type='button';trigger.className='select-trigger';trigger.setAttribute('role','combobox');trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');
      const label=document.createElement('span'),chevron=document.createElement('span');chevron.className='select-chevron';chevron.setAttribute('aria-hidden','true');trigger.append(label,chevron);wrap.append(trigger);
      select.classList.add('select-native');select.tabIndex=-1;select.setAttribute('aria-hidden','true');
      const sync=()=>{label.textContent=select.selectedOptions[0]?.textContent||'Выберите';trigger.disabled=select.matches(':disabled');trigger.setAttribute('aria-required',String(select.required));const name=select.getAttribute('aria-label')||select.labels?.[0]?.childNodes[0]?.textContent||'Выбор';trigger.setAttribute('aria-label',name.trim()+': '+label.textContent)};
      select.addEventListener('change',sync);select.addEventListener('input',sync);select.addEventListener('invalid',event=>{event.preventDefault();trigger.focus();open()});
      const observer=new MutationObserver(()=>{if(!select.isConnected){observer.disconnect();tracked.delete(select);return}sync();if(opened?.select===select)opened.render()});observer.observe(select,{childList:true,subtree:true,attributes:true});
      function open(){if(select.matches(':disabled'))return;if(opened?.select===select){close(true);return}close();document.querySelectorAll('.select-menu-closing').forEach(panel=>panel.remove());sync();
        const panel=document.createElement('div');panel.className='select-menu';panel.id='select-menu-'+crypto.randomUUID();trigger.setAttribute('aria-controls',panel.id);trigger.setAttribute('aria-expanded','true');
        const search=document.createElement('input');search.type='search';search.className='select-menu-search';search.placeholder='Найти…';search.setAttribute('aria-label','Поиск вариантов');search.autocomplete='off';
        const list=document.createElement('div');list.className='select-menu-list';list.setAttribute('role','listbox');list.id=panel.id+'-options';list.setAttribute('aria-label',trigger.getAttribute('aria-label'));panel.append(search,list);search.setAttribute('role','combobox');search.setAttribute('aria-controls',list.id);search.setAttribute('aria-expanded','true');search.setAttribute('aria-autocomplete','list');trigger.setAttribute('aria-controls',list.id);
        const host=select.closest('dialog[open]')||document.body;
        if(typeof panel.showPopover==='function'){panel.setAttribute('popover','manual');host.append(panel);panel.showPopover()}else host.append(panel);
        let choices=[],index=0;
        const position=()=>{if(!select.isConnected){close();return}
          const r=trigger.getBoundingClientRect(),margin=12,viewportWidth=Math.max(1,innerWidth),viewportHeight=Math.max(1,innerHeight);
          const width=Math.min(Math.max(r.width,240),Math.max(1,viewportWidth-margin*2));
          panel.style.width=width+'px';
          panel.style.left=Math.max(0,Math.min(Math.max(margin,r.left),viewportWidth-width-margin))+'px';
          panel.style.bottom='auto';
          panel.style.maxHeight=Math.max(1,Math.min(330,viewportHeight-margin*2))+'px';
          panel.style.top=margin+'px';
          const panelHeight=panel.offsetHeight;
          const spaceBelow=viewportHeight-r.bottom-margin,spaceAbove=r.top-margin;
          const opensAbove=spaceBelow<panelHeight+6&&spaceAbove>spaceBelow;
          const desiredTop=opensAbove?r.top-panelHeight-6:r.bottom+6;
          panel.style.top=Math.max(0,Math.min(Math.max(margin,desiredTop),viewportHeight-panelHeight-margin))+'px';
        };
        const highlight=()=>{choices.forEach((choice,n)=>{choice.button.classList.toggle('select-option-active',n===index)});const choice=choices[index];if(choice){search.setAttribute('aria-activedescendant',choice.button.id);choice.button.scrollIntoView({block:'nearest'})}else search.removeAttribute('aria-activedescendant')};
        const choose=option=>{if(option.disabled)return;select.value=option.value;select.dispatchEvent(new Event('input',{bubbles:true}));select.dispatchEvent(new Event('change',{bubbles:true}));sync();close(true)};
        const render=()=>{list.replaceChildren();choices=[];const query=search.value.trim().toLocaleLowerCase('ru');Array.from(select.options).forEach((option,n)=>{if(option.hidden||!option.textContent.toLocaleLowerCase('ru').includes(query))return;const button=document.createElement('button');button.type='button';button.className='select-option';button.id=panel.id+'-'+n;button.tabIndex=-1;button.setAttribute('role','option');button.setAttribute('aria-selected',String(option.selected));button.disabled=option.disabled||option.parentElement?.disabled===true;const text=document.createElement('span');text.textContent=option.textContent;button.append(text);if(option.selected){const mark=document.createElement('span');mark.textContent='✓';mark.setAttribute('aria-hidden','true');button.append(mark)}button.onclick=()=>choose(option);list.append(button);if(!button.disabled)choices.push({option,button})});index=Math.max(0,choices.findIndex(choice=>choice.option.selected));if(!choices.length){const empty=document.createElement('p');empty.className='select-menu-empty';empty.textContent='Ничего не найдено';list.append(empty)}highlight();position()};
        const keydown=event=>{if(event.key==='Escape'){event.preventDefault();close(true)}else if(event.key==='Tab'){close()}else if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();if(event.key==='Home')index=0;else if(event.key==='End')index=choices.length-1;else index=Math.max(0,Math.min(choices.length-1,index+(event.key==='ArrowDown'?1:-1)));highlight()}else if(event.key==='Enter'){event.preventDefault();if(choices[index])choose(choices[index].option)}};
        const outside=event=>{if(!panel.contains(event.target)&&!wrap.contains(event.target))close()};
        const scroll=event=>{if(!panel.contains(event.target))position()};
        search.oninput=()=>{render();select.dispatchEvent(new CustomEvent('smetra-select-search',{detail:{query:search.value}}))};panel.addEventListener('keydown',keydown);document.addEventListener('pointerdown',outside);window.addEventListener('resize',position);document.addEventListener('scroll',scroll,true);
        opened={select,panel,trigger,render,cleanup:()=>{document.removeEventListener('pointerdown',outside);window.removeEventListener('resize',position);document.removeEventListener('scroll',scroll,true)}};render();search.focus();
      }
      trigger.onclick=open;trigger.onkeydown=event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();open()}};instances.set(select,{sync,observer});tracked.add(select);sync();
    }
  }
  window.SmetraSelects={enhance,close};
  enhance();const observer=new MutationObserver(records=>{let removed=false;for(const record of records){if(record.removedNodes.length)removed=true;for(const node of record.addedNodes)if(node.nodeType===1&&!node.closest('.select-menu'))enhance(node)}if(removed)for(const select of tracked)if(!select.isConnected){instances.get(select).observer.disconnect();tracked.delete(select)}if(opened&&(!opened.select.isConnected||opened.select.closest('dialog')&&!opened.select.closest('dialog').open))close()});observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['open']});
})();
