/* Minimal production UI for existing five-system backend. Everything is reviewed server-side. */
window.SmetraFieldFlows=(()=>{
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const $=(root,s)=>root.querySelector(s), $$=(root,s)=>Array.from(root.querySelectorAll(s));
  const money=(value,currency='RUB')=>new Intl.NumberFormat('ru-RU',{style:'currency',currency}).format((value||0)/100);
  const post=(url,data)=>api(url,{method:'POST',body:JSON.stringify(data)});
  const field=(name,label,value='',type='text',props='')=>'<label class="ff-field"><span>'+esc(label)+'</span><input name="'+name+'" type="'+type+'" value="'+esc(value)+'" '+props+'></label>';
  const section=(id,label,title,description,body)=>'<section class="ff-section" id="'+id+'"><span class="ff-kicker">'+label+'</span><h2>'+title+'</h2><p class="ff-description">'+description+'</p>'+body+'<p class="ff-feedback" data-feedback role="status" hidden></p></section>';
  function feedback(host,message){const el=$(host,'[data-feedback]');if(el){el.hidden=false;el.textContent=message;}}
  function encode64(bytes){let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(text);}
  async function readFile(file,limit){if(!file||!file.size||file.size>limit)throw Error('Файл превышает лимит '+(limit/1e6).toFixed(1)+' МБ');return new Uint8Array(await file.arrayBuffer());}
  let recorder=null;
  function abortRecording(){if(!recorder)return;const old=recorder;recorder=null;clearTimeout(old.timeout);old.stream.getTracks().forEach(t=>t.stop());if(old.rec.state!=='inactive')old.rec.stop();}
  document.addEventListener('smetra:before-view',abortRecording);
  async function audioToWav(blob){
    const array=await blob.arrayBuffer(),ctx=new (window.AudioContext||window.webkitAudioContext)();
    try {
      const decoded=await ctx.decodeAudioData(array);
      const sampleRate=16000,frames=Math.floor(decoded.duration*sampleRate);
      if(frames<3200||frames>480000)throw Error('Запись должна длиться от 0,2 до 30 секунд');
      const samples=decoded.getChannelData(0),rate=decoded.sampleRate,buffer=new ArrayBuffer(44+frames*2),view=new DataView(buffer);
      const ascii=(at,text)=>{for(let i=0;i<text.length;i++)view.setUint8(at+i,text.charCodeAt(i));};
      ascii(0,'RIFF');view.setUint32(4,buffer.byteLength-8,true);ascii(8,'WAVE');ascii(12,'fmt ');
      view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,sampleRate,true);
      view.setUint32(28,sampleRate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);ascii(36,'data');
      view.setUint32(40,frames*2,true);
      for(let i=0;i<frames;i++){const f=i*rate/sampleRate,k=Math.floor(f),mix=(samples[k]||0)*(1-f+k)+(samples[k+1]||0)*(f-k);
        const value=Math.min(1,Math.max(-1,mix));view.setInt16(44+i*2,Math.round(value<0?value*32768:value*32767),true);}
      return new Uint8Array(buffer);
    }finally{await ctx.close();}
  }
  async function draftRequest(sectionHost,target,endpoint,payload,button,isCurrent){
    if(button.disabled)return;
    const old=button.textContent;button.disabled=true;button.textContent='Анализируем…';
    try{
      if(!(await window.SmetraEstimateSafety.ensureConsent()))throw Error('Подтвердите условия использования ИИ.');
      const result=await post(endpoint,payload);
      if(isCurrent())showDraft(target,result,isCurrent);
    }catch(error){if(isCurrent())feedback(sectionHost,error.message);}
    finally{if(button.isConnected){button.disabled=false;button.textContent=old;}}
  }
  function showDraft(host,result,isCurrent){
    const draft=result.draft;
    if(!Array.isArray(draft?.items)||!draft.items.length){feedback(host.closest('.ff-section'),'Не получилось извлечь позиции. Попробуйте уточнить исходные данные.');return;}
    const rows=draft.items.map((line,i)=>'<div class="ff-draft-row" data-draft-row><span class="ff-row-num">'+(i+1)+'</span>'+
      field('name','Работа',line.name,'text','required maxlength="200"')+
      field('quantity','Объём',line.quantity,'number','required min="0.0001" step="any"')+
      field('unit','Ед.',line.unit,'text','required maxlength="30"')+
      field('unit_price','Цена, ₽',Number(line.unit_price||0)/100,'number','required min="0" step="0.01"')+
      (line.requires_measurement?'<small class="ff-warning">Нужен замер</small>':'')+'</div>').join('');
    host.innerHTML='<div class="ff-draft-heading"><h3>Предварительный черновик</h3><p>Проверьте все позиции: ИИ не рассчитывает итоговую сумму.</p></div>'+
      (result.transcript?'<details><summary>Распознанный текст</summary><p>'+esc(result.transcript)+'</p></details>':'')+
      '<form data-draft-form>'+field('title','Название сметы',draft.title,'text','required maxlength="120"')+
      field('client','Клиент',draft.client||'Заказчик','text','required maxlength="120"')+rows+
      '<label class="ff-consent"><input name="reviewed" type="checkbox" required>Я проверил(а) работы, единицы и расценки</label>'+
      '<div class="ff-actions"><button type="submit" class="btn primary">Сохранить черновик</button><span class="ff-hint">Клиенту не отправляется</span></div><p data-feedback role="status" hidden></p></form>';
    const form=$(host,'[data-draft-form]');
    form.onsubmit=async event=>{
      event.preventDefault();if(form.dataset.pending)return;
      const items=[];
      for(const line of $$(form,'[data-draft-row]')){
        const price=Number($(line,'[name=unit_price]').value),kopecks=Math.round(price*100);
        if(!Number.isSafeInteger(kopecks)||Math.abs(price*100-kopecks)>.001){feedback(form,'Проверьте цены и округление.');return;}
        items.push({name:$(line,'[name=name]').value,quantity:$(line,'[name=quantity]').value,unit:$(line,'[name=unit]').value,unit_price:kopecks});
      }
      if(items.every(line=>line.unit_price===0)){feedback(form,'Необходимо указать хотя бы одну подтверждённую цену.');return;}
      const button=$(form,'button[type=submit]');button.disabled=true;form.dataset.pending='true';
      try{
        await post('/quotes',{title:$(form,'[name=title]').value,client:$(form,'[name=client]').value,items,
          description:draft.description||'',terms:draft.terms||'',ai_draft_usage_id:draft.ai_draft_usage_id,ai_generated:true});
        if(isCurrent())host.innerHTML='<p class="ff-success">Черновик сохранён. Проверьте итоговую стоимость в реестре.</p><a class="btn primary" href="#quotes">Открыть сметы →</a>';
      }catch(error){feedback(form,error.message);}
      finally{if(button.isConnected)button.disabled=false;delete form.dataset.pending;}
    };
  }
  function roomPayload(form){return {rooms:[{
    name:$(form,'[name=name]').value,length:$(form,'[name=length]').value,width:$(form,'[name=width]').value,
    height:$(form,'[name=height]').value,unit:'м',openings_m2:$(form,'[name=openings]').value||'0',
    mix_kg_per_m2:$(form,'[name=rate]').value||'0',bag_kg:$(form,'[name=bag]').value||'25',
    waste_percent:$(form,'[name=waste]').value||'0'
  }]};}
  async function fieldwork(isCurrent){
    const [quotes,objects]=await Promise.all([api('/quotes'),api('/construction/objects')]);if(!isCurrent())return;
    const approved=(quotes.quotes||[]).filter(x=>x.published_version>0&&['sent','viewed','changes_requested'].includes(x.approval_state));
    view('<section class="ff-page"><header class="ff-heading"><span class="ff-kicker">СМЕТРА / ИНСТРУМЕНТЫ</span><h1>Инструменты смет</h1><p>Голос, документы, обмеры и работа с клиентом — без непроверенных сумм и автоматической публикации.</p></header>'+
      section('ff-voice','01 / ГОЛОС','Смета на слух','Запишите голосовую заметку до 25 секунд или выберите аудиофайл WAV, MP3, FLAC.',
        '<div class="ff-actions"><button type="button" class="btn" data-record>Записать голос</button><span data-record-info class="ff-hint">Микрофон включается только по запросу</span></div>'+
        '<div class="ff-actions"><label class="ff-upload">Аудиофайл<input type="file" name="audio" accept=".wav,.mp3,.flac"></label><button type="button" class="btn primary" data-audio-submit>Создать черновик</button></div><div data-voice-result></div>')+
      section('ff-pdf','02 / PDF','Разбор дизайн-проекта','PDF с текстовым слоем: до 12 страниц, максимум 2 МБ. Результат нужно проверить.',
        '<form data-pdf-form><div class="ff-actions"><label class="ff-upload">PDF-проект<input type="file" accept=".pdf,application/pdf" name="pdf" required></label><button type="submit" class="btn primary">Разобрать PDF</button></div>'+
        field('instructions','Что извлечь','','text','maxlength="1500" placeholder="Ведомость отделки"')+'</form><div data-pdf-result></div>')+
      section('ff-ar','03 / ОБМЕРЫ','Геометрия помещения','Внесите результаты ручного обмера или AR-сканирования. Точные площади и расход посчитает сервер.',
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
      section('ff-share','04 / ОТПРАВКА','Отправка сметы клиенту','Клиент увидит опубликованную версию после входа с подтверждённым email.',
        '<form data-share-form><label class="ff-field"><span>Опубликованная смета</span><select name="quote" required><option value="">Выберите смету</option>'+
        approved.map(q=>'<option value="'+esc(q.id)+'">'+esc(q.title)+' · '+money(q.amount_kopecks,q.currency)+'</option>').join('')+'</select></label>'+
        field('email','Email клиента','','email','required autocomplete="email" maxlength="254" placeholder="client@example.ru"')+
        '<div class="ff-actions"><button type="submit" class="btn primary" '+(approved.length?'':'disabled')+'>Отправить клиенту</button><a href="#quotes" class="ff-link">Реестр смет →</a></div></form>'+
        (approved.length?'':'<p class="ff-hint">Сначала опубликуйте проверенную смету.</p>')+'<div data-share-result></div>')+'</section>');
    const voice=document.querySelector('#ff-voice'),record=$(voice,'[data-record]'),fileButton=$(voice,'[data-audio-submit]');
    const voiceHost=$(voice,'[data-voice-result]');
    const useAudio=async bytes=>draftRequest(voice,voiceHost,'/voice/draft',{format:'wav',audio:encode64(bytes)},fileButton,isCurrent);
    record.onclick=async()=>{
      if(recorder){const current=recorder;recorder=null;clearTimeout(current.timeout);current.rec.stop();record.textContent='Записать голос';return;}
      if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){feedback(voice,'Микрофон недоступен. Загрузите аудио.');return;}
      try{
        const stream=await navigator.mediaDevices.getUserMedia({audio:true});
        if(!isCurrent()){stream.getTracks().forEach(t=>t.stop());return;}
        const chunks=[],rec=new MediaRecorder(stream);
        rec.ondataavailable=event=>{if(event.data.size)chunks.push(event.data);};
        rec.onstop=async()=>{
          stream.getTracks().forEach(t=>t.stop());
          if(!chunks.length||!isCurrent())return;
          try{await useAudio(await audioToWav(new Blob(chunks,{type:rec.mimeType})));}
          catch(error){feedback(voice,error.message);}
        };
        rec.start();record.textContent='Остановить запись';
        const timeout=setTimeout(()=>{if(recorder?.rec===rec){recorder=null;rec.stop();record.textContent='Записать голос';}},25000);
        recorder={rec,stream,timeout};
      }catch(error){feedback(voice,error.name==='NotAllowedError'?'Разрешите доступ к микрофону.':'Не получилось начать запись.');}
    };
    fileButton.onclick=async()=>{
      try{
        const file=$(voice,'[name=audio]').files[0],bytes=await readFile(file,1400000);
        const format=file.name.split('.').pop().toLowerCase();
        if(!['mp3','wav','flac'].includes(format))throw Error('Поддерживаются WAV, MP3 и FLAC.');
        await draftRequest(voice,voiceHost,'/voice/draft',{format,audio:encode64(bytes)},fileButton,isCurrent);
      }catch(error){feedback(voice,error.message);}
    };
    const pdf=document.querySelector('#ff-pdf'),pdfForm=$(pdf,'[data-pdf-form]');
    pdfForm.onsubmit=async event=>{
      event.preventDefault();
      try{
        const file=$(pdfForm,'[name=pdf]').files[0],bytes=await readFile(file,2000000);
        if(!file.name.toLowerCase().endsWith('.pdf'))throw Error('Выберите PDF-файл.');
        await draftRequest(pdf,$(pdf,'[data-pdf-result]'),'/design-projects/draft',
          {file:{name:file.name.slice(0,180),mime:'application/pdf',content:encode64(bytes)},
           instructions:$(pdfForm,'[name=instructions]').value},$(pdfForm,'button[type=submit]'),isCurrent);
      }catch(error){feedback(pdf,error.message);}
    };
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
    const share=document.querySelector('#ff-share'),form=$(share,'[data-share-form]');
    form.onsubmit=async event=>{
      event.preventDefault();const button=$(form,'button[type=submit]');button.disabled=true;
      try{
        const result=await post('/shares',{quote_id:$(form,'[name=quote]').value,email:$(form,'[name=email]').value});
        if(!isCurrent())return;
        const host=$(share,'[data-share-result]');
        host.innerHTML='<p class="ff-success">Приглашение отправлено. Доступ ограничен почтой получателя.</p><button class="ff-link" type="button" data-check>Проверить ответ</button><span data-share-status></span>';
        $(host,'[data-check]').onclick=async()=>{
          try{
            const response=await api('/shares/'+encodeURIComponent(result.id));
            $(host,'[data-share-status]').textContent=' · '+({approved:'Согласовано',changes_requested:'Есть предложения по изменениям',draft:'Ответ в работе'}[response.response?.status]||'Ожидает клиента');
          }catch(error){feedback(share,error.message);}
        };
      }catch(error){feedback(share,error.message);}
      finally{button.disabled=false;}
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
  return {render:(section,active)=>section==='inbox'?inbox(active):fieldwork(active),stop:abortRecording};
})();