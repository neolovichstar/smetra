/* Bridge to the Android app. In a browser this is inert: SmetraShell.available
   is false and every feature keeps its web behaviour. Inside the app the
   native side injects window.SmetraNative only for this exact origin. */
(() => {
  const port = window.SmetraNative;
  const available = Boolean(port && typeof port.postMessage === 'function');
  const pending = new Map(), listeners = new Map();
  let sequence = 0, capabilities = null;

  const receive = raw => {
    let message;
    try { message = JSON.parse(typeof raw === 'string' ? raw : raw?.data); } catch { return; }
    if (!message || message.v !== 1) return;
    if (message.event) { (listeners.get(message.event) || []).forEach(fn => { try { fn(message.data || {}); } catch {} }); return; }
    const entry = pending.get(message.id);
    if (!entry) return;
    pending.delete(message.id);
    clearTimeout(entry.timer);
    if (message.ok) entry.resolve(message.result || {});
    else { const error = Error(message.error?.message || 'Действие недоступно'); error.code = message.error?.code || 'failed'; entry.reject(error); }
  };
  if (available) {
    if (typeof port.addEventListener === 'function') port.addEventListener('message', event => receive(event.data));
    else port.onmessage = event => receive(event.data);
  }

  const call = (op, args = {}, { timeout = 30000 } = {}) => new Promise((resolve, reject) => {
    if (!available) { const error = Error('Доступно только в приложении Сметра'); error.code = 'unavailable'; reject(error); return; }
    const id = 'r' + (++sequence) + Date.now().toString(36);
    const timer = timeout ? setTimeout(() => {
      pending.delete(id);
      const error = Error('Приложение не ответило. Попробуйте ещё раз.'); error.code = 'timeout'; reject(error);
    }, timeout) : null;
    pending.set(id, { resolve, reject, timer });
    port.postMessage(JSON.stringify({ v: 1, id, op, args }));
  });

  const on = (event, fn) => { if (!listeners.has(event)) listeners.set(event, []); listeners.get(event).push(fn); };
  const ready = available ? call('app.hello', {}, { timeout: 5000 }).then(value => (capabilities = value)).catch(() => null) : Promise.resolve(null);
  const has = feature => {
    const value = capabilities?.features?.[feature];
    return feature === 'ar' ? value === 'supported' : Boolean(value);
  };

  // Android Back: close the topmost overlay first; otherwise native history decides.
  const handleBack = () => {
    const menu = document.querySelector('.sm-context');
    if (menu) { window.SmetraContextMenu?.close(); return true; }
    const dialogs = [...document.querySelectorAll('dialog[open]')];
    const top = dialogs[dialogs.length - 1];
    if (top) {
      const cancel = top.querySelector('[data-dialog-cancel],[data-dialog-close],.dialog-close,[aria-label="Закрыть"]');
      if (cancel) cancel.click(); else top.close();
      return true;
    }
    const comms = document.querySelector('#communication-center.is-open');
    if (comms) { window.SmetraCommunication?.close(); return true; }
    const drawer = document.body.classList.contains('nav-open');
    if (drawer) { document.querySelector('.nav-toggle')?.click(); return true; }
    return false;
  };

  window.SmetraShell = { available, ready, call, on, has, handleBack, get capabilities() { return capabilities; } };
  if (!available) return;
  document.documentElement.classList.add('in-app');

  // System bars follow the page theme.
  const theme = () => call('app.setTheme', { dark: document.documentElement.dataset.theme !== 'light' }, { timeout: 3000 }).catch(() => {});
  new MutationObserver(theme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  ready.then(theme);

  // Downloads made from blob: links cannot leave the WebView; hand them to Android.
  const toBase64 = buffer => {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(binary);
  };
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[download]');
    if (!link || !/^(blob:|data:)/.test(link.href)) return;
    event.preventDefault();
    (async () => {
      try {
        const response = await fetch(link.href);
        const blob = await response.blob();
        if (blob.size > 10 * 1024 * 1024) throw Error('Файл больше 10 МБ — откройте его в браузере');
        await call('file.save', { name: link.download || 'smetra-file', mime: blob.type, base64: toBase64(await blob.arrayBuffer()) }, { timeout: 0 });
        if (typeof notify === 'function') notify('Файл сохранён');
      } catch (error) {
        if (error.code !== 'cancelled' && typeof notify === 'function') notify(error.message);
      }
    })();
  }, true);

  on('auth.returned', () => { document.body.classList.remove('smetra-app-transitioning'); delete document.body.dataset.appState; });
  on('auth.error', data => { document.body.classList.remove('smetra-app-transitioning'); const status = document.querySelector('#auth-status'); if (status) status.textContent = data.message || 'Не удалось войти'; });
  on('share.received', data => {
    // Text shared from another app becomes a draft for the assistant.
    if (data.text) { try { sessionStorage.setItem('smetra.shared.text', data.text); } catch {} }
    if (typeof tab !== 'undefined' && typeof render === 'function') { tab = 'assistant'; history.pushState({}, '', '/app#assistant'); render(); }
  });
  on('app.update', data => {
    const bar = document.createElement('div');
    bar.className = 'app-update' + (data.required ? ' is-required' : '');
    bar.setAttribute('role', data.required ? 'alertdialog' : 'status');
    bar.innerHTML = '<div><strong></strong><p></p></div><button type="button" class="btn primary">Обновить</button>' + (data.required ? '' : '<button type="button" class="icon-button" aria-label="Позже">×</button>');
    bar.querySelector('strong').textContent = data.required ? 'Нужна новая версия приложения' : 'Доступно обновление приложения';
    bar.querySelector('p').textContent = data.message || (data.required ? 'Эта версия больше не поддерживается. Обновите приложение в RuStore — данные сохранятся.' : 'Новые возможности камеры и замеров. Остальное обновляется само.');
    bar.querySelector('.btn').onclick = () => call('app.openStore').catch(() => {});
    bar.querySelector('.icon-button')?.addEventListener('click', () => bar.remove());
    document.body.append(bar);
  });
})();
