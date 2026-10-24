/* Premium materials, price monitoring and cloud-drive imports. */
(() => {
  const esc = escapeHtml;
  const money = (value, code) => value == null ? 'Цена не определена' : new Intl.NumberFormat('ru-RU',{style:'currency',currency:code||'RUB',maximumFractionDigits:2}).format(Number(value)/100);
  const when = value => value ? new Intl.DateTimeFormat('ru-RU',{dateStyle:'medium',timeStyle:'short'}).format(new Date(Number(value)*1000)) : 'Не проверялось';
  const provider = value => value === 'yandex_disk' ? 'Яндекс.Диск' : value === 'google_drive' ? 'Google Drive' : 'Облако';
  const state = value => ({queued:'В очереди',running:'Обработка',retry:'Повторная попытка',needs_review:'Нужна проверка',completed:'Готово',failed:'Ошибка',active:'Активно',disabled:'Отключено',reauth_required:'Нужна авторизация',paused:'На паузе'})[value] || value || '—';
  const stock = value => ({in_stock:'В наличии',out_of_stock:'Нет в наличии',preorder:'Предзаказ',backorder:'Под заказ',unknown:'Не определено'})[value] || 'Не определено';
  const arr = value => Array.isArray(value) ? value : [];
  const drafts = value => arr(value).filter(q => q.status === 'draft' && !Number(q.published_version || 0));
  const quoteOptions = value => '<option value="">Не привязывать к смете</option>' + drafts(value).map(q => '<option value="' + esc(q.id) + '">' + esc(q.title || 'Черновик') + ' · ' + esc(q.client || 'Без клиента') + '</option>').join('');

  async function render(active) {
    active = active || (() => true);
    let features;
    try { features = await api('/premium/features'); }
    catch (error) {
      if (active()) view(header('Материалы и облака','Источники цен и интеграции.') + '<section class="premium-empty"><h2>Раздел временно недоступен</h2><p>' + esc(error.message) + '</p><button class="btn" id="premium-retry">Повторить</button></section>');
      document.querySelector('#premium-retry')?.addEventListener('click', () => render(active));
      return;
    }
    if (!active()) return;
    if (!(features.cloud_drives && features.product_monitor && features.visual_estimates)) {
      view(header('Материалы и облака','Расширенные инструменты для материалов, цен и документов.') +
        '<section class="premium-lock"><span class="premium-kicker">РАСШИРЕННЫЕ ИНСТРУМЕНТЫ</span><h2>Материалы под контролем.</h2><p>Подключайте Яндекс.Диск и Google Drive, связывайте товарные источники со сметой и отслеживайте изменения цен. Импорт документов всегда требует вашей проверки.</p><div class="premium-lock-grid"><article><span class="premium-number">01</span><h3>Материалы</h3><p>Ссылки, характеристики и поставщики рядом с позициями сметы.</p></article><article><span class="premium-number">02</span><h3>История цен</h3><p>Наблюдения и уведомления. Сметная цена не меняется сама.</p></article><article><span class="premium-number">03</span><h3>Облачные документы</h3><p>Синхронизация папок и импорт после ручного подтверждения.</p></article></div><p class="premium-lock-note">Инструменты предусмотрены для тарифов «PRO Плюс» и «TEAM».</p><button class="btn primary" id="premium-go-billing" type="button">Посмотреть тариф</button></section>');
      document.querySelector('#premium-go-billing')?.addEventListener('click', () => { tab='billing'; location.hash='billing'; window.render(); });
      return;
    }

    let quotes=[], sources=[], connections=[], folders=[], jobs=[];
    try {
      const r = await Promise.all([api('/quotes'),api('/premium/product-sources'),api('/premium/cloud/connections'),api('/premium/cloud/folders'),api('/premium/cloud/jobs')]);
      quotes = r[0].quotes || r[0].items || []; sources = r[1].sources || []; connections = r[2].connections || []; folders = r[3].folders || []; jobs = r[4].jobs || [];
    } catch (error) {
      if (!active()) return;
      view(header('Материалы и облака','Источники цен, папки и документы.') + '<section class="premium-empty"><h2>Не удалось загрузить раздел</h2><p>' + esc(error.message) + '</p><button class="btn" id="premium-retry">Повторить</button></section>');
      document.querySelector('#premium-retry')?.addEventListener('click', () => render(active));
      return;
    }
    if (!active()) return;
    const draftsList = drafts(quotes);
    const canSync = connections.some(c => c.status === 'active');
    const sourceHtml = sources.length ? sources.map(s => '<article class="premium-source"><div class="premium-source-main"><span class="premium-source-host">' + esc(s.hostname) + '</span><h3>' + esc(s.product_title || s.url) + '</h3><p>' + esc(s.brand || 'Бренд не определён') + (s.sku ? ' · Артикул ' + esc(s.sku) : '') + '</p><div class="premium-source-meta"><span>' + esc(stock(s.availability)) + '</span><span>Проверено: ' + esc(when(s.last_checked_at)) + '</span><span>' + esc(state(s.source_status)) + '</span></div>' + (s.last_error ? '<p class="premium-error">' + esc(s.last_error) + '</p>' : '') + '</div><div class="premium-source-actions"><strong>' + esc(money(s.price_kopecks,s.currency)) + '</strong><button class="btn small" type="button" data-premium-history="' + esc(s.id) + '">История цен</button>' + (s.monitored ? '<button class="btn small" type="button" data-premium-disable-source="' + esc(s.id) + '">Остановить</button>' : '') + '</div><div class="premium-history" data-premium-history-view="' + esc(s.id) + '" hidden></div></article>').join('') : '<p class="muted">Источников пока нет. Проверьте ссылку на товар выше.</p>';
    const connectionHtml = connections.length ? connections.map(c => '<article class="premium-connection"><span class="premium-provider-symbol">' + (c.provider === 'yandex_disk' ? 'Я' : 'G') + '</span><div class="premium-connection-copy"><strong>' + esc(provider(c.provider)) + '</strong><span>' + esc(c.account_label || 'Подключение') + '</span><small>' + esc(state(c.status)) + (c.last_synced_at ? ' · ' + esc(when(c.last_synced_at)) : '') + '</small>' + (c.last_error ? '<small class="premium-error">' + esc(c.last_error) + '</small>' : '') + '</div><button class="btn small" type="button" data-premium-disconnect="' + esc(c.id) + '">Отключить</button></article>').join('') : '<p class="muted">Облака не подключены. Яндекс.Диск использует существующий OAuth-клиент, если для него разрешено чтение Диска.</p>';
    const folderHtml = folders.length ? folders.map(f => '<article class="premium-folder"><div><strong>' + esc(f.folder_name || f.folder_id) + '</strong><span>' + esc(provider(f.provider)) + ' · ' + esc(f.account_label || '') + '</span><small>' + (f.quote_id ? 'Привязана к черновику сметы' : 'Не привязана к смете') + (f.last_synced_at ? ' · ' + esc(when(f.last_synced_at)) : '') + '</small>' + (f.last_error ? '<small class="premium-error">' + esc(f.last_error) + '</small>' : '') + '</div><div class="premium-folder-actions"><span class="premium-state">' + esc(state(f.status)) + '</span><button class="btn small" data-premium-resync="' + esc(f.id) + '">Синхронизировать</button><button class="btn small" data-premium-disable-folder="' + esc(f.id) + '">Отключить</button></div></article>').join('') : '<p class="muted">Добавьте папку, чтобы искать новые и изменённые документы.</p>';
    const jobsHtml = jobs.length ? jobs.map(j => '<article class="premium-job" data-premium-job-card="' + esc(j.id) + '"><span class="premium-job-kind">' + (j.mime === 'application/pdf' ? 'PDF' : 'DOC') + '</span><div class="premium-job-copy"><strong>' + esc(j.name) + '</strong><span>' + esc(provider(j.provider)) + (j.quote_id ? ' · Смета привязана' : ' · Без сметы') + '</span><small>' + esc(state(j.status)) + (j.updated_at ? ' · ' + esc(when(j.updated_at)) : '') + '</small>' + (j.error ? '<small class="premium-error">' + esc(j.error) + '</small>' : '') + '</div><button class="btn small" type="button" data-premium-review="' + esc(j.id) + '">Проверить</button><div class="premium-job-review" data-premium-job-review="' + esc(j.id) + '" hidden></div></article>').join('') : '<p class="muted">Очередь пуста. После синхронизации появятся документы до 5 МБ.</p>';
    const connectionOptions = connections.filter(c => c.status === 'active').map(c => '<option value="' + esc(c.id) + '">' + esc(provider(c.provider)) + ' · ' + esc(c.account_label || 'Подключение') + '</option>').join('');

    view(header('Материалы и облака','Проверяйте поставщиков, отслеживайте цены и импортируйте документы после проверки.') +
      '<section class="premium-tools-page"><div class="premium-intro"><div><span class="premium-kicker">МАТЕРИАЛЫ / ИНТЕГРАЦИИ</span><h1>Всё нужное для сметы.<br><span>Без ручного хаоса.</span></h1><p>Внешние цены — наблюдения, распознанные данные — предложение к импорту. Без автоматической замены стоимости сметы.</p></div><div class="premium-intro-metric"><strong>' + sources.length + '</strong><span>источников цен</span><i></i><strong>' + jobs.filter(j => j.status === 'needs_review').length + '</strong><span>документов ждут проверки</span></div></div>' +
      '<section class="premium-section"><div class="premium-section-heading"><div><span class="premium-kicker">01 / ПОСТАВЩИКИ</span><h2>Проверить и отслеживать товар</h2><p>Разрешённые источники проходят проверку адреса и перенаправлений.</p></div></div><form id="premium-product-form" class="premium-form"><div class="premium-form-grid"><div class="field"><label for="premium-product-url">Ссылка на товар</label><input id="premium-product-url" name="url" type="url" maxlength="2048" placeholder="https://…" required></div><div class="field"><label for="premium-product-quote">Черновик сметы</label><select id="premium-product-quote" name="quote_id">' + quoteOptions(quotes) + '</select></div><div class="field"><label for="premium-product-item">Позиция сметы</label><select id="premium-product-item" name="quote_item_id" disabled><option value="">Сначала выберите смету</option></select></div><div class="premium-form-submit"><button class="btn primary" type="submit" id="premium-product-preview-button">Проверить ссылку</button><span>Пока это только наблюдение, не цена сметы.</span></div></div></form><div id="premium-product-preview" class="premium-preview" hidden></div><div class="premium-list-heading"><h3>Мониторинг цен</h3><span>' + sources.length + ' источников</span></div><div class="premium-source-list">' + sourceHtml + '</div></section>' +
      '<section class="premium-section"><div class="premium-section-heading"><div><span class="premium-kicker">02 / СИНХРОНИЗАЦИЯ</span><h2>Облачные документы</h2><p>OAuth-токены хранятся зашифрованно. Файлы остаются в облаке.</p></div><button class="btn" id="premium-sync-all" type="button" ' + (canSync ? '' : 'disabled') + '>Синхронизировать сейчас</button></div><div class="premium-connect-row"><button class="premium-connect" type="button" data-premium-connect="yandex_disk"><span class="premium-provider-symbol">Я</span><span><strong>Подключить Яндекс.Диск</strong><small>Чтение папок и документов</small></span><span>↗</span></button><button class="premium-connect" type="button" data-premium-connect="google_drive"><span class="premium-provider-symbol">G</span><span><strong>Подключить Google Drive</strong><small>Чтение папок и документов</small></span><span>↗</span></button></div><div class="premium-connection-list">' + connectionHtml + '</div><details class="premium-folder-setup" ' + (canSync ? 'open' : '') + '><summary>Добавить папку для синхронизации</summary><form id="premium-folder-form" class="premium-form"><div class="premium-form-grid"><div class="field"><label for="premium-folder-connection">Облачное подключение</label><select id="premium-folder-connection" name="connection_id" required>' + (connectionOptions || '<option value="">Сначала подключите облако</option>') + '</select></div><div class="field"><label for="premium-folder-id">ID папки или путь</label><input id="premium-folder-id" name="folder_id" maxlength="1024" placeholder="ID Google Drive или /Документы/Сметы" required></div><div class="field"><label for="premium-folder-quote">Черновик сметы для импорта</label><select id="premium-folder-quote" name="quote_id">' + quoteOptions(quotes) + '</select></div><label class="premium-checkbox"><input type="checkbox" name="recursive" checked><span><strong>Включить вложенные папки</strong><small>Синхронизация ограничена по глубине и числу файлов.</small></span></label><div class="premium-form-submit"><button class="btn primary" type="submit" ' + (canSync ? '' : 'disabled') + '>Добавить папку</button><span>Для Яндекс.Диска используйте полный путь с начальным /.</span></div></div><p class="form-error" role="alert"></p></form></details><div class="premium-list-heading"><h3>Папки</h3><span>' + folders.length + ' привязок</span></div><div class="premium-folder-list">' + folderHtml + '</div></section>' +
      '<section class="premium-section"><div class="premium-section-heading"><div><span class="premium-kicker">03 / ПРОВЕРКА</span><h2>Импорт документов</h2><p>Данные попадут в черновик только после проверки и отдельного подтверждения.</p></div><button type="button" class="btn" id="premium-refresh-jobs">Обновить очередь</button></div><div class="premium-job-list">' + jobsHtml + '</div></section></section>');

    window.SmetraPriceImpact?.mount(quotes,active);
    if (new URLSearchParams(location.search).get('cloud') === 'connected') {
      history.replaceState(null,'','/app#premium'); notify('Облако подключено. Обновляем список…'); await render(active); return;
    }
    let quote = null, product = null;
    const quoteSelect = document.querySelector('#premium-product-quote');
    const itemSelect = document.querySelector('#premium-product-item');
    const preview = document.querySelector('#premium-product-preview');
    async function loadQuote(id) {
      quote=null; itemSelect.disabled=true; itemSelect.innerHTML='<option value="">Загружаем позиции…</option>';
      if (!id) { itemSelect.innerHTML='<option value="">Выберите черновик сметы</option>'; if (product) paintProduct(); return; }
      try {
        const r=await api('/quotes/'+encodeURIComponent(id)); if(!active())return;
        if(!r.quote || r.quote.status!=='draft' || Number(r.quote.published_version||0)>0) { itemSelect.innerHTML='<option value="">Доступны только черновики</option>'; return; }
        quote=r.quote; const items=arr(quote.items);
        itemSelect.innerHTML=items.map(i=>'<option value="'+esc(i.line_id||'')+'">'+esc(i.name||'Без названия')+' · '+esc(i.quantity||'1')+' '+esc(i.unit||'шт.')+'</option>').join('');
        if(!items.length)itemSelect.innerHTML='<option value="">Добавьте позицию в смету</option>';
        itemSelect.disabled=!items.length; if(product)paintProduct();
      } catch (error) { itemSelect.innerHTML='<option value="">Не удалось загрузить позиции</option>'; notify(error.message); }
    }
    function paintProduct() {
      const ready=Boolean(quote && quote.status==='draft' && itemSelect.value);
      preview.hidden=false;
      preview.innerHTML='<div class="premium-preview-top"><span class="premium-kicker">РЕЗУЛЬТАТ ПРОВЕРКИ</span><span class="premium-state">'+esc(stock(product.availability))+'</span></div><div class="premium-preview-body"><div><h3>'+esc(product.product_title||'Карточка товара')+'</h3><p>'+esc(product.brand||'Бренд не определён')+(product.sku?' · Артикул '+esc(product.sku):'')+'</p><a href="'+esc(product.url)+'" target="_blank" rel="noopener noreferrer">'+esc(product.hostname||product.url)+' ↗</a></div><strong>'+esc(money(product.price_kopecks,product.currency))+'</strong></div><p class="premium-preview-note">Наблюдение: '+esc(when(product.observed_at))+'. Цена сметы не изменена.</p><div class="premium-preview-actions"><button class="btn primary" id="premium-save-source" type="button" '+(ready?'':'disabled')+'>Привязать к позиции и следить за ценой</button><span>'+(ready?'Цена магазина будет сохранена отдельно.':'Выберите черновик сметы и позицию.')+'</span></div>';
      preview.querySelector('#premium-save-source')?.addEventListener('click',async ev=>{
        if(!quote || !itemSelect.value || !product)return; ev.currentTarget.disabled=true;
        try { await api('/premium/product-sources',{method:'POST',body:JSON.stringify({quote_id:quote.id,quote_item_id:itemSelect.value,revision:quote.revision,url:product.url})}); notify('Источник цены сохранён. Сметная стоимость не менялась.'); await render(active); }
        catch(error){notify(error.message);ev.currentTarget.disabled=false}
      });
    }
    quoteSelect?.addEventListener('change',()=>loadQuote(quoteSelect.value));
    itemSelect?.addEventListener('change',()=>{if(product)paintProduct()});
    if(quoteSelect?.value)await loadQuote(quoteSelect.value);
    document.querySelector('#premium-product-form')?.addEventListener('submit',async ev=>{
      ev.preventDefault();const button=document.querySelector('#premium-product-preview-button');button.disabled=true;button.textContent='Проверяем…';
      try { const r=await api('/premium/products/preview',{method:'POST',body:JSON.stringify({url:document.querySelector('#premium-product-url').value.trim()})}); if(!active())return;product=r.product;paintProduct(); }
      catch(error){notify(error.message)} finally {if(button.isConnected){button.disabled=false;button.textContent='Проверить ссылку'}}
    });
    document.querySelectorAll('[data-premium-connect]').forEach(b=>b.addEventListener('click',async()=>{
      b.disabled=true;try{const r=await api('/premium/cloud/oauth/'+encodeURIComponent(b.dataset.premiumConnect));if(r.authorize_url)location.assign(r.authorize_url);else throw Error('Сервис не вернул ссылку авторизации.')}catch(error){notify(error.message);b.disabled=false}
    }));
    document.querySelector('#premium-sync-all')?.addEventListener('click',async ev=>{
      ev.currentTarget.disabled=true;try{const r=await api('/premium/cloud/sync',{method:'POST',body:JSON.stringify({})});notify('Запрошена синхронизация папок: '+(r.queued||0));await render(active)}catch(error){notify(error.message);ev.currentTarget.disabled=false}
    });
    document.querySelector('#premium-folder-form')?.addEventListener('submit',async ev=>{
      ev.preventDefault();const form=ev.currentTarget,button=form.querySelector('[type=submit]'),error=form.querySelector('[role=alert]');error.textContent='';button.disabled=true;
      try{const d=Object.fromEntries(new FormData(form));await api('/premium/cloud/folders',{method:'POST',body:JSON.stringify({connection_id:d.connection_id,folder_id:String(d.folder_id||'').trim(),quote_id:d.quote_id||null,recursive:form.elements.recursive.checked})});notify('Папка добавлена; синхронизация запрошена.');await render(active)}
      catch(err){error.textContent=err.message;button.disabled=false}
    });
    document.querySelector('#premium-refresh-jobs')?.addEventListener('click',()=>render(active));
    document.querySelector('.premium-tools-page')?.addEventListener('click',async ev=>{
      const b=ev.target.closest('button');if(!b)return;
      if(b.dataset.premiumDisconnect){
        if(!confirm('Отключить облако и его синхронизации?'))return;b.disabled=true;
        try{await api('/premium/cloud/connections',{method:'DELETE',body:JSON.stringify({connection_id:b.dataset.premiumDisconnect})});notify('Облако отключено.');await render(active)}catch(error){notify(error.message);b.disabled=false}
      } else if(b.dataset.premiumDisableSource){
        if(!confirm('Остановить мониторинг этой цены?'))return;b.disabled=true;
        try{await api('/premium/product-sources/'+encodeURIComponent(b.dataset.premiumDisableSource),{method:'DELETE',body:JSON.stringify({})});notify('Мониторинг остановлен.');await render(active)}catch(error){notify(error.message);b.disabled=false}
      } else if(b.dataset.premiumDisableFolder){
        if(!confirm('Отключить эту папку?'))return;b.disabled=true;
        try{await api('/premium/cloud/folders/'+encodeURIComponent(b.dataset.premiumDisableFolder),{method:'DELETE',body:JSON.stringify({})});notify('Синхронизация папки остановлена.');await render(active)}catch(error){notify(error.message);b.disabled=false}
      } else if(b.dataset.premiumResync){
        b.disabled=true;try{const r=await api('/premium/cloud/sync',{method:'POST',body:JSON.stringify({})});notify('Запрошена синхронизация: '+(r.queued||0)+' папок.');await render(active)}catch(error){notify(error.message);b.disabled=false}
      } else if(b.dataset.premiumHistory){
        const id=b.dataset.premiumHistory,target=document.querySelector('[data-premium-history-view="'+CSS.escape(id)+'"]');if(!target)return;
        if(!target.hidden){target.hidden=true;target.replaceChildren();return}target.hidden=false;target.textContent='Загружаем историю…';
        try{const r=await api('/premium/price-history/'+encodeURIComponent(id));target.innerHTML=r.history?.length?'<h4>История наблюдений</h4><div class="premium-history-list">'+r.history.map(x=>'<div><span>'+esc(when(x.observed_at))+'<small>'+esc(stock(x.availability))+'</small></span><strong>'+esc(money(x.price_kopecks,x.currency))+'</strong></div>').join('')+'</div>':'<p>Пока есть только первое наблюдение. Следующая проверка запланирована автоматически.</p>'}catch(error){target.textContent=error.message}
      } else if(b.dataset.premiumReview){
        const id=b.dataset.premiumReview,target=document.querySelector('[data-premium-job-review="'+CSS.escape(id)+'"]');if(!target)return;
        if(!target.hidden){target.hidden=true;target.replaceChildren();return}target.hidden=false;target.textContent='Загружаем распознанные данные…';
        try{
          const r=await api('/premium/cloud/jobs/'+encodeURIComponent(id)),j=r.job,p=j.proposal||{},items=arr(p.items);
          target.innerHTML='<div class="premium-review-heading"><div><span class="premium-kicker">ПРЕДЛОЖЕНИЕ К ИМПОРТУ</span><h3>'+esc(p.merchant||j.name)+'</h3><p>'+esc(p.date||'Дата не распознана')+' · '+esc(p.document_type||'Тип не определён')+'</p></div><strong>'+esc(money(p.total_kopecks,p.currency))+'</strong></div><p>'+esc(p.notes||'Проверьте строки и суммы ниже.')+'</p><div class="premium-review-lines">'+(items.length?items.map((i,n)=>'<div><span>'+(n+1)+'. '+esc(i.name)+'<small>'+esc(i.quantity||'1')+' '+esc(i.unit||'шт.')+(i.sku?' · '+esc(i.sku):'')+'</small></span><strong>'+esc(money(i.unit_price_kopecks,p.currency))+'</strong></div>').join(''):'<p>Товарные строки для импорта не найдены.</p>')+'</div>'+(j.quote_id?'<label class="premium-confirm-check"><input type="checkbox" data-premium-confirm-check="'+esc(id)+'"><span>Я проверил позиции и цены и подтверждаю добавление в связанный черновик сметы.</span></label><button class="btn primary" type="button" data-premium-confirm-import="'+esc(id)+'" disabled>Подтвердить импорт в смету</button>':'<p class="premium-error">Папка не связана со сметой. Привяжите папку к черновику и выполните синхронизацию ещё раз.')+'<p class="premium-review-note">Распознавание может ошибаться. Проверьте состав, количество и цену вручную.</p>';
        }catch(error){target.textContent=error.message}
      } else if(b.dataset.premiumConfirmImport){
        const id=b.dataset.premiumConfirmImport,card=document.querySelector('[data-premium-job-card="'+CSS.escape(id)+'"]'),check=card?.querySelector('[data-premium-confirm-check]');
        if(!check?.checked){notify('Сначала подтвердите, что проверили позиции.');return}
        if(!confirm('Добавить распознанные позиции в черновик сметы?'))return;b.disabled=true;
        try{const r=await api('/premium/cloud/jobs/'+encodeURIComponent(id),{method:'POST',body:JSON.stringify({})});notify('Добавлено позиций: '+(r.imported_items||0)+'. Проверьте итоговую сумму.');await render(active)}catch(error){notify(error.message);b.disabled=false}
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
