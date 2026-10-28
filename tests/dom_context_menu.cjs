const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const html=[
'<div id="shell"><nav id="sidebar"><button data-tab="assistant">Ассистент</button></nav>',
'<button id="command-open">Поиск</button><main id="content">',
'<section class="quote-row"><button data-work="quote" data-id="q17"><strong>Ремонт кухни</strong></button></section>',
'<section class="record-line"><button data-work="entity" data-kind="clients" data-id="c1"><strong>Иван Петров</strong></button></section>',
'<section class="record-line"><button data-work="task-toggle" aria-checked="false">Готово</button><button data-work="entity" data-kind="tasks" data-id="t1"><strong>Замер кухни</strong></button></section>',
'<section class="record-line document-row"><strong>Акт приёмки №15</strong><button data-work="ask-document" data-id="doc1">ИИ</button><button data-work="download-document" data-id="doc1">PDF</button></section>',
'<section class="record-line"><button data-work="entity" data-kind="catalog" data-id="cat1"><strong>Шпаклёвка</strong></button><button data-work="catalog-favorite" aria-pressed="false">☆</button></section>',
'<article class="vault-file-tile"><div class="vault-file-details"><strong>contract.pdf</strong></div>',
'<button data-action="open" data-id="f1">Открыть</button><button data-action="ask" data-id="f1">ИИ</button>',
'<button data-action="manage" data-id="f1">Инфо</button><button data-action="archive" data-id="f1">Архив</button>',
'<button data-action="delete" data-id="f1">Удалить</button></article>',
'<div class="record-line file-center-row"><div class="file-description"><strong>Отчёт.md</strong></div><button data-file-open="f2">Открыть</button><button data-file-edit="f2">Изменить</button><button data-file-manage="f2">Инфо</button><button data-file-ask="f2">ИИ</button></div>',
'<table class="estimate-table"><tbody><tr><td><strong>Штукатурка стен</strong></td><td>14 м²</td></tr></tbody></table>',
'<article class="premium-folder"><div><strong>Рабочие документы</strong></div><button data-premium-disable-folder="folder-1">Убрать</button></article>',
'<div class="premium-folder-entry"><button class="premium-folder-select">▱ Договоры</button><button class="premium-folder-enter">Открыть</button></div>',
'<div class="premium-cloud-file"><span class="premium-cloud-file-name">Прайс.xlsx</span></div>',
'<div class="premium-connect" data-cloud-card="google_drive"><div class="premium-connect-copy"><strong>Google Drive</strong></div>',
'<button data-premium-select="google_drive">Выбрать</button><button data-premium-disconnect="conn-1">Отключить</button></div>',
'<div class="assistant-conversation-row" data-thread-id="conv1" data-pinned="0"><button data-conversation="conv1">',
'<span class="assistant-conversation-title">Проверка сметы</span></button><button data-thread-rename>Переименовать</button>',
'<button data-thread-pin>Закрепить</button><button data-thread-delete>Удалить</button></div>',
'<article class="assistant-message"><div class="assistant-markdown">Привет, проверяем смету.</div></article>',
'<textarea id="assistant-input">текст</textarea><input id="secret" type="password" value="private">','<a id="link" href="https://example.org/report">Отчёт</a>',
'<div id="empty">Пустое место</div></main></div>'
].join('');
const dom=new JSDOM(html,{url:'https://smetra.online/app#quotes',runScripts:'outside-only'});
const w=dom.window,d=dom.window.document;
w.matchMedia=()=>({matches:true});w.SmetraIcons={svg:()=>'<svg></svg>'};w.notify=()=>{};
w.navigator.clipboard={writeText:async()=>{},readText:async()=>''};
const receivedContext=[];w.SmetraAssistantContext=context=>receivedContext.push(context);w.SmetraLoadFeature=async()=>{};
w.Workspace={currentWorkspaceId:()=> 'workspace-1'};
w.eval(fs.readFileSync('apps/web/ui/context-menu.js','utf8'));
const labels=sel=>Array.from(w.SmetraContextMenu.describe(d.querySelector(sel)).items,x=>x.label);
const has=(ls,v)=>assert.ok(ls.includes(v),JSON.stringify({ls,v}));
const quote=labels('.quote-row');
has(quote,'Открыть');has(quote,'Спросить ИИ об этом');has(quote,'Скопировать название');
assert.ok(!quote.includes('Светлая тема')&&!quote.includes('Обновить раздел'));
has(labels('[data-kind="clients"]'),'Спросить ИИ об этом');
assert.deepEqual(labels('[data-kind="tasks"]'),['Открыть','Отметить выполненной','Скопировать название']);
assert.deepEqual(labels('.document-row'),['Скачать PDF','Спросить ИИ о документе','Скопировать название']);
assert.deepEqual(labels('[data-kind="catalog"]'),['Открыть','В избранное','Скопировать название']);
assert.deepEqual(labels('.vault-file-tile'),['Открыть','Спросить ИИ о файле','Сведения о файле','В архив','Удалить…','Скопировать название']);
assert.deepEqual(labels('.file-center-row'),['Открыть','Редактировать','Спросить ИИ о файле','Сведения о файле','Скопировать название']);
assert.deepEqual(labels('.estimate-table tbody tr'),['Копировать позицию','Спросить ИИ о позиции']);
assert.deepEqual(labels('.premium-folder'),['Скопировать название','Убрать из синхронизации…']);
has(labels('.premium-folder-entry'),'Открыть вложенные папки');
assert.deepEqual(labels('.premium-cloud-file'),['Скопировать название']);
assert.deepEqual(labels('.premium-connect'),['Показать папки','Отключить…']);
has(labels('.assistant-conversation-row'),'Переименовать');
has(labels('.assistant-conversation-row'),'Закрепить');
has(labels('.assistant-conversation-row'),'Удалить диалог…');
has(labels('.assistant-message'),'Копировать сообщение');
assert.deepEqual(labels('#link'),['Открыть в новой вкладке','Скопировать адрес']);
assert.deepEqual(labels('#assistant-input'),['Вставить','Выделить всё']);
assert.deepEqual(labels('#empty'),['Поиск по Сметре']);
assert.deepEqual(labels('#sidebar button'),['Открыть раздел']);
let opened=0,folderOpened=0,renamed=0;
d.querySelector('[data-action="open"]').onclick=()=>opened++;
d.querySelector('.premium-folder-enter').onclick=()=>folderOpened++;
d.querySelector('[data-thread-rename]').onclick=()=>renamed++;
(async()=>{
  await w.SmetraContextMenu.describe(d.querySelector('.vault-file-tile')).items[0].run();
  await w.SmetraContextMenu.describe(d.querySelector('.premium-folder-entry')).items[1].run();
  await w.SmetraContextMenu.describe(d.querySelector('.assistant-conversation-row')).items[1].run();
  assert.deepEqual([opened,folderOpened,renamed],[1,1,1]);
  await w.SmetraContextMenu.describe(d.querySelector('.quote-row')).items[1].run();
  assert.deepEqual(JSON.parse(JSON.stringify(receivedContext)),[{entity:'quotes',id:'q17',label:'Ремонт кухни',workspace_id:'workspace-1'}],
    'Selected quote id and current workspace are forwarded to assistant context');
  const event=new w.MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:15,clientY:20});
  d.querySelector('.quote-row').dispatchEvent(event);
  assert.equal(event.defaultPrevented,true);
  assert.match(d.querySelector('.sm-context-heading').textContent,/Ремонт кухни/);
  assert.ok([...d.querySelectorAll('.sm-context-item')].some(x=>x.textContent.includes('Спросить ИИ об этом')));
  w.SmetraContextMenu.close();assert.equal(d.querySelectorAll('.sm-context').length,0);
  const shift=new w.MouseEvent('contextmenu',{bubbles:true,cancelable:true,shiftKey:true});
  d.querySelector('#empty').dispatchEvent(shift);
  assert.equal(shift.defaultPrevented,false);
  const passwordEvent=new w.MouseEvent('contextmenu',{bubbles:true,cancelable:true});
  d.querySelector('#secret').dispatchEvent(passwordEvent);
  assert.equal(passwordEvent.defaultPrevented,false,'Password inputs retain the native menu');
  assert.match(fs.readFileSync('apps/web/app.html','utf8'),/context-menu\.js\?v=20261028-target1/);
  dom.window.close();
  console.log('PASS: rightclick scope quote, client, task, file, folder, cloud, chat, link, editor, blank');
})().catch(e=>{console.error(e);process.exit(1)});