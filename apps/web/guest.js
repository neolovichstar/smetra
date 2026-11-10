/* Local scratchpad only: no guest accounts, API requests or entitlement changes. */
window.SmetraGuest=(()=>{
  const KEY='smetra.guest.draft.v1',MAX_ROWS=10,MAX_BYTES=16000;
  let active=false,host=null,draft=null,callbacks={},generation=0,persistent=true;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clean=value=>{
    if(!value||typeof value!=='object')return null;
    return {title:String(value.title||'Моя первая смета').slice(0,120),client:'',description:'',items:(Array.isArray(value.items)?value.items:[]).slice(0,MAX_ROWS).map(row=>({
      name:String(row?.name||'').slice(0,160),quantity:String(row?.quantity??'1').slice(0,20),unit:String(row?.unit||'м²').slice(0,12),
      unit_price:Number.isSafeInteger(row?.unit_price)&&row.unit_price>=0&&row.unit_price<=100000000?row.unit_price:0,
      coefficient:'1',markup:'0',discount:'0',tax:'0',cost_price:0,category:row?.category==='Материалы'?'Материалы':'Работы',optional:false,included:true
    }))};
  };
  function load(){try{const raw=localStorage.getItem(KEY);return raw&&raw.length<=MAX_BYTES?clean(JSON.parse(raw)):null}catch{return null}}
  function persist(){try{localStorage.setItem(KEY,JSON.stringify(draft));persistent=true}catch{persistent=false}}
  function leave(){active=false;generation++;host?.remove();host=null;document.body.classList.remove('guest-mode')}
  function askAuth(){if(active)callbacks.onAuth?.()}
  function body(html){const target=host?.querySelector('#guest-body');if(active&&target)target.innerHTML=html}
  function home(){
    body('<div class="guest-intro"><span class="overline">ГОСТЕВОЙ РЕЖИМ</span><h1>Начните с расчёта.</h1><p class="muted">Калькуляторы и один черновик до 10 позиций.</p><div class="guest-actions"><button class="btn primary" data-guest="draft">'+(draft?'Продолжить черновик':'Составить черновик')+'</button><button class="btn" data-guest="calculators">Калькуляторы материалов</button></div><div class="guest-signin"><button class="btn" data-guest="auth">Войти или создать аккаунт</button><p class="muted">Для сохранения, ИИ и экспорта.</p></div><details class="guest-help"><summary>О гостевом режиме</summary><p class="muted">Черновик хранится только на этом устройстве. Очистка данных удалит его. После входа можно перенести черновик в аккаунт; сохранение, ИИ, отправка заказчику и экспорт доступны в пределах тарифа.</p></details></div>');
  }
  function total(){
    const target=host?.querySelector('#guest-total');if(!target)return false;
    try{
      let sum=0;
      for(const row of draft.items){if(!/^\d{1,6}(?:[.,]\d{1,4})?$/.test(row.quantity)||Number(row.quantity.replace(',','.'))<=0)throw Error('Укажите положительное количество, до 4 знаков после запятой.');sum+=window.Workspace.calculateLineTotal({...row,quantity:row.quantity.replace(',','.')})}
      if(!Number.isSafeInteger(sum))throw Error('Сумма слишком велика.');
      target.textContent=new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB'}).format(sum/100);
      host.querySelector('#guest-error').textContent=persistent?'Предварительный черновик. Перед сохранением проверьте объёмы и цены.':'Память устройства недоступна. Не закрывайте приложение до переноса черновика в аккаунт.';
      return true;
    }catch(error){target.textContent='—';host.querySelector('#guest-error').textContent=error.message;return false}
  }
  function editor(){
    draft=clean(draft)||{title:'Моя первая смета',items:[]};
    if(!draft.items.length)draft.items.push(clean({items:[{name:'',quantity:'1',unit:'м²',unit_price:0}]}).items[0]);
    body('<button class="btn small" data-guest="home">← Начало</button><h1>Черновик сметы</h1><label class="field">Название<input id="guest-title" maxlength="120" value="'+esc(draft.title)+'"></label><div class="guest-rows">'+draft.items.map((row,i)=>'<section class="panel guest-row" data-row="'+i+'"><label>Работа или материал<input data-field="name" maxlength="160" value="'+esc(row.name)+'" placeholder="Например, покраска стен"></label><div class="guest-row-numbers"><label>Количество<input data-field="quantity" inputmode="decimal" maxlength="20" value="'+esc(row.quantity)+'"></label><label>Единица<input data-field="unit" maxlength="12" value="'+esc(row.unit)+'"></label><label>Цена за единицу, ₽<input data-field="price" inputmode="decimal" maxlength="12" value="'+esc(row.unit_price/100)+'"></label></div><button type="button" class="btn small" data-remove="'+i+'" aria-label="Удалить позицию '+(i+1)+'">Удалить</button></section>').join('')+'</div><div class="guest-actions"><button class="btn" data-guest="add" '+(draft.items.length>=MAX_ROWS?'disabled':'')+'>Добавить позицию · '+draft.items.length+'/10</button><strong>Итого: <span id="guest-total"></span></strong></div><p id="guest-error" class="muted" role="status"></p><div class="guest-actions"><button class="btn primary" data-guest="save">Сохранить в аккаунт</button><button class="btn small" data-guest="clear">Удалить черновик</button></div>');
    host.querySelector('#guest-title').oninput=event=>{draft.title=event.target.value;persist()};
    host.querySelectorAll('[data-field]').forEach(input=>input.oninput=()=>{
      const row=draft.items[Number(input.closest('[data-row]').dataset.row)],field=input.dataset.field;
      if(field==='price'){
        try{const price=window.Workspace.majorToKopecks(input.value.replace(',','.'));if(price>100000000)throw Error('Цена слишком велика.');row.unit_price=price;input.setCustomValidity('')}
        catch(error){input.setCustomValidity(error.message);host.querySelector('#guest-error').textContent=error.message;return}
      }else row[field]=input.value;
      persist();total();
    });
    persist();total();
  }
  async function calculators(){
    const mine=++generation;body('<p role="status">Открываем калькуляторы…</p>');
    try{
      await window.SmetraLoadFeature('calculators');if(!active||mine!==generation)return;
      window.SmetraCalculators.render({view:html=>body('<button class="btn small" data-guest="home">← Начало</button>'+html),onDraft:async next=>{
        if(!active)return;
        if(draft?.items?.some(row=>row.name)&&!await window.SmetraDialog.confirm({title:'Заменить гостевой черновик?',message:'В гостевом режиме доступен один черновик. Текущий будет заменён расчётом материалов.',confirmLabel:'Заменить'}))return;
        if(!active)return;draft=clean(next);persist();editor();
      }});
    }catch(error){if(active&&mine===generation)body('<p role="alert">'+esc(error.message)+'</p><button class="btn" data-guest="home">Назад</button>')}
  }
  async function click(event){
    const button=event.target.closest('button');if(!button||!active)return;
    if(button.hasAttribute('data-remove')){draft.items.splice(Number(button.dataset.remove),1);editor();return}
    switch(button.dataset.guest){
      case 'home':generation++;home();break;
      case 'auth':askAuth();break;
      case 'draft':generation++;editor();break;
      case 'calculators':void calculators();break;
      case 'add':if(draft.items.length<MAX_ROWS){draft.items.push({name:'',quantity:'1',unit:'м²',unit_price:0});editor()}break;
      case 'save':
        if(!total()||!host.querySelector('#guest-title').value.trim()||!draft.items.every(row=>row.name.trim()&&row.unit.trim())||host.querySelector('input:invalid')){host.querySelector('#guest-error').textContent='Заполните название, позиции, количество и корректные цены.';return}
        try{const next=clean(draft);next.items.forEach(row=>row.quantity=row.quantity.replace(',','.'));sessionStorage.setItem('smetra.previewDraft',JSON.stringify(next));askAuth()}
        catch{host.querySelector('#guest-error').textContent='Не удалось подготовить перенос. Проверьте доступ к памяти устройства.'}break;
      case 'clear':
        if(await window.SmetraDialog.confirm({title:'Удалить гостевой черновик?',message:'Это действие удалит черновик только с этого устройства.',confirmLabel:'Удалить',danger:true})){if(!active)return;draft=null;try{localStorage.removeItem(KEY);sessionStorage.removeItem('smetra.previewDraft')}catch{}home()}break;
    }
  }
  function enter(options={}){
    leave();callbacks=options;draft=load();active=true;
    document.querySelector('#auth')?.classList.add('hidden');document.body.classList.remove('auth-mode');document.body.classList.add('guest-mode');
    host=document.createElement('main');host.id='smetra-guest';host.className='guest-page';
    host.innerHTML='<header class="guest-header"><a class="guest-brand" href="/">сметра<span>.</span></a></header><div id="guest-body"></div><footer><a href="/terms">Условия использования</a> · <a href="/privacy">Конфиденциальность</a></footer>';
    document.body.append(host);host.addEventListener('click',click);home();
    document.querySelector('.skip-link')?.setAttribute('href','#guest-body');
    host.querySelector('#guest-body').tabIndex=-1;
  }
  return {enter,leave,clean,get active(){return active}};
})();
