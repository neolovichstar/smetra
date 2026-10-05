/* Authenticated previews for files already attached to a workspace record. */
window.SmetraFilePreview = (() => {
  let dialog;
  let objectUrl;
  let controller;
  const officeTypes=['application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','text/csv'];

  function officeView(body, data) {
    body.classList.add('file-office-body');
    const toolbar=document.createElement('div');toolbar.className='file-office-toolbar';
    const search=document.createElement('input');search.type='search';search.placeholder='Найти в документе';search.setAttribute('aria-label','Поиск в документе');
    const count=document.createElement('span');count.className='file-office-count';count.setAttribute('aria-live','polite');
    const sheet=document.createElement('select');sheet.setAttribute('aria-label','Лист таблицы');
    toolbar.append(search);if(data.sheets){for(const [index,item] of data.sheets.entries()){const option=document.createElement('option');option.value=index;option.textContent=item.name;sheet.append(option)}toolbar.append(sheet)}toolbar.append(count);
    const viewer=document.createElement('div');viewer.className='file-office-content';
    const note=document.createElement('p');note.className='file-office-note';note.textContent=(data.truncated?'Показана часть документа. ':'')+data.note;
    body.replaceChildren(toolbar,viewer,note);
    let sort=-1,descending=false;const widths=Array(20).fill(150);
    const collator=new Intl.Collator('ru',{numeric:true,sensitivity:'base'});
    const marked=(host,value)=>{
      const text=String(value??''),phrase=search.value.trim();
      if(!phrase){host.textContent=text;return}
      const lower=text.toLocaleLowerCase('ru'),needle=phrase.toLocaleLowerCase('ru');let start=0,at;
      while((at=lower.indexOf(needle,start))!==-1){host.append(document.createTextNode(text.slice(start,at)));const mark=document.createElement('mark');mark.textContent=text.slice(at,at+phrase.length);host.append(mark);start=at+phrase.length}host.append(document.createTextNode(text.slice(start)));
    };
    const paint=()=>{
      viewer.replaceChildren();const phrase=search.value.trim().toLocaleLowerCase('ru');
      if(data.blocks){
        viewer.classList.add('file-office-document');let found=0;
        for(const block of data.blocks){const value=block.text??block.rows.flat().join(' ');if(phrase&&!value.toLocaleLowerCase('ru').includes(phrase))continue;found++;
          if(block.type==='table'){const wrap=document.createElement('div');wrap.className='file-office-doc-table';const table=document.createElement('table');for(const row of block.rows){const tr=document.createElement('tr');for(const cell of row){const td=document.createElement('td');marked(td,cell);tr.append(td)}table.append(tr)}wrap.append(table);viewer.append(wrap)}else{const p=document.createElement(block.type==='heading'?'h2':'p');marked(p,block.text);viewer.append(p)}
        }
        count.textContent=phrase?found+' фрагментов':'';if(!found)viewer.textContent=phrase?'Совпадений нет':'В документе нет текста';return;
      }
      const source=data.sheets[Number(sheet.value)||0],rows=source.rows.filter(row=>!phrase||row.cells.join(' ').toLocaleLowerCase('ru').includes(phrase));
      if(sort>=0)rows.sort((a,b)=>(descending?-1:1)*collator.compare(a.cells[sort]||'',b.cells[sort]||''));
      count.textContent=rows.length+' строк';const table=document.createElement('table');table.className='file-office-table';
      const columns=Math.max(1,...source.rows.map(row=>row.cells.length));
      const group=document.createElement('colgroup'),rowNumber=document.createElement('col');rowNumber.style.width='48px';group.append(rowNumber);
      for(let i=0;i<columns;i++){const column=document.createElement('col');column.style.width=widths[i]+'px';group.append(column)}table.append(group);
      const head=document.createElement('thead'),top=document.createElement('tr'),index=document.createElement('th');index.textContent='#';top.append(index);
      for(let i=0;i<columns;i++){
        const th=document.createElement('th'),button=document.createElement('button');button.type='button';button.textContent=String.fromCharCode(65+i)+(sort===i?(descending?' ↓':' ↑'):'');button.setAttribute('aria-label','Сортировать столбец '+String.fromCharCode(65+i));th.setAttribute('aria-sort',sort===i?(descending?'descending':'ascending'):'none');button.onclick=()=>{descending=sort===i&&!descending;sort=i;paint()};th.append(button);
        const handle=document.createElement('span');handle.className='file-column-resize';handle.tabIndex=0;handle.setAttribute('role','separator');handle.setAttribute('aria-orientation','vertical');handle.setAttribute('aria-label','Ширина столбца '+String.fromCharCode(65+i));
        const resize=value=>{widths[i]=Math.max(80,Math.min(500,value));group.children[i+1].style.width=widths[i]+'px';table.style.width=(48+widths.slice(0,columns).reduce((a,b)=>a+b,0))+'px'};
        handle.onkeydown=event=>{if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();resize(widths[i]+(event.key==='ArrowLeft'?-20:20))}};
        handle.onpointerdown=event=>{event.preventDefault();handle.setPointerCapture(event.pointerId);const start=event.clientX,width=widths[i];handle.onpointermove=next=>resize(width+next.clientX-start);handle.onpointerup=()=>{handle.onpointermove=null};handle.onpointercancel=()=>{handle.onpointermove=null}};th.append(handle);top.append(th);
      }
      head.append(top);table.append(head);const tbody=document.createElement('tbody');
      for(const row of rows){const tr=document.createElement('tr'),number=document.createElement('th');number.scope='row';number.textContent=row.number;tr.append(number);for(let i=0;i<columns;i++){const td=document.createElement('td');marked(td,row.cells[i]||'');tr.append(td)}tbody.append(tr)}table.append(tbody);table.style.width=(48+widths.slice(0,columns).reduce((a,b)=>a+b,0))+'px';viewer.append(table);
      if(!rows.length){const empty=document.createElement('p');empty.textContent=phrase?'Совпадений нет':'Лист пуст';viewer.append(empty)}
    };
    search.oninput=paint;sheet.onchange=()=>{sort=-1;descending=false;paint()};paint();
  }

  function release() {
    controller?.abort();
    controller = undefined;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = undefined;
    dialog?.querySelector('.file-preview-body')?.replaceChildren();
  }

  function close() {
    if (dialog?.open) dialog.close();
    release();
  }

  function ensureDialog() {
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.className = 'file-preview-dialog';
    dialog.innerHTML = '<div class="file-preview-top"><div><span>СМЕТРА / ФАЙЛ</span><strong class="file-preview-name"></strong></div><div class="file-preview-actions"><button class="btn small file-preview-save" type="button">Скачать</button><button class="file-preview-close" type="button" aria-label="Закрыть просмотр">×</button></div></div><div class="file-preview-body" role="status"></div>';
    dialog.querySelector('.file-preview-close').addEventListener('click', close);
    dialog.addEventListener('close', release);
    dialog.addEventListener('click', event => {
      if (event.target === dialog) close();
    });
    document.body.append(dialog);
    return dialog;
  }

  async function open(file, workspaceId) {
    const view = ensureDialog();
    release();
    view.querySelector('.file-preview-name').textContent = file.name;
    const body = view.querySelector('.file-preview-body');
    body.classList.remove('file-office-body');
    body.textContent = 'Открываем файл…';
    view.querySelector('.file-preview-save').disabled = true;
    if (!view.open) view.showModal();
    controller = new AbortController();
    const request = controller;
    try {
      if(officeTypes.includes(file.mime)){
        const response=await fetch('/api/files/'+encodeURIComponent(file.id)+'/preview',{credentials:'same-origin',headers:workspaceId?{'X-Workspace-Id':workspaceId}:{},signal:request.signal});
        const data=await response.json();if(!response.ok)throw new Error(data.error||'Не удалось открыть документ');
        if(request!==controller||!view.open)return;officeView(body,data);
        const save=view.querySelector('.file-preview-save');save.disabled=false;save.onclick=async()=>{save.disabled=true;try{await window.Workspace.download('/files/'+encodeURIComponent(file.id),file.name)}catch(error){window.notify?.(error.message)}finally{save.disabled=false}};return;
      }
      const response = await fetch('/api/files/' + encodeURIComponent(file.id), {
        credentials: 'same-origin',
        headers: workspaceId ? {'X-Workspace-Id': workspaceId} : {},
        signal: request.signal
      });
      if (!response.ok) {
        let message = 'Не удалось открыть файл';
        try { message = (await response.json()).error || message; } catch (_) { /* HTTP error */ }
        throw new Error(message);
      }
      const bytes = await response.blob();
      if (request !== controller || !view.open) return;
      if (!['image/png', 'image/jpeg', 'application/pdf', 'text/plain'].includes(file.mime) ||
          bytes.type !== file.mime) throw new Error('Формат файла не поддерживается');
      body.replaceChildren();
      if (file.mime === 'text/plain') {
        const markdown = file.name.toLowerCase().endsWith('.md');
        const content = document.createElement(markdown ? 'div' : 'pre');
        content.className = markdown ? 'assistant-markdown file-preview-markdown' : 'file-preview-text';
        const text = await bytes.text();
        if (markdown && typeof window.assistantMarkdown === 'function' && text.length <= 200000) content.innerHTML = window.assistantMarkdown(text);
        else content.textContent = text;
        if (request !== controller || !view.open) return;
        body.append(content);
      } else {
        objectUrl = URL.createObjectURL(bytes);
        if (file.mime === 'application/pdf') {
          const frame = document.createElement('iframe');
          frame.title = file.name;
          frame.src = objectUrl;
          frame.className = 'file-preview-pdf';
          body.append(frame);
        } else {
          const image = document.createElement('img');
          image.alt = file.name;
          image.src = objectUrl;
          image.className = 'file-preview-image';
          body.append(image);
        }
      }
      const save = view.querySelector('.file-preview-save');
      save.disabled = false;
      save.onclick = () => {
        const url = objectUrl || URL.createObjectURL(bytes);
        const link = document.createElement('a');
        link.href = url;
        link.download = file.name;
        link.click();
        if (!objectUrl) setTimeout(() => URL.revokeObjectURL(url), 30000);
      };
    } catch (error) {
      if (error.name === 'AbortError' || !view.open) return;
      body.textContent = error.message;
    }
  }

  return {open, close};
})();
