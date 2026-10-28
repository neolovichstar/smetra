/* Compact room geometry and AR tools. AI drafts, PDF reviews and sharing live in their respective workflows. */
window.SmetraFieldFlows=(()=>{
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const $=(root,s)=>root.querySelector(s), $$=(root,s)=>Array.from(root.querySelectorAll(s));
  const money=(value,currency='RUB')=>new Intl.NumberFormat('ru-RU',{style:'currency',currency}).format((value||0)/100);
  const post=(url,data)=>api(url,{method:'POST',body:JSON.stringify(data)});
  const field=(name,label,value='',type='text',props='')=>'<label class="ff-field"><span>'+esc(label)+'</span><input name="'+name+'" type="'+type+'" value="'+esc(value)+'" '+props+'></label>';
  const section=(id,label,title,description,body)=>'<section class="ff-section" id="'+id+'"><span class="ff-kicker">'+label+'</span><h2>'+title+'</h2><p class="ff-description">'+description+'</p>'+body+'<p class="ff-feedback" data-feedback role="status" hidden></p></section>';
  function feedback(host,message){const el=$(host,'[data-feedback]');if(el){el.hidden=false;el.textContent=message;}}
  function roomPayload(form){return {rooms:[{
    name:$(form,'[name=name]').value,length:$(form,'[name=length]').value,width:$(form,'[name=width]').value,
    height:$(form,'[name=height]').value,unit:'м',openings_m2:$(form,'[name=openings]').value||'0',
    mix_kg_per_m2:$(form,'[name=rate]').value||'0',bag_kg:$(form,'[name=bag]').value||'25',
    waste_percent:$(form,'[name=waste]').value||'0'
  }]};}
  async function fieldwork(isCurrent){
    const objects=await api('/construction/objects');if(!isCurrent())return;
    view('<section class="ff-page"><header class="ff-heading"><span class="ff-kicker">СМЕТРА / ГЕОМЕТРИЯ</span><h1>Геометрия помещения</h1><p class="ff-description">Ручной обмер и AR-сканирование. Подготовку сметы, разбор аудио и дизайн-проектов выполняет ассистент.</p></header>'+
      section('ff-ar','01 / ОБМЕРЫ','Геометрия помещения','Внесите результаты ручного обмера или AR-сканирования. Точные площади и расход посчитает сервер.',
        '<form data-room-form><label class="ff-field"><span>Строительный объект</span><select name="object" required><option value="">Выберите объект</option>'+
        (objects.items||[]).map(o=>'<option value="'+esc(o.id)+'">'+esc(o.name)+'</option>').join('')+'</select></label><div class="ff-field-grid">'+
        field('name','Помещение','Ванная','text','required maxlength="120"')+
        field('length','Длина, м','4','number','required min="0.5" max="100" step="any"')+
        field('width','Ширина, м','3','number','required min="0.5" max="100" step="any"')+
        field('height','Высота, м','2.7','number','required min="0.5" max="100" step="any"')+
        field('openings','Проёмы, м²','2','number','required min="0" step="any"')+
        field('rate','Смесь, кг/м²','1.2','number','min="0" max="100" step="any"')+
        field('bag','Вес мешка, кг','25','number','min="0.1" max="100" step="any"')+
        field('waste','Запас, %','10','number','min="0" max="100" step="any"')+'</div>'+
        '<label class="ff-consent"><input type="checkbox" name="reviewed">Размеры и нормы расхода проверены</label>'+
        '<div class="ff-actions"><button type="submit" class="btn">Рассчитать</button><button type="button" class="btn primary" data-room-import disabled>Импортировать</button><a href="#construction" class="ff-link">Объекты →</a></div></form><div data-ar-result></div>')+

      '</section>');
    // ARCore camera measurements remain in the object screen and Android shell,
    // never simulated by the web browser.
    const arLink=document.createElement('a');
    arLink.className='ff-link';arLink.href='#construction';arLink.textContent='AR-сканирование доступно в объекте на Android с ARCore';
    document.querySelector('#ff-ar .ff-actions')?.append(arLink);
    const ar=document.querySelector('#ff-ar'),roomForm=$(ar,'[data-room-form]'),importButton=$(ar,'[data-room-import]'),check=$(ar,'[name=reviewed]');
    let reviewed=null;
    roomForm.addEventListener('input',event=>{
      if(event.target===check){importButton.disabled=!(reviewed&&check.checked);return;}
      reviewed=null;importButton.disabled=true;$(ar,'[data-ar-result]').replaceChildren();
    });
    roomForm.onsubmit=async event=>{
      event.preventDefault();const btn=$(roomForm,'button[type=submit]');btn.disabled=true;
      try{
        const id=$(roomForm,'[name=object]').value;
        reviewed=roomPayload(roomForm);
        const result=await post('/construction/objects/'+encodeURIComponent(id)+'/scan/preview',reviewed);
        if(!isCurrent())return;
        const r=result.rooms[0];
        $(ar,'[data-ar-result]').innerHTML='<div class="ff-metrics"><span><b>'+esc(r.floor_m2)+' м²</b> пола</span><span><b>'+esc(r.net_walls_m2)+' м²</b> стен</span><span><b>'+esc(r.bags)+'</b> мешков смеси</span></div>';
        importButton.disabled=!check.checked;
      }catch(error){reviewed=null;feedback(ar,error.message);}
      finally{btn.disabled=false;}
    };
    importButton.onclick=async()=>{
      if(!reviewed||!check.checked)return;
      importButton.disabled=true;
      try{
        const id=$(roomForm,'[name=object]').value;
        await post('/construction/objects/'+encodeURIComponent(id)+'/scan/import',{...reviewed,review_confirmed:true});
        if(!isCurrent())return;
        $(ar,'[data-ar-result]').innerHTML='<p class="ff-success">Помещение импортировано. Проверьте его в объекте.</p>';
        reviewed=null;check.checked=false;
      }catch(error){feedback(ar,error.message);}
    };
  }
  async function inbox(isCurrent){
    const result=await api('/shared-inbox');if(!isCurrent())return;
    const items=result.inbox||[];
    view('<section class="ff-page ff-inbox"><header class="ff-heading"><span class="ff-kicker">КЛИЕНТ / СОГЛАСОВАНИЕ</span><h1>Полученные сметы</h1><p>Документы доступны только владельцу подтверждённого почтового адреса.</p></header>'+
      '<div data-inbox-items>'+ (items.length?items.map(item=>'<button type="button" class="ff-inbox-row" data-id="'+esc(item.id)+'"><span><strong>'+esc(item.title)+'</strong><small>Версия '+esc(item.quote_version)+'</small></span><span>Открыть →</span></button>').join(''):
      '<p class="ff-empty">Пока нет предложений. Приглашённые сметы появятся здесь.</p>')+'</div><div data-inbox-detail hidden></div><p data-feedback hidden role="status"></p></section>');
    const root=document.querySelector('.ff-inbox'),list=$(root,'[data-inbox-items]'),detail=$(root,'[data-inbox-detail]');
    const show=async id=>{
      if(!items.some(i=>i.id===id))return;
      try{
        const record=await api('/shared-inbox/'+encodeURIComponent(id));
        if(!isCurrent())return;
        try{sessionStorage.removeItem('smetra.pendingShare')}catch{}
        list.hidden=true;detail.hidden=false;
        renderOffer(detail,record,()=>{list.hidden=false;detail.hidden=true;},isCurrent);
      }catch(error){feedback(root,error.message);}
    };
    $$(root,'[data-id]').forEach(b=>b.onclick=()=>show(b.dataset.id));
    let pending=new URLSearchParams(location.search).get('share');
    if(!pending)try{pending=sessionStorage.getItem('smetra.pendingShare')}catch{}
    if(pending&&items.some(i=>i.id===pending))await show(pending);
  }
  function renderOffer(host,record,back,isCurrent){
    const doc=record.quote,lines=doc.items||[],readonly=['approved','changes_requested'].includes(record.status);
    host.innerHTML='<button type="button" class="ff-link" data-back>← Все предложения</button><h2>'+esc(doc.title)+'</h2>'+
      '<p class="ff-description">Изменение набора работ потребует подтверждения исполнителя.</p>'+
      '<div class="ff-offer-lines">'+lines.map((line,i)=>'<div class="ff-offer-line"><span>'+esc(line.name)+'<small>'+esc(line.quantity)+' '+esc(line.unit)+'</small></span>'+
        (line.optional?'<label class="ff-consent"><input type="checkbox" data-opt="'+i+'" '+(record.selected_optional.includes(i)?'checked':'')+(readonly?' disabled':'')+'>Включить</label>':'<span class="ff-hint">Обязательно</span>')+
        '<strong>'+money(line.subtotal,doc.currency)+'</strong></div>').join('')+'</div>'+
      '<div class="ff-offer-total"><span>С выбранными позициями</span><strong data-total>'+money(record.selected_total_kopecks,doc.currency)+'</strong></div>'+
      (readonly?'<p class="ff-success">Ответ отправлен: '+(record.status==='approved'?'согласовано':'предложены изменения')+'</p>':
      '<div class="ff-actions"><button type="button" class="btn primary" data-approve>Подтвердить выбор</button><button type="button" class="btn" data-change>Запросить изменения</button></div>')+
      '<p class="ff-feedback" data-feedback hidden role="status"></p>';
    $(host,'[data-back]').onclick=back;
    if(readonly)return;
    const boxes=$$(host,'[data-opt]'),approve=$(host,'[data-approve]'),change=$(host,'[data-change]');
    let revision=record.revision,busy=false,selected=[...record.selected_optional];
    const freeze=flag=>{busy=flag;boxes.forEach(b=>b.disabled=flag);approve.disabled=flag;change.disabled=flag;};
    boxes.forEach(b=>b.onchange=async()=>{
      if(busy)return;
      freeze(true);const newSelection=boxes.filter(x=>x.checked).map(x=>Number(x.dataset.opt));
      try{
        const result=await post('/shared-inbox/'+encodeURIComponent(record.share_id)+'/selection',
          {revision,included_optional:newSelection});
        if(!isCurrent())return;
        selected=newSelection;revision=result.revision;$(host,'[data-total]').textContent=money(result.selected_total_kopecks,doc.currency);
      }catch(error){boxes.forEach(x=>x.checked=selected.includes(Number(x.dataset.opt)));feedback(host,error.message);}
      finally{if(isCurrent())freeze(false);}
    });
    const send=async action=>{
      if(busy)return;freeze(true);
      try{
        await post('/shared-inbox/'+encodeURIComponent(record.share_id)+'/approve',{revision,action});
        const result=await api('/shared-inbox/'+encodeURIComponent(record.share_id));
        if(isCurrent())renderOffer(host,result,back,isCurrent);
      }catch(error){feedback(host,error.message);if(isCurrent())freeze(false);}
    };
    approve.onclick=()=>send('approve');change.onclick=()=>send('request_changes');
  }
  return {render:(section,active)=>section==='inbox'?inbox(active):fieldwork(active),stop:()=>{}};
})();
