/* Small conveniences shared by every section of the cabinet:
   - file inputs get a styled «Выбрать файл» button with the chosen name;
   - phones: the top bar hides while scrolling down, re-tapping the current tab
     scrolls up or goes back to the section list, pull down to refresh in the app;
   - desktop: «/» focuses the section search, «N» creates a record, «?» lists keys. */
(() => {
  const content = () => document.getElementById('content');
  const visible = el => Boolean(el && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
  const phone = window.matchMedia ? matchMedia('(max-width:800px)') : { matches: false };

  // File inputs: the native control is in English on many systems and does not
  // follow the theme. The input stays in the form (validation, setInputFiles).
  const describe = input => {
    const files = [...(input.files || [])];
    return files.length > 1 ? 'Файлов: ' + files.length : files[0]?.name || 'Файл не выбран';
  };
  const enhance = input => {
    // Inputs hidden by the page already have their own trigger (an icon or a label).
    if (input.hidden || input.dataset.filePick || input.closest('[hidden]') || input.getBoundingClientRect().width < 4 || getComputedStyle(input).opacity === '0') return;
    input.dataset.filePick = '1';
    input.classList.add('file-pick-input');
    input.tabIndex = -1;
    const pick = document.createElement('span');
    pick.className = 'file-pick';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn small file-pick-button';
    button.textContent = input.multiple ? 'Выбрать файлы' : 'Выбрать файл';
    const name = document.createElement('span');
    name.className = 'file-pick-name';
    name.textContent = describe(input);
    if (input.id) button.setAttribute('aria-describedby', input.id + '-name'), name.id = input.id + '-name';
    const label = input.labels?.[0]?.textContent?.trim();
    if (label) button.setAttribute('aria-label', (input.multiple ? 'Выбрать файлы: ' : 'Выбрать файл: ') + label);
    button.addEventListener('click', event => { event.preventDefault(); input.click(); });
    input.addEventListener('change', () => { name.textContent = describe(input); pick.classList.toggle('has-file', Boolean(input.files?.length)); });
    input.form?.addEventListener('reset', () => setTimeout(() => { name.textContent = describe(input); pick.classList.remove('has-file'); }));
    pick.append(button, name);
    input.after(pick);
  };
  const scan = root => root.querySelectorAll?.('input[type=file]').forEach(enhance);
  // Horizontal tab strips on phones: keep the selected tab in view.
  const reveal = tab => { const strip = tab?.parentElement; if (!phone.matches || !strip || strip.scrollWidth <= strip.clientWidth) return; strip.scrollTo({ left: tab.offsetLeft - (strip.clientWidth - tab.offsetWidth) / 2, behavior: 'smooth' }); };
  new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => {
    if (node.nodeType !== 1) return;
    if (node.matches('input[type=file]')) enhance(node); else scan(node);
    const selected = node.querySelector?.('.hub-tabs [aria-selected="true"]');
    if (selected) requestAnimationFrame(() => reveal(selected));
  }))).observe(document.body, { childList: true, subtree: true });
  document.addEventListener('click', event => { const tab = event.target.closest?.('.hub-tabs [role=tab]'); if (tab) requestAnimationFrame(() => reveal(tab)); });
  scan(document);

  const typing = target => target?.closest?.('input,textarea,select,[contenteditable="true"],dialog,[role=dialog],.command-palette');

  // Phones: hide the top bar on the way down, bring it back on the way up.
  let lastY = scrollY;
  addEventListener('scroll', () => {
    const y = Math.max(0, scrollY), body = document.body;
    if (!phone.matches || body.classList.contains('nav-open')) { body.classList.remove('topbar-hidden'); lastY = y; return; }
    if (Math.abs(y - lastY) < 8) return;
    body.classList.toggle('topbar-hidden', y > lastY && y > 120);
    lastY = y;
  }, { passive: true });
  phone.addEventListener?.('change', () => document.body.classList.remove('topbar-hidden'));

  // Re-tapping the current tab: scroll to the top, or leave an open record.
  const bar = document.getElementById('mobile-tabbar');
  bar?.addEventListener('click', event => {
    const button = event.target.closest('[data-tab]');
    if (!button || !button.classList.contains('active')) return;
    if (scrollY > 40) { scrollTo({ top: 0, behavior: 'smooth' }); return; }
    const back = [...(content()?.querySelectorAll('[data-work=navigate],#construction-back,#knowledge-back,#file-editor-back,#review-back') || [])].find(visible);
    back?.click();
  });

  // Pull to refresh inside the Android app and the installed PWA (browsers have their own).
  const standalone = () => window.SmetraShell?.available || matchMedia('(display-mode: standalone)').matches;
  let pull = null;
  const indicator = document.createElement('div');
  indicator.className = 'pull-refresh';
  indicator.setAttribute('aria-hidden', 'true');
  indicator.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 4v5h-5"/></svg>';
  document.body.append(indicator);
  const scrollsInside = target => {
    for (let node = target; node && node !== document.body; node = node.parentElement) {
      if (node.scrollTop > 0) return true;
      if (node.matches?.('textarea,[contenteditable="true"],.sm-dialog,.modal,dialog')) return true;
    }
    return false;
  };
  addEventListener('touchstart', event => {
    pull = null;
    if (!standalone() || event.touches.length !== 1 || scrollY > 0 || document.body.classList.contains('nav-open') || document.querySelector('dialog[open],.modal-backdrop:not(.hidden)') || scrollsInside(event.target)) return;
    pull = { y: event.touches[0].clientY, x: event.touches[0].clientX, distance: 0 };
  }, { passive: true });
  addEventListener('touchmove', event => {
    if (!pull) return;
    const dy = event.touches[0].clientY - pull.y, dx = Math.abs(event.touches[0].clientX - pull.x);
    if (dy <= 0 || dx > dy || scrollY > 0) { pull.distance = 0; indicator.classList.remove('is-pulling', 'is-ready'); return; }
    pull.distance = Math.min(dy * 0.5, 96);
    indicator.classList.add('is-pulling');
    indicator.classList.toggle('is-ready', pull.distance >= 64);
    indicator.style.setProperty('--pull', pull.distance + 'px');
    indicator.style.setProperty('--pull-turn', pull.distance * 3.6 + 'deg');
  }, { passive: true });
  addEventListener('touchend', async () => {
    const ready = pull?.distance >= 64;
    pull = null;
    indicator.classList.remove('is-pulling', 'is-ready');
    indicator.style.removeProperty('--pull');
    indicator.style.removeProperty('--pull-turn');
    if (!ready || typeof window.render !== 'function') return;
    indicator.classList.add('is-loading');
    try { await window.render(); } finally { indicator.classList.remove('is-loading'); }
  }, { passive: true });

  // Desktop keys. Ignored while typing, in dialogs and with modifiers.
  const searchField = () => [...(content()?.querySelectorAll('input[type=search],input[id$=search],input[placeholder^="Найти"],input[placeholder^="Название, категория"]') || [])].find(visible);
  const createButton = () => [...(content()?.querySelectorAll('.topline-actions .btn.primary,.topline .btn.primary,.topline-actions .btn') || [])].find(button => visible(button) && !button.disabled && /^(\+\s*)?(Создать|Новый|Новая|Добавить|Записать)/.test(button.textContent.trim()));
  const keys = [['/', 'Поиск в разделе'], ['N', 'Создать запись в разделе'], ['Ctrl + K', 'Быстрый переход'], ['Ctrl + Z / Y', 'Отменить и повторить в смете'], ['Ctrl + S', 'Сохранить смету'], ['Esc', 'Закрыть окно или меню'], ['?', 'Эта подсказка']];
  const help = () => {
    if (document.querySelector('.keys-help[open]')) return;
    const dialog = document.createElement('dialog');
    dialog.className = 'sm-dialog keys-help';
    dialog.setAttribute('aria-labelledby', 'keys-help-title');
    dialog.innerHTML = '<form method="dialog" class="sm-dialog-body"><h2 id="keys-help-title">Горячие клавиши</h2><dl class="keys-help-list"></dl><div class="sm-dialog-actions"><button class="btn primary" value="close">Понятно</button></div></form>';
    const list = dialog.querySelector('dl');
    keys.forEach(([key, text]) => {
      const term = document.createElement('dt'), description = document.createElement('dd');
      key.split(' ').forEach(part => { if (part === '+' || part === '/') term.append(' ' + part + ' '); else { const kbd = document.createElement('kbd'); kbd.textContent = part; term.append(kbd); } });
      description.textContent = text;
      list.append(term, description);
    });
    dialog.addEventListener('close', () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
  };
  document.addEventListener('keydown', event => {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || event.isComposing || typing(event.target) || !content()) return;
    if (document.querySelector('dialog[open]') || document.body.classList.contains('nav-open')) return;
    if (event.key === '/' || (event.code === 'Slash' && !event.shiftKey)) {
      const field = searchField();
      if (field) { event.preventDefault(); field.focus(); field.select?.(); }
    } else if (event.code === 'KeyN' && !event.shiftKey) {
      const button = createButton();
      if (button) { event.preventDefault(); button.click(); }
    } else if (event.key === '?' || (event.code === 'Slash' && event.shiftKey)) {
      event.preventDefault();
      help();
    }
  });

  // Phones: the section's main «create» action moves from the top of the page
  // into the thumb zone, above the tab bar. The original button stays in the
  // DOM (hidden on phones) and does the work.
  const fab = document.createElement('button');
  fab.type = 'button';
  fab.className = 'page-fab';
  fab.hidden = true;
  fab.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg><span></span>';
  document.body.append(fab);
  let source = null;
  const syncFab = () => {
    const next = [...(content()?.querySelectorAll('.topline-actions .btn.primary,.page-actions .btn.primary') || [])].find(button => !button.disabled && /^(\+\s*)?(Создать|Новый|Новая|Добавить|Записать)/.test(button.textContent.trim()));
    if (source && source !== next) source.classList.remove('fab-source');
    source = next || null;
    fab.hidden = !source;
    if (!source) return;
    source.classList.add('fab-source');
    const label = source.textContent.trim();
    fab.querySelector('span').textContent = label;
    fab.setAttribute('aria-label', label);
  };
  fab.addEventListener('click', () => source?.click());
  const main = content();
  let queued = false;
  if (main) new MutationObserver(() => { if (queued) return; queued = true; requestAnimationFrame(() => { queued = false; syncFab(); }); }).observe(main, { childList: true, subtree: true });
  syncFab();

})();
