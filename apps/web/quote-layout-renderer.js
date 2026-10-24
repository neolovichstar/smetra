/* Declarative quote document engine. No arbitrary HTML/CSS or model-calculated totals. */
(() => {
 'use strict';
 const KINDS=new Set(['title','intro','summary','items','breakdown','notes','divider','section','metrics','terms','rooms']);
 const STYLES=new Set(['editorial','minimal','technical','compact']);
 const TONES=new Set(['neutral','warm','graphite','sage','sand']);
 const node=(tag,cl,text)=>{const n=document.createElement(tag);if(cl)n.className=cl;if(text!==undefined)n.textContent=String(text);return n};
 const safeLayout=value=>{
   const l=value||{},blocks=Array.isArray(l.blocks)?l.blocks:[];
   if(blocks.length<1||blocks.length>24)return null;
   if(!blocks.some(b=>b.kind==='summary')||!blocks.some(b=>b.kind==='items'))return null;
   if(!blocks.every(b=>b&&KINDS.has(b.kind)))return null;
   return {version:1,style:STYLES.has(l.style)?l.style:'editorial',
     tone:TONES.has(l.tone)?l.tone:'neutral',
     blocks:blocks.map((b,i)=>({kind:b.kind,title:String(b.title||'').slice(0,100),
     description:String(b.description||'').slice(0,400),width:b.width==='half'?'half':'full',key:String(i)}))};
 };
 const base=()=>({version:1,style:'editorial',tone:'neutral',blocks:[
   {kind:'title',title:'',description:'',width:'full'},
   {kind:'summary',title:'Общая стоимость',description:'',width:'full'},
   {kind:'items',title:'Состав работ и материалов',description:'',width:'full'},
   {kind:'breakdown',title:'Распределение затрат',description:'',width:'full'},
   {kind:'terms',title:'Условия',description:'',width:'full'}]});
 const textBlock=(kind,heading,content)=>{
   const box=node('section','smetra-document-'+kind);
   if(heading)box.append(node('h3','',heading));
   if(content)box.append(node('p','',content));
   return box;
 };
 const cost=v=>Number.isSafeInteger(v)?v:null;
 function render({quote,layout,pending,onLayoutChange}){
   const l=safeLayout(layout)||safeLayout(base());
   const root=node('article','smetra-document smetra-document--'+l.style+' smetra-document-tone--'+l.tone);
   const configured=pending?.preview&&['quote_items','quote_structure'].includes(pending.preview.kind);
   const items=configured&&Array.isArray(pending?.arguments?.items)?pending.arguments.items:Array.isArray(quote.items)?quote.items:[];
   const currency=quote.currency||'RUB',format=v=>window.SmetraQuoteVisuals?.money(v,currency)||'—';
   const isPending=configured&&pending.arguments?.id===quote.id;
   const total=isPending&&cost(pending.preview.after_total)!==null?pending.preview.after_total:quote.amount_kopecks;
   const add=(block,custom)=>{
     if(!block)return;
     block.classList.add('smetra-document-block',custom.width==='half'?'is-half':'is-full');
     root.append(block);
   };
   for(const block of l.blocks){
     const heading=block.title;
     switch(block.kind){
       case 'title':{
         const t=node('header','smetra-document-title');
         t.append(node('small','','СМЕТРА · ИНДИВИДУАЛЬНЫЙ РАСЧЁТ'));
         t.append(node('h2','',heading||quote.title||'Смета'));
         if(quote.client)t.append(node('p','',quote.client));
         if(block.description)t.append(node('p','smetra-document-lead',block.description));
         add(t,block);break;
       }
       case 'intro':add(textBlock('intro',heading||'О проекте',block.description||quote.description),block);break;
       case 'summary':{
         const box=node('section','smetra-document-summary');
         box.append(node('span','',heading||'Стоимость по смете'));
         box.append(node('strong','',format(total)));
         if(isPending)box.append(node('small','smetra-document-warning','Предложение ИИ · пока не сохранено'));
         if(block.description)box.append(node('p','',block.description));
         add(box,block);break;
       }
       case 'items':{
         const section=node('section','smetra-document-items');
         section.append(node('h3','',heading||'Позиции'));
         if(block.description)section.append(node('p','smetra-document-note',block.description));
         const table=node('div','smetra-document-lines');
         items.slice(0,200).forEach((item,i)=>{
           const line=node('div','smetra-document-line');
           const caption=node('div','smetra-document-line-caption');
           caption.append(node('small','',String(i+1).padStart(2,'0')),node('span','',item.name||'Позиция'));
           if(item.description)caption.append(node('p','',item.description));
           line.append(caption,node('span','smetra-document-line-quantity',String(item.quantity||'—')+' '+String(item.unit||'')),
            node('strong','',cost(item.subtotal)===null?'—':format(item.subtotal)));
           table.append(line);
         });
         section.append(table);add(section,block);break;
       }
       case 'breakdown':{
         const visual=window.SmetraQuoteVisuals?.breakdown(items,currency);
         if(visual){const h=visual.querySelector('.smetra-visual-heading strong');if(h)h.textContent=heading||'Структура затрат';add(visual,block)}
         break;
       }
       case 'metrics':{
         const metric=node('section','smetra-document-metrics');
         metric.append(node('h3','',heading||'Показатели'),node('strong','',String(items.length)+' позиций'));
         if(block.description)metric.append(node('p','',block.description));
         add(metric,block);break;
       }
       case 'notes':add(textBlock('notes',heading||'Примечания',block.description||quote.description),block);break;
       case 'terms':add(textBlock('terms',heading||'Условия',block.description||quote.terms),block);break;
       case 'section':add(textBlock('section',heading||'Раздел',block.description),block);break;
       case 'divider':add(node('hr','smetra-document-divider'),block);break;
       case 'rooms':{
         const el=node('div','smetra-document-room-host');
         window.SmetraQuoteVisuals?.mountRooms(el,Array.isArray(quote.zones)?quote.zones:[]);
         if(el.children.length)add(el,block);break;
       }
     }
   }
   return root;
 }
 const keyed=(workspace,user,id)=>'smetra.quote.layout.v1:'+workspace+':'+user+':'+id;
 const save=(workspace,user,id,value)=>{
  const normalized=safeLayout(value);if(!normalized||!id)return false;
  try{localStorage.setItem(keyed(workspace,user,id),JSON.stringify(normalized));return true}catch{return false}
 };
 const load=(workspace,user,id)=>{
  try{return safeLayout(JSON.parse(localStorage.getItem(keyed(workspace,user,id))||'null'))||base()}catch{return base()}
 };
 const configure=({container,value,onChange})=>{
   const l=safeLayout(value)||base();
   const wrapper=node('section','smetra-document-config');
   wrapper.append(node('h3','','Настроить документ'));
   const styles=node('div','smetra-document-config-styles');
   ['editorial','minimal','technical','compact'].forEach(style=>{
     const b=node('button','',''+({editorial:'Редакционный',minimal:'Минимализм',technical:'Технический',compact:'Компактный'}[style]));
     b.type='button';b.setAttribute('aria-pressed',String(l.style===style));
     b.onclick=()=>{l.style=style;onChange(safeLayout(l))};styles.append(b);
   });
   wrapper.append(styles);
   const rows=node('div','smetra-document-config-rows');
   const relabel={title:'Заголовок',intro:'Введение',summary:'Итого',items:'Позиции',breakdown:'Диаграмма',notes:'Заметки',
     divider:'Разделитель',section:'Секция',metrics:'Показатели',terms:'Условия',rooms:'Помещения'};
   l.blocks.forEach((block,index)=>{
     const row=node('div','smetra-document-config-row');
     row.append(node('span','',block.title||relabel[block.kind]||block.kind));
     for(const [symbol,direction] of [['↑',-1],['↓',1]]){
       const move=node('button','',symbol);move.type='button';move.disabled=index+direction<0||index+direction>=l.blocks.length;
       move.onclick=()=>{const other=l.blocks[index+direction];l.blocks[index+direction]=block;l.blocks[index]=other;onChange(safeLayout(l))};
       row.append(move);
     }
     if(!['summary','items'].includes(block.kind)){
       const remove=node('button','','×');remove.type='button';remove.setAttribute('aria-label','Убрать блок');
       remove.onclick=()=>{l.blocks.splice(index,1);onChange(safeLayout(l))};row.append(remove);
     }
     rows.append(row);
   });
   wrapper.append(rows);
   const add=node('select','smetra-document-config-add');
   add.setAttribute('aria-label','Добавить блок');add.append(node('option','','Добавить блок…'));
   [...KINDS].forEach(kind=>{const o=node('option','',relabel[kind]);o.value=kind;add.append(o)});
   add.onchange=()=>{if(!KINDS.has(add.value)||l.blocks.length>=24)return;
      l.blocks.push({kind:add.value,title:'',description:'',width:'full'});
      onChange(safeLayout(l))};wrapper.append(add);
   container.replaceChildren(wrapper);
 };
 window.SmetraQuoteLayout={render,base,safeLayout,load,save,configure};
})();
