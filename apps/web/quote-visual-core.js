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
    const footer=el('p','smetra-visual-footnote','Диаграмма построена по подтверждённым расчётным суммам сервера. Неизвестные цены не оцениваются.');
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

  function mountAssistant({host,fetchQuote,onOpenEditor}){
    if(!host||typeof fetchQuote!=='function')throw Error('Quote preview requires an authorized quote fetcher');
    const panel=el('aside','smetra-quote-preview');
    panel.id='smetra-quote-preview';
    panel.setAttribute('aria-label','Предпросмотр сметы');
    panel.setAttribute('aria-hidden','true');
    panel.hidden=true;
    const header=el('header','smetra-quote-preview-header');
    const titleWrap=el('div','smetra-quote-preview-heading');
    titleWrap.append(el('small','','СМЕТРА / ПРЕДПРОСМОТР'),el('h2','','Редактор сметы'));
    const close=el('button','smetra-quote-preview-close','×');
    close.type='button';close.setAttribute('aria-label','Закрыть предпросмотр');
    close.onclick=()=>setOpen(false);
    header.append(titleWrap,close);panel.append(header);
    const content=el('div','smetra-quote-preview-content');panel.append(content);
    const hostRoot=host.closest('.assistant-studio');
    host.append(panel);
    let current=null,pending=null,visible=false,seq=0;
    const render=()=>{
      if(!visible)return;
      content.replaceChildren();
      if(!current){content.append(el('p','smetra-visual-empty','Выберите смету, чтобы посмотреть позиции и изменения.'));return}
      const quote=current;
      const title=el('div','smetra-quote-preview-title');
      title.append(el('h3','',quote.title||'Смета'),el('span','',quote.approval_state==='draft'?'Черновик':'Только просмотр'));
      content.append(title);
      const preview=pending?.preview||null;
      const ready=preview&&['quote_items','quote_structure','fields'].includes(preview.kind);
      const stagedItems=ready && Array.isArray(pending.arguments?.items)?pending.arguments.items:null;
      const rows=stagedItems||quote.items||[];
      const total=ready&&Number.isSafeInteger(preview.after_total)?preview.after_total:quote.amount_kopecks;
      if(preview&&pending.arguments?.id!==quote.id)pending=null;
      const summary=el('div','smetra-quote-preview-total');
      summary.append(el('span','',ready?'После подтверждения':'По сохранённой смете'),el('strong','',money(total,quote.currency)));
      content.append(summary);
      if(ready){
        const notification=el('section','smetra-quote-preview-pending');
        notification.append(el('strong','','Предложение ИИ · не сохранено'),el('p','',pending.summary||'Проверьте изменения в чате перед применением.'));
        if(preview.before_total!==undefined&&preview.after_total!==undefined){
          notification.append(el('div','smetra-quote-difference',
            'Было '+money(preview.before_total,quote.currency)+' → '+money(preview.after_total,quote.currency)));
        }
        content.append(notification);
      }
      const listing=el('section','smetra-quote-lines');
      const h=el('div','smetra-visual-heading');
      h.append(el('strong','','Позиции'),el('small','',String(rows.length)));listing.append(h);
      const table=el('div','smetra-quote-lines-table');
      rows.slice(0,100).forEach((item,index)=>{
        const row=el('div','smetra-quote-line');
        const info=el('div','smetra-quote-line-name');
        info.append(el('small','',String(index+1).padStart(2,'0')),el('span','',item.name||'Без названия'));
        const qty=el('div','smetra-quote-line-qty',(item.quantity||'—')+' '+(item.unit||''));
        const subtotal=Number.isSafeInteger(item.subtotal)?money(item.subtotal,quote.currency):'Не рассчитано';
        row.append(info,qty,el('strong','',subtotal));table.append(row);
      });
      listing.append(table);if(rows.length>100)listing.append(el('p','smetra-visual-footnote','Показаны первые 100 позиций.'));
      content.append(listing);
      content.append(breakdown(rows,quote.currency));
      const foot=el('div','smetra-quote-preview-actions');
      const edit=el('button','smetra-quote-open-editor','Открыть редактор');
      edit.type='button';edit.onclick=()=>{if(quote.id)onOpenEditor?.(quote.id)};
      foot.append(edit);
      if(ready)foot.append(el('p','smetra-visual-footnote','Применить или отклонить предложение можно в чате.'));
      content.append(foot);
    };
    function setOpen(open){
      visible=Boolean(open);panel.hidden=!visible;panel.setAttribute('aria-hidden',String(!visible));
      hostRoot?.classList.toggle('has-quote-preview',visible);
      if(visible)render();
    }
    const load=async id=>{
      if(!id)return;
      const request=++seq;setOpen(true);
      content.replaceChildren(el('p','smetra-visual-empty','Загружаю смету…'));
      try{
        const response=await fetchQuote(id);
        if(request!==seq||!host.isConnected)return;
        current=response?.quote||response;
        if(!current||current.id!==id)throw Error('Смета недоступна');
        pending=null;render();
      }catch(error){
        if(request===seq)content.replaceChildren(el('p','smetra-visual-empty',error?.message||'Не удалось загрузить смету'));
      }
    };
    const propose=async action=>{
      if(!action||!action.tool||!action.arguments)return;
      const isQuote=/quote/.test(action.tool);
      if(!isQuote)return;
      const id=action.arguments.id;
      if(typeof id!=='string'||!id)return;
      if(!current||current.id!==id)await load(id);
      if(!current||current.id!==id)return;
      pending=action;setOpen(true);render();
    };
    const refresh=async()=>{
      if(!current)return;
      const id=current.id;await load(id);
    };
    return {load,propose,refresh,close:()=>setOpen(false),open:()=>setOpen(true),
      destroy:()=>{seq++;hostRoot?.classList.remove('has-quote-preview');panel.remove()},
      get currentId(){return current?.id||''}};
  }
  window.SmetraQuoteVisuals={mountAssistant,mountRooms,breakdown,serverAmounts,roomDiagram,money};
})();
