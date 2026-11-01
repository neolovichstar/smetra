/* Cabinet context menu. Right click shows actions that fit the target: text
   editing in fields, copying a selection or a message, links, and quick
   workspace commands. Shift + right click still opens the browser menu, and
   touch devices keep their native long-press behaviour. */
(() => {
  const icon = name => window.SmetraIcons ? window.SmetraIcons.svg(name, 16) : '';
  const fine = () => window.matchMedia?.('(pointer:fine)')?.matches !== false;
  let menu = null, returnFocus = null;

  const editable = el => el?.closest?.('input:not([type=checkbox]):not([type=radio]):not([type=file]):not([type=range]):not([type=color]),textarea,[contenteditable=""],[contenteditable="true"]');
  const fieldSelection = field => field && typeof field.selectionStart === 'number' ? field.value.slice(field.selectionStart, field.selectionEnd) : '';
  const pageSelection = () => String(window.getSelection?.() || '').trim();
  const toast = text => { if (typeof notify === 'function') notify(text); };
  const copy = async text => {
    try { await navigator.clipboard.writeText(text); toast('Скопировано'); }
    catch { toast('Не удалось скопировать — используйте Ctrl+C'); }
  };
  const insert = (field, text) => {
    if (typeof field.setRangeText === 'function') {
      field.setRangeText(text, field.selectionStart, field.selectionEnd, 'end');
      field.dispatchEvent(new Event('input', { bubbles: true }));
    } else document.execCommand?.('insertText', false, text);
  };
  const go = section => {
    if (typeof tab === 'undefined' || typeof render !== 'function') return Promise.resolve();
    tab = section;
    if (location.hash.slice(1) !== section) history.pushState({}, '', location.pathname + location.search + '#' + section);
    return Promise.resolve(render());
  };
  const askAssistant = async text => {
    await go('assistant');
    for (let i = 0; i < 50; i++) {
      const input = document.querySelector('#assistant-input');
      if (input && !input.disabled) {
        input.value = (input.value ? input.value + '\n\n' : '') + text;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.focus();
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  };

  const items = target => {
    const list = [];
    const field = editable(target);
    const link = target.closest?.('a[href]');
    const message = target.closest?.('.assistant-message,.tg-msg');
    const selected = field ? fieldSelection(field) : pageSelection();
    if (field && !field.readOnly && !field.disabled && field.tagName !== 'DIV') {
      list.push({ label: 'Вырезать', icon: 'x', key: 'Ctrl+X', disabled: !selected, run: async () => { await copy(selected); insert(field, ''); } });
      list.push({ label: 'Копировать', icon: 'copy', key: 'Ctrl+C', disabled: !selected, run: () => copy(selected) });
      list.push({ label: 'Вставить', icon: 'file-text', key: 'Ctrl+V', run: async () => {
        try { const text = await navigator.clipboard.readText(); field.focus(); insert(field, text); }
        catch { toast('Браузер не дал доступ к буферу — используйте Ctrl+V'); }
      } });
      list.push({ label: 'Выделить всё', icon: 'check', key: 'Ctrl+A', run: () => { field.focus(); field.select?.(); } });
      list.push('sep');
    } else if (selected) {
      list.push({ label: 'Копировать', icon: 'copy', key: 'Ctrl+C', run: () => copy(selected) });
      list.push({ label: 'Спросить ассистента', icon: 'sparkle', run: () => askAssistant(selected) });
      list.push('sep');
    }
    if (link) {
      const href = link.href;
      list.push({ label: 'Открыть в новой вкладке', icon: 'arrow-up-right', run: () => window.open(href, '_blank', 'noopener') });
      if (/^https?:/.test(href)) list.push({ label: 'Копировать ссылку', icon: 'link', run: () => copy(href) });
      list.push('sep');
    }
    if (message && !selected) {
      const text = (message.querySelector('.assistant-markdown,.tg-text') || message).innerText.trim();
      if (text) { list.push({ label: 'Копировать сообщение', icon: 'copy', run: () => copy(text) }); list.push('sep'); }
    }
    list.push({ label: 'Назад', icon: 'arrow-left', run: () => history.back() });
    list.push({ label: 'Обновить раздел', icon: 'refresh', run: () => (typeof render === 'function' ? render() : location.reload()) });
    list.push('sep');
    list.push({ label: 'Поиск по Сметре', icon: 'search', key: 'Ctrl+K', run: () => document.querySelector('#command-open')?.click() });
    if (typeof tab === 'undefined' || tab !== 'assistant') list.push({ label: 'Открыть ассистента', icon: 'sparkle', run: () => go('assistant') });
    list.push({ label: document.documentElement.dataset.theme === 'light' ? 'Тёмная тема' : 'Светлая тема', icon: document.documentElement.dataset.theme === 'light' ? 'moon' : 'sun', run: () => document.querySelector('#theme')?.click() });
    // Trim separators at the edges and doubled separators.
    return list.filter((item, i, all) => item !== 'sep' || (i > 0 && i < all.length - 1 && all[i - 1] !== 'sep'));
  };

  const close = (restore = true) => {
    if (!menu) return;
    const node = menu; menu = null;
    node.classList.add('is-closing');
    setTimeout(() => node.remove(), 120);
    document.removeEventListener('pointerdown', outside, true);
    window.removeEventListener('blur', blurClose);
    window.removeEventListener('resize', blurClose);
    document.removeEventListener('scroll', blurClose, true);
    if (restore && returnFocus?.isConnected) returnFocus.focus?.({ preventScroll: true });
  };
  const outside = event => { if (menu && !menu.contains(event.target)) close(false); };
  const blurClose = () => close(false);

  const open = (event, entries) => {
    close(false);
    returnFocus = document.activeElement;
    menu = document.createElement('div');
    menu.className = 'sm-context';
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', 'Действия');
    for (const entry of entries) {
      if (entry === 'sep') { const line = document.createElement('div'); line.className = 'sm-context-sep'; line.setAttribute('role', 'separator'); menu.append(line); continue; }
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'sm-context-item';
      button.setAttribute('role', 'menuitem');
      button.tabIndex = -1;
      button.disabled = Boolean(entry.disabled);
      button.innerHTML = icon(entry.icon) + '<span></span>' + (entry.key ? '<kbd></kbd>' : '');
      button.querySelector('span').textContent = entry.label;
      if (entry.key) button.querySelector('kbd').textContent = entry.key;
      button.addEventListener('click', () => { close(false); Promise.resolve(entry.run()).catch(() => {}); });
      menu.append(button);
    }
    document.body.append(menu);
    // The top layer keeps the menu above open modal dialogs.
    if (typeof menu.showPopover === 'function') { menu.setAttribute('popover', 'manual'); try { menu.showPopover(); } catch {} }
    const rect = menu.getBoundingClientRect(), margin = 8;
    const left = Math.min(event.clientX, innerWidth - rect.width - margin);
    const top = event.clientY + rect.height > innerHeight - margin ? Math.max(margin, event.clientY - rect.height) : event.clientY;
    menu.style.left = Math.max(margin, left) + 'px';
    menu.style.top = top + 'px';
    menu.querySelector('.sm-context-item:not(:disabled)')?.focus({ preventScroll: true });
    menu.addEventListener('keydown', key => {
      const buttons = [...menu.querySelectorAll('.sm-context-item:not(:disabled)')];
      const index = buttons.indexOf(document.activeElement);
      if (key.key === 'Escape') { key.preventDefault(); close(); }
      else if (key.key === 'ArrowDown' || key.key === 'ArrowUp') { key.preventDefault(); const step = key.key === 'ArrowDown' ? 1 : -1; buttons[(index + step + buttons.length) % buttons.length]?.focus(); }
      else if (key.key === 'Home' || key.key === 'End') { key.preventDefault(); buttons[key.key === 'Home' ? 0 : buttons.length - 1]?.focus(); }
      else if (key.key === 'Tab') { key.preventDefault(); close(); }
    });
    setTimeout(() => {
      document.addEventListener('pointerdown', outside, true);
      window.addEventListener('blur', blurClose);
      window.addEventListener('resize', blurClose);
      document.addEventListener('scroll', blurClose, true);
    });
  };

  document.addEventListener('contextmenu', event => {
    if (event.shiftKey || !fine() || event.defaultPrevented) return;
    const target = event.target instanceof Element ? event.target : event.target?.parentElement;
    if (!target || target.closest('.sm-context,[data-native-context]')) return;
    // Only inside the cabinet; the sign-in screen keeps the browser menu.
    if (!target.closest('#shell,.app-nav,#communication-center,dialog[open]')) return;
    event.preventDefault();
    open(event, items(target));
  });
  window.SmetraContextMenu = { close };
})();
