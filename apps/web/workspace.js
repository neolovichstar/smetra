/* Workspace UI. All persistent business actions go through the authenticated API. */
window.Workspace = (() => {
  const labels = {draft:'Черновик',sent:'Отправлена',viewed:'Просмотрена',changes_requested:'Нужны изменения',approved:'Согласована',rejected:'Отклонена',expired:'Истекла',planned:'Запланирован',in_progress:'В работе',waiting:'Ожидание',completed:'Завершён',cancelled:'Отменён',todo:'К выполнению',done:'Готово',person:'Физлицо',company:'Компания',low:'Низкий',normal:'Обычный',high:'Высокий',bank_transfer:'Перевод',cash:'Наличные',external:'Внешняя оплата',owner:'Владелец',admin:'Администратор',manager:'Менеджер',member:'Участник',viewer:'Наблюдатель'};
  const names = {clients:'Клиенты',catalog:'Расценки',projects:'Заказы',tasks:'Задачи',leads:'Лиды',documents:'Документы',files:'Файлы',finance:'Финансы',calendar:'Календарь',team:'Команда',notifications:'Уведомления',activity:'История'};
  const e = escapeHtml;
  const moneyFormatters=new Map();
  const money = (n,c='RUB') => {if(!moneyFormatters.has(c))moneyFormatters.set(c,new Intl.NumberFormat('ru-RU',{style:'currency',currency:c,maximumFractionDigits:2}));return moneyFormatters.get(c).format((n||0)/100)};
  const status = value => `<span class="pill status-${e(value)}">${e(labels[value]||value)}</span>`;
  let current, generation=0, workspace, workspaces=[], modal, modalTimer;
  function pageRequest(change=false){const mine=change?++generation:generation,owner=user,section=tab;return ()=>mine===generation&&owner===user&&section===tab}
  const roleCanWrite = () => workspace?.role !== 'viewer';
  const option = (values, selected) => values.map(v=>{const [value,label]=Array.isArray(v)?v:[v,labels[v]||v];return `<option value="${e(value)}" ${value===selected?'selected':''}>${e(label)}</option>`}).join('');
  const field = (key,label,value='',type='text',extra='') => `<div class="field"><label for="f-${key}">${e(label)}</label>${type==='textarea'?`<textarea id="f-${key}" name="${key}" rows="3" ${extra}>${e(value??'')}</textarea>`:`<input id="f-${key}" name="${key}" type="${type}" value="${e(value??'')}" ${extra}>`}</div>`;
  const select = (key,label,values,selected='') => `<div class="field"><label for="f-${key}">${e(label)}</label><select name="${key}" id="f-${key}">${option(values,selected)}</select></div>`;
  const empty = (title,text) => `<div class="empty"><span class="eyebrow">Начните с первого шага</span><h3>${e(title)}</h3><p>${e(text)}</p></div>`;
  const button = (label,action,id='',cls='') => `<button class="btn small ${cls}" data-work="${action}" data-id="${e(id)}">${label}</button>`;
  const mainTitle = (title,subtitle,actions='') => header(title,subtitle,actions);
  const formObject = form => Object.fromEntries(new FormData(form));
  const decimalUnits=(value,places=4)=>{
    const match=String(value??0).trim().match(/^(\d{1,16})(?:\.(\d{0,16}))?(?:e([+-]?\d{1,2}))?$/i);
    if(!match)throw Error('Проверьте числовое значение');
    const exponent=Number(match[3]||0),shift=places+exponent-(match[2]||'').length;
    if(Math.abs(exponent)>12)throw Error('Число слишком большое');
    const digits=BigInt(match[1]+(match[2]||''));
    if(shift>=0)return digits*10n**BigInt(shift);
    const divisor=10n**BigInt(-shift);if(digits%divisor)throw Error('Допустимо до '+places+' знаков после запятой');return digits/divisor;
  };
  const safeMoney=value=>{const number=Number(value);if(!Number.isSafeInteger(number)||number<0)throw Error('Проверьте сумму');return number};
  const amount = value => safeMoney(decimalUnits(value||'0',2));
  const calculateLineTotal=row=>{
    if(row.optional&&!row.included)return 0;
    const scale=10000n,hundred=100n*scale;
    const quantity=decimalUnits(row.quantity||'0'),coefficient=decimalUnits(row.coefficient||'1');
    const markup=decimalUnits(row.markup||'0'),discount=decimalUnits(row.discount||'0'),tax=decimalUnits(row.tax||'0');
    if(discount>hundred||tax>hundred)throw Error('Скидка и налог — до 100%');
    const divisor=scale*scale*hundred*hundred;
    const raw=quantity*BigInt(row.unit_price||0)*coefficient*(hundred+markup)*(hundred-discount);
    const base=(raw+divisor/2n)/divisor;
    return safeMoney(base+(base*tax+hundred/2n)/hundred);
  };
  function closeModal(){if(!modal?.open)return;modal.classList.add('is-closing');clearTimeout(modalTimer);modalTimer=setTimeout(()=>{modal.close();modal.classList.remove('is-closing');document.body.classList.remove('modal-open')},matchMedia('(prefers-reduced-motion: reduce)').matches?0:200)}
  function openModal(title,subtitle,content){
    if(!modal){modal=document.createElement('dialog');modal.id='workspace-dialog';modal.className='experience-dialog workspace-dialog';document.body.append(modal);modal.addEventListener('cancel',ev=>{ev.preventDefault();closeModal()});modal.addEventListener('click',ev=>{if(ev.target===modal){const r=modal.getBoundingClientRect();if(ev.clientX<r.left||ev.clientX>r.right||ev.clientY<r.top||ev.clientY>r.bottom)closeModal()}});modal.addEventListener('close',()=>{if(!modal.open){document.body.classList.remove('modal-open');modal.replaceChildren()}})}
    clearTimeout(modalTimer);modal.classList.remove('is-closing');
    modal.innerHTML=`<div class="modal-topbar"><span>СМЕТРА / РАБОЧЕЕ ПРОСТРАНСТВО</span><button class="icon-button" data-close aria-label="Закрыть"><img class="icon" src="/assets/icons/x.svg" alt=""></button></div><div class="dialog-heading"><div><h2>${e(title)}</h2><p>${e(subtitle)}</p></div></div>${content}`;
    modal.querySelector('[data-close]').onclick=closeModal;
    if(!modal.open)modal.showModal();document.body.classList.add('modal-open');
    return modal;
  }
  async function submitForm(form,fn){
    form.onsubmit=async ev=>{ev.preventDefault();if(form.dataset.submitting==='true')return;form.dataset.submitting='true';const b=form.querySelector('[type=submit]');const error=form.querySelector('[role=alert]');if(b)b.disabled=true;if(error)error.textContent='';try{await fn(formObject(form));}catch(err){if(error)error.textContent=err.message;else notify(err.message)}finally{delete form.dataset.submitting;if(b?.isConnected)b.disabled=false}};
  }
  const formEnd = (text='Сохранить') => `<p class="form-error" role="alert"></p><div class="form-actions"><button class="btn primary" type="submit">${text}</button><button class="btn" type="button" data-cancel>Отмена</button></div></form>`;
  function bindCancel(root){root.querySelector('[data-cancel]')?.addEventListener('click',closeModal)}
  function setWorkspace(response){
    workspace=response.workspace;workspaces=response.workspaces;
    const name=document.querySelector('#workspace-name');if(name)name.textContent=workspace.name;
  }
  async function init(){const mine=generation,owner=user;const response=await api('/workspace');if(mine===generation&&owner===user)setWorkspace(response)}
  async function render(section){
    const mine=++generation;current=section;
    const active=pageRequest();
    if(!['dashboard','quotes',...Object.keys(names)].includes(section))return false;
    if(!workspace && section!=='dashboard')await init();
    if(!active())return true;
    let html='';
    let fileCenterData;
    const add=roleCanWrite()?button(({clients:'Добавить клиента',catalog:'Добавить расценку',projects:'Новый проект',tasks:'Новая задача',leads:'Новый лид'})[section]||'Добавить','new',section,'primary'):'';
    if(section==='dashboard'){
      const response=await api('/dashboard');if(!active())return true;
      setWorkspace(response);
      const data=response.overview,actions=response.actions||{items:[],summary:{}},capabilities=response.capabilities,recent=response.quotes;
      const balance=data.currencies.find(c=>c.currency===workspace.currency)||{paid:0,unpaid:0,cash_profit:0,currency:workspace.currency};
      html=`<div class="dashboard-intro"><h1>Сегодня</h1>${button('Создать смету ↗','quote-new','','primary')}</div>`+
        (roleCanWrite()?`<section class="capture-panel" aria-labelledby="capture-title"><div class="capture-heading"><h2 id="capture-title">Что нужно посчитать?</h2></div><form id="capture-form"><label for="capture-text">Запрос клиента</label><textarea id="capture-text" rows="1" maxlength="8000" placeholder="Вставьте сообщение клиента…"></textarea>${capabilities.ai_drafting?'<label class="capture-file" for="capture-file">Прикрепить файл · до 2 МБ</label><input id="capture-file" type="file" accept=".png,.jpg,.jpeg,.pdf,.txt,.md,.csv,.xlsx,.docx" aria-label="Прикрепить запрос клиента">':''}<div class="capture-actions">${capabilities.ai_drafting?'<button class="btn primary" type="submit">Составить черновик</button>':'<button class="btn primary" type="button" id="capture-manual">Открыть редактор</button>'}</div><p id="capture-status" role="status"></p></form><div class="capture-shortcuts">${button("Создать вручную","quote-new")}${button("Мои расценки","navigate","catalog")}${button("Спросить ассистента","navigate","assistant")}</div></section>`:'')+
        `<div class="dashboard-metrics" aria-label="Показатели работы"><div class="dashboard-metric"><span>Активные проекты</span><strong>${actions.summary.active_projects||0}</strong></div><div class="dashboard-metric"><span>Ждут оплаты</span><strong>${actions.summary.waiting_payments||0}</strong></div><div class="dashboard-metric"><span>Согласовано за месяц</span><strong>${actions.summary.approved_this_month||0}</strong></div><div class="dashboard-metric"><span>Получено за месяц · ${e(balance.currency)}</span><strong>${money(actions.summary.received_this_month?.[balance.currency]||0,balance.currency)}</strong></div></div>`+
        `<section class="today-actions" aria-labelledby="today-actions-title"><div class="section-top"><div><span class="eyebrow">СЛЕДУЮЩИЙ ШАГ</span><h2 id="today-actions-title">Требует внимания</h2></div></div>${actions.items.length?actions.items.map(item=>`<div class="today-action"><div><strong>${e(item.title)}</strong><small>${e(item.detail)}${item.due_date?' · '+e(item.due_date):''}${item.amount_kopecks?' · '+money(item.amount_kopecks,item.currency):''}</small></div><button class="btn small" data-work="${item.kind==='quote'?'quote':'entity'}" data-kind="${item.kind==='project'?'projects':item.kind==='lead'?'leads':'tasks'}" data-id="${e(item.entity_id)}">${e(item.action)} ↗</button></div>`).join(''):'<p class="muted today-clear">На сегодня срочных действий нет. Можно подготовить следующий запрос клиента.</p>'}</section>`+
        `<div class="dashboard-work"><section class="panel"><div class="section-top"><h3>Сметы</h3>${button('Все сметы ↗','navigate','quotes')}</div>${recent.length?quoteRows(recent):empty('Пока нет смет','Создайте первую смету.')}</section><div class="dashboard-aside"><section class="panel"><div class="section-top"><h3>Сроки</h3>${button('Все задачи','navigate','tasks')}</div>${data.deadlines.length?data.deadlines.map(d=>`<div class="record-line"><div><strong>${e(d.name)}</strong><small>${e(d.due_date)} · ${d.kind==='task'?'Задача':'Заказ'}</small></div>${status(d.status)}</div>`).join(''):empty('Пока нет сроков','Добавьте дату к заказу или задаче.')}</section></div></div>`;
      html='<section class="workspace-home">'+html+'</section>';
    }else if(section==='quotes'){
      const result=await api('/quotes');if(!active())return true;
      quotes=result.quotes;
      html=mainTitle('Сметы','',button('Создать смету','quote-new','','primary'))+`<section class="panel"><div class="toolbar"><input type="search" id="workspace-search" placeholder="Название или клиент" aria-label="Поиск смет"></div><div id="records">${quoteRows(quotes)}</div>${quotes.length===30?button('Показать ещё','more-quotes'):''}</section>`;
    }else if(['clients','catalog','projects','tasks','leads'].includes(section)){
      const result=await api('/'+section);if(!active())return true;
      html=mainTitle(names[section],{clients:'Контакты и вся история работы.',catalog:'Единая цена для новых смет. Изменения сохраняются в истории.',projects:'Согласованные условия превращаются в работу.',tasks:'Небольшие шаги к завершённой работе.',leads:'От знакомства до нового заказа.'}[section],add+(section==='leads'&&roleCanWrite()?button('Ссылка для заявки','intake-link'):''))+`<section class="panel"><div class="toolbar"><input id="workspace-search" type="search" aria-label="Поиск" placeholder="${section==='catalog'?'Название, категория или артикул':'Найти по названию'}">${section==='catalog'?`<select id="catalog-category" aria-label="Категория">${option([['','Все категории'],...(result.categories||[]).map(value=>[value,value])],'')}</select><label class="catalog-favorite-filter"><input id="catalog-favorites" type="checkbox"> Избранное</label><label class="catalog-favorite-filter"><input id="catalog-recent" type="checkbox"> Недавние</label>`:''}${['clients','catalog'].includes(section)?button(section==='catalog'?'Импорт':'Импорт CSV','import',section)+button('Экспорт CSV','export',section):''}</div><div id="records">${section==='leads'?kanban(result.items):entityRows(section,result.items)}</div>${result.items.length===50?button('Показать ещё','more-entities',section):''}</section>`;
      window.Workspace.records=result.items;
    }else if(section==='finance'){
      const [overview,receipts,expenses]=await Promise.all([api('/overview'),api('/receipts'),api('/expenses')]);if(!active())return true;
      html=mainTitle('Финансы','Полученные деньги и расходы. Каждая валюта считается отдельно.',button('Записать оплату','money','receipts','primary')+button('Добавить расход','money','expenses'))+
        (overview.currencies.length?overview.currencies.map(c=>`<div class="stats business-stats"><div class="stat"><span>Получено · ${e(c.currency)}</span><strong>${money(c.paid,c.currency)}</strong></div><div class="stat"><span>Расходы</span><strong>${money(c.actual_cost,c.currency)}</strong></div><div class="stat"><span>Денежный результат</span><strong>${money(c.cash_profit,c.currency)}</strong><small>Поступления минус расходы</small></div><div class="stat"><span>Ожидаемая оплата</span><strong>${money(c.unpaid,c.currency)}</strong></div></div>`).join(''):empty('Финансы начинаются с заказа','Создайте заказ из согласованной сметы.'))+
        `<div class="workspace-columns"><section class="panel"><h3>Поступления</h3>${moneyRows(receipts.items)}</section><section class="panel"><h3>Расходы</h3>${moneyRows(expenses.items,true)}</section></div>`;
    }else if(section==='calendar'){
      const result=await api('/overview');if(!active())return true;
      const days=[...new Set(result.deadlines.map(item=>item.due_date))];
      html=mainTitle('Календарь','Ближайшие сроки по задачам и проектам.',button('Новая задача','new','tasks','primary'))+`<section class="panel agenda">${days.length?days.map(day=>`<section class="agenda-day"><time datetime="${e(day)}"><strong>${e(day.slice(-2))}</strong><span>${e(new Intl.DateTimeFormat('ru-RU',{month:'short',weekday:'short'}).format(new Date(day+'T12:00:00')))}</span></time><div>${result.deadlines.filter(item=>item.due_date===day).map(d=>`<div class="record-line"><button class="record-title" data-work="entity" data-kind="${d.kind==='task'?'tasks':'projects'}" data-id="${e(d.id)}"><strong>${e(d.name)}</strong><small>${d.kind==='task'?'Задача':'Проект'}</small></button>${status(d.status)}</div>`).join('')}</div></section>`).join(''):empty('Сроки пока не назначены','Укажите дату в проекте или задаче.')}</section>`;
    }else if(section==='activity'||section==='notifications'){
      const result=await api('/'+section);if(!active())return true;
      html=mainTitle(names[section],section==='activity'?'Кто, что и когда изменил.':'Ответы клиентов и события заказов.',section==='notifications'?button('Отметить прочитанными','read-notifications'):'')+`<section class="panel">${section==='activity'?activityList(result.items):result.items.map(n=>`<div class="record-line ${n.is_read?'':'unread'}"><strong>${e(n.message)}</strong><small>${date(n.created_at)}</small></div>`).join('')||empty('Пока тихо','Новые события появятся здесь.')}</section>`;
    }else if(section==='team'){
      const result=await api('/workspace/members');if(!active())return true;
      html=mainTitle('Рабочее пространство','Роли определяют доступ к данным и действиям.',button('Добавить участника','member','','primary'))+
        `<section class="panel"><div class="form-grid">${select('workspace','Пространство',workspaces.map(w=>[w.id,w.name]),workspace.id)}<div class="field"><label>Ваша роль</label><p>${e(labels[workspace.role])}</p></div></div><h3>Команда</h3>${result.items.map(m=>`<div class="record-line"><div><strong>${e(m.name)}</strong><small>${e(m.email)}</small></div>${status(m.role)}${m.role!=='owner'?button('Убрать','remove-member',m.user_id):''}</div>`).join('')}</section><section class="panel"><h3>Настройки бизнеса</h3><form id="workspace-settings"><div class="form-grid">${field('name','Название',workspace.name,'text','required maxlength="120"')}${select('currency','Валюта',['RUB','USD','EUR','KZT','BYN','GBP'],workspace.currency)}</div>${field('company_details','Реквизиты',workspace.settings.company_details||'','textarea')}${field('pipeline','Этапы лидов — по одному в строке',(workspace.settings.pipeline||['Новый','Связались','Обсуждение','Смета','Ожидает решения','Выигран','Проигран']).join('\n'),'textarea')}<p class="form-error" role="alert"></p><button class="btn primary" type="submit">Сохранить</button></form></section>`;
    }else if(section==='files'){
      fileCenterData=await api('/files');if(!active())return true;
      html=mainTitle('Файлы','Вложения смет, клиентов и заказов. Текстовые файлы доступны для поиска и ассистента.')+
        `<section class="panel file-center"><div class="toolbar"><input id="file-center-search" type="search" aria-label="Поиск файлов" placeholder="Найти файл по названию"></div><div id="file-center-list"></div></section>`;
    }else if(section==='documents'){
      const result=await api('/documents');if(!active())return true;
      html=mainTitle('Документы','Предложения, акты и условия работы.',button('Создать документ','document','','primary'))+`<section class="panel document-register">${result.items.length?result.items.map(d=>`<div class="record-line document-row"><span class="file-type" aria-hidden="true">PDF</span><div><strong>${e(d.name)} № ${d.number}</strong><small>${date(d.created_at)} · ${e(d.template)}</small></div><div class="attachment-actions">${button('Спросить AI','ask-document',d.id).replace('data-work=',`data-label="${e(d.name)}" data-work=`)}${button('Скачать PDF','download-document',d.id)}</div></div>`).join(''):empty('Документы пока не созданы','Выберите смету, вид документа и оформление.')}</section>`;
    }else return false;
    if(!active())return true;
    view(`<section class="workspace-section section-${e(section)}">${html}</section>`);bind(section);
    if(section==='files')bindFileCenter(fileCenterData);
    if(section==='dashboard'&&user.quote_count===0&&roleCanWrite()&&window.SmetraLoadFeature){await window.SmetraLoadFeature('growth');if(!active())return true;window.SmetraGrowth.onboarding(document.querySelector('.workspace-home')||document.querySelector('#content'));}
    if(section==='team')await customFieldSettings();
    return true;
  }
  function bindFileCenter(initial){
    const list=document.querySelector('#file-center-list'),search=document.querySelector('#file-center-search');
    let files=initial.items,timer,request=0;const mine=generation;
    const paint=()=>{list.innerHTML=files.length?files.map(file=>`<div class="record-line file-center-row"><span class="file-type" aria-hidden="true">${e(file.name.split('.').pop().slice(0,4).toUpperCase())}</span><div class="file-description"><strong>${e(file.name)}</strong><small>${Math.ceil(file.size/1024)} КБ · ${date(file.created_at)}</small></div><div class="attachment-actions"><button class="btn small" data-file-open="${e(file.id)}">Открыть</button>${file.name.toLowerCase().endsWith('.md')?`<button class="btn small" data-file-edit="${e(file.id)}">Изменить</button>`:''}${roleCanWrite()?`<button class="btn small" data-file-manage="${e(file.id)}">Данные</button>`:''}${['text/plain','application/pdf','text/csv','application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'].includes(file.mime)?`<button class="btn small" data-file-ask="${e(file.id)}">Спросить AI</button>`:''}</div></div>`).join(''):empty('Файлы не найдены','Прикрепите файл к смете, клиенту или проекту.')};
    paint();
    search.insertAdjacentHTML('afterend','<button class="btn small" id="file-new-note" type="button">+ Заметка .md</button>');
    document.querySelector('#file-new-note').onclick=()=>window.SmetraFileEditor?.open();
    search.oninput=()=>{clearTimeout(timer);const sequence=++request,value=search.value.trim();timer=setTimeout(async()=>{if(!search.isConnected||mine!==generation)return;try{const result=await api('/files?q='+encodeURIComponent(value));if(sequence!==request||!search.isConnected||mine!==generation)return;files=result.items;paint()}catch(error){if(sequence===request&&search.isConnected&&mine===generation)notify(error.message)}},200)};
    list.onclick=event=>{const button=event.target.closest('[data-file-open],[data-file-ask],[data-file-edit],[data-file-manage]');if(!button)return;const id=button.dataset.fileOpen||button.dataset.fileAsk||button.dataset.fileEdit||button.dataset.fileManage,file=files.find(item=>item.id===id);if(!file)return;if(button.dataset.fileAsk)askAbout('files',file.id,file.name);else if(button.dataset.fileManage)manageFile(file.id).catch(error=>notify(error.message));else if(button.dataset.fileEdit)window.SmetraFileEditor?.open(file);else window.SmetraFilePreview?.open(file,workspace?.id)};
  }
  async function manageFile(id){
    const active=pageRequest();
    const [metadata,clients,quotes,projects,objects]=await Promise.all([api('/files/'+encodeURIComponent(id)+'/metadata'),api('/clients'),api('/quotes'),api('/projects'),api('/construction/objects')]);
    if(!active())return;
    const file=metadata.file;
    const groups=[['clients','Клиенты','client_id',clients.items],['quotes','Сметы','quote_id',quotes.quotes],['projects','Заказы','project_id',projects.items],['construction','Объекты','construction_id',objects.items]];
    let selected='';for(const [kind,,field] of groups)if(file[field])selected=kind+':'+file[field];
    const options=groups.map(([kind,title,,items])=>`<optgroup label="${e(title)}">${(items||[]).map(item=>`<option value="${e(kind+':'+item.id)}">${e(item.name||item.title)}</option>`).join('')}</optgroup>`).join('');
    const root=openModal('Данные файла','Содержимое сохраняется. Публичные вложения и файлы журнала переносить нельзя.',`<form><label>Название<input name="name" required maxlength="180" value="${e(file.name)}"></label><label>Прикреплён к<select name="target"><option value="">Сохранить текущую привязку</option>${options}</select></label>${formEnd()}</form>`);
    bindCancel(root);const form=root.querySelector('form');form.elements.target.value=selected;
    if(form.elements.target.value!==selected)form.elements.target.value='';
    submitForm(form,async values=>{const body={name:values.name,metadata_etag:file.metadata_etag};if(values.target&&values.target!==selected){[body.target,body.target_id]=values.target.split(':')}await api('/files/'+encodeURIComponent(id)+'/metadata',{method:'PATCH',body:JSON.stringify(body)});closeModal();notify('Данные файла сохранены');await render('files')});
  }
  function activityList(items){return items.length?`<div class="activity-list">${items.map(a=>`<div class="activity-item"><span class="activity-dot"></span><div><strong>${e(a.action)}</strong><small>${e(a.actor||'Сметра')} · ${date(a.created_at)}</small>${a.detail?`<p>${e(a.detail)}</p>`:''}</div></div>`).join('')}</div>`:empty('История начинается здесь','События появятся после первого действия.')}
  function quoteRows(items){return items.length?items.map(q=>`<div class="record-line quote-row"><button class="record-title" data-work="quote" data-id="${q.id}"><span class="quote-file-icon" aria-hidden="true"></span><span><strong>${e(q.title)}</strong><small>${e(q.client)} · ${q.published_version?'v'+q.published_version:'Новая смета'}</small></span></button><div class="record-meta">${status(q.approval_state)}<b>${money(q.amount_kopecks,q.currency)}</b>${button('Открыть ↗','quote',q.id)}</div></div>`).join(''):empty('Первый расчёт — начало работы','Создайте смету, добавьте позиции и отправьте ссылку клиенту.')}
  function entityRows(kind,items){
    const emptyStates={clients:['Ваши клиенты — здесь','Добавьте контакт, чтобы связать с ним сметы и проекты.'],catalog:['Начните со своих расценок','Добавьте работу или импортируйте прайс.'],projects:['Первый проект впереди','Создайте проект из согласованной сметы.'],tasks:['Всё под контролем','Добавьте задачу и назначьте срок.']};
    if(!items.length)return empty(...(emptyStates[kind]||['Пока нет записей','Добавьте первую запись.']));
    const row=r=>{
      const initials=String(r.name||'').trim().split(/\s+/).slice(0,2).map(word=>Array.from(word)[0]||'').join('').toUpperCase();
      const phone=String(r.phone||'').replace(/[^\d+]/g,'');
      return `<div class="record-line ${kind}-row ${kind==='catalog'?'catalog-row':''}">
        ${kind==='clients'?`<span class="contact-monogram" aria-hidden="true">${e(initials)}</span>`:''}
        ${kind==='tasks'?roleCanWrite()?`<button type="button" class="task-toggle" data-work="task-toggle" data-id="${e(r.id)}" role="checkbox" aria-checked="${r.status==='done'}" aria-label="${r.status==='done'?'Вернуть в работу':'Завершить задачу'}: ${e(r.name)}"></button>`:'<span class="task-readonly" aria-hidden="true"></span>':''}
        <button class="record-title" data-work="entity" data-kind="${kind}" data-id="${e(r.id)}"><strong>${e(r.name)}</strong><small>${e(r.company||r.email||r.category||r.due_date||r.description?.slice(0,80)||'')}${kind==='catalog'&&r.article?' · '+e(r.article):''}</small></button>
        <div class="record-meta">${r.status?status(r.status):''}
          ${kind==='clients'?`${phone?`<a class="contact-link" href="tel:${e(phone)}" aria-label="Позвонить ${e(r.name)}">Телефон</a>`:''}${r.email?`<a class="contact-link" href="mailto:${encodeURIComponent(r.email)}" aria-label="Написать ${e(r.name)}">Почта</a>`:''}`:''}
          ${kind==='catalog'?`<b>${money(r.price,workspace.currency)} <small>/ ${e(r.unit)}</small></b><button class="catalog-star" type="button" data-work="catalog-favorite" data-id="${e(r.id)}" aria-label="${r.favorite?'Убрать из избранного':'Добавить в избранное'}" aria-pressed="${r.favorite?'true':'false'}">${r.favorite?'★':'☆'}</button>`:''}
          ${kind==='projects'?`<b>${money(r.amount_kopecks,r.currency)}</b>`:''}${button('Открыть ↗','entity',r.id).replace('data-work=',`data-kind="${kind}" data-work=`)}
        </div></div>`;
    };
    if(kind==='tasks')return [['todo','К выполнению'],['in_progress','В работе'],['waiting','Ожидание'],['done','Завершено'],['cancelled','Отменено']].map(([state,title])=>{
      const group=items.filter(item=>item.status===state);return group.length?`<section class="task-group"><h3>${title}<span>${group.length}</span></h3>${group.map(row).join('')}</section>`:'';
    }).join('')+items.filter(item=>!['todo','in_progress','waiting','done','cancelled'].includes(item.status)).map(row).join('');
    if(kind==='clients'){
      const sorted=[...items].sort((a,b)=>String(a.name).localeCompare(String(b.name),'ru'));
      const letters=[...new Set(sorted.map(item=>Array.from(String(item.name).trim())[0]?.toUpperCase()||'#'))];
      return letters.map(letter=>`<section class="contact-group"><h3>${e(letter)}</h3><div>${sorted.filter(item=>(Array.from(String(item.name).trim())[0]?.toUpperCase()||'#')===letter).map(row).join('')}</div></section>`).join('');
    }
    return items.map(row).join('');
  }
  function moneyRows(items,expense=false){return items.length?items.map(r=>`<div class="record-line money-row ${expense?'money-expense':'money-income'}"><span class="money-direction" aria-hidden="true">${expense?'−':'+'}</span><div><strong>${e(r.name)}</strong><small>${e(expense?r.category:labels[r.method]||r.method)} · ${e(r.payment_date||r.expense_date)}</small></div><b>${money(r.amount_kopecks,r.currency)}</b></div>`).join(''):empty(expense?'Расходов пока нет':'Поступлений пока нет',expense?'Добавьте расходы по проекту.':'Запишите первую оплату от клиента.')}
  function kanban(items){return `<div class="kanban">${(workspace.settings.pipeline||['Новый','Связались','Обсуждение','Смета','Ожидает решения','Выигран','Проигран']).map(s=>`<section class="kanban-column" data-stage="${e(s)}"><h3>${e(s)} <small>${items.filter(i=>i.status===s).length}</small></h3>${items.filter(i=>i.status===s).map(i=>`<button class="kanban-card" draggable="true" data-work="entity" data-kind="leads" data-id="${i.id}"><strong>${e(i.name)}</strong><small>${money(i.amount_kopecks,workspace.currency)}</small></button>`).join('')}</section>`).join('')}</div>`}
  function bind(section){
    const mine=generation;
    document.querySelector('#content').onclick=ev=>{const b=ev.target.closest('[data-work]');if(b)action(b).catch(err=>notify(err.message))};
    if(section==='dashboard')bindCapture();
    if(section==='catalog'){
      let timer,request=0;
      const refresh=async()=>{if(current!=='catalog'||mine!==generation)return;const sequence=++request,query=catalogQuery();const result=await api('/catalog?'+query);if(current!=='catalog'||mine!==generation||sequence!==request||catalogQuery()!==query)return;window.Workspace.records=result.items;document.querySelector('#records').innerHTML=entityRows('catalog',result.items);const more=document.querySelector('[data-work="more-entities"]');if(more)more.classList.toggle('hidden',result.items.length<50)};
      document.querySelector('#workspace-search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>refresh().catch(err=>notify(err.message)),220)};
      document.querySelector('#catalog-category').onchange=()=>refresh().catch(err=>notify(err.message));
      document.querySelector('#catalog-favorites').onchange=()=>refresh().catch(err=>notify(err.message));
      document.querySelector('#catalog-recent').onchange=()=>refresh().catch(err=>notify(err.message));
      return;
    }
    let timer;
    document.querySelector('#workspace-search')?.addEventListener('input',ev=>{clearTimeout(timer);const value=ev.target.value;timer=setTimeout(async()=>{if(mine!==generation)return;try{const result=await api('/'+section+'?q='+encodeURIComponent(value));if(mine!==generation||current!==section||document.querySelector('#workspace-search')?.value!==value)return;const list=result.quotes||result.items;window.Workspace.records=list;if(section==='quotes')quotes=list;document.querySelector('#records').innerHTML=section==='quotes'?quoteRows(list):section==='leads'?kanban(list):entityRows(section,list);const more=document.querySelector('[data-work^=more-]');if(more)more.classList.toggle('hidden',list.length<(section==='quotes'?30:50))}catch(err){if(mine===generation)notify(err.message)}},220)});
    document.querySelectorAll('[draggable]').forEach(el=>el.ondragstart=ev=>ev.dataTransfer.setData('text/plain',el.dataset.id));
    document.querySelectorAll('[data-stage]').forEach(el=>{el.ondragover=ev=>ev.preventDefault();el.ondrop=async ev=>{ev.preventDefault();const id=ev.dataTransfer.getData('text/plain');const item=window.Workspace.records.find(i=>i.id===id);if(!item)return;try{await api('/leads/'+id,{method:'PATCH',body:JSON.stringify({...item,status:el.dataset.stage})});await render('leads')}catch(err){notify(err.message)}}});
    const switcher=document.querySelector('#f-workspace');if(switcher)switcher.onchange=async()=>{sessionStorage.setItem('workspace_id',switcher.value);sessionStorage.removeItem('smetra.assistant.context');workspace=null;await render(current)};
    const settings=document.querySelector('#workspace-settings');if(settings){settings.querySelectorAll('[id^="f-"]').forEach(control=>{const previous=control.id;control.id='workspace-'+previous;settings.querySelector(`label[for="${previous}"]`)?.setAttribute('for',control.id)});submitForm(settings,async d=>{await api('/workspace',{method:'PATCH',body:JSON.stringify({name:d.name,currency:d.currency,settings:{company_details:d.company_details,pipeline:d.pipeline.split('\n').map(x=>x.trim()).filter(Boolean)}})});await init();notify('Настройки сохранены')})}
  }
  function catalogQuery(){const query=new URLSearchParams();query.set('q',document.querySelector('#workspace-search')?.value||'');const category=document.querySelector('#catalog-category')?.value;if(category)query.set('category',category);if(document.querySelector('#catalog-favorites')?.checked)query.set('favorite','1');if(document.querySelector('#catalog-recent')?.checked)query.set('recent','1');return query.toString()}
  function bindCapture(){
    const form=document.querySelector('#capture-form');if(!form)return;
    const input=form.querySelector('#capture-text'),status=form.querySelector('#capture-status');
    const attachment=form.querySelector('#capture-file');
    attachment?.addEventListener('change',()=>{
      status.textContent=attachment.files[0]?'Файл: '+attachment.files[0].name:'';
    });
    const key='smetra.capture.'+workspace.id;
    try{input.value=localStorage.getItem(key)||''}catch{}
    input.addEventListener('input',()=>{try{localStorage.setItem(key,input.value)}catch{}});
    const manual=async()=>{const text=input.value.trim();if(!text){input.reportValidity();return}await editor({title:text.split(/\n|[.!?]/)[0].slice(0,120),description:text,client:'',items:[{name:'',quantity:'1',unit:'усл.',unit_price:0}]})};
    form.querySelector('#capture-manual')?.addEventListener('click',()=>manual().catch(err=>{status.textContent=err.message}));
    form.addEventListener('submit',async ev=>{ev.preventDefault();const button=form.querySelector('[type=submit]');if(!button||button.disabled)return;const text=input.value.trim(),file=form.querySelector('#capture-file')?.files[0];if(!text&&!file){input.focus();status.textContent='Вставьте запрос или выберите файл.';return}button.disabled=true;status.textContent='Составляем черновик…';try{const body={text};if(file){if(file.size>2_000_000)throw Error('Файл должен быть не больше 2 МБ');const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Не удалось прочитать файл'));reader.readAsDataURL(file)});body.file={name:file.name,mime:file.type||({pdf:'application/pdf',txt:'text/plain',md:'text/plain',csv:'text/csv',xlsx:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',docx:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}[file.name.split('.').pop().toLowerCase()]||''),content}}const result=await api('/ai/draft',{method:'POST',body:JSON.stringify(body)});await editor(result.draft);notify('Черновик готов. Проверьте позиции и цены.')}catch(err){status.textContent=err.message+' Текст сохранён здесь; можно повторить позже.'}finally{button.disabled=false}});
  }
  async function action(b){
    const a=b.dataset.work,id=b.dataset.id;
    if(a==='navigate'){tab=id;location.hash=id;return window.render()}
    if(a==='quote-new')return editor();
    if(a==='task-toggle'){
      const item=window.Workspace.records?.find(row=>row.id===id);if(!item||!roleCanWrite())return;
      b.disabled=true;
      try{const result=await api('/tasks/'+encodeURIComponent(id),{method:'PATCH',body:JSON.stringify({revision:item.revision,status:item.status==='done'?'todo':'done'})});Object.assign(item,result.item);document.querySelector('#records').innerHTML=entityRows('tasks',window.Workspace.records)}
      finally{if(b.isConnected)b.disabled=false}
      return;
    }
    if(a==='intake-link'){const r=await api('/intake',{method:'POST'});await navigator.clipboard.writeText(r.form.public_url);notify('Ссылка для заявки скопирована');return}
    if(a==='quote')return quoteDetail(id);
    if(a==='new')return entityForm(id);
    if(a==='entity')return b.dataset.kind==='catalog'?catalogDetail(id):['projects','clients'].includes(b.dataset.kind)?entityDetail(b.dataset.kind,id):entityForm(b.dataset.kind,id);
    if(a==='catalog-favorite'){const item=window.Workspace.records?.find(row=>row.id===id);if(!item)return;await api('/catalog/'+id,{method:'PATCH',body:JSON.stringify({revision:item.revision,favorite:item.favorite?0:1})});return render('catalog')}
    if(a==='money')return moneyForm(id);
    if(a==='member')return memberForm();
    if(a==='remove-member'){return confirmAction('Убрать участника?','Доступ к этому пространству будет закрыт.',async()=>{await api('/workspace/members/'+id,{method:'DELETE'});await render('team')})}
    if(a==='read-notifications'){await api('/notifications',{method:'POST'});return render('notifications')}
    if(a==='more-quotes'||a==='more-entities'){
      const kind=a==='more-quotes'?'quotes':id;const existing=kind==='quotes'?quotes:window.Workspace.records;
      const q=document.querySelector('#workspace-search')?.value||'';const filters=kind==='catalog'?catalogQuery():'q='+encodeURIComponent(q);const result=await api('/'+kind+'?offset='+existing.length+'&'+filters);const next=result.quotes||result.items;existing.push(...next);document.querySelector('#records').innerHTML=kind==='quotes'?quoteRows(existing):kind==='leads'?kanban(existing):entityRows(kind,existing);if(next.length<(kind==='quotes'?30:50))b.disabled=true;return;
    }
    if(a==='document')return documentForm();
    if(a==='download-document')return download('/documents/'+id+'/pdf','smetra-'+id+'.pdf');
    if(a==='ask-document')return askAbout('documents',id,b.dataset.label||'Документ');
    if(a==='export')return download('/transfer/'+id+'?format=csv',id+'.csv');
    if(a==='import')return importForm(id);
  }
  async function confirmAction(title,text,fn){const root=openModal(title,text,`<form>${formEnd('Подтвердить')}`);bindCancel(root);submitForm(root.querySelector('form'),async()=>{await fn();closeModal()})}
  async function askAbout(entity,id,label){const active=pageRequest();try{if(window.SmetraLoadFeature)await window.SmetraLoadFeature('assistant');if(!active())return;window.SmetraAssistantContext?.({entity,id,label,workspace_id:workspace?.id});document.querySelector('[data-tab="assistant"]')?.click()}catch(error){if(active())notify(error.message)}}
  async function quoteDetail(id){
    const active=pageRequest(true);
    const [{quote:q,activity},versions]=await Promise.all([api('/quotes/'+id),api('/quotes/'+id+'/versions')]);
    if(!active())return;
    view(mainTitle(e(q.title),`${e(q.client)} · ${q.currency} · ${q.published_version?'Версия '+q.published_version:'Новый расчёт'}`,button('← Все сметы','navigate','quotes')+'<button class="btn small" id="ask-ai">Спросить AI ↗</button>')+
      `<div class="workspace-columns quote-detail"><section class="panel"><div class="section-top">${status(q.approval_state)}<span class="muted">${q.view_count} просмотров</span></div><p class="preserve-lines">${e(q.description)}</p>${itemTable(q.items,q.currency)}<div class="quote-summary"><span>Итого</span><strong>${money(q.amount_kopecks,q.currency)}</strong></div><p class="muted preserve-lines">${e(q.terms)}</p><div class="row wrap" id="quote-controls">${q.approval_state!=='approved'?button('Редактировать','edit'):''}${['draft','changes_requested','rejected'].includes(q.approval_state)?button('Отправить клиенту','publish','','primary'):''}${q.published_version?button('Клиентская ссылка ↗','link'):''}${q.approval_state==='approved'?button('Создать заказ','project','','primary'):''}${q.published_version?button('Сравнить версии','review'):''}${button('Создать копию','copy')}${button('Документ','document')}</div></section><aside><section class="panel"><span class="eyebrow">Только для команды</span><h3>Экономика сметы</h3><div class="record-line"><span>Себестоимость</span><strong>${money(q.internal_cost,q.currency)}</strong></div><div class="record-line"><span>Плановая прибыль</span><strong>${money(q.profit,q.currency)}</strong></div><p class="muted">Эти данные скрыты от клиента.</p></section><section class="panel"><h3>Версии</h3>${versions.versions.length?versions.versions.map(v=>`<div class="record-line"><div><strong>v${v.version}</strong><small>${date(v.created_at)} · ${e(v.comment)}</small></div><b>${money(v.snapshot.amount_kopecks,q.currency)}</b>${button('Сравнить','review',String(v.version))}</div>`).join(''):'<p class="muted">Версия фиксируется при отправке.</p>'}</section></aside></div><section class="panel"><h3>История</h3>${activityList(activity)}</section>`);
    const reviewQuote=async options=>{if(window.SmetraLoadFeature)await window.SmetraLoadFeature('quoteReview');if(active())await window.SmetraQuoteReview.open(q,versions.versions,options)};
    document.querySelectorAll('[data-work="review"]').forEach(button=>button.onclick=async event=>{event.stopPropagation();if(button.disabled)return;button.disabled=true;try{await reviewQuote(button.dataset.id?{source:button.dataset.id}:{})}catch(error){if(active())notify(error.message)}finally{if(button.isConnected)button.disabled=false}});
    bind('quotes');document.querySelector('#ask-ai').onclick=()=>askAbout('quotes',id,q.title);document.querySelector('#quote-controls').onclick=async ev=>{const b=ev.target.closest('button');if(!b)return;ev.stopPropagation();b.disabled=true;try{
      if(b.dataset.work==='edit')return editor(q);
      if(b.dataset.work==='link'){await navigator.clipboard.writeText(q.public_url);notify('Ссылка скопирована');return}
      if(b.dataset.work==='publish'&&q.published_version){await reviewQuote({publish:true});return}
      if(b.dataset.work==='publish'){const root=openModal('Отправить новую версию','Клиент увидит зафиксированные позиции, стоимость и условия.',`<form>${field('comment','Что изменилось по сравнению с прошлой версией','','textarea')}${formEnd('Зафиксировать и отправить')}`);bindCancel(root);submitForm(root.querySelector('form'),async d=>{await api('/quotes/'+id+'/publish',{method:'POST',body:JSON.stringify({revision:q.revision,comment:d.comment})});closeModal();await quoteDetail(id)});return}
      if(b.dataset.work==='project'){const r=await api('/quotes/'+id+'/project',{method:'POST'});return entityDetail('projects',r.project.id)}
      if(b.dataset.work==='copy'){const r=await api('/quotes/'+id+'/copy',{method:'POST'});return editor(r.quote)}
      if(b.dataset.work==='document')return documentForm(id);
    }catch(err){notify(err.message)}finally{if(b.isConnected)b.disabled=false}};
    await attachments('quote_id',id);
  }
  function itemTable(items,currency='RUB'){return items?.length?`<div class="table-wrap"><table class="estimate-table"><thead><tr><th>Позиция</th><th>Количество</th><th>Цена</th><th>Сумма</th></tr></thead><tbody>${items.map(i=>`<tr class="${i.included?'':'excluded'}"><td><strong>${e(i.name)}</strong>${i.description?`<small>${e(i.description)}</small>`:''}${i.optional?'<small>Дополнительная позиция</small>':''}</td><td>${e(i.quantity)} ${e(i.unit)}</td><td>${money(i.unit_price,currency)}</td><td>${money(i.subtotal,currency)}${Number(i.tax)?`<small>Налог ${e(i.tax)}%</small>`:''}</td></tr>`).join('')}</tbody></table></div>`:''}
  async function editor(quote){
    const active=pageRequest(true);
    if(window.SmetraLoadFeature)await window.SmetraLoadFeature('quoteEditor');
    if(!workspace)await init();
    if(!active())return;
    const [clients,catalog,capabilities]=await Promise.all([api('/clients'),api('/catalog'),api('/capabilities')]);
    if(!active())return;
    const catalogOptions=items=>[['','Добавить из расценок'],...items.slice().sort((a,b)=>b.favorite-a.favorite).map(c=>[c.id,(c.favorite?'Избранное · ':'')+c.name+' · '+money(c.price,workspace.currency)+' / '+c.unit])];
    const owner=user,workspaceId=workspace.id,checkpointSession=crypto.randomUUID();
    const draftKey='smetra.draft.'+owner.id+'.'+workspaceId+'.'+(quote?.id||'new');
    let rows=quote?.items?.length?structuredClone(quote.items):[{name:'',quantity:'1',unit:'шт.',unit_price:quote?.amount_kopecks||0,cost_price:0,tax:'0',discount:'0',markup:'0',optional:false,included:true,description:'',category:''}];
    rows=rows.map(r=>({line_id:crypto.randomUUID(),cost_price:0,discount:'0',markup:'0',coefficient:'1',tax:'0',included:true,optional:false,...r}));
    let q=quote||{};
    const custom=await customControls('estimates',q.custom_fields);
    if(!active())return;
    view(mainTitle(q.id?'Редактирование сметы':'Новая смета','Черновик сохраняется автоматически. Отправьте клиенту, когда всё готово.',button('← К сметам','navigate','quotes'))+
      `<form id="estimate-editor"><div class="workspace-columns editor-layout"><section class="editor-main"><div class="panel editor-basics"><h3 class="editor-section-title">Данные сметы</h3><div class="form-grid">${field('title','Название',q.title||'','text','required maxlength="120"')}${select('currency','Валюта',[['RUB','Рубли · ₽'],['USD','Доллары · $'],['EUR','Евро · €'],['KZT','Тенге · ₸'],['BYN','Белорусские рубли'],['GBP','Фунты · £']],q.currency||workspace.currency)}${select('client_id','Клиент',[['','Новый клиент'],...clients.items.map(c=>[c.id,c.name])],q.client_id||'')}${field('client','Имя или компания',q.client||'','text','required maxlength="120"')}</div><details class="editor-description" ${q.description?'open':''}><summary>Описание сметы</summary>${field('description','Описание',q.description||'','textarea')}</details></div><section class="panel editor-positions"><div class="section-top"><h3 class="editor-section-title">Позиции</h3><div class="catalog-picker"><input id="catalog-search" type="search" aria-label="Найти расценку" placeholder="Найти расценку"><div class="row">${select('catalog','Добавить из расценок',catalogOptions(catalog.items))}</div></div></div><div class="editor-history"><div><button type="button" class="editor-tool" id="editor-undo" disabled aria-label="Отменить правку">↶ <span>Отменить</span></button><button type="button" class="editor-tool" id="editor-redo" disabled aria-label="Повторить правку">↷ <span>Повторить</span></button></div><span id="editor-save-state" role="status" aria-live="polite">Автосохранение включено</span></div><div class="editor-recovery" id="editor-recovery" hidden><span>Есть черновик с этого устройства</span><button type="button" id="editor-recover">Восстановить</button><button type="button" id="editor-discard">Удалить локальный</button></div><div class="editor-conflict" id="editor-conflict" hidden><p>Другая редакция сохранена на сервере. Ваши правки остались здесь.</p><button type="button" class="btn small" id="editor-reload">Открыть серверную</button><button type="button" class="btn small" id="editor-save-copy">Сохранить правки копией</button></div><button type="button" class="editor-tool" id="editor-retry" hidden>Повторить сохранение</button><div id="editor-rows"></div><details class="editor-bulk" id="editor-bulk"><summary>Изменить несколько позиций</summary><div class="editor-bulk-heading"><strong>Выбранные позиции</strong><span id="editor-bulk-count">Не выбраны</span><button class="editor-bulk-link" type="button" id="editor-bulk-all">Выбрать все</button></div><div class="editor-bulk-controls"><label>Поле<select id="editor-bulk-field"><option value="coefficient">Коэффициент цены</option><option value="markup">Наценка, %</option><option value="unit">Единица</option><option value="category">Категория</option></select></label><label>Новое значение<input id="editor-bulk-value" type="text" inputmode="decimal" maxlength="100" placeholder="Например, 1.15" autocomplete="off"></label><button class="btn small" type="button" id="editor-bulk-preview">Сравнить</button></div><div id="editor-bulk-diff" aria-live="polite"></div><button class="editor-bulk-link" type="button" id="editor-bulk-undo" hidden>Отменить последнюю правку</button></details><button type="button" class="btn small" id="add-row">+ Добавить позицию</button></section><details class="panel"><summary>Условия и сроки</summary>${field('terms','Условия',q.terms||'','textarea')}<div class="form-grid">${field('due_date','Срок выполнения',q.due_date||'','date')}${field('expiry','Предложение действительно до',q.expires_at?new Date(q.expires_at*1000).toISOString().slice(0,10):'','date')}</div></details></section><aside class="editor-aside"><section class="panel"><h3 class="editor-section-title">Итого по смете</h3><div class="editor-total" id="editor-total"></div><p class="muted">С учётом скидок и налогов</p><p class="form-error" role="alert"></p><button class="btn primary full-width" type="submit">Сохранить и закрыть</button><details class="editor-device"><summary>Черновик на устройстве</summary><button class="editor-tool" type="button" id="local-draft">Сохранить контрольную точку</button><button class="editor-tool" type="button" id="restore-draft">Восстановить контрольную точку</button><p class="note" id="draft-state" role="status"></p></details></section></aside></div></form>`);
    bind('quotes');const form=document.querySelector('#estimate-editor');window.SmetraSelects?.enhance(form);
    if(custom.html)form.querySelector('.editor-layout>section').insertAdjacentHTML('beforeend',`<details class="panel"><summary>Дополнительные поля</summary><div class="form-grid">${custom.html}</div></details>`);
    if(capabilities.ai_drafting){const b=document.createElement('button');b.type='button';b.className='editor-tool editor-ai-action';b.textContent='Составить с ассистентом';form.querySelector('.editor-aside .panel').append(b);b.onclick=()=>aiDraft()}
    const selectedRows=new Set();let pendingBulk=null,lastBulk=null,history,writer;
    const live=()=>active()&&form.isConnected&&user===owner&&workspace?.id===workspaceId;
    const rowId=()=>crypto.randomUUID();
    const bulkField=document.querySelector('#editor-bulk-field'),bulkValue=document.querySelector('#editor-bulk-value'),bulkDiff=document.querySelector('#editor-bulk-diff');
    const bulkCount=document.querySelector('#editor-bulk-count'),bulkAll=document.querySelector('#editor-bulk-all'),bulkUndo=document.querySelector('#editor-bulk-undo');
    const lineTotal=calculateLineTotal;
    const total=()=>{try{document.querySelector('#editor-total').textContent=money(rows.reduce((sum,row)=>sum+lineTotal(row),0),form.elements.currency.value)}catch(error){document.querySelector('#editor-total').textContent=error.message}};
    const bulkState=()=>{bulkCount.textContent=selectedRows.size?`${selectedRows.size} из ${rows.length} строк`:'Не выбраны';bulkAll.textContent=selectedRows.size===Math.min(rows.length,50)?'Снять выбор':rows.length>50?'Выбрать первые 50':'Выбрать все';bulkUndo.hidden=!lastBulk;if(selectedRows.size)document.querySelector('#editor-bulk').open=true};
    const clearBulk=()=>{pendingBulk=null;bulkDiff.replaceChildren();bulkState()};
    const paint=()=>{document.querySelector('#editor-rows').innerHTML=rows.map((i,n)=>`<div class="editor-item" data-row="${n}"><div class="item-heading"><label class="editor-row-select"><input type="checkbox" data-bulk-select="${n}" aria-label="Выбрать позицию ${n+1}" ${selectedRows.has(n)?'checked':''}></label><button type="button" class="editor-drag" draggable="true" data-drag="${n}" aria-label="Перетащить позицию ${n+1}">⠿</button><input data-key="name" aria-label="Название позиции ${n+1}" value="${e(i.name)}" placeholder="Название услуги, работы или товара" required maxlength="200"><button type="button" class="icon-button" data-remove="${n}" aria-label="Удалить позицию ${n+1}">×</button></div><div class="editor-row-tools"><span>Позиция ${n+1}</span><div><button type="button" data-move="${n}" data-direction="-1" ${n===0?'disabled':''} aria-label="Переместить позицию ${n+1} вверх">↑</button><button type="button" data-move="${n}" data-direction="1" ${n===rows.length-1?'disabled':''} aria-label="Переместить позицию ${n+1} вниз">↓</button><button type="button" data-duplicate="${n}" aria-label="Копировать позицию ${n+1}">Копировать</button></div></div><div class="item-fields">${rowField('quantity','Количество',i._raw?.quantity??i.quantity,'number','0.0001')}${rowField('unit','Единица',i.unit)}${rowField('unit_price','Цена',i._raw?.unit_price??i.unit_price/100,'number','0.01')}${rowField('cost_price','Себестоимость',i._raw?.cost_price??i.cost_price/100,'number','0.01')}</div><details><summary>Скидка, налог и детали</summary><div class="item-fields">${rowField('discount','Скидка, %',i._raw?.discount??(i.discount||0),'number','0.01')}${rowField('tax','Налог, %',i._raw?.tax??(i.tax||0),'number','0.01')}${rowField('markup','Наценка, %',i._raw?.markup??(i.markup||0),'number','0.01')}${rowField('coefficient','Коэффициент цены',i._raw?.coefficient??(i.coefficient||1),'number','0.001')}${rowField('category','Категория',i.category||'')}</div><label class="check-label"><input type="checkbox" data-key="optional" ${i.optional?'checked':''}> Дополнительная позиция</label><label class="check-label"><input type="checkbox" data-key="included" ${i.included?'checked':''}> Включена в итог</label></details></div>`).join('');total();bulkState()};
    const rowContainer=document.querySelector('#editor-rows');
    rowContainer.oninput=ev=>{const key=ev.target.dataset.key;if(!key)return;const index=Number(ev.target.closest('[data-row]').dataset.row),row=rows[index];if(ev.target.type==='number'){row._raw??={};row._raw[key]=ev.target.value}try{row[key]=ev.target.type==='checkbox'?ev.target.checked:['unit_price','cost_price'].includes(key)?amount(ev.target.value):ev.target.value;ev.target.setCustomValidity('')}catch(error){ev.target.setCustomValidity(error.message);return}if(lastBulk?.field===key&&lastBulk.changes.some(change=>change.index===index))lastBulk=null;total();clearBulk()};
    rowContainer.onchange=ev=>{if(ev.target.dataset.bulkSelect===undefined)return;const index=Number(ev.target.dataset.bulkSelect);if(ev.target.checked){if(selectedRows.size>=50){ev.target.checked=false;notify('За один раз можно изменить до 50 строк');return}selectedRows.add(index)}else selectedRows.delete(index);clearBulk()};
    const changed=(group=null)=>{if(!history)return;history.push(snapshot(),group);historyState();writer?.changed()};
    const structureChanged=()=>{selectedRows.clear();lastBulk=null;clearBulk();paint();changed()};
    const move=(from,to)=>{if(to<0||to>=rows.length||from===to)return;rows.splice(to,0,rows.splice(from,1)[0]);structureChanged()};
    rowContainer.onclick=ev=>{const duplicate=ev.target.closest('[data-duplicate]'),moving=ev.target.closest('[data-move]');if(duplicate){if(rows.length>=200){notify('До 200 позиций в смете');return}const index=Number(duplicate.dataset.duplicate),copy=structuredClone(rows[index]);copy.line_id=rowId();rows.splice(index+1,0,copy);structureChanged();return}if(moving){const index=Number(moving.dataset.move);move(index,index+Number(moving.dataset.direction));return}const b=ev.target.closest('[data-remove]');if(!b)return;if(rows.length===1){notify('Оставьте хотя бы одну позицию');return}rows.splice(Number(b.dataset.remove),1);selectedRows.clear();lastBulk=null;clearBulk();paint();changed()};
    let dragging=null;rowContainer.ondragstart=ev=>{const handle=ev.target.closest('[data-drag]');if(!handle){ev.preventDefault();return}dragging=Number(handle.dataset.drag);ev.dataTransfer?.setData('text/plain',String(dragging));if(ev.dataTransfer)ev.dataTransfer.effectAllowed='move'};
    rowContainer.ondragover=ev=>{if(dragging!==null&&ev.target.closest('[data-row]'))ev.preventDefault()};
    rowContainer.ondrop=ev=>{ev.preventDefault();const row=ev.target.closest('[data-row]');if(row&&dragging!==null)move(dragging,Number(row.dataset.row));dragging=null};rowContainer.ondragend=()=>{dragging=null};
    document.querySelector('#add-row').onclick=()=>{if(rows.length>=200){notify('До 200 позиций в смете');return}rows.push({line_id:rowId(),name:'',quantity:'1',unit:'шт.',unit_price:0,cost_price:0,tax:'0',discount:'0',markup:'0',optional:false,included:true});clearBulk();paint();changed()};
    form.elements.currency.onchange=()=>{total();clearBulk()};
    form.elements.client_id.onchange=()=>{const c=clients.items.find(c=>c.id===form.elements.client_id.value);if(c)form.elements.client.value=c.name};
    let catalogSearchTimer,catalogSearchVersion=0;
    document.querySelector('#catalog-search').oninput=ev=>{clearTimeout(catalogSearchTimer);const value=ev.target.value.trim(),version=++catalogSearchVersion;catalogSearchTimer=setTimeout(async()=>{try{const found=await api('/catalog?q='+encodeURIComponent(value));if(version!==catalogSearchVersion||!form.isConnected)return;catalog.items=found.items;form.elements.catalog.innerHTML=option(catalogOptions(catalog.items),'')}catch(err){notify(err.message)}},220)};
    form.elements.catalog.addEventListener('smetra-select-search',event=>{const input=form.querySelector('#catalog-search');input.value=event.detail.query;input.dispatchEvent(new Event('input',{bubbles:true}))});
    form.elements.catalog.onchange=()=>{const c=catalog.items.find(c=>c.id===form.elements.catalog.value);if(!c)return;if(rows.length>=200){notify('До 200 позиций в смете');return}rows.push({line_id:rowId(),name:c.name,description:c.description,quantity:'1',unit:c.unit,unit_price:c.price,cost_price:c.cost_price,tax:c.tax,category:c.category,discount:'0',markup:'0',optional:false,included:true});form.elements.catalog.value='';paint();window.SmetraSelects?.enhance(form);changed();api('/catalog/'+c.id+'/use',{method:'POST',body:'{}'}).catch(()=>notify('Не удалось обновить список недавних расценок'))};
    bulkAll.onclick=()=>{const select=selectedRows.size!==Math.min(rows.length,50);selectedRows.clear();if(select)rows.slice(0,50).forEach((_,index)=>selectedRows.add(index));rowContainer.querySelectorAll('[data-bulk-select]').forEach(input=>input.checked=selectedRows.has(Number(input.dataset.bulkSelect)));clearBulk()};
    bulkField.onchange=()=>{bulkValue.value='';bulkValue.placeholder=({coefficient:'Например, 1.15',markup:'Например, 8',unit:'Например, м²',category:'Например, Отделка'})[bulkField.value];bulkValue.inputMode=['coefficient','markup'].includes(bulkField.value)?'decimal':'text';clearBulk()};
    bulkValue.oninput=clearBulk;
    document.querySelector('#editor-bulk-preview').onclick=()=>{
      for(const control of rowContainer.querySelectorAll('input[type=number]'))if(!control.reportValidity())return;
      if(!selectedRows.size){notify('Выберите позиции для изменения');return}
      const key=bulkField.value,raw=bulkValue.value.trim();let value=raw;
      if(key==='coefficient'||key==='markup'){
        value=raw.replace(',','.');const numeric=Number(value),minimum=key==='coefficient'?0.001:0,maximum=key==='coefficient'?100:1000;
        if(!/^\d+(\.\d{1,3})?$/.test(value)||!Number.isFinite(numeric)||numeric<minimum||numeric>maximum){notify(key==='coefficient'?'Коэффициент: от 0,001 до 100':'Наценка: от 0 до 1000%');return}
      }else if((key==='unit'&&!value)||value.length>(key==='unit'?30:100)){notify(key==='unit'?'Укажите единицу до 30 символов':'Категория — до 100 символов');return}
      const changes=[...selectedRows].sort((a,b)=>a-b).map(index=>({index,before:String(rows[index][key]??''),after:value,oldTotal:lineTotal(rows[index]),newTotal:lineTotal({...rows[index],[key]:value})}));
      if(changes.some(change=>!Number.isFinite(change.oldTotal)||!Number.isFinite(change.newTotal))){notify('Проверьте числовые поля выбранных строк');return}
      if(changes.every(change=>change.before===change.after)){notify('Выбранные строки не изменятся');return}
      pendingBulk={key,changes};const oldTotal=rows.reduce((sum,row)=>sum+lineTotal(row),0),newTotal=oldTotal+changes.reduce((sum,change)=>sum+change.newTotal-change.oldTotal,0);
      bulkDiff.innerHTML=`<div class="editor-bulk-summary"><strong>Проверьте изменения</strong><span>${money(oldTotal,form.elements.currency.value)} → ${money(newTotal,form.elements.currency.value)}</span></div>${changes.map(change=>`<div class="editor-bulk-diff-row"><span>${e(rows[change.index].name||'Позиция '+(change.index+1))}</span><span>${e(change.before||'—')} → <b>${e(change.after||'—')}</b></span></div>`).join('')}<button class="btn small primary" type="button" id="editor-bulk-apply">Применить к ${changes.length} строкам</button>`;
      document.querySelector('#editor-bulk-apply').onclick=()=>{
        if(!pendingBulk||pendingBulk.changes.some(change=>!rows[change.index]||String(rows[change.index][pendingBulk.key]??'')!==change.before)){notify('Строки изменились. Проверьте правку заново.');clearBulk();return}
        for(const change of pendingBulk.changes){rows[change.index][pendingBulk.key]=change.after;if(rows[change.index]._raw)delete rows[change.index]._raw[pendingBulk.key]}
        lastBulk=pendingBulk;clearBulk();paint();changed();notify('Изменения внесены в черновик сметы');
      };
    };
    bulkUndo.onclick=()=>{
      if(!lastBulk)return;
      if(lastBulk.changes.some(change=>!rows[change.index]||String(rows[change.index][lastBulk.key]??'')!==change.after)){notify('Строки изменились после массовой правки. Отмените их вручную.');return}
      for(const change of lastBulk.changes){rows[change.index][lastBulk.key]=change.before;if(rows[change.index]._raw)delete rows[change.index]._raw[lastBulk.key]}
      lastBulk=null;clearBulk();paint();changed();notify('Массовая правка отменена');
    };
    const controls=()=>Array.from(form.querySelectorAll('[name]')).filter(control=>control.name!=='catalog');
    const snapshot=()=>({fields:Object.fromEntries(controls().map(control=>[control.name,control.type==='checkbox'?control.checked:control.multiple?Array.from(control.selectedOptions).map(o=>o.value):control.value])),items:structuredClone(rows)});
    const payload=()=>{const d=formObject(form);return {title:d.title,client:d.client,client_id:d.client_id||null,currency:d.currency,description:d.description,terms:d.terms,due_date:d.due_date,custom_fields:custom.read(form),expires_at:d.expiry?Math.floor(new Date(d.expiry+'T23:59:59').getTime()/1000):null,items:rows.map(({_raw,...row})=>row)}};
    const restore=stored=>{rows=structuredClone(stored.items).map(row=>({line_id:rowId(),...row}));for(const [key,value] of Object.entries(stored.fields)){const control=form.elements[key];if(!control)continue;if(control.type==='checkbox')control.checked=value;else if(control.multiple)Array.from(control.options).forEach(option=>option.selected=value.includes(option.value));else control.value=value??''}selectedRows.clear();lastBulk=null;clearBulk();paint();window.SmetraSelects?.enhance(form)};
    const historyState=()=>{form.querySelector('#editor-undo').disabled=!history.canUndo;form.querySelector('#editor-redo').disabled=!history.canRedo};
    paint();history=new window.SmetraQuoteEditorState.History(snapshot());
    const saveState=form.querySelector('#editor-save-state'),retry=form.querySelector('#editor-retry'),conflict=form.querySelector('#editor-conflict');
    const recovery=form.querySelector('#editor-recovery');let local;
    try{local=JSON.parse(localStorage.getItem(draftKey)||'null');recovery.hidden=!local?.snapshot}catch{}
    writer=window.SmetraQuoteEditorState.writer({quote:q,active:live,data:payload,snapshot,valid:()=>{try{return form.checkValidity()&&rows.length>0&&rows.every(row=>row.name.trim()&&Number(row.quantity)>0)&&rows.reduce((sum,row)=>sum+lineTotal(row),0)>0}catch{return false}},
      request:api,persist:value=>{try{localStorage.setItem(draftKey,JSON.stringify(value))}catch{saveState.dataset.localUnavailable='true'}},
      state:(kind,text)=>{saveState.dataset.state=kind;saveState.textContent=text+(saveState.dataset.localUnavailable?' · Локальное хранилище недоступно':'');retry.hidden=!['offline','invalid'].includes(kind);conflict.hidden=kind!=='conflict'},
      accept:(quote,first)=>{q=quote;if(first)user.quote_count++}
    });
    window.SmetraQuoteEditor={leave:()=>{writer.stop();if(window.SmetraQuoteEditor?.form===form)window.SmetraQuoteEditor=null},form};
    const undo=()=>{const value=history.undo();if(value){restore(value);historyState();writer.changed()}};
    const redo=()=>{const value=history.redo();if(value){restore(value);historyState();writer.changed()}};
    form.querySelector('#editor-undo').onclick=undo;form.querySelector('#editor-redo').onclick=redo;
    form.addEventListener('input',ev=>{if(ev.target.closest('#editor-bulk')||ev.target.id==='catalog-search')return;changed(ev.target.name||rows[Number(ev.target.closest('[data-row]')?.dataset.row)]?.line_id+':'+ev.target.dataset.key)});
    form.addEventListener('change',ev=>{if(ev.target.name&&ev.target.name!=='catalog')changed()});
    form.addEventListener('keydown',ev=>{if(!(ev.ctrlKey||ev.metaKey)||ev.altKey||ev.target.closest('#editor-bulk')||ev.target.id==='catalog-search')return;const key=ev.key.toLowerCase();if(key==='z'||key==='y'){ev.preventDefault();key==='y'||ev.shiftKey?redo():undo()}else if(key==='s'){ev.preventDefault();writer.retry()}});
    retry.onclick=()=>writer.retry();
    const recover=async(sourceKey=draftKey)=>{if(saveState.dataset.state==='saving'){notify('Дождитесь текущего сохранения');return}try{const saved=JSON.parse(localStorage.getItem(sourceKey)||'null');if(!saved?.snapshot){notify('Локального черновика нет');return}
      if(saved.quote?.id&&saved.quote.id!==q.id){const result=await api('/quotes/'+saved.quote.id);if(!live())return;await editor(result.quote);const root=document.querySelector('#estimate-editor');if(root){const targetKey='smetra.draft.'+owner.id+'.'+workspaceId+'.'+saved.quote.id;localStorage.setItem(targetKey,JSON.stringify(saved));root.querySelector('#editor-recovery').hidden=false;root.querySelector('#editor-recover').click()}return}
      if(q.id&&!(sourceKey===draftKey+'.manual'&&saved.session===checkpointSession)&&saved.quote?.revision!==q.revision&&!(saved.pending&&saved.quote?.revision===q.revision-1)){notify('Редакция на сервере изменилась. Откройте сохранённые правки как копию.');restore(saved.snapshot);history.push(snapshot());historyState();writer.conflict(saved.quote);conflict.hidden=false;saveState.textContent='Конфликт редакций. Сохраните правки копией.';return}
      restore(saved.snapshot);history.push(snapshot());historyState();writer.restore(saved);recovery.hidden=true;
    }catch(error){if(live())notify(error.message||'Не удалось прочитать черновик')}};
    form.querySelector('#editor-recover').onclick=()=>recover();
    form.querySelector('#restore-draft').onclick=()=>recover(localStorage.getItem(draftKey+'.manual')?draftKey+'.manual':draftKey);
    form.querySelector('#editor-discard').onclick=()=>{localStorage.removeItem(draftKey);recovery.hidden=true};
    form.querySelector('#local-draft').onclick=()=>{try{localStorage.setItem(draftKey+'.manual',JSON.stringify({quote:q,snapshot:snapshot(),session:checkpointSession,savedAt:Date.now()}))}catch{notify('Хранилище устройства недоступно');return}writer.changed();form.querySelector('#draft-state').textContent='Правки сохранены на устройстве; автосохранение продолжится.'};
    form.querySelector('#editor-reload').onclick=async()=>{try{const value=await api('/quotes/'+q.id);if(live())await editor(value.quote)}catch(error){if(live())notify(error.message)}};
    const copyKey=crypto.randomUUID();let copyBody;
    form.querySelector('#editor-save-copy').onclick=async()=>{if(!form.reportValidity())return;const button=form.querySelector('#editor-save-copy');button.disabled=true;try{copyBody??={...payload(),title:payload().title.slice(0,110)+' — копия'};const result=await api('/quotes',{method:'POST',headers:{'Idempotency-Key':copyKey},body:JSON.stringify(copyBody)});if(!live())return;writer.stop(false);window.SmetraQuoteEditor=null;localStorage.removeItem(draftKey);user.quote_count++;await quoteDetail(result.quote.id);notify('Правки сохранены отдельной сметой')}catch(error){if(live())notify(error.message)}finally{button.disabled=false}};
    form.onsubmit=async ev=>{ev.preventDefault();if(!form.reportValidity())return;const button=form.querySelector('[type=submit]');if(button.disabled)return;button.disabled=true;try{const saved=await writer.flush();if(!saved||!live())return;writer.stop(false);window.SmetraQuoteEditor=null;localStorage.removeItem(draftKey);await quoteDetail(saved.id);notify('Смета сохранена')}catch(error){if(live())notify(error.message)}finally{button.disabled=false}};
  }

  function rowField(key,label,value,type='text',step=''){const limits={quantity:[.0001,1000000],unit_price:[0,10000000000],cost_price:[0,10000000000],discount:[0,100],tax:[0,100],markup:[0,10000],coefficient:[.001,100]}[key]||[0,10000000000];return `<label>${label}<input data-key="${key}" value="${e(value)}" type="${type}" ${type==='number'?`required min="${limits[0]}" max="${limits[1]}" step="${step||'1'}"`:''} aria-label="${label}"></label>`}
  async function catalogDetail(id){
    const {item}=await api('/catalog/'+id);
    const history=item.price_history||[];
    const count=history.length,plural=count%10===1&&count%100!==11?'запись':[2,3,4].includes(count%10)&&!(count%100>=12&&count%100<=14)?'записи':'записей';
    view(mainTitle(e(item.name),'',button('← К расценкам','navigate','catalog')+(roleCanWrite()?button('Редактировать','catalog-edit',id,'primary'):''))+
      `<section class="catalog-detail"><div class="catalog-detail-price"><span class="eyebrow">ТЕКУЩАЯ ЦЕНА</span><strong>${money(item.price,workspace.currency)}</strong><span>за ${e(item.unit)}</span></div><div class="catalog-detail-meta"><div><span>Категория</span><strong>${e(item.category||'Без категории')}</strong></div><div><span>Тип</span><strong>${e({work:'Работа',material:'Материал',equipment:'Оборудование',service:'Услуга',other:'Прочее'}[item.item_type]||item.item_type)}</strong></div>${item.article?`<div><span>Артикул</span><strong>${e(item.article)}</strong></div>`:''}<div><span>Себестоимость</span><strong>${money(item.cost_price,workspace.currency)}</strong></div></div></section>`+
      `${item.description?`<section class="catalog-description"><h2>Описание</h2><p class="preserve-lines">${e(item.description)}</p></section>`:''}`+
      `<section class="catalog-history"><div class="section-top"><h2>История цены</h2><span>${count} ${plural}</span></div>${history.length?history.map((entry,index)=>`<div class="catalog-history-row"><time>${date(entry.created_at)}</time><strong>${money(entry.price,workspace.currency)}</strong><span>${index===history.length-1?'Начальная цена':history[index+1]&&entry.price!==history[index+1].price?`Изменение ${money(entry.price-history[index+1].price,workspace.currency)}`:'Изменена себестоимость'}</span></div>`).join(''):'<p class="muted">История начнётся со следующего изменения цены.</p>'}</section>`);
    bind('catalog-detail');
    document.querySelector('[data-work="catalog-edit"]')?.addEventListener('click',()=>entityForm('catalog',id));
  }
  async function entityForm(kind,id,defaults={}){
    const item=id?(await api('/'+kind+'/'+id)).item:defaults;
    let fields=field('name','Название / имя',item.name||'','text','required maxlength="200"');
    if(kind==='clients')fields+=select('type','Тип',['person','company'],item.type||'person')+field('company','Компания',item.company)+field('email','Почта',item.email,'email')+field('phone','Телефон',item.phone,'tel')+field('telegram','Telegram',item.telegram)+field('notes','Заметки',item.notes,'textarea');
    if(kind==='catalog')fields+=select('item_type','Тип',[['work','Работа'],['material','Материал'],['equipment','Оборудование'],['service','Услуга'],['other','Прочее']],item.item_type||'service')+field('price','Цена',item.price?item.price/100:0,'number','min="0" step="0.01"')+field('cost_price','Себестоимость',item.cost_price?item.cost_price/100:0,'number','min="0" step="0.01"')+field('unit','Единица',item.unit||'шт.')+field('consumption_rate','Расход на единицу работы',item.consumption_rate||'0','number','min="0" step="any"')+field('category','Категория',item.category)+field('supplier','Поставщик',item.supplier)+field('article','Артикул',item.article)+field('tax','Налог, %',item.tax||'0','number','min="0" max="100" step="0.01"')+field('description','Описание',item.description,'textarea')+field('notes','Примечание',item.notes,'textarea')+`<label class="catalog-favorite-field"><input type="checkbox" name="favorite" value="1" ${item.favorite?'checked':''}> В избранном</label>`;
    if(['projects','stages','tasks','leads'].includes(kind)){
      fields+=field('description','Описание',item.description,'textarea');
      if(kind==='tasks')fields+=select('status','Статус',['todo','in_progress','done'],item.status||'todo')+select('priority','Приоритет',['low','normal','high'],item.priority||'normal');
      else fields+=select('status','Статус',kind==='leads'?(workspace.settings.pipeline||['Новый','Связались','Обсуждение','Смета','Ожидает решения','Выигран','Проигран']):(workspace.settings.project_statuses||['planned','in_progress','waiting','completed','cancelled']),item.status|| (kind==='leads'?'Новый':'planned'))+field('amount_kopecks','Стоимость',item.amount_kopecks?item.amount_kopecks/100:0,'number','min="0" step="0.01"');
      if(kind!=='leads')fields+=field('due_date','Срок',item.due_date||'','date');
      if(kind==='projects')fields+=select('currency','Валюта',['RUB','USD','EUR','KZT','BYN','GBP'],item.currency||workspace.currency);
      if(['tasks','stages'].includes(kind)){const projects=await api('/projects');fields+=select('project_id','Заказ',[['','Не привязана'],...projects.items.map(p=>[p.id,p.name])],item.project_id||'')}
    }
    const custom=['clients','projects'].includes(kind)?await customControls(kind,item.custom_fields):null;
    const root=openModal(id?'Редактирование':'Новая запись',names[kind]||'Этап заказа',`<form id="entity-form"><div class="form-grid">${fields}${custom?.html||''}</div>${formEnd()}`);bindCancel(root);
    if(kind==='leads'&&item.request){const request=item.request;root.querySelector('form').insertAdjacentHTML('beforebegin',`<div class="intake-request"><span class="eyebrow">ЗАЯВКА КЛИЕНТА</span><p class="preserve-lines">${e(request.details)}</p><div class="record-line"><span>Бюджет</span><strong>${request.budget_kopecks?money(request.budget_kopecks,workspace.currency):'Не указан'}</strong></div>${request.due_date?`<div class="record-line"><span>Срок</span><strong>${e(request.due_date)}</strong></div>`:''}${request.comment?`<p class="muted preserve-lines">${e(request.comment)}</p>`:''}<button type="button" class="btn small" id="request-client">Открыть клиента ↗</button></div>`);root.querySelector('#request-client').onclick=()=>{closeModal();entityDetail('clients',request.client_id)}}
    submitForm(root.querySelector('form'),async d=>{for(const k of ['price','cost_price','amount_kopecks'])if(k in d)d[k]=amount(d[k]);if(kind==='catalog'){d.favorite=root.querySelector('[name="favorite"]').checked?1:0;if(!id){const matches=(await api('/catalog?q='+encodeURIComponent(d.name))).items.filter(row=>row.name.trim().toLocaleLowerCase('ru')===d.name.trim().toLocaleLowerCase('ru')&&row.unit.trim().toLocaleLowerCase('ru')===d.unit.trim().toLocaleLowerCase('ru'));if(matches.length&&!root.querySelector('#catalog-duplicate-override')?.checked){if(!root.querySelector('#catalog-duplicate-override'))root.querySelector('.form-actions').insertAdjacentHTML('beforebegin','<label class="catalog-duplicate-warning"><input id="catalog-duplicate-override" type="checkbox"> Создать ещё одну позицию с таким названием и единицей</label>');throw Error('Похожая расценка уже есть. Откройте её или разрешите создание дубликата.')}}}if(custom)d.custom_fields=custom.read(root.querySelector('form'));if(id)d.revision=item.revision;if(item.project_id&&!d.project_id)d.project_id=item.project_id;if(item.quote_id){d.amount_kopecks=item.amount_kopecks;d.currency=item.currency}await api('/'+kind+(id?'/'+id:''),{method:id?'PATCH':'POST',body:JSON.stringify(d)});closeModal();if(defaults.project_id)await entityDetail('projects',defaults.project_id);else if(kind==='catalog'&&id)await catalogDetail(id);else await render(current);notify('Сохранено')});
  }
  async function entityDetail(kind,id){
    const active=pageRequest(true);
    const {item:p}=await api('/'+kind+'/'+id);
    if(!active())return;
    view(mainTitle(e(p.name),kind==='projects'?'Условия, этапы и деньги по заказу.':'История отношений с клиентом.',button('← Назад','navigate',kind)+'<button class="btn small" id="ask-ai">Спросить AI ↗</button>')+`<div class="workspace-columns"><section class="panel"><div class="section-top"><h3>${kind==='projects'?'Заказ':'Контакты'}</h3><button class="btn small" id="edit-entity">Редактировать</button></div>${p.status?status(p.status):''}<p class="preserve-lines">${e(p.description||p.notes||'')}</p>${kind==='projects'?`<div class="quote-summary"><span>Стоимость</span><strong>${money(p.amount_kopecks,p.currency)}</strong></div><div class="record-line"><span>Получено</span><b>${money(p.paid,p.currency)}</b></div><div class="record-line"><span>Осталось</span><b>${money(p.amount_kopecks-p.paid,p.currency)}</b></div><div class="row wrap"><button class="btn primary" id="project-receipt">Записать оплату</button><button class="btn" id="project-expense">Добавить расход</button></div>`:`<div class="client-contact-lines">${[p.company,p.email,p.phone,p.telegram].filter(Boolean).map(value=>`<p>${e(value)}</p>`).join('')||'<p class="muted">Контакты не указаны.</p>'}</div>`}</section><section class="panel"><div class="section-top"><h3>${kind==='projects'?'Этапы':'Заказы'}</h3>${kind==='projects'?'<button class="btn small" id="new-stage">+ Этап</button>':''}</div>${kind==='projects'?(p.stages.length?p.stages.map(s=>`<div class="record-line"><button class="record-title stage-edit" data-id="${s.id}"><strong>${e(s.name)}</strong><small>${e(s.due_date)}</small></button>${status(s.status)}<b>${money(s.amount_kopecks,p.currency)}</b></div>`).join(''):empty('Разбейте работу на этапы','Название, стоимость и срок — всё необходимое.')):entityRows('projects',p.projects)}</section></div>${kind==='projects'?`<div class="workspace-columns"><section class="panel"><h3>Оплаты</h3>${moneyRows(p.payments.map(r=>({...r,name:p.name,currency:p.currency})))}</section><section class="panel"><h3>Расходы</h3>${moneyRows(p.expenses.map(r=>({...r,name:p.name,currency:p.currency})),true)}</section></div>`:`<section class="panel"><h3>Сметы клиента</h3>${quoteRows(p.quotes)}</section>`}`);
    if(kind==='clients')document.querySelector('#content').insertAdjacentHTML('beforeend',`<div class="workspace-columns client-history"><section class="panel"><h3>Заявки</h3>${p.requests?.length?p.requests.map(r=>`<div class="record-line"><div><strong>${e(r.details.slice(0,160))}</strong><small>${date(r.created_at)}${r.due_date?' · срок '+e(r.due_date):''}</small></div><button class="btn small" data-work="entity" data-kind="leads" data-id="${e(r.lead_id)}">Открыть лид ↗</button></div>`).join(''):empty('Заявок пока нет','Они появятся после отправки клиентской формы.')}</section><section class="panel"><h3>Поступления</h3>${p.payments?.length?p.payments.map(r=>`<div class="record-line"><div><strong>${e(r.name)}</strong><small>${e(r.payment_date)}</small></div><b>${money(r.amount_kopecks,r.currency)}</b></div>`).join(''):empty('Оплат пока нет','Запишите полученную оплату в проекте.')}</section></div><section class="panel"><h3>История клиента</h3>${activityList(p.timeline||[])}</section>`);
    bind(kind);document.querySelector('#ask-ai').onclick=()=>askAbout(kind,id,p.name);document.querySelector('#edit-entity').onclick=()=>entityForm(kind,id);
    document.querySelector('#project-receipt')?.addEventListener('click',()=>moneyForm('receipts',id));document.querySelector('#project-expense')?.addEventListener('click',()=>moneyForm('expenses',id));document.querySelector('#new-stage')?.addEventListener('click',()=>entityForm('stages',null,{project_id:id}));document.querySelectorAll('.stage-edit').forEach(b=>b.onclick=()=>entityForm('stages',b.dataset.id,{project_id:id}));
    await attachments(kind==='projects'?'project_id':'client_id',id);
  }
  async function moneyForm(kind,projectId=''){
    const projects=await api('/projects');const expense=kind==='expenses';
    const root=openModal(expense?'Добавить расход':'Записать полученную оплату',expense?'Расход уменьшит денежный результат заказа.':'Укажите уже полученные деньги. Запись не списывает средства с клиента.',`<form><div class="form-grid">${select('project_id','Заказ',projects.items.map(p=>[p.id,p.name+' · '+p.currency]),projectId)}${field('amount_kopecks','Сумма','','number','min="0.01" step="0.01" required')}${field(expense?'expense_date':'payment_date','Дата',new Date().toISOString().slice(0,10),'date','required')}${expense?field('category','Категория','','text','required'):select('method','Способ',['bank_transfer','cash','external'],'bank_transfer')}</div>${field('comment','Комментарий','','textarea')}${formEnd('Записать')}`);bindCancel(root);const key=crypto.randomUUID();
    submitForm(root.querySelector('form'),async d=>{d.amount_kopecks=amount(d.amount_kopecks);await api('/'+kind,{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify(d)});closeModal();if(projectId)await entityDetail('projects',projectId);else await render('finance')});
  }
  async function memberForm(){const root=openModal('Добавить в команду','Участник должен иметь аккаунт в Сметре.',`<form>${field('email','Почта','','email','required')}${select('role','Роль',['viewer','member','manager','admin'],'member')}${formEnd('Добавить')}`);bindCancel(root);submitForm(root.querySelector('form'),async d=>{await api('/workspace/members',{method:'POST',body:JSON.stringify(d)});closeModal();await render('team')})}
  async function customControls(kind,stored={}){
    const data=await api('/custom-fields');const definitions=data.items.filter(f=>f.entity_type===kind);const values=typeof stored==='string'?JSON.parse(stored):stored||{};
    const html=definitions.map(f=>{const key='custom_'+f.id,value=values[f.id]??'',options=JSON.parse(f.options);if(f.type==='checkbox')return `<label class="check-label"><input name="${key}" type="checkbox" ${value?'checked':''}>${e(f.name)}</label>`;if(f.type==='multi_select')return `<div class="field"><label for="f-${key}">${e(f.name)}</label><select id="f-${key}" name="${key}" multiple>${options.map(o=>`<option ${Array.isArray(value)&&value.includes(o)?'selected':''}>${e(o)}</option>`).join('')}</select></div>`;if(f.type==='select')return select(key,f.name,[['','Не выбрано'],...options],value);return field(key,f.name,value,{text:'text',number:'number',date:'date',url:'url'}[f.type]||'text',f.type==='number'?'step="0.0001"':'')}).join('');
    return {html,read(form){const result={};definitions.forEach(f=>{const control=form.elements['custom_'+f.id];if(!control)return;const value=f.type==='checkbox'?control.checked:f.type==='multi_select'?Array.from(control.selectedOptions).map(o=>o.value):control.value;if(value!==''&&(!Array.isArray(value)||value.length))result[f.id]=value});return result}};
  }
  async function customFieldSettings(){
    const active=pageRequest();
    const data=await api('/custom-fields');if(!active()||current!=='team')return;const section=document.createElement('section');section.className='panel';section.innerHTML=`<div class="section-top"><h3>Дополнительные поля</h3><button class="btn small" id="new-custom-field">+ Поле</button></div><p class="muted">Настройте клиентов, сметы и заказы под свой способ работы.</p>${data.items.map(f=>`<div class="record-line"><strong>${e(f.name)}</strong><small>${e({clients:'Клиенты',estimates:'Сметы',projects:'Заказы'}[f.entity_type])} · ${e(f.type)}</small></div>`).join('')}`;document.querySelector('#content').append(section);section.querySelector('button').onclick=()=>{const root=openModal('Дополнительное поле','Поле появится в редакторе выбранной сущности.',`<form>${field('name','Название','','text','required maxlength="120"')}${select('entity_type','Где показывать',[['clients','Клиенты'],['estimates','Сметы'],['projects','Заказы']],'clients')}${select('type','Тип',[['text','Текст'],['number','Число'],['date','Дата'],['select','Выбор'],['multi_select','Множественный выбор'],['checkbox','Флажок'],['url','Ссылка']],'text')}${field('options','Варианты выбора — по одному в строке','','textarea')}${formEnd('Создать поле')}`);bindCancel(root);submitForm(root.querySelector('form'),async d=>{d.options=d.options.split('\n').map(x=>x.trim()).filter(Boolean);await api('/custom-fields',{method:'POST',body:JSON.stringify(d)});closeModal();await render('team')})};
  }
  async function aiDraft(){const root=openModal('Из описания — в черновик','Текст будет отправлен AI-провайдеру. Проверьте позиции и цены перед сохранением.',`<form>${field('text','Что нужно сделать?','','textarea','required maxlength="8000"')}<p class="muted">Неизвестные цены останутся нулевыми. Ничего не отправляется клиенту автоматически.</p>${formEnd('Составить черновик')}`);bindCancel(root);submitForm(root.querySelector('form'),async d=>{const r=await api('/ai/draft',{method:'POST',body:JSON.stringify(d)});closeModal();await editor(r.draft)})}
  async function attachments(key,id){
    const active=pageRequest();
    const data=await api('/files?'+key+'='+encodeURIComponent(id));
    if(!active())return;
    const maximum=data.max_upload_bytes||3000000;
    const section=document.createElement('section');
    section.className='panel';
    section.innerHTML=`<div class="section-top"><h3>Файлы</h3>${roleCanWrite()?'<button type="button" class="btn small" id="upload-attachment">+ Прикрепить</button>':''}</div><p class="muted">PNG, JPEG, PDF, TXT, MD, DOCX, XLSX, CSV · до ${maximum/1000000} МБ</p><div class="attachment-list">${data.items.map(f=>`<div class="record-line attachment-row"><div><strong title="${e(f.name)}">${e(f.name)}</strong><small>${Math.ceil(f.size/1024)} КБ · ${f.public?'Доступен клиенту':'Только команда'}</small></div><div class="attachment-actions"><button class="btn small file-preview-open" type="button" data-id="${e(f.id)}">Открыть</button>${['text/plain','application/pdf','text/csv','application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'].includes(f.mime)?`<button class="btn small file-ask-ai" type="button" data-id="${e(f.id)}">Спросить AI</button>`:''}<button class="btn small file-download" type="button" data-id="${e(f.id)}">Скачать</button></div></div>`).join('')||'<p class="muted">Вложений пока нет.</p>'}</div>`;
    document.querySelector('#content').append(section);
    section.querySelectorAll('.file-preview-open').forEach(button=>{
      button.onclick=()=>{
        const file=data.items.find(item=>item.id===button.dataset.id);
        if(file)window.SmetraFilePreview.open(file,workspace?.id);
      };
    });
    section.querySelectorAll('.file-ask-ai').forEach(button=>{
      button.onclick=()=>{
        const file=data.items.find(item=>item.id===button.dataset.id);
        if(file)askAbout('files',file.id,file.name);
      };
    });
    section.querySelectorAll('.file-download').forEach(button=>{
      button.onclick=()=>{
        const file=data.items.find(item=>item.id===button.dataset.id);
        if(file)download('/files/'+file.id,file.name).catch(err=>notify(err.message));
      };
    });
    section.querySelector('#upload-attachment')?.addEventListener('click',()=>{
      const root=openModal('Прикрепить файл','Файл сохранится в выбранной записи.',`<form><div class="field"><label for="attachment-file">Выберите файл</label><input id="attachment-file" type="file" accept=".png,.jpg,.jpeg,.pdf,.txt,.md,.docx,.xlsx,.csv" required></div>${key==='quote_id'?'<label class="check-label"><input name="public" type="checkbox"> Показать по клиентской ссылке</label>':''}${formEnd('Загрузить')}`);
      bindCancel(root);
      submitForm(root.querySelector('form'),async d=>{
        const file=root.querySelector('[type=file]').files[0];
        if(file.size>maximum)throw Error(`Файл должен быть не больше ${maximum/1000000} МБ`);
        const content=await new Promise((resolve,reject)=>{
          const reader=new FileReader();
          reader.onload=()=>resolve(String(reader.result).split(',')[1]);
          reader.onerror=reject;
          reader.readAsDataURL(file);
        });
        await api('/files',{method:'POST',body:JSON.stringify({[key]:id,name:file.name,content,public:d.public?1:0})});
        closeModal();
        section.remove();
        await attachments(key,id);
      });
    });
  }
  async function documentForm(quoteId=''){
    const result=await api('/quotes');const root=openModal('Создать документ','Документ сохранит условия выбранной версии.',`<form>${select('quote_id','Смета',result.quotes.map(q=>[q.id,q.title]),quoteId)}<div class="form-grid">${select('kind','Вид',[['estimate','Смета'],['proposal','Предложение'],['invoice','Счёт'],['act','Акт'],['contract','Договор-шаблон'],['reference','Справка об оплате']],'estimate')}${select('template','Оформление',['Minimal','Classic','Business','Modern'],'Minimal')}</div>${formEnd('Сформировать PDF')}`);bindCancel(root);submitForm(root.querySelector('form'),async d=>{const r=await api('/documents',{method:'POST',body:JSON.stringify(d)});closeModal();await download('/documents/'+r.document.id+'/pdf','smetra-'+r.document.number+'.pdf');tab='documents';location.hash=tab;await window.render()});
  }
  async function download(path,filename){const headers={};if(sessionStorage.getItem('workspace_id'))headers['X-Workspace-Id']=sessionStorage.getItem('workspace_id');const response=await fetch('/api'+path,{credentials:'same-origin',headers});if(!response.ok){const r=await response.json();throw Error(r.error||'Не удалось скачать файл')}const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000)}
  async function importForm(kind){
    const catalog=kind==='catalog';
    const root=openModal(catalog?'Импорт расценок':'Импорт клиентов',catalog?'Вставьте таблицу из Excel или CSV. Изменения существующих позиций не затрагиваются.':'Колонки CSV: name, company, email, phone, notes.',`<form>${catalog?select('input_format','Формат',[['excel','Таблица из Excel'],['csv','CSV']], 'excel'):''}${field('csv',catalog?'Таблица / CSV':'Содержимое CSV','','textarea','required maxlength="50000"')}<p class="muted">${catalog?'Excel: название, цена в ₽, себестоимость в ₽, единица, категория. Первая строка с заголовками необязательна. ':' '}До 200 строк. Ошибки отменяют весь импорт.</p>${catalog?'<label class="catalog-duplicate-warning"><input id="import-allow-duplicates" type="checkbox"> Разрешить повторяющиеся названия и единицы</label>':''}${formEnd('Импортировать')}`);bindCancel(root);
    if(catalog){const format=root.querySelector('[name=input_format]'),input=root.querySelector('[name=csv]'),note=root.querySelector('p.muted');format.onchange=()=>{const csv=format.value==='csv';note.textContent=(csv?'CSV из экспорта Сметры: name, price, cost_price, unit, category. Цены и себестоимость — в копейках. Для цен в рублях выберите таблицу из Excel. ':'Excel: название, цена в ₽, себестоимость в ₽, единица, категория. Первая строка с заголовками необязательна. ')+'До 200 строк. Ошибки отменяют весь импорт.';input.placeholder=csv?'name,price,cost_price,unit,category\nПокраска,25000,12000,м²,Отделка':'Название\tЦена, ₽\tСебестоимость, ₽\tЕдиница\tКатегория\nПокраска\t250\t120\tм²\tОтделка'};format.onchange()}
    submitForm(root.querySelector('form'),async d=>{const csv=catalog&&d.input_format==='excel'?excelTableToCsv(d.csv):d.csv;const r=await api('/transfer/'+kind,{method:'POST',body:JSON.stringify({csv,allow_duplicates:catalog&&root.querySelector('#import-allow-duplicates').checked})});closeModal();await render(kind);notify('Импортировано: '+r.count)})
  }
  function excelTableToCsv(text){
    const rows=text.trim().split(/\r?\n/).map(line=>line.split('\t'));
    if(rows[0]&&['name','название','наименование'].includes(rows[0][0].trim().toLocaleLowerCase('ru')))rows.shift();
    if(!rows.length||rows.length>200)throw Error('Вставьте от 1 до 200 строк');
    const escape=value=>'"'+String(value??'').replaceAll('"','""')+'"';
    const toKopecks=value=>{const clean=String(value??'0').replace(/[\s\u00a0₽]/g,'').replace(',','.');if(!/^\d+(?:\.\d{1,2})?$/.test(clean))throw Error('Цена должна быть числом с двумя знаками после запятой');return amount(clean)};
    return ['name,price,cost_price,unit,category',...rows.map((cells,index)=>{if(cells.length<2||cells.length>5||!cells[0]?.trim())throw Error('Проверьте строку '+(index+1)+': нужно название и цена');return [cells[0].trim(),toKopecks(cells[1]),toKopecks(cells[2]),cells[3]?.trim()||'шт.',cells[4]?.trim()||''].map(escape).join(',')})].join('\n');
  }
  async function intakePage(tokenValue){
    const host=document.querySelector('#public-quote');
    document.querySelector('#landing')?.classList.add('hidden');host.classList.remove('hidden');document.querySelector('.nav .links')?.classList.add('hidden');
    try{
      const form=await api('/public/intake?token='+encodeURIComponent(tokenValue));
      host.innerHTML=`<div class="portal-heading"><span class="eyebrow">ЗАЯВКА ДЛЯ ${e(form.business)}</span><h1>${e(form.title)}</h1><p class="muted">Расскажите о задаче. Исполнитель получит запрос и сможет ответить вам напрямую.</p></div><section class="intake-page-form"><form id="client-intake"><div class="form-grid">${field('name','Ваше имя','','text','required maxlength="120"')}${field('email','Почта для ответа','','email','maxlength="254"')}${field('phone','Телефон','','tel','maxlength="50"')}</div>${field('details','Что нужно сделать','','textarea','required maxlength="3000"')}<div class="form-grid">${field('budget','Ориентир бюджета, ₽','','number','min="0" step="0.01"')}${field('due_date','Желаемый срок','','date')}</div>${field('comment','Дополнение','','textarea','maxlength="3000"')}<div class="field"><label for="intake-file">Файл · PNG, JPEG, PDF, TXT, MD, DOCX, XLSX, CSV до 1 МБ</label><input id="intake-file" type="file" accept=".png,.jpg,.jpeg,.pdf,.txt,.md,.docx,.xlsx,.csv"></div><p class="muted">Укажите почту или телефон. Файл и контакты видит только исполнитель.</p><p class="form-error" role="alert"></p><button class="btn primary" type="submit">Отправить заявку</button></form></section>`;
      submitForm(host.querySelector('form'),async d=>{
        const file=host.querySelector('#intake-file').files[0];let attachment;
        if(file){if(file.size>form.max_upload_bytes)throw Error('Файл должен быть не больше 1 МБ');const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Не удалось прочитать файл'));reader.readAsDataURL(file)});attachment={name:file.name,content}}
        await api('/public/intake',{method:'POST',body:JSON.stringify({token:tokenValue,name:d.name,email:d.email,phone:d.phone,details:d.details,budget_kopecks:d.budget?amount(d.budget):0,due_date:d.due_date,comment:d.comment,...(attachment?{file:attachment}:{})})});
        host.innerHTML='<div class="portal-heading"><span class="eyebrow">ЗАЯВКА ОТПРАВЛЕНА</span><h1>Спасибо.</h1><p class="muted">Исполнитель получил ваш запрос и свяжется с вами по указанному контакту.</p></div>';
      });
    }catch(err){host.innerHTML=`<section class="panel"><h1>Форма недоступна</h1><p>${e(err.message)}</p></section>`}
  }
  async function publicPage(tokenValue){
    const host=document.querySelector('#public-quote');
    document.querySelector('#landing')?.classList.add('hidden');host.classList.remove('hidden');document.querySelector('.nav .links')?.classList.add('hidden');
    try{
      const r=await api('/public/quote?token='+encodeURIComponent(tokenValue));const q=r.quote;
      const canReply=['sent','viewed','changes_requested'].includes(q.approval_state);
      host.innerHTML=`<div class="portal-heading"><span class="eyebrow">Предложение от ${e(r.author)}</span><h1>${e(q.title)}</h1><p class="muted">Для ${e(q.client)} · Версия ${q.published_version}</p>${status(q.approval_state)}</div><div class="workspace-columns"><section class="panel"><p class="preserve-lines">${e(q.description)}</p>${itemTable(q.items,q.currency)}<div class="quote-summary"><span>Итого</span><strong>${money(q.amount_kopecks,q.currency)}</strong></div>${q.due_date?`<p>Срок: ${e(q.due_date)}</p>`:''}<p class="muted preserve-lines">${e(q.terms)}</p></section><aside><section class="panel"><h3>${canReply?'Обсудим следующий шаг?':'Решение по предложению'}</h3>${canReply?`<form id="client-response">${field('name','Ваше имя','','text','required maxlength="120"')}${field('comment','Комментарий','','textarea')}<p class="form-error" role="alert"></p><button class="btn primary full-width" type="submit">Согласовать предложение</button><div class="row wrap"><button class="btn small" type="button" data-response="changes_requested">Нужны изменения</button><button class="btn small" type="button" data-response="rejected">Отклонить</button></div></form>`:`<p class="muted">${q.approval_state==='approved'?'Условия согласованы. Дальнейшая работа появится ниже.':q.approval_state==='draft'?'Исполнитель готовит новую версию. Эта версия сохранена для истории.':'Текущий статус: '+e(labels[q.approval_state]||q.approval_state)}</p>`}</section><section class="panel"><h3>История версий</h3>${r.versions.map(v=>`<div class="record-line"><div><strong>v${v.version}</strong><small>${e(v.comment)}</small></div><b>${money(v.amount_kopecks,q.currency)}</b></div>`).join('')}</section></aside></div>${r.project?`<section class="panel"><div class="section-top"><h2>Работа по заказу</h2>${status(r.project.status)}</div>${(r.stages||[]).map(s=>`<div class="record-line"><div><strong>${e(s.name)}</strong><small>${e(s.due_date)}</small></div>${status(s.status)}</div>`).join('')}<div class="quote-summary"><span>Получено исполнителем</span><strong>${money((r.payments||[]).reduce((s,p)=>s+p.amount_kopecks,0),q.currency)}</strong></div></section>`:''}<section class="panel"><h3>Обсуждение</h3>${r.comments.map(c=>`<article class="comment"><strong>${e(c.author)}</strong><small>${date(c.created_at)}</small><p class="preserve-lines">${e(c.message)}</p></article>`).join('')||'<p class="muted">Вопросы и комментарии к этому предложению.</p>'}<form id="public-comment"><div class="form-grid">${field('name','Ваше имя','','text','required maxlength="120"')}${field('comment','Комментарий','','textarea','required maxlength="3000"')}</div><p class="form-error" role="alert"></p><button class="btn" type="submit">Задать вопрос</button></form></section>`;
      if(r.show_branding!==false)host.insertAdjacentHTML('beforeend','<footer class="public-branding"><span>\u0421\u0434\u0435\u043b\u0430\u043d\u043e \u0432 \u0421\u043c\u0435\u0442\u0440\u0435</span><a href="/app?register=1">\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u0441\u0432\u043e\u044e \u0441\u043c\u0435\u0442\u0443 \u2197</a></footer>');
      if(r.files?.length||r.documents?.length){const section=document.createElement('section');section.className='panel';section.innerHTML='<h3>Файлы и документы</h3>'+[...(r.files||[]).map(f=>({...f,kind:'file'})),...(r.documents||[]).map(f=>({...f,kind:'document'}))].map(f=>`<div class="record-line"><strong>${e(f.name)}</strong><a class="btn small" href="/api/public/${f.kind}?token=${encodeURIComponent(tokenValue)}&id=${encodeURIComponent(f.id)}" download>Скачать</a></div>`).join('');host.append(section)}
      const response=host.querySelector('#client-response');if(response){submitForm(response,async d=>{await api('/public/respond',{method:'POST',body:JSON.stringify({...d,token:tokenValue,version:q.published_version,action:'approved'})});await publicPage(tokenValue)});response.querySelectorAll('[data-response]').forEach(b=>b.onclick=async()=>{if(!response.reportValidity())return;b.disabled=true;try{await api('/public/respond',{method:'POST',body:JSON.stringify({...formObject(response),token:tokenValue,version:q.published_version,action:b.dataset.response})});await publicPage(tokenValue)}catch(err){response.querySelector('[role=alert]').textContent=err.message;b.disabled=false}})}
      submitForm(host.querySelector('#public-comment'),async d=>{await api('/public/comment',{method:'POST',body:JSON.stringify({...d,token:tokenValue})});await publicPage(tokenValue)});
    }catch(err){host.innerHTML=`<section class="panel"><h1>Не удалось открыть предложение</h1><p>${e(err.message)}</p><button class="btn" id="portal-retry">Повторить</button></section>`;host.querySelector('button').onclick=()=>publicPage(tokenValue)}
  }
  document.addEventListener('keydown',ev=>{if((ev.ctrlKey||ev.metaKey)&&ev.key.toLowerCase()==='k'&&user){ev.preventDefault();palette()}});
  document.querySelector('#command-open')?.addEventListener('click',()=>{if(user)palette()});
  async function palette(){const root=openModal('Быстрый переход','Найдите клиента, смету, заказ или документ.',`<input id="command-search" type="search" placeholder="Поиск или действие…" aria-label="Глобальный поиск"><div id="command-results" class="command-results">${button('Создать смету','quote-new')}${Object.keys(names).slice(0,8).map(k=>button(names[k],'navigate',k)).join('')}</div>`);let timer;root.querySelector('input').focus();root.querySelector('input').oninput=ev=>{clearTimeout(timer);const q=ev.target.value;timer=setTimeout(async()=>{try{const r=await api('/search?q='+encodeURIComponent(q));if(root.querySelector('input').value!==q)return;root.querySelector('#command-results').innerHTML=r.items.map(i=>`<button class="command-result" data-work="${i.kind==='quotes'?'quote':'navigate'}" data-id="${i.kind==='quotes'?i.id:i.kind}"><span>${e(i.name)}</span><small>${e(names[i.kind]||'Смета')}</small></button>`).join('')||'<p class="muted">Ничего не найдено</p>'}catch(err){notify(err.message)}},180)};root.querySelector('#command-results').onclick=async ev=>{const b=ev.target.closest('[data-work]');if(b){closeModal();await action(b)}}}
  return {render,editor,calculateLineTotal,majorToKopecks:amount,openQuote:quoteDetail,openEntity:entityDetail,publicPage,intakePage,download,records:[],currentWorkspaceId:()=>workspace?.id,reset:()=>{workspace=null;current=null;workspaces=[];generation++;window.Workspace.records=[];clearTimeout(modalTimer);if(modal?.open)modal.close();modal?.replaceChildren();document.body.classList.remove('modal-open');window.SmetraFilePreview?.close();sessionStorage.removeItem('smetra.assistant.context')},palette};
})();
