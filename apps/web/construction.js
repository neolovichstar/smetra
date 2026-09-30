/* Field workflow: object -> room -> measured quantity -> estimate. */
(() => {
  let selected = null;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const val = (form, name) => form.elements[name]?.value?.trim() || '';
  const send = (path, data) => api(path, {method:'POST', body:JSON.stringify(data)});
  const money = kopecks => new Intl.NumberFormat('ru-RU', {style:'currency', currency:'RUB'}).format((kopecks || 0) / 100);
  const number = value => Number(String(value).replace(',', '.'));
  const field = (name, label, type='text', extra='') => `<label><span>${label}</span><input name="${name}" type="${type}" ${extra}></label>`;
  const options = (items, selectedId='') => items.map(item => `<option value="${esc(item.id)}" ${item.id===selectedId?'selected':''}>${esc(item.name)}</option>`).join('');
  const kinds = {work:'Работа',material:'Материал',equipment:'Оборудование',service:'Услуга',other:'Прочее'};
  async function request(path, data, after) {
    try { await send(path, data); await after(); }
    catch (error) { notify(error.message); }
  }
  async function list() {
    const result = await api('/construction/objects');
    view(`<div class="topline"><div><span class="eyebrow">СТРОИТЕЛЬНЫЙ РЕЖИМ</span><h1>Объекты и замеры</h1><p class="muted">От размеров помещения до сметы и контроля выполнения.</p></div></div>
      <section class="construction-intro"><div><strong>Новый объект</strong><small>Обычные сметы остаются доступны отдельно.</small></div><form id="construction-new" class="construction-inline">${field('name','Название объекта','text','required maxlength="200" placeholder="Квартира на Лесной"')}<button class="btn primary">Создать объект</button></form></section>
      <section class="construction-list"><div class="construction-section-title"><h2>В работе</h2><span>${result.items.length}</span></div>${result.items.length?result.items.map(item=>`<button class="construction-object" data-id="${esc(item.id)}"><span><strong>${esc(item.name)}</strong><small>${esc(item.description || 'Замеры, объёмы и смета')}</small></span><span class="construction-object-right">${item.quote_id?'Смета создана':'Замеры'} <b>↗</b></span></button>`).join(''):'<p class="construction-empty">Создайте объект и добавьте первое помещение.</p>'}</section>`);
    document.querySelector('#construction-new').onsubmit = event => {event.preventDefault();const form=event.currentTarget;request('/construction/objects',{name:val(form,'name')},async()=>{const objects=await api('/construction/objects');selected=objects.items[0]?.id;await detail()})};
    document.querySelectorAll('.construction-object').forEach(button => button.onclick=()=>{selected=button.dataset.id;detail()});
  }
  async function detail() {
    const data = await api('/construction/objects/' + encodeURIComponent(selected));
    const obj=data.object, zones=data.zones, rows=data.quantities;
    view(`<div class="construction-back"><button id="construction-back" type="button">← Все объекты</button><span>ОБЪЕКТ / ${esc(obj.status.toUpperCase())}</span></div>
      <div class="topline construction-heading"><div><h1>${esc(obj.name)}</h1><p class="muted">${esc(obj.description || 'Добавьте размеры помещений, затем работы и материалы.')}</p></div><div class="topline-actions"><button id="construction-export" class="btn small">Скачать XLSX</button>${obj.quote_id?`<button id="construction-quote-open" class="btn primary">Открыть смету ↗</button>`:`<button id="construction-quote" class="btn primary" ${rows.length?'':'disabled'}>Создать смету ↗</button>`}</div></div>
      <div class="construction-metrics"><div><span>План</span><strong>${money(data.totals.planned_kopecks)}</strong></div><div><span>Факт по позициям</span><strong>${money(data.totals.actual_kopecks)}</strong></div><div><span>Себестоимость</span><strong>${money(data.totals.cost_kopecks)}</strong></div></div>
      <section class="construction-section"><div class="construction-section-title"><h2>01 / Помещения</h2><span>${zones.length}</span></div><form id="construction-zone" class="construction-inline">${field('name','Название','text','required placeholder="Кухня" maxlength="120"')}${field('length','Длина, м','number','required min="0.001" step="any" placeholder="5"')}${field('width','Ширина, м','number','required min="0.001" step="any" placeholder="4"')}${field('height','Высота, м','number','min="0" step="any" placeholder="2.8"')}<button class="btn">Добавить помещение</button></form>
      ${zones.length?zones.map(zone=>`<div class="construction-row"><strong>${esc(zone.name)}</strong><span>${esc(zone.length_m)} × ${esc(zone.width_m)} м</span><b>${(number(zone.length_m)*number(zone.width_m)).toLocaleString('ru-RU')} м²</b></div>`).join(''):'<p class="construction-empty">Помещений пока нет. Их размеры станут переменными для расчёта.</p>'}
      <form id="construction-measurement" class="construction-inline construction-subform"><label><span>Помещение</span><select name="zone_id" required><option value="">Выберите</option>${options(zones)}</select></label>${field('symbol','Переменная','text','required pattern="[a-z][a-z0-9_]{1,31}" placeholder="window_area"')}${field('value','Замер','number','required min="0" step="any" placeholder="1.5"')}<label><span>Единица</span><select name="unit"><option value="м²">м²</option><option value="м">м</option><option value="см">см</option><option value="шт.">шт.</option></select></label><button class="btn">Записать замер</button></form>
      ${data.measurements.map(item=>`<div class="construction-row"><strong>${esc(item.symbol)}</strong><span>${esc(zones.find(zone=>zone.id===item.zone_id)?.name||'Объект')}</span><b>${esc(item.value)} ${esc(item.unit)}</b></div>`).join('')}</section>
      <section class="construction-section"><div class="construction-section-title"><h2>02 / Ведомость объёмов</h2><span>${rows.length}</span></div><form id="construction-quantity" class="construction-inline construction-quantity-form"><label><span>Помещение</span><select name="zone_id" required><option value="">Выберите</option>${options(zones)}</select></label><label><span>Тип</span><select name="kind"><option value="work">Работа</option><option value="material">Материал</option><option value="equipment">Оборудование</option></select></label>${field('title','Наименование','text','required maxlength="200" placeholder="Покраска стен"')}${field('formula','Формула объёма','text','required value="area" maxlength="160"')}${field('unit_price','Цена за ед., ₽','number','min="0" step="0.01" value="0"')}<button class="btn">Рассчитать и добавить</button></form>
      <p class="construction-hint">Формула использует длину, ширину и высоту помещения: <code>area</code>, <code>perimeter * height - openings</code>, <code>volume</code>. Для материала укажите расход на единицу работы ниже.</p>
      ${rows.length?`<div class="construction-table"><div class="construction-table-head"><span>Позиция</span><span>Объём</span><span>План</span><span>Факт</span></div>${rows.map(item=>`<div class="construction-table-row"><span><strong>${esc(item.title)}</strong><small>${esc(kinds[item.kind]||item.kind)} · ${esc(item.formula)}</small></span><span>${esc(item.quantity)} ${esc(item.unit)}</span><span>${money(item.planned_total_kopecks)}</span><span>${esc(item.actual_quantity)} ${esc(item.unit)}</span></div>`).join('')}</div><form id="construction-fact" class="construction-inline construction-subform"><label><span>Выполненная позиция</span><select name="quantity_id" required>${rows.map(item=>`<option value="${esc(item.id)}">${esc(item.title)}</option>`).join('')}</select></label>${field('quantity','Фактический объём','number','required min="0.0001" step="any" placeholder="8"')}<button class="btn">Записать факт</button></form>`:'<p class="construction-empty">Добавьте работу. Объём рассчитается из реальных размеров.</p>'}
      </section><section class="construction-section"><div class="construction-section-title"><h2>03 / Материалы по норме</h2></div><form id="construction-material" class="construction-inline"><label><span>Работа</span><select name="parent_work_id" required><option value="">Выберите</option>${rows.filter(row=>row.kind==='work').map(row=>`<option value="${esc(row.id)}">${esc(row.title)} · ${esc(row.quantity)} ${esc(row.unit)}</option>`).join('')}</select></label>${field('title','Материал','text','required placeholder="Краска" maxlength="200"')}${field('consumption_rate','Расход на ед.','number','required min="0.0001" step="any" placeholder="0.2"')}${field('waste_percent','Запас, %','number','min="0" max="100" step="any" value="0"')}${field('unit_price','Цена за ед., ₽','number','min="0" step="0.01" value="0"')}<button class="btn">Добавить материал</button></form></section>
      <section class="construction-section"><div class="construction-section-title"><h2>04 / Фото и документы</h2><span id="construction-file-count"></span></div><label class="construction-upload">Прикрепить фото, PDF или TXT<input id="construction-file" type="file" accept="image/png,image/jpeg,application/pdf,text/plain" hidden></label><div id="construction-files"></div></section>`);
    document.querySelector('#construction-back').onclick=()=>{selected=null;list()};
    document.querySelector('#construction-zone').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;request(`/construction/objects/${selected}/zones`,{name:val(form,'name'),length:val(form,'length'),width:val(form,'width'),height:val(form,'height')||0},detail)};
    document.querySelector('#construction-measurement').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;request(`/construction/objects/${selected}/measurements`,{zone_id:val(form,'zone_id'),symbol:val(form,'symbol'),value:val(form,'value'),unit:val(form,'unit'),source:'manual'},detail)};
    document.querySelector('#construction-quantity').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;const price=Math.round(number(val(form,'unit_price'))*100);request(`/construction/objects/${selected}/quantities`,{zone_id:val(form,'zone_id'),kind:val(form,'kind'),title:val(form,'title'),formula:val(form,'formula'),unit_price:price,unit:val(form,'kind')==='material'?'шт.':'м²'},detail)};
    document.querySelector('#construction-material').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;const price=Math.round(number(val(form,'unit_price'))*100);request(`/construction/objects/${selected}/quantities`,{parent_work_id:val(form,'parent_work_id'),kind:'material',title:val(form,'title'),unit:'л',consumption_rate:val(form,'consumption_rate'),waste_percent:val(form,'waste_percent')||0,unit_price:price},detail)};
    const factForm=document.querySelector('#construction-fact');if(factForm)factForm.onsubmit=event=>{event.preventDefault();const form=event.currentTarget;request(`/construction/objects/${selected}/facts`,{quantity_id:val(form,'quantity_id'),quantity:val(form,'quantity')},detail)};
    document.querySelector('#construction-export').onclick=downloadSheet;
    document.querySelector('#construction-quote')?.addEventListener('click',()=>request(`/construction/objects/${selected}/quote`,{},detail));
    document.querySelector('#construction-quote-open')?.addEventListener('click',()=>{location.hash='quotes';tab='quotes';window.render()});
    document.querySelector('#construction-file').onchange=upload;
    loadFiles();
  }
  async function loadFiles(){
    try{const files=(await api('/files?construction_id='+encodeURIComponent(selected))).items;
      const count=document.querySelector('#construction-file-count'),list=document.querySelector('#construction-files');if(!count||!list)return;
      count.textContent=files.length;list.innerHTML=files.map(file=>`<div class="construction-row"><strong>${esc(file.name)}</strong><span>${Math.ceil(file.size/1024)} КБ</span><button class="btn small" data-file="${esc(file.id)}">Открыть</button></div>`).join('')||'<p class="construction-empty">Файлов пока нет.</p>';
      list.querySelectorAll('[data-file]').forEach(button=>button.onclick=()=>{const file=files.find(item=>item.id===button.dataset.file);window.SmetraFilePreview?.open(file,sessionStorage.getItem('workspace_id'))});
    }catch(error){notify(error.message)}
  }
  async function upload(event){
    const file=event.target.files[0];if(!file)return;if(file.size>5000000){notify('Максимум 5 МБ');return}
    try{const bytes=new Uint8Array(await file.arrayBuffer());let text='';for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));await send('/files',{construction_id:selected,name:file.name,content:btoa(text)});await loadFiles();notify('Файл прикреплён')}
    catch(error){notify(error.message)}finally{event.target.value=''}
  }
  async function downloadSheet(){
    try{const headers={};const workspace=sessionStorage.getItem('workspace_id');if(workspace)headers['X-Workspace-Id']=workspace;
      const response=await fetch('/api/construction/objects/'+encodeURIComponent(selected)+'/xlsx',{credentials:'same-origin',headers});if(!response.ok)throw Error((await response.json()).error||'Ошибка экспорта');const blob=await response.blob();const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download='smetra-vedomost.xlsx';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),5000)}catch(error){notify(error.message)}
  }
  window.SmetraConstruction = () => selected ? detail() : list();
})();
