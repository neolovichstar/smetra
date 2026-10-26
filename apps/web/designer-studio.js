/* Interior design workspace. Data is isolated by authenticated workspace on the server. */
(() => {
  'use strict';
  let selected=null, account=null, space=null, generation=0, busy=false, offset=0;
  const h=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const money=n=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB'}).format((n||0)/100);
  const price=n=>n?(n/100).toFixed(2):'0';
  const kopecks=value=>{
    const s=String(value??'').replace(',','.').trim();
    if(!/^\d{1,13}(\.\d{1,2})?$/.test(s))throw Error('Укажите сумму в рублях, до двух знаков после запятой');
    const a=s.split('.'),n=Number(a[0])*100+Number((a[1]||'').padEnd(2,'0'));
    if(!Number.isSafeInteger(n)||n>1e15)throw Error('Сумма слишком большая');
    return n;
  };
  const categories={finish:'Отделка',furniture:'Мебель',lighting:'Освещение',plumbing:'Сантехника',decor:'Декор',equipment:'Оборудование',work:'Работы',other:'Другое'};
  const states={planned:'Запланировано',selected:'Подобрано',approved:'Согласовано',ordered:'Заказано',delivered:'Доставлено',installed:'Установлено'};
  const options=(map,current)=>Object.entries(map).map(([id,title])=>'<option value="'+h(id)+'" '+(current===id?'selected':'')+'>'+h(title)+'</option>').join('');
  const input=(key,label,placeholder,value='',extra='')=>'<label class="designer-field"><span>'+h(label)+'</span><input name="'+key+'" placeholder="'+h(placeholder)+'" value="'+h(value)+'" '+extra+'></label>';
  const btn=(name,attrs)=>'<button class="btn small" type="button" '+(attrs||'')+'>'+name+'</button>';
  const isCurrent=(mine,accountId,workspaceId)=>generation===mine&&tab==='designer'&&user?.id===accountId&&sessionStorage.getItem('workspace_id')===workspaceId;
  const userId=()=>user?.id;
  const workspaceId=()=>sessionStorage.getItem('workspace_id');
  const request=(path,payload,method='POST')=>api(path,{method,body:JSON.stringify(payload)});
  function resetScope(){const a=userId(),s=workspaceId();if(a!==account||s!==space){account=a;space=s;selected=null;offset=0;}}
  async function modify(fn,refresh){
    if(busy)return;busy=true;
    const buttons=[...document.querySelectorAll('.designer-studio button')];buttons.forEach(el=>el.disabled=true);
    try{await fn();if(tab==='designer'&&account===userId()&&space===workspaceId()){await refresh();notify('Сохранено');}}
    catch(error){if(tab==='designer'){notify(error.message);if(error.status===409)await (selected?detail():list()).catch(()=>{});}}
    finally{busy=false;buttons.forEach(el=>{if(el.isConnected)el.disabled=false;});}
  }
  async function list(){
    const mine=++generation,a=userId(),s=workspaceId();
    const result=await api('/designer/projects?offset='+offset);
    if(!isCurrent(mine,a,s))return;
    const projects=result.projects||[];
    view('<section class="designer-studio"><header class="designer-heading"><span class="eyebrow">СМЕТРА / РЕЖИМ ДИЗАЙНЕРА</span><h1>Дизайн интерьера</h1><p>Спецификация мебели, отделки, освещения, сантехники и оборудования.</p></header>'+
      '<section class="designer-section"><h2>Новый проект</h2><form id="designer-create" class="designer-horizontal">'+
      input('name','Название','Квартира на Лесной','','required maxlength="200"')+
      input('budget','Бюджет, ₽','800000','0','required inputmode="decimal"')+
      '<button class="btn primary" type="submit">Создать проект</button></form></section>'+
      '<section class="designer-section"><h2>Проекты</h2>'+
      (projects.length?'<div class="designer-projects">'+projects.map(p=>
        '<button class="designer-project" type="button" data-open="'+h(p.id)+'"><span><strong>'+h(p.name)+'</strong><small>'+h(p.description||'Комплектация и бюджет')+'</small></span><b>'+money(p.budget_kopecks)+' ↗</b></button>').join('')+'</div>':
        '<p class="designer-empty">Создайте проект, чтобы составить первую спецификацию по помещениям.</p>')+
      '<div class="designer-pagination">'+(offset>0?btn('← Назад','id="designer-prev"'):'')+
      (projects.length===50?btn('Следующая страница →','id="designer-next"'):'')+'</div></section></section>');
    const form=document.querySelector('#designer-create');
    form.onsubmit=event=>{event.preventDefault();if(busy)return;const fd=new FormData(form);let total;
      try{total=kopecks(fd.get('budget'));}catch(error){notify(error.message);return;}
      modify(()=>request('/designer/projects',{name:fd.get('name'),budget_kopecks:total}),async()=>{offset=0;await list();});
    };
    document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>{selected=b.dataset.open;detail().catch(error=>notify(error.message));});
    document.querySelector('#designer-prev')?.addEventListener('click',()=>{offset=Math.max(0,offset-50);list().catch(err=>notify(err.message))});
    document.querySelector('#designer-next')?.addEventListener('click',()=>{offset+=50;list().catch(err=>notify(err.message))});
  }
  const base=id=>'/designer/projects/'+encodeURIComponent(id);
  const roomsSelect=rooms=>'<option value="">Общее / весь проект</option>'+rooms.map(r=>'<option value="'+h(r.id)+'">'+h(r.name)+'</option>').join('');
  async function detail(){
    const mine=++generation,a=userId(),s=workspaceId(),projectId=selected;
    const data=await api(base(projectId));
    if(!isCurrent(mine,a,s)||selected!==projectId)return;
    const p=data.project,rooms=data.rooms,items=data.items,sum=data.summary;
    const names=new Map(rooms.map(r=>[r.id,r.name]));
    const totals=new Map(rooms.map(r=>[r.id,0]));totals.set('',0);
    items.forEach(i=>totals.set(i.room_id||'',(totals.get(i.room_id||'')||0)+i.total_kopecks));
    const pct=p.budget_kopecks?Math.min(100,Math.round(sum.total_kopecks/p.budget_kopecks*100)):0;
    const rows=items.map(i=>
      '<tr><td><strong>'+h(i.name)+'</strong><small>'+h(categories[i.kind]||i.kind)+(i.article?' · '+h(i.article):'')+(i.supplier?' · '+h(i.supplier):'')+'</small></td>'+
      '<td>'+h(names.get(i.room_id)||'Общее')+'</td><td>'+h(i.quantity)+' '+h(i.unit)+'</td>'+
      '<td>'+(i.price_missing?'Не указана':money(i.unit_price))+'</td><td>'+(i.price_missing?'—':money(i.total_kopecks))+'</td>'+
      '<td>'+h(states[i.status]||i.status)+'</td><td class="designer-actions">'+btn('Изменить','data-edit-item="'+h(i.id)+'"')+
      btn('×','data-remove-item="'+h(i.id)+'" aria-label="Удалить позицию '+h(i.name)+'"')+'</td></tr>').join('');
    view('<section class="designer-studio">'+btn('← Все дизайн-проекты','id="designer-back"')+
      '<header class="designer-heading"><span class="eyebrow">СМЕТРА / ДИЗАЙН ИНТЕРЬЕРА</span><h1>'+h(p.name)+'</h1><p>'+h(p.description||'Комплектация и бюджет по помещениям')+'</p>'+
      '<div class="designer-controls">'+btn('Экспорт CSV','id="designer-export"')+btn('Бюджет проекта','id="designer-budget"')+
      btn('Удалить проект','id="designer-remove-project"')+'</div></header>'+
      '<div class="designer-metrics"><div><span>Комплектация</span><strong>'+money(sum.total_kopecks)+'</strong></div>'+
      '<div><span>Плановый бюджет</span><strong>'+money(sum.budget_kopecks)+'</strong></div>'+
      '<div><span>Осталось</span><strong '+(sum.remainder_kopecks<0?'class="designer-over"':'')+'>'+money(sum.remainder_kopecks)+'</strong></div>'+
      '<div><span>Без цены</span><strong>'+sum.missing_prices+'</strong></div></div>'+
      '<progress class="designer-progress" aria-label="Использование бюджета" value="'+pct+'" max="100"></progress>'+
      (sum.missing_prices?'<p class="designer-warning">У '+sum.missing_prices+' позиций нет подтверждённой цены. Расчёт предварительный.</p>':'')+
      '<section class="designer-section"><h2>Помещения и бюджеты</h2><div class="designer-rooms">'+rooms.map(r=>
        '<div class="designer-room"><span><strong>'+h(r.name)+'</strong><small>'+h(r.notes||'')+'</small></span><b>'+money(totals.get(r.id))+'</b>'+
        btn('Изменить','data-edit-room="'+h(r.id)+'"')+btn('×','data-remove-room="'+h(r.id)+'" aria-label="Удалить помещение '+h(r.name)+'"')+'</div>').join('')+
      '<div class="designer-room"><span><strong>Общие позиции</strong></span><b>'+money(totals.get(''))+'</b></div></div>'+
      '<form id="designer-room" class="designer-horizontal">'+
      input('name','Помещение','Гостиная','','required maxlength="120"')+input('notes','Примечание','Площадь, особенности','','maxlength="2000"')+
      '<button class="btn primary" type="submit">Добавить помещение</button>'+btn('Отмена','id="designer-room-cancel" hidden')+'</form></section>'+
      '<section class="designer-section"><h2>Спецификация · '+items.length+' позиций</h2>'+
      (rows?'<div class="designer-table-wrap"><table class="designer-table"><thead><tr><th>Позиция</th><th>Помещение</th><th>Количество</th><th>Цена</th><th>Сумма</th><th>Статус</th><th>Действия</th></tr></thead><tbody>'+rows+'</tbody></table></div>':
      '<p class="designer-empty">Добавьте мебель, материалы, свет или другое оснащение для комплектации.</p>')+
      '<form id="designer-item" class="designer-editor"><h3 id="designer-item-title">Новая позиция</h3><div class="designer-grid">'+
      '<label class="designer-field"><span>Категория</span><select name="kind">'+options(categories,'furniture')+'</select></label>'+
      input('name','Наименование','Например, модульный диван','','required maxlength="200"')+
      '<label class="designer-field"><span>Помещение</span><select name="room_id">'+roomsSelect(rooms)+'</select></label>'+
      input('article','Артикул','Код производителя','','maxlength="100"')+
      input('supplier','Поставщик / бренд','Поставщик','','maxlength="200"')+
      input('quantity','Количество','1','1','required inputmode="decimal"')+
      input('unit','Единица','шт.','шт.','required maxlength="30"')+
      input('price','Цена за единицу, ₽','Неизвестно — 0','0','required inputmode="decimal"')+
      '<label class="designer-field"><span>Статус</span><select name="status">'+options(states,'planned')+'</select></label>'+
      input('notes','Примечание','Материал, цвет, размеры, ссылка','','maxlength="2000"')+
      '</div><div class="designer-controls"><button class="btn primary" type="submit">Добавить позицию</button>'+btn('Отмена','id="designer-item-cancel" hidden')+
      '</div></form></section></section>');
    document.querySelector('#designer-back').onclick=()=>{selected=null;list().catch(err=>notify(err.message));};
    document.querySelector('#designer-export').onclick=()=>exportCSV(data);
    document.querySelector('#designer-budget').onclick=()=>{
      const name=prompt('Название дизайн-проекта',p.name);if(name===null)return;
      const value=prompt('Плановый бюджет, ₽',price(p.budget_kopecks));if(value===null)return;
      let cost;try{cost=kopecks(value)}catch(err){notify(err.message);return}
      modify(()=>request(base(projectId),{name,budget_kopecks:cost,revision:p.revision},'PATCH'),()=>detail());
    };
    document.querySelector('#designer-remove-project').onclick=()=>{if(!confirm('Удалить проект, все помещения и позиции без возможности восстановления?'))return;modify(()=>api(base(projectId),{method:'DELETE'}),()=>{selected=null;return list()});};
    const roomForm=document.querySelector('#designer-room'),roomCancel=document.querySelector('#designer-room-cancel');
    const resetRoom=()=>{roomForm.reset();delete roomForm.dataset.id;delete roomForm.dataset.revision;roomForm.querySelector('button[type=submit]').textContent='Добавить помещение';roomCancel.hidden=true;};
    roomCancel.onclick=resetRoom;
    document.querySelectorAll('[data-edit-room]').forEach(b=>b.onclick=()=>{
      const item=rooms.find(r=>r.id===b.dataset.editRoom);if(!item)return;
      roomForm.elements.namedItem('name').value=item.name;roomForm.elements.namedItem('notes').value=item.notes;
      roomForm.dataset.id=item.id;roomForm.dataset.revision=item.revision;roomCancel.hidden=false;
      roomForm.querySelector('button[type=submit]').textContent='Сохранить помещение';
      roomForm.scrollIntoView({behavior:'smooth',block:'center'});
    });
    roomForm.onsubmit=event=>{event.preventDefault();const fd=new FormData(roomForm),id=roomForm.dataset.id,body={name:fd.get('name'),notes:fd.get('notes')};
      if(id)body.revision=Number(roomForm.dataset.revision);
      modify(()=>request(base(projectId)+'/rooms'+(id?'/'+encodeURIComponent(id):''),body,id?'PATCH':'POST'),()=>detail());};
    document.querySelectorAll('[data-remove-room]').forEach(b=>b.onclick=()=>{
      if(!confirm('Удалить помещение? Его позиции будут перенесены в «Общее».'))return;
      modify(()=>api(base(projectId)+'/rooms/'+encodeURIComponent(b.dataset.removeRoom),{method:'DELETE'}),()=>detail());});
    const itemForm=document.querySelector('#designer-item'),itemCancel=document.querySelector('#designer-item-cancel');
    const resetItem=()=>{itemForm.reset();delete itemForm.dataset.id;delete itemForm.dataset.revision;document.querySelector('#designer-item-title').textContent='Новая позиция';itemForm.querySelector('button[type=submit]').textContent='Добавить позицию';itemCancel.hidden=true;};
    itemCancel.onclick=resetItem;
    document.querySelectorAll('[data-edit-item]').forEach(b=>b.onclick=()=>{
      const item=items.find(i=>i.id===b.dataset.editItem);if(!item)return;
      for(const key of ['kind','name','room_id','article','supplier','quantity','unit','status','notes']){
        const el=itemForm.elements.namedItem(key);if(el)el.value=item[key]||'';
      }
      itemForm.elements.namedItem('price').value=price(item.unit_price);
      itemForm.dataset.id=item.id;itemForm.dataset.revision=item.revision;itemCancel.hidden=false;
      document.querySelector('#designer-item-title').textContent='Изменение позиции';
      itemForm.querySelector('button[type=submit]').textContent='Сохранить изменения';
      itemForm.scrollIntoView({behavior:'smooth',block:'start'});
    });
    itemForm.onsubmit=event=>{event.preventDefault();const fd=new FormData(itemForm),id=itemForm.dataset.id;
      let amount;try{amount=kopecks(fd.get('price'))}catch(err){notify(err.message);return}
      const body=Object.fromEntries(fd);body.unit_price=amount;
      if(id)body.revision=Number(itemForm.dataset.revision);
      modify(()=>request(base(projectId)+'/items'+(id?'/'+encodeURIComponent(id):''),body,id?'PATCH':'POST'),()=>detail());
    };
    document.querySelectorAll('[data-remove-item]').forEach(b=>b.onclick=()=>{
      if(!confirm('Удалить эту позицию из спецификации?'))return;
      modify(()=>api(base(projectId)+'/items/'+encodeURIComponent(b.dataset.removeItem),{method:'DELETE'}),()=>detail());});
  }
  function exportCSV(data){
    const cols=['Помещение','Категория','Название','Артикул','Поставщик','Количество','Ед.','Цена, ₽','Сумма, ₽','Статус','Примечание'];
    const rooms=new Map(data.rooms.map(r=>[r.id,r.name]));
    const rows=data.items.map(i=>[rooms.get(i.room_id)||'Общее',categories[i.kind],i.name,i.article,i.supplier,i.quantity,i.unit,
      i.price_missing?'':price(i.unit_price),i.price_missing?'':price(i.total_kopecks),states[i.status],i.notes]);
    const cell=value=>{let v=String(value??'');if(/^\s*[=+\-@]/.test(v))v="'"+v;return '"'+v.replace(/"/g,'""')+'"';};
    const text='\ufeff'+[cols,...rows].map(r=>r.map(cell).join(';')).join('\r\n');
    const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8;'}));
    const link=document.createElement('a');link.href=url;link.download='smetra-design-'+data.project.id+'.csv';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1500);
  }
  window.SmetraDesigner=()=>{resetScope();return (selected?detail():list()).catch(error=>{
    if(tab==='designer'){notify(error.message);view('<section class="designer-studio"><h1>Раздел временно недоступен</h1><p>Проверьте подключение или повторите попытку.</p></section>');}
  });};
})();
