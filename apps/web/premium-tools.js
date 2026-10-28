/* Premium materials, price monitoring and cloud-drive imports. */
(() => {
  const esc = escapeHtml;
  const money = (value, code) => value == null ? 'Цена не определена' : new Intl.NumberFormat('ru-RU',{style:'currency',currency:code||'RUB',maximumFractionDigits:2}).format(Number(value)/100);
  const when = value => value ? new Intl.DateTimeFormat('ru-RU',{dateStyle:'medium',timeStyle:'short'}).format(new Date(Number(value)*1000)) : 'Не проверялось';
  const provider = value => value === 'yandex_disk' ? 'Яндекс.Диск' : value === 'google_drive' ? 'Google Drive' : 'Облако';
  const state = value => ({queued:'В очереди',running:'Обработка',retry:'Повторная попытка',needs_review:'Нужна проверка',completed:'Готово',failed:'Ошибка',cancelled:'Отменено',active:'Активно',disabled:'Отключено',reauth_required:'Нужна авторизация',paused:'На паузе'})[value] || value || '—';
  const stock = value => ({in_stock:'В наличии',out_of_stock:'Нет в наличии',preorder:'Предзаказ',backorder:'Под заказ',unknown:'Не определено'})[value] || 'Не определено';
  const arr = value => Array.isArray(value) ? value : [];
  const drafts = value => arr(value).filter(q => q.status === 'draft' && !Number(q.published_version || 0));
  let selectedCloudProvider = null;
  let renderGeneration = 0;
  const quoteOptions = value => '<option value="">Не привязывать к смете</option>' + drafts(value).map(q => '<option value="' + esc(q.id) + '">' + esc(q.title || 'Черновик') + ' · ' + esc(q.client || 'Без клиента') + '</option>').join('');

  async function render(active) {
    active = active || (() => true);
    const generation = ++renderGeneration;
    const valid = () => generation === renderGeneration && active();
    let features;
    try { features = await api('/premium/features'); }
    catch (error) {
      if (!valid()) return;
      view(header('Материалы и облака','') + '<section class="premium-empty"><h2>Раздел временно недоступен</h2><p>' + esc(error.message) + '</p><button class="btn" id="premium-retry">Повторить</button></section>');
      document.querySelector('#premium-retry')?.addEventListener('click', () => render(active));
      return;
    }
    if (!valid()) return;
    if (!(features.cloud_drives && features.product_monitor && features.visual_estimates)) {
      view(header('Материалы и облака','') +
        '<section class="premium-lock"><span class="premium-kicker">РАСШИРЕННЫЕ ИНСТРУМЕНТЫ</span><h2>Материалы под контролем.</h2><p>Подключайте Яндекс.Диск и Google Drive, связывайте товарные источники со сметой и отслеживайте изменения цен. Импорт документов всегда требует вашей проверки.</p><div class="premium-lock-grid"><article><span class="premium-number">01</span><h3>Материалы</h3><p>Ссылки, характеристики и поставщики рядом с позициями сметы.</p></article><article><span class="premium-number">02</span><h3>История цен</h3><p>Наблюдения и уведомления. Сметная цена не меняется сама.</p></article><article><span class="premium-number">03</span><h3>Облачные документы</h3><p>Синхронизация папок и импорт после ручного подтверждения.</p></article></div><p class="premium-lock-note">Инструменты предусмотрены для тарифов «PRO Плюс» и «TEAM».</p><button class="btn primary" id="premium-go-billing" type="button">Посмотреть тариф</button></section>');
      document.querySelector('#premium-go-billing')?.addEventListener('click', () => { tab='billing'; location.hash='billing'; window.render(); });
      return;
    }

    let quotes=[], sources=[], connections=[], folders=[], jobs=[];
    try {
      const r = await Promise.all([api('/quotes'),api('/premium/product-sources'),api('/premium/cloud/connections'),api('/premium/cloud/folders'),api('/premium/cloud/jobs')]);
      quotes = r[0].quotes || r[0].items || []; sources = r[1].sources || []; connections = r[2].connections || []; folders = r[3].folders || []; jobs = r[4].jobs || [];
    } catch (error) {
      if (!valid()) return;
      view(header('Материалы и облака','') + '<section class="premium-empty"><h2>Не удалось загрузить раздел</h2><p>' + esc(error.message) + '</p><button class="btn" id="premium-retry">Повторить</button></section>');
      document.querySelector('#premium-retry')?.addEventListener('click', () => render(active));
      return;
    }
    if (!valid()) return;
    const draftsList = drafts(quotes);
    const activeCloudFolders = cloud => folders.filter(f => f.provider === cloud && f.status === 'active');
    const sourceHtml = sources.length ? sources.map(s => '<article class="premium-source"><div class="premium-source-main"><span class="premium-source-host">' + esc(s.hostname) + '</span><h3>' + esc(s.product_title || s.url) + '</h3><p>' + esc(s.brand || 'Бренд не определён') + (s.sku ? ' · Артикул ' + esc(s.sku) : '') + '</p><div class="premium-source-meta"><span>' + esc(stock(s.availability)) + '</span><span>Проверено: ' + esc(when(s.last_checked_at)) + '</span><span>' + esc(state(s.source_status)) + '</span></div>' + (s.last_error ? '<p class="premium-error">' + esc(s.last_error) + '</p>' : '') + '</div><div class="premium-source-actions"><strong>' + esc(money(s.price_kopecks,s.currency)) + '</strong><button class="btn small" type="button" data-premium-history="' + esc(s.id) + '">История цен</button>' + (s.monitored ? '<button class="btn small" type="button" data-premium-disable-source="' + esc(s.id) + '">Остановить</button>' : '') + '</div><div class="premium-history" data-premium-history-view="' + esc(s.id) + '" hidden></div></article>').join('') : '<p class="premium-empty-state">Проверенные товары появятся здесь. Добавьте первую ссылку выше.</p>';
    // Selection and OAuth/disconnection must be separate controls.
    if (!['yandex_disk','google_drive'].includes(selectedCloudProvider)) {
      selectedCloudProvider = connections.find(c=>c.status==='active')?.provider || 'yandex_disk';
    }
    const selectedConnection=connections.find(c=>c.provider===selectedCloudProvider&&c.status==='active');
    const cloudCards = [
      ['yandex_disk','Яндекс.Диск','yandex-disk.svg'],
      ['google_drive','Google Drive','google-drive.png'],
    ].map(([id,label,icon])=>{
      const c=connections.find(row=>row.provider===id&&row.status==='active');
      const connected=Boolean(c),selected=id===selectedCloudProvider;
      const action=connected?'data-premium-disconnect="'+esc(c.id)+'"':'data-premium-connect="'+id+'"';
      const meta=connected?'Подключено · '+esc(c.account_label||'Аккаунт'):'Не подключён';
      return '<div class="premium-connect'+(connected?' is-connected':'')+(selected?' is-selected':'')+'" data-cloud-card="'+id+'">'
        +'<button class="premium-connect-select" type="button" data-premium-select="'+id+'" aria-pressed="'+selected+'" aria-controls="premium-cloud-folders" aria-label="Показать папки: '+label+'">'
        +'<span class="premium-provider-symbol" aria-hidden="true"><img src="/assets/providers/'+icon+'" width="40" height="40" alt=""></span>'
        +'<span class="premium-connect-copy"><strong>'+label+'</strong><small>'+meta+'</small></span>'
        +'</button><button class="premium-connect-action" type="button" '+action+' aria-label="'+(connected?'Отключить ':'Подключить ')+label+'">'
        +(connected?'Отключить':'Подключить')+'</button></div>';
    }).join('');
    const folderHtml = cloud => {
      const scoped=activeCloudFolders(cloud);
      return scoped.length ? scoped.map(f=>'<article class="premium-folder"><div><strong>'+esc(f.folder_name||f.folder_id)+'</strong><small>'+esc(f.account_label||provider(f.provider))+(f.quote_id?' · Привязана к смете':'')+'</small>'+(f.last_error?'<small class="premium-error">'+esc(f.last_error)+'</small>':'<small>'+(f.sync_requested?'Ожидает фоновой проверки':f.last_synced_at?'Обновлено: '+esc(when(f.last_synced_at)):'Автоматическое обновление запланировано')+'</small>')+'</div><div class="premium-folder-actions"><span class="premium-state">'+(f.last_error?'Ошибка':'Авто')+'</span><button class="btn small" type="button" data-premium-disable-folder="'+esc(f.id)+'" aria-label="Убрать папку '+esc(f.folder_name||f.folder_id)+' из синхронизации">Убрать</button></div></article>').join('') : '<p class="premium-empty-state">Здесь пока нет добавленных папок. Выберите каталог выше — дальнейшее обновление произойдёт автоматически.</p>';
    };
    const jobsHtml = jobs.length ? jobs.map(j => '<article class="premium-job" data-premium-job-card="' + esc(j.id) + '"><span class="premium-job-kind">' + (j.mime === 'application/pdf' ? 'PDF' : 'DOC') + '</span><div class="premium-job-copy"><strong>' + esc(j.name) + '</strong><span>' + esc(provider(j.provider)) + (j.quote_id ? ' · Смета привязана' : ' · Без сметы') + '</span><small>' + esc(state(j.status)) + (j.updated_at ? ' · ' + esc(when(j.updated_at)) : '') + '</small>' + (j.error ? '<small class="premium-error">' + esc(j.error) + '</small>' : '') + '</div>'+(j.status==='failed'?'<button class="btn small" type="button" data-premium-retry="'+esc(j.id)+'">Повторить</button>':'<button class="btn small" type="button" data-premium-review="'+esc(j.id)+'">Проверить</button>')+'<div class="premium-job-review" data-premium-job-review="' + esc(j.id) + '" hidden></div></article>').join('') : '<p class="premium-empty-state">Документов для проверки пока нет. Они появятся после синхронизации папок.</p>';

    view(header('Материалы и облака','') +
      '<section class="premium-tools-page"><div class="premium-intro"><div class="premium-intro-copy"><h2>Цены и документы под контролем</h2><p>Следите за ценами поставщиков и собирайте документы из облака. Изменения попадут в смету только после вашей проверки.</p></div><div class="premium-intro-metrics" aria-label="Обзор материалов"><div class="premium-intro-metric"><strong>' + sources.length + '</strong><span>источников цен</span></div><div class="premium-intro-metric"><strong>' + jobs.filter(j => j.status === 'needs_review').length + '</strong><span>документов к проверке</span></div></div></div>' +
      '<section class="premium-section"><div class="premium-section-heading"><div><span class="premium-kicker">01 / ПОСТАВЩИКИ</span><h2>Проверить и отслеживать товар</h2><p>Добавьте ссылку на товар и при необходимости свяжите её с позицией черновика.</p></div></div><form id="premium-product-form" class="premium-form"><div class="premium-form-grid"><div class="field"><label for="premium-product-url">Ссылка на товар</label><input id="premium-product-url" name="url" type="url" maxlength="2048" placeholder="https://…" required></div><div class="field"><label for="premium-product-quote">Черновик сметы</label><select id="premium-product-quote" name="quote_id">' + quoteOptions(quotes) + '</select></div><div class="field"><label for="premium-product-item">Позиция сметы</label><select id="premium-product-item" name="quote_item_id" disabled><option value="">Сначала выберите смету</option></select></div><div class="premium-form-submit"><button class="btn primary" type="submit" id="premium-product-preview-button">Проверить ссылку</button><span>Проверка не меняет стоимость сметы.</span></div></div></form><div id="premium-product-preview" class="premium-preview" hidden></div><div class="premium-list-block"><div class="premium-list-heading"><h3>Мониторинг цен</h3><span>' + sources.length + ' источников</span></div><div class="premium-source-list">' + sourceHtml + '</div></div></section>' +
      '<section class="premium-section"><div class="premium-section-heading"><div><span class="premium-kicker">02 / СИНХРОНИЗАЦИЯ</span><h2>Облачные документы</h2><p>Подключите диск, выберите папку и укажите, какие документы синхронизировать. Ваши файлы не меняются.</p></div></div>'
      +'<div class="premium-cloud-select-heading"><span class="premium-cloud-step">ШАГ 1 · ВЫБОР ДИСКА</span><span>Нажмите на карточку нужного сервиса</span></div>'
      +'<div class="premium-connect-row" role="group" aria-label="Выбрать облачный диск">'+cloudCards+'</div>'
      +'<section class="premium-cloud-folders" id="premium-cloud-folders" aria-label="Папки выбранного диска"><div class="premium-cloud-folders-heading"><div><span class="premium-cloud-step">ШАГ 2 · ВЫБОР ПАПКИ</span><h3>Папки и файлы</h3><p>Выберите папку или откройте вложенную. Файлы показаны для просмотра — они не выбираются по отдельности.</p></div><span id="premium-cloud-name">'+esc(provider(selectedCloudProvider))+'</span></div>'
      +'<form id="premium-folder-form" class="premium-form"><input id="premium-folder-connection" name="connection_id" type="hidden" value="'+esc(selectedConnection?.id||'')+'"><input id="premium-folder-id" name="folder_id" type="hidden" required>'
      +'<div id="premium-folder-browser" class="premium-folder-browser" aria-label="Выбор папки облака"><div class="premium-folder-browser-head"><button class="premium-folder-back" id="premium-folder-back" type="button" disabled aria-label="На уровень выше">←</button><span id="premium-folder-location" title="Текущий каталог">Мой диск</span><button class="btn small premium-folder-pick-current" id="premium-folder-select-current" type="button" disabled>Выбрать «Мой диск»</button></div><div id="premium-folder-entries" class="premium-folder-entries" role="list" aria-label="Содержимое папки">Загружаем содержимое…</div><button class="btn small hidden" id="premium-folder-next" type="button">Показать ещё</button></div>'
      +'<details class="premium-folder-options"><summary>Дополнительно: смета и вложенные папки</summary><div class="premium-folder-options-content"><div class="field"><label for="premium-folder-quote">Черновик сметы для импорта</label><select id="premium-folder-quote" name="quote_id">'+quoteOptions(quotes)+'</select></div><label class="premium-checkbox"><input type="checkbox" name="recursive" checked><span><strong>Включить вложенные папки</strong><small>Синхронизация ограничена по глубине и числу файлов.</small></span></label></div></details>'
      +'<div class="premium-folder-confirm"><div class="premium-folder-selected"><span class="premium-folder-selected-icon" aria-hidden="true">✓</span><span id="premium-folder-choice" role="status" aria-live="polite">Сначала выберите папку выше</span></div><button class="btn premium-folder-start" type="submit" id="premium-folder-submit" disabled>Добавить папку</button></div><p class="premium-folder-disclaimer">Импорт позиций в смету потребует отдельного подтверждения.</p><p class="form-error" role="alert"></p></form></section>'
      +'<div class="premium-list-block premium-cloud-sync-list"><div class="premium-list-heading"><h3>Добавленные папки</h3><div class="premium-synced-actions"><span>Обновляются автоматически</span><span id="premium-cloud-folder-count">'+activeCloudFolders(selectedCloudProvider).length+' папок</span></div></div><div class="premium-folder-list" aria-label="Синхронизируемые папки">'+folderHtml(selectedCloudProvider)+'</div></div></section>'+
      '<section class="premium-section"><div class="premium-section-heading"><div><span class="premium-kicker">03 / ПРОВЕРКА</span><h2>Импорт документов</h2><p>Данные попадут в черновик только после проверки и отдельного подтверждения.</p></div><button type="button" class="btn" id="premium-refresh-jobs">Обновить очередь</button></div><div class="premium-job-list">' + jobsHtml + '</div></section></section>');

    if (new URLSearchParams(location.search).get('cloud') === 'connected') {
      history.replaceState(null,'','/app#premium'); notify('Облако подключено. Обновляем список…'); await render(active); return;
    }
    let quote = null, product = null, quoteRequest = 0;
    const quoteSelect = document.querySelector('#premium-product-quote');
    const itemSelect = document.querySelector('#premium-product-item');
    const preview = document.querySelector('#premium-product-preview');
    async function loadQuote(id) {
      const request = ++quoteRequest;
      quote=null; itemSelect.disabled=true; itemSelect.innerHTML='<option value="">Загружаем позиции…</option>';
      if (product) paintProduct();
      if (!id) { itemSelect.innerHTML='<option value="">Выберите черновик сметы</option>'; if (product) paintProduct(); return; }
      try {
        const r=await api('/quotes/'+encodeURIComponent(id)); if(!valid()||request!==quoteRequest||quoteSelect.value!==id||!itemSelect.isConnected)return;
        if(!r.quote || r.quote.status!=='draft' || Number(r.quote.published_version||0)>0) { itemSelect.innerHTML='<option value="">Доступны только черновики</option>'; return; }
        quote=r.quote; const items=arr(quote.items);
        itemSelect.innerHTML=items.map(i=>'<option value="'+esc(i.line_id||'')+'">'+esc(i.name||'Без названия')+' · '+esc(i.quantity||'1')+' '+esc(i.unit||'шт.')+'</option>').join('');
        if(!items.length)itemSelect.innerHTML='<option value="">Добавьте позицию в смету</option>';
        itemSelect.disabled=!items.length; if(product)paintProduct();
      } catch (error) { if(!valid()||request!==quoteRequest||!itemSelect.isConnected)return;itemSelect.innerHTML='<option value="">Не удалось загрузить позиции</option>'; notify(error.message); }
    }
    function paintProduct() {
      const ready=Boolean(quote && quote.status==='draft' && itemSelect.value);
      preview.hidden=false;
      preview.innerHTML='<div class="premium-preview-top"><span class="premium-kicker">РЕЗУЛЬТАТ ПРОВЕРКИ</span><span class="premium-state">'+esc(stock(product.availability))+'</span></div><div class="premium-preview-body"><div><h3>'+esc(product.product_title||'Карточка товара')+'</h3><p>'+esc(product.brand||'Бренд не определён')+(product.sku?' · Артикул '+esc(product.sku):'')+'</p><a href="'+esc(product.url)+'" target="_blank" rel="noopener noreferrer">'+esc(product.hostname||product.url)+' ↗</a></div><strong>'+esc(money(product.price_kopecks,product.currency))+'</strong></div><p class="premium-preview-note">Наблюдение: '+esc(when(product.observed_at))+'. Цена сметы не изменена.</p><div class="premium-preview-actions"><button class="btn primary" id="premium-save-source" type="button" '+(ready?'':'disabled')+'>Привязать к позиции и следить за ценой</button><span>'+(ready?'Цена магазина будет сохранена отдельно.':'Выберите черновик сметы и позицию.')+'</span></div>';
      preview.querySelector('#premium-save-source')?.addEventListener('click',async ev=>{
        const button=ev.currentTarget;
        if(button.disabled||!valid()||!quote||!itemSelect.value||!product)return;button.disabled=true;
        try { await api('/premium/product-sources',{method:'POST',body:JSON.stringify({quote_id:quote.id,quote_item_id:itemSelect.value,revision:quote.revision,url:product.url})}); if(!valid())return;notify('Источник цены сохранён. Сметная стоимость не менялась.'); await render(active); }
        catch(error){if(valid())notify(error.message)}
        finally{if(button.isConnected)button.disabled=false}
      });
    }
    quoteSelect?.addEventListener('change',()=>loadQuote(quoteSelect.value));
    itemSelect?.addEventListener('change',()=>{if(product)paintProduct()});
    if(quoteSelect?.value)await loadQuote(quoteSelect.value);
    document.querySelector('#premium-product-form')?.addEventListener('submit',async ev=>{
      ev.preventDefault();const button=ev.currentTarget.querySelector('#premium-product-preview-button');if(button.disabled||!valid())return;button.disabled=true;button.textContent='Проверяем…';
      try { const r=await api('/premium/products/preview',{method:'POST',body:JSON.stringify({url:document.querySelector('#premium-product-url').value.trim()})}); if(!valid())return;product=r.product;paintProduct(); }
      catch(error){if(valid())notify(error.message)} finally {if(button.isConnected){button.disabled=false;button.textContent='Проверить ссылку'}}
    });
    document.querySelectorAll('[data-premium-connect]').forEach(b=>b.addEventListener('click',async()=>{
      if(b.disabled||!valid())return;b.disabled=true;try{const r=await api('/premium/cloud/oauth/'+encodeURIComponent(b.dataset.premiumConnect));if(!valid())return;if(r.authorize_url)location.assign(r.authorize_url);else throw Error('Сервис не вернул ссылку авторизации.')}catch(error){if(valid())notify(error.message);b.disabled=false}
    }));
    // Browse direct children only; lazy pagination, no all-files scan.
    const folderForm=document.querySelector('#premium-folder-form');
    const folderConnection=document.querySelector('#premium-folder-connection');
    const folderId=document.querySelector('#premium-folder-id');
    const folderEntries=document.querySelector('#premium-folder-entries');
    const folderLocation=document.querySelector('#premium-folder-location');
    const folderChoice=document.querySelector('#premium-folder-choice');
    const folderBack=document.querySelector('#premium-folder-back');
    const folderNext=document.querySelector('#premium-folder-next');
    let folderPath=[],folderCursor='',folderRequest=0,folderSelection=0,folderSaving=false;
    const folderSubmit=document.querySelector('#premium-folder-submit');
    const pickCurrent=document.querySelector('#premium-folder-select-current');
    function clearFolderSelection(){
      folderSelection++;
      folderId.value='';
      folderChoice.textContent='Сначала выберите папку выше';
      folderChoice.closest('.premium-folder-selected')?.classList.remove('has-selection');
      folderSubmit.disabled=true;
    }
    function setFolderSelection(id,name){
      folderSelection++;
      folderId.value=String(id);
      folderChoice.textContent=provider(selectedCloudProvider)+' / '+(folderPath.length ? folderPath.map(x=>x.name).join(' / ')+(name?' / ':'') : '')+name;
      folderChoice.closest('.premium-folder-selected')?.classList.add('has-selection');
      folderSubmit.disabled=folderSaving;
    }
    async function browseFolder(next=false){
      const seq=++folderRequest;
      const conn=connections.find(c=>c.id===folderConnection.value&&c.status==='active');
      const pageToken=next?folderCursor:'';
      if(!next){clearFolderSelection();folderEntries.replaceChildren();folderCursor=''}
      folderNext.classList.add('hidden');
      folderBack.disabled=folderPath.length===0;
      pickCurrent.disabled=!conn;
      folderLocation.textContent=folderPath.length?'Мой диск / '+folderPath.map(f=>f.name).join(' / '):'Мой диск';
      pickCurrent.textContent=folderPath.length?'Выбрать текущую':'Выбрать «Мой диск»';
      if(!conn){folderEntries.textContent='Этот диск пока не подключён. Нажмите «Подключить» в карточке выше.';return}
      const params=new URLSearchParams({connection_id:conn.id,parent:folderPath.length?folderPath[folderPath.length-1].id:(conn.provider==='google_drive'?'root':'/')});
      if(next&&pageToken)params.set('cursor',pageToken);
      const message=document.createElement('div');message.className='premium-folder-message';message.textContent='Загружаем содержимое…';folderEntries.append(message);
      try{
        const payload=await api('/premium/cloud/browse-folders?'+params.toString());
        if(seq!==folderRequest||!valid())return;
        message.remove();
        const rows=Array.isArray(payload.folders)?payload.folders:[];
        const files=Array.isArray(payload.files)?payload.files:[];
        if(!rows.length&&!files.length&&!next){
          const empty=document.createElement('div');empty.className='premium-folder-empty';
          empty.textContent='Здесь пока нет папок или файлов. Вы можете выбрать текущую папку для будущей синхронизации.';
          folderEntries.append(empty);
        }
        for(const entry of rows){
          // Two accessible actions per row: choose for sync or open subfolders.
          // Avoid nested buttons and click-only spans, which break keyboard use.
          const item=document.createElement('div');item.className='premium-folder-entry';item.setAttribute('role','listitem');
          const name=document.createElement('button');name.type='button';name.className='premium-folder-select';name.textContent='▱  '+String(entry.name||'Папка');name.setAttribute('aria-pressed','false');name.setAttribute('aria-label','Выбрать папку '+String(entry.name||'Папка'));
          const move=document.createElement('button');move.type='button';move.className='premium-folder-enter';move.textContent='Открыть ›';move.setAttribute('aria-label','Открыть вложенные папки: '+String(entry.name||'Папка'));
          item.append(name,move);
          name.addEventListener('click',()=>{
            folderEntries.querySelectorAll('.premium-folder-select').forEach(x=>x.setAttribute('aria-pressed','false'));
            folderEntries.querySelectorAll('.premium-folder-entry').forEach(x=>x.classList.remove('is-selected'));
            name.setAttribute('aria-pressed','true');
            item.classList.add('is-selected');
            setFolderSelection(entry.id,String(entry.name||'Папка'));
          });
          move.addEventListener('click',()=>{folderPath.push({id:entry.id,name:entry.name});void browseFolder()});
          folderEntries.append(item);
        }
        for(const entry of files){
          if(!entry||typeof entry.name!=='string')continue;
          const item=document.createElement('div');item.className='premium-cloud-file';item.setAttribute('role','listitem');
          const kind=document.createElement('span');kind.className='premium-cloud-file-kind';kind.setAttribute('aria-hidden','true');
          const extension=entry.name.split('.').pop().toUpperCase();
          kind.textContent=['PDF','XLSX','DOCX','CSV','TXT','PNG','JPG'].includes(extension)?extension:'FILE';
          const name=document.createElement('span');name.className='premium-cloud-file-name';name.textContent=entry.name;
          item.append(kind,name);folderEntries.append(item);
        }
        folderCursor=String(payload.next_cursor||'');
        folderNext.classList.toggle('hidden',!folderCursor);
      }catch(error){
        if(seq!==folderRequest||!valid())return;
        message.remove();
        const note=document.createElement('div');note.className='premium-folder-message';note.textContent='Не удалось загрузить содержимое: '+error.message;folderEntries.append(note);
      }
    }
    function selectCloud(id){
      if(!['yandex_disk','google_drive'].includes(id))return;
      selectedCloudProvider=id;
      document.querySelectorAll('[data-premium-select]').forEach(button=>{
        const selected=button.dataset.premiumSelect===id;
        button.setAttribute('aria-pressed',String(selected));
        button.closest('.premium-connect')?.classList.toggle('is-selected',selected);
      });
      const connection=connections.find(c=>c.provider===id&&c.status==='active');
      folderConnection.value=connection?.id||'';
      document.querySelector('#premium-cloud-name').textContent=provider(id);
      document.querySelector('.premium-folder-list').innerHTML=folderHtml(id);
      document.querySelector('#premium-cloud-folder-count').textContent=activeCloudFolders(id).length+' папок';
      clearFolderSelection();
      document.querySelector('#premium-folder-form .form-error').textContent='';
      folderPath=[];
      void browseFolder();
    }
    document.querySelectorAll('[data-premium-select]').forEach(button=>{
      button.addEventListener('click',()=>selectCloud(button.dataset.premiumSelect));
    });
    // Empty card area also selects. OAuth/disconnect only via the small action.
    document.querySelector('.premium-connect-row')?.addEventListener('click',event=>{
      if(event.target.closest('[data-premium-select],[data-premium-connect],[data-premium-disconnect]'))return;
      const card=event.target.closest('[data-cloud-card]');
      if(card)selectCloud(card.dataset.cloudCard);
    });
    document.querySelector('#premium-folder-select-current')?.addEventListener('click',()=>{
      const connection=connections.find(c=>c.id===folderConnection.value&&c.status==='active');
      if(!connection)return;
      setFolderSelection(folderPath.length?folderPath[folderPath.length-1].id:(connection.provider==='google_drive'?'root':'/'),folderPath.length?'':'Мой диск');
      folderEntries.querySelectorAll('.premium-folder-select').forEach(x=>x.setAttribute('aria-pressed','false'));
      folderEntries.querySelectorAll('.premium-folder-entry').forEach(x=>x.classList.remove('is-selected'));
    });
    folderBack?.addEventListener('click',()=>{folderPath.pop();void browseFolder()});
    folderNext?.addEventListener('click',()=>{if(folderCursor)void browseFolder(true)});
    if(folderConnection?.value)void browseFolder();
    document.querySelector('#premium-folder-form')?.addEventListener('submit',async ev=>{
      ev.preventDefault();if(folderSaving||!valid())return;const form=ev.currentTarget,button=form.querySelector('[type=submit]'),error=form.querySelector('[role=alert]');error.textContent='';if(!folderConnection.value){error.textContent='Сначала подключите выбранный диск.';return}if(!folderId.value){error.textContent='Выберите папку из списка перед добавлением.';return}folderSaving=true;button.disabled=true;const selection=folderSelection;
      try{
        const d=Object.fromEntries(new FormData(form));
        await api('/premium/cloud/folders',{method:'POST',body:JSON.stringify({connection_id:d.connection_id,folder_id:String(d.folder_id||'').trim(),quote_id:d.quote_id||null,recursive:form.elements.recursive.checked})});
        // Update only the folder list, never rebuild or scroll the whole page.
        const latest=await api('/premium/cloud/folders');
        if(!valid()||!folderForm.isConnected)return;
        folders=latest.folders||[];
        document.querySelector('.premium-folder-list').innerHTML=folderHtml(selectedCloudProvider);
        document.querySelector('#premium-cloud-folder-count').textContent=activeCloudFolders(selectedCloudProvider).length+' папок';
        if(selection===folderSelection)clearFolderSelection();
        notify('Папка добавлена. Обновление выполняется автоматически по расписанию.');
      }catch(err){if(valid()&&form.isConnected)error.textContent=err.message}
      finally{folderSaving=false;if(valid()&&form.isConnected)button.disabled=!folderId.value}
    });
    document.querySelector('#premium-refresh-jobs')?.addEventListener('click',()=>render(active));
    async function change(button,question,path,options,done){
      if(button.disabled||!valid())return;
      button.disabled=true;
      try{
        if(!(await window.SmetraDialog.confirm(question))||!valid()||!button.isConnected)return;
        const result=await api(path,options);
        if(valid())await done(result);
      }catch(error){if(valid())notify(error.message)}
      finally{if(button.isConnected)button.disabled=false}
    }
    document.querySelector('.premium-tools-page')?.addEventListener('click',async ev=>{
      const b=ev.target.closest('button');if(!b)return;
      if(b.dataset.premiumDisconnect){
        await change(b,{title:'Отключить облако?',message:'Синхронизации с ним тоже остановятся.',confirmLabel:'Отключить',danger:true},'/premium/cloud/connections',{method:'DELETE',body:JSON.stringify({connection_id:b.dataset.premiumDisconnect})},async()=>{notify('Облако отключено.');await render(active)});
      } else if(b.dataset.premiumDisableSource){
        await change(b,{title:'Остановить мониторинг цены?',confirmLabel:'Остановить',danger:true},'/premium/product-sources/'+encodeURIComponent(b.dataset.premiumDisableSource),{method:'DELETE',body:JSON.stringify({})},async()=>{notify('Мониторинг остановлен.');await render(active)});
      } else if(b.dataset.premiumDisableFolder){
        await change(b,{title:'Отключить эту папку?',confirmLabel:'Отключить',danger:true},'/premium/cloud/folders/'+encodeURIComponent(b.dataset.premiumDisableFolder),{method:'DELETE',body:JSON.stringify({})},async()=>{notify('Папка убрана из автоматической синхронизации.');const latest=await api('/premium/cloud/folders');if(!valid())return;folders=latest.folders||[];document.querySelector('.premium-folder-list').innerHTML=folderHtml(selectedCloudProvider);document.querySelector('#premium-cloud-folder-count').textContent=activeCloudFolders(selectedCloudProvider).length+' папок'});
      } else if(b.dataset.premiumHistory){
        const id=b.dataset.premiumHistory,target=document.querySelector('[data-premium-history-view="'+CSS.escape(id)+'"]');if(!target)return;
        if(!target.hidden){target.hidden=true;target.replaceChildren();return}target.hidden=false;target.textContent='Загружаем историю…';
        try{const r=await api('/premium/price-history/'+encodeURIComponent(id));if(!valid()||!target.isConnected||target.hidden)return;target.innerHTML=r.history?.length?'<h4>История наблюдений</h4><div class="premium-history-list">'+r.history.map(x=>'<div><span>'+esc(when(x.observed_at))+'<small>'+esc(stock(x.availability))+'</small></span><strong>'+esc(money(x.price_kopecks,x.currency))+'</strong></div>').join('')+'</div>':'<p>Пока есть только первое наблюдение. Следующая проверка запланирована автоматически.</p>'}catch(error){if(valid()&&target.isConnected&&!target.hidden)target.textContent=error.message}
      } else if(b.dataset.premiumRetry){
        if(b.disabled||!valid())return;b.disabled=true;
        try{await api('/premium/cloud/jobs/'+encodeURIComponent(b.dataset.premiumRetry)+'/retry',{method:'POST',body:'{}'});if(!valid())return;notify('Документ снова поставлен в очередь.');await render(active)}
        catch(error){if(valid())notify(error.message)}finally{if(b.isConnected)b.disabled=false}
      } else if(b.dataset.premiumReview){
        const id=b.dataset.premiumReview,target=document.querySelector('[data-premium-job-review="'+CSS.escape(id)+'"]');if(!target)return;
        if(!target.hidden){target.hidden=true;target.replaceChildren();return}target.hidden=false;target.textContent='Загружаем распознанные данные…';
        try{
          const r=await api('/premium/cloud/jobs/'+encodeURIComponent(id)),j=r.job,p=j.proposal||{},items=arr(p.items);
          if(!valid()||!target.isConnected||target.hidden)return;
          target.innerHTML='<div class="premium-review-heading"><div><span class="premium-kicker">ПРЕДЛОЖЕНИЕ К ИМПОРТУ</span><h3>'+esc(p.merchant||j.name)+'</h3><p>'+esc(p.date||'Дата не распознана')+' · '+esc(p.document_type||'Тип не определён')+'</p></div><strong>'+esc(money(p.total_kopecks,p.currency))+'</strong></div><p>'+esc(p.notes||'Проверьте строки и суммы ниже.')+'</p><div class="premium-review-lines">'+(items.length?items.map((i,n)=>'<div><span>'+(n+1)+'. '+esc(i.name)+'<small>'+esc(i.quantity||'1')+' '+esc(i.unit||'шт.')+(i.sku?' · '+esc(i.sku):'')+'</small></span><strong>'+esc(money(i.unit_price_kopecks,p.currency))+'</strong></div>').join(''):'<p>Товарные строки для импорта не найдены.</p>')+'</div>'+(j.quote_id&&j.status==='needs_review'&&p.needs_confirmation&&items.length?'<label class="premium-confirm-check"><input type="checkbox" data-premium-confirm-check="'+esc(id)+'"><span>Я проверил позиции и цены и подтверждаю добавление в связанный черновик сметы.</span></label><button class="btn primary" type="button" data-premium-confirm-import="'+esc(id)+'" disabled>Подтвердить импорт в смету</button>':'<p class="premium-review-note">'+esc(j.status==='needs_review'?(j.quote_id?'В документе нет товарных строк для импорта.':'Папка не связана со сметой. Привяжите её к черновику.'):'Состояние обработки: '+state(j.status)+'.')+'</p>')+'<p class="premium-review-note">Распознавание может ошибаться. Проверьте состав, количество и цену вручную.</p>';
        }catch(error){if(valid()&&target.isConnected&&!target.hidden)target.textContent=error.message}
      } else if(b.dataset.premiumConfirmImport){
        const id=b.dataset.premiumConfirmImport,card=document.querySelector('[data-premium-job-card="'+CSS.escape(id)+'"]'),check=card?.querySelector('[data-premium-confirm-check]');
        if(!check?.checked){notify('Сначала подтвердите, что проверили позиции.');return}
        await change(b,{title:'Добавить позиции в черновик?',message:'Распознанные позиции попадут в черновик сметы. Проверьте их перед отправкой клиенту.',confirmLabel:'Добавить'},'/premium/cloud/jobs/'+encodeURIComponent(id),{method:'POST',body:JSON.stringify({})},async r=>{notify('Добавлено позиций: '+(r.imported_items||0)+'. Проверьте итоговую сумму.');await render(active)});
      }
    });
    document.querySelector('.premium-job-list')?.addEventListener('change',ev=>{
      const check=ev.target.closest('[data-premium-confirm-check]');if(!check)return;
      const b=document.querySelector('[data-premium-confirm-import="'+CSS.escape(check.dataset.premiumConfirmCheck)+'"]');if(b)b.disabled=!check.checked;
    });
    if(new URLSearchParams(location.search).has('cloud')){const url=new URL(location.href);url.searchParams.delete('cloud');history.replaceState(null,'',url.pathname+url.hash)}
  }
  window.SmetraPremiumTools = { render };
})();
