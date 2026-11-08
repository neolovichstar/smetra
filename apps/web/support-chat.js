'use strict';
/* Support as a messenger: threads in a rail on the left, a Telegram-like
   conversation on the right. The AI support agent answers first; the user can
   bring in a person at any time and the history stays in the same thread. */
window.SmetraSupport = (() => {
  const kit = () => window.SmetraChatKit;
  const icon = (name, size = 18) => window.SmetraIcons ? window.SmetraIcons.svg(name, size) : '';
  let revision = 0, pollTimer = null;

  const stop = () => { clearInterval(pollTimer); pollTimer = null; };

  const render = async (parentActive = () => true) => {
    stop();
    const mine = ++revision, owner = user;
    const active = () => parentActive() && mine === revision && owner === user && tab === 'support';
    const state = { threads: [], current: null, messages: [], sending: false };
    let threadRevision = 0;

    const railCollapsed = (() => { try { return localStorage.getItem('smetra.support.rail-collapsed') === 'true'; } catch { return false; } })();
    view(`<section class="support-studio tg${railCollapsed ? ' is-rail-collapsed' : ''}" aria-label="Поддержка">
      <aside class="tg-rail" aria-label="Обращения">
        <header class="tg-rail-head">${typeof railToggleMarkup === 'function' ? railToggleMarkup(railCollapsed, 'support-rail-toggle') : ''}<h1>Поддержка</h1><button class="btn small" type="button" id="support-new" aria-label="Новое обращение" title="Новое обращение">${icon('pencil')}<span>Новое</span></button></header>
        <div class="tg-list" id="support-threads" role="list"></div>
        <footer class="tg-rail-foot">${typeof supportContacts === 'string' ? supportContacts : ''}</footer>
      </aside>
      <div class="tg-chat" id="support-chat">
        <header class="tg-head">
          <button class="icon-button tg-back" type="button" id="support-back" aria-label="К списку обращений">${icon('arrow-left')}</button>
          <span class="tg-avatar tg-avatar-brand" aria-hidden="true">${icon('headset', 20)}</span>
          <div class="tg-head-copy"><strong id="support-title">Поддержка Сметры</strong><small id="support-status">ИИ-помощник · можно позвать сотрудника</small></div>
          <button class="btn small" type="button" id="support-handoff" hidden>${icon('user')}<span>Позвать сотрудника</span></button>
        </header>
        ${typeof emailNotice === 'function' ? emailNotice() : ''}
        <div class="tg-messages" id="support-messages" role="log" aria-live="polite"></div>
        <form id="support-form" class="tg-compose" autocomplete="off">
          <label class="visually-hidden" for="message">Сообщение в поддержку</label>
          <div class="support-compose-surface"><div id="support-attachments" class="support-attachments" hidden></div><textarea id="message" rows="1" maxlength="4000" placeholder="Сообщение…" required></textarea>
          <input type="file" id="support-image-input" accept="image/jpeg,image/png,image/webp" multiple hidden><button type="button" class="support-attach" id="support-attach" aria-label="Прикрепить изображения" title="Прикрепить изображения">${icon('plus',18)}</button><button class="tg-send" type="submit" aria-label="Отправить сообщение" title="Отправить">${icon('arrow-up',18)}</button></div>
        </form>
      </div>
    </section>`);

    const root = document.querySelector('.support-studio');
    const list = root.querySelector('#support-threads');
    const log = root.querySelector('#support-messages');
    const form = root.querySelector('#support-form');
    const input = form.querySelector('#message');
    const send = form.querySelector('.tg-send');
    const title = root.querySelector('#support-title');
    const status = root.querySelector('#support-status');
    const handoff = root.querySelector('#support-handoff');
    const grow = kit().composer(input, form);
    const syncSend = () => { send.disabled = state.sending || input.disabled || preparing>0 || (!input.value.trim()&&!pendingImages.length); attach.disabled=state.sending||input.disabled||preparing>0; imageInput.disabled=attach.disabled; };
    let pendingImages=[],preparing=0;
    const imageInput=form.querySelector('#support-image-input'),attach=form.querySelector('#support-attach'),tray=form.querySelector('#support-attachments');
    const renderImages=()=>{
      tray.hidden=!pendingImages.length;
      tray.innerHTML=pendingImages.map((image,index)=>`<div class="support-attachment"><img src="${kit().esc(image.data_url)}" alt="${kit().esc(image.name)}"><button type="button" data-support-remove="${index}" aria-label="Убрать изображение ${index+1}">${icon('x',14)}</button></div>`).join('');
      tray.querySelectorAll('[data-support-remove]').forEach(button=>button.onclick=()=>{pendingImages.splice(Number(button.dataset.supportRemove),1);renderImages();syncSend();});
      input.required=!pendingImages.length;
    };
    const clearImages=()=>{pendingImages=[];imageInput.value='';renderImages();};
    const compressImage=async file=>{
      if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>10000000)throw Error('Выберите JPEG, PNG или WebP до 10 МБ.');
      const url=URL.createObjectURL(file),image=new Image();
      try{
        await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('Не удалось прочитать изображение.'));image.src=url;});
        if(image.naturalWidth*image.naturalHeight>20000000)throw Error('Изображение слишком большое. Выберите снимок до 20 мегапикселей.');
        const scale=Math.min(1,1600/Math.max(image.naturalWidth,image.naturalHeight)),canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));
        canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);
        let blob;
        for(const quality of [.82,.65,.45,.25]){blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/webp',quality));if(blob&&blob.size<=200000)break;}
        if(!blob||blob.size>200000)throw Error('Не удалось сжать изображение. Выберите снимок меньшего размера.');
        const data_url=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Не удалось прочитать файл.'));reader.readAsDataURL(blob);});
        return {name:file.name.slice(0,100),data_url};
      }finally{URL.revokeObjectURL(url);}
    };
    const addImages=async files=>{
      if(state.sending||input.disabled||preparing||!active())return;
      const selected=[...files];if(selected.length+pendingImages.length>3){notify('Можно прикрепить до трёх изображений.');return;}
      const selection=threadRevision;preparing++;syncSend();
      try{for(const file of selected){const image=await compressImage(file);if(!active()||selection!==threadRevision)return;pendingImages.push(image);renderImages();}}
      catch(error){if(active()&&selection===threadRevision)notify(error.message);}
      finally{preparing--;if(active())syncSend();}
    };
    attach.onclick=()=>imageInput.click();imageInput.onchange=()=>{void addImages(imageInput.files);imageInput.value='';};
    input.addEventListener('paste',event=>{const images=[...(event.clipboardData?.files||[])].filter(file=>file.type.startsWith('image/'));if(images.length){event.preventDefault();void addImages(images);}});

    input.addEventListener('input', syncSend);
    if (typeof bindRailToggle === 'function') bindRailToggle(root.querySelector('#support-rail-toggle'), root, 'smetra.support.rail-collapsed');

    const welcome = () => `<div class="tg-welcome">
        <span class="tg-avatar tg-avatar-brand tg-avatar-lg" aria-hidden="true">${icon('headset', 28)}</span>
        <h2>Чем помочь?</h2>
        <p>Опишите, что не получается. Сначала ответит ИИ-помощник. Если нужна проверка сотрудника, он передаст обращение. Переписка сохранится здесь.</p>
      </div>`;

    const toMessages = rows => rows.map(m => ({
      id: m.id, body: m.body, created_at: Number(m.created_at || 0),
      mine: m.sender_type === 'user', attachments: m.metadata?.attachments||[],
      kind: m.sender_type === 'system' ? 'system' : m.sender_type,
      author: m.sender_type === 'admin' ? 'Сотрудник поддержки' : m.sender_type === 'assistant' ? 'ИИ поддержки' : 'Вы',
    }));

    const paintHead = () => {
      const c = state.current;
      title.textContent = c ? (c.subject || 'Обращение') : 'Поддержка Сметры';
      status.textContent = !c ? 'ИИ-помощник · можно позвать сотрудника'
        : c.status === 'closed' ? 'Обращение закрыто'
        : c.needs_human ? 'Передано сотруднику · ответим здесь'
        : 'ИИ-помощник · можно позвать сотрудника';
      status.classList.toggle('is-waiting', Boolean(c?.needs_human));
      handoff.hidden = !c || c.needs_human || c.status === 'closed';
      const closed = c?.status === 'closed';
      input.disabled = closed; syncSend();
      input.placeholder = closed ? 'Обращение закрыто. Создайте новое' : 'Сообщение…';
      root.classList.toggle('is-chat-open', Boolean(c) || root.classList.contains('is-composing'));
    };

    const paintMessages = (extra = '', follow = true) => {
      const scrollTop = log.scrollTop;
      if (!state.current && !state.messages.length) { log.innerHTML = welcome() + extra; return; }
      log.innerHTML = kit().thread(state.messages, { showAuthors: true }) + extra;
      log.scrollTop = follow ? log.scrollHeight : scrollTop;
    };

    const paintList = () => {
      if (!state.threads.length) { list.innerHTML = '<p class="tg-list-empty">Здесь появятся ваши обращения.</p>'; return; }
      list.innerHTML = state.threads.map(t => {
        const preview = t.last_message || (t.needs_human ? 'Ожидает сотрудника' : 'Открыть переписку');
        const on = state.current?.id === t.id;
        return `<button type="button" class="tg-row${on ? ' is-active' : ''}" data-thread="${kit().esc(t.id)}" role="listitem" aria-current="${on}" title="${kit().esc(t.subject || 'Обращение')}">
          <span class="tg-avatar tg-avatar-brand" aria-hidden="true">${icon('headset', 18)}</span>
          <span class="tg-row-copy"><span class="tg-row-top"><strong>${kit().esc(t.subject || 'Обращение')}</strong><time>${kit().esc(kit().stamp(t.last_message_at || t.updated_at || t.created_at))}</time></span>
          <span class="tg-row-bottom"><span class="tg-preview">${kit().esc(preview)}</span>${t.status === 'closed' ? '<span class="tg-badge is-muted">закрыто</span>' : t.needs_human ? '<span class="tg-badge is-waiting">сотрудник</span>' : ''}</span></span>
        </button>`;
      }).join('');
    };

    const loadThreads = async () => {
      const data = await api('/support/threads');
      if (!active()) return;
      state.threads = Array.isArray(data?.threads) ? data.threads : [];
      if (state.current) state.current = state.threads.find(t => t.id === state.current.id) || state.current;
      paintList(); paintHead();
    };

    const loadMessages = async (quiet = false) => {
      const c = state.current, targetRevision = threadRevision; if (!c) return;
      const data = await api('/support/threads/' + encodeURIComponent(c.id) + '/messages');
      if (!active() || threadRevision !== targetRevision || state.current?.id !== c.id) return;
      const next = toMessages(Array.isArray(data?.messages) ? data.messages : []);
      if (quiet && next.length === state.messages.length) return;
      const follow = !quiet || log.scrollHeight - log.scrollTop - log.clientHeight < 80;
      state.messages = next; paintMessages('', follow);
    };

    const open = async id => {
      const targetRevision = ++threadRevision;
      clearImages();
      state.current = state.threads.find(t => t.id === id) || null;
      state.messages = []; paintList(); paintHead();
      log.innerHTML = '<div class="tg-loading" role="status">Загружаем переписку…</div>';
      try { await loadMessages(); } catch (error) { if (active() && threadRevision === targetRevision) log.innerHTML = `<p class="tg-error" role="alert">${kit().esc(error.message)}</p>`; }
      if (active() && threadRevision === targetRevision && matchMedia?.('(min-width:801px)')?.matches) input.focus({ preventScroll: true });
    };

    const fresh = () => {
      threadRevision++;
      state.current = null; state.messages = []; clearImages();
      root.classList.add('is-composing');
      paintList(); paintHead(); paintMessages();
      input.focus({ preventScroll: true });
    };

    list.addEventListener('click', event => { const row = event.target.closest('[data-thread]'); if (row) { root.classList.remove('is-composing'); open(row.dataset.thread); } });
    root.querySelector('#support-new').onclick = fresh;
    root.querySelector('#support-back').onclick = () => { threadRevision++; state.current = null; state.messages = []; root.classList.remove('is-chat-open', 'is-composing'); paintList(); paintHead(); paintMessages(); };

    handoff.onclick = async () => {
      const c = state.current; if (!c || handoff.disabled) return;
      const targetRevision = threadRevision;
      const ok = await window.SmetraDialog.confirm({ title: 'Позвать сотрудника?', message: 'Обращение попадёт в очередь команды поддержки. Ответ придёт в эту переписку.', confirmLabel: 'Позвать' });
      if (!ok || !active() || threadRevision !== targetRevision || state.current?.id !== c.id) return;
      handoff.disabled = true;
      try {
        await api('/support/threads/' + encodeURIComponent(c.id) + '/handoff', { method: 'POST', body: JSON.stringify({ reason: 'user_requested_human' }) });
        if (!active() || threadRevision !== targetRevision || state.current?.id !== c.id) return;
        c.needs_human = true; paintHead(); await loadMessages(); await loadThreads();
      } catch (error) { notify(error.message); }
      finally { handoff.disabled = false; }
    };

    form.onsubmit = async event => {
      event.preventDefault();
      const message = input.value.trim();
      if ((!message&&!pendingImages.length) || state.sending || input.disabled || preparing) return;
      const draft = input.value, images=pendingImages, target = state.current, submittedRevision = threadRevision;
      pendingImages=[];renderImages();
      const currentTarget = () => active() && threadRevision === submittedRevision;
      let accepted = false;
      state.sending = true; send.disabled = true;
      input.value = ''; grow();
      const optimistic = { id: 'pending', body: message, created_at: Date.now() / 1000, mine: true, kind: 'user', author: 'Вы', attachments: images, pending: true };
      const before = state.messages;
      state.messages = [...before, optimistic];
      root.classList.add('is-chat-open');
      paintMessages(state.current?.needs_human ? '' : kit().typing('Поддержка печатает'));
      try {
        if (target) {
          await api('/support/threads/' + encodeURIComponent(target.id) + '/messages', { method: 'POST', body: JSON.stringify({ message, ...(images.length?{attachments:images}:{}) }) });
          accepted = true;
          if (!currentTarget()) return;
          await loadMessages(); await loadThreads();
        } else {
          const subject = (message.replace(/\s+/g, ' ').slice(0,60)||'Изображения к обращению').trim();
          const data = await api('/support', { method: 'POST', body: JSON.stringify({ message, subject, ...(images.length?{attachments:images}:{}) }) });
          accepted = true;
          if (!currentTarget()) return;
          root.classList.remove('is-composing');
          await loadThreads();
          if (currentTarget() && data?.ticket_id) await open(data.ticket_id);
        }
      } catch (error) {
        if (!currentTarget()) return;
        if (!accepted) {
          if (!input.value) { input.value = draft; grow(); }
          pendingImages=[...images,...pendingImages].slice(0,3);renderImages();
          state.messages = before;
        } else optimistic.pending = false;
        paintMessages(); notify(error.message);
      } finally {
        state.sending = false;
        if (active() && send.isConnected) syncSend();
      }
    };

    paintHead(); paintMessages();
    try { await loadThreads(); } catch (error) { if (active()) list.innerHTML = `<p class="tg-error" role="alert">${kit().esc(error.message)}</p>`; }
    if (!active()) return;
    // With no history yet there is nothing to pick: go straight to writing.
    if (!state.threads.length) { root.classList.add('is-composing'); paintHead(); }
    // A person may answer at any moment; keep the open thread fresh.
    pollTimer = setInterval(() => {
      if (!active()) { stop(); return; }
      if (document.hidden || state.sending || !state.current) return;
      loadMessages(true).catch(() => {});
    }, 8000);
  };

  return { render, stop };
})();
