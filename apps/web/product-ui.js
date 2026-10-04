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
  function decorate(root) {
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
