/* Local, MIT-licensed Phosphor icons. Captions and accessible names stay intact. */
(() => {
  'use strict';
  const navigation = {
    today:'house', dashboard:'house', clients:'users', quotes:'file-text', projects:'briefcase',
    construction:'buildings', leads:'users', tasks:'check-square', calendar:'calendar',
    assistant:'sparkle', finance:'wallet', catalog:'book-open', files:'folder',
    documents:'files', team:'users', notifications:'bell', billing:'credit-card',
    support:'lifebuoy', settings:'gear', admin:'shield-check'
  };
  const explicit = {
    'assistant-send':'arrow-up-right', 'assistant-rename':'pencil-simple',
    'assistant-pin':'push-pin', 'assistant-delete':'trash',
    'assistant-context-remove':'x', 'assistant-knowledge':'book-open',
    'logout':'sign-out'
  };
  const captions = [
    [/^(создать|добавить|новый|новая|\+ диалог)/i,'plus'],
    [/^(сохранить|применить|подтвердить)/i,'check'],
    [/^(скачать|экспорт)/i,'download-simple'],
    [/^(обновить|повторить)/i,'arrow-clockwise'],
    [/^(прикрепить|выбрать файл)/i,'paperclip'],
    [/^(найти|поиск)/i,'magnifying-glass'],
    [/^(отправить|поделиться|клиентская ссылка)/i,'arrow-up-right'],
    [/^(фильтр)/i,'funnel'],[/^(диалоги)/i,'chat-circle']
  ];
  const sidebar = document.getElementById('sidebar');
  const groups = [...(sidebar?.querySelectorAll('.sidebar-group') || [])];
  if (groups.length) {
    const primary = groups[0];
    const order = ['dashboard','assistant','quotes','projects','clients'];
    order.forEach(tab => {
      const control = sidebar.querySelector(`[data-tab="${tab}"]`);
      if (control) primary.append(control);
    });
    const headings = ['','Работа','Библиотека','Аккаунт'];
    groups.forEach((group,index) => {
      const heading = group.querySelector('.sidebar-heading');
      if (!heading) return;
      if (index === 0) { heading.hidden = true; return; }
      const toggle = document.createElement('button');
      toggle.type = 'button'; toggle.className = 'sidebar-disclosure';
      toggle.textContent = headings[index] || heading.textContent;
      toggle.setAttribute('aria-expanded','false');
      const items = document.createElement('div');
      items.className = 'sidebar-group-items'; items.id = `sidebar-group-${index}`; items.hidden = true;
      toggle.setAttribute('aria-controls',items.id);
      [...group.querySelectorAll('[data-tab]')].forEach(control => items.append(control));
      // Construction belongs to the work group, alongside tasks and calendar.
      if (index === 1) {
        const construction = primary.querySelector('[data-tab="construction"]');
        if (construction) items.prepend(construction);
      }
      heading.replaceWith(toggle); group.append(items);
      toggle.onclick = () => {
        items.hidden = !items.hidden;
        toggle.setAttribute('aria-expanded',String(!items.hidden));
      };
    });
  }
  function syncNavigation() {
    const active = sidebar?.querySelector('[data-tab].active');
    document.querySelectorAll('[data-mode]').forEach(control => {
      control.setAttribute('aria-pressed',String(control.dataset.mode === (active?.dataset.tab === 'assistant'?'assistant':'dashboard')));
    });
    const items = active?.closest('.sidebar-group-items');
    if (items?.hidden) {
      items.hidden = false;
      items.previousElementSibling?.setAttribute('aria-expanded','true');
    }
  }
  document.querySelectorAll('[data-mode]').forEach(control => {
    control.onclick = () => sidebar?.querySelector(`[data-tab="${control.dataset.mode}"]`)?.click();
  });
  const collapse = document.getElementById('sidebar-collapse');
  if (collapse) collapse.onclick = () => {
    const compact = document.body.classList.toggle('sidebar-compact');
    collapse.setAttribute('aria-expanded',String(!compact));
    collapse.setAttribute('aria-label',compact?'Развернуть меню':'Свернуть меню');
  };
  if (sidebar) new MutationObserver(syncNavigation).observe(sidebar,{attributes:true,attributeFilter:['class'],subtree:true});
  syncNavigation();
  function decorate(root) {
    root.querySelectorAll('#capture-text').forEach(input => {
      if (input.dataset.autogrow) return;
      input.dataset.autogrow = 'true';
      const resize = () => {
        input.style.height = 'auto';
        input.style.height = `${Math.min(180,Math.max(44,input.scrollHeight))}px`;
        input.style.overflowY = input.scrollHeight > 180 ? 'auto':'hidden';
      };
      input.addEventListener('input',resize); resize();
    });
    root.querySelectorAll('.today-actions').forEach(section => {
      section.classList.toggle('is-empty', !!section.querySelector('.today-clear'));
    });
    root.querySelectorAll('.dashboard-work').forEach(section => {
      section.classList.toggle('is-empty', !section.querySelector('.record-line,.quote'));
    });
    root.querySelectorAll('.workspace-home .dashboard-aside').forEach(section => {
      section.classList.toggle('is-empty', !section.querySelector('.record-line'));
    });
    root.querySelectorAll('button, a.btn').forEach(button => {
      if (button.dataset.uiIcon) return;
      const name = navigation[button.dataset.tab] || explicit[button.id] ||
        captions.find(([pattern]) => pattern.test(button.textContent.trim()))?.[1];
      if (!name) return;
      button.dataset.uiIcon = name;
      button.style.setProperty('--ui-icon', `url('/assets/icons/${name}.svg')`);
      if (button.hasAttribute('aria-label') && /^[↗✎◇×]$/.test(button.textContent.trim())) {
        button.dataset.uiIconOnly = 'true';
      }
    });
  }
  decorate(document);
  let pending = false;
  const content = document.getElementById('content');
  if (!content) return;
  new MutationObserver(records => {
    if (pending || !records.some(record => record.addedNodes.length)) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; decorate(content); });
  }).observe(content, {childList:true, subtree:true});
})();
