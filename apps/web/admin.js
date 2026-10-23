/* Owner console: compact, task-oriented, and deliberately separate from the customer workspace. */
(() => {
  const state = {section:'users', search:'', status:'all', offset:0, support:'open', overview:null, users:[], total:0, request:0, selectedSupportId:null, pollTimer:null, escalationSeen:null};
  const actionNames = {block:'Заблокировать', unblock:'Разблокировать', grant:'Выдать Про на 31 день', revoke:'Отозвать Про'};
  const auditNames = {'admin.block':'Блокировка','admin.unblock':'Разблокировка','admin.grant':'Доступ Про выдан','admin.revoke':'Доступ Про отозван','admin.support.open':'Обращение открыто','admin.support.closed':'Обращение закрыто'};
  const paymentNames = {pending:'Ожидает',succeeded:'Оплачен',canceled:'Отменён',refunded:'Возврат'};
  const time = seconds => seconds ? date(Number(seconds)>1e12?Number(seconds)/1000:Number(seconds)) : '—';
  const label = value => escapeHtml(String(value ?? ''));
  const count = value => new Intl.NumberFormat('ru-RU').format(value || 0);

  function empty(title, note) {
    return `<div class="admin-empty"><span aria-hidden="true">○</span><strong>${title}</strong><p>${note}</p></div>`;
  }

  function heading() {
    const stats = state.overview.stats;
    const dateLabel = new Intl.DateTimeFormat('ru-RU',{dateStyle:'long',timeStyle:'short'}).format(new Date());
    return `<div class="admin-head"><div><span class="admin-kicker"><i></i> СМЕТРА / УПРАВЛЕНИЕ</span><h1>Пульс платформы<span>.</span></h1><p>Пользователи, обращения и оплаты.</p></div><button class="admin-refresh" type="button" data-admin-refresh aria-label="Обновить данные"><span aria-hidden="true">↻</span> Обновить</button></div>
      <div class="admin-dateline"><span>Операционная сводка</span><time>${label(dateLabel)}</time></div>
      <div class="admin-metrics" aria-label="Показатели платформы">
        <div><span>Пользователи</span><strong data-admin-metric="users">${count(stats.users)}</strong><small>всего активных аккаунтов</small></div>
        <div><span>Доступ Про</span><strong data-admin-metric="subscriptions">${count(stats.subscriptions)}</strong><small>действует сейчас</small></div>
        <div><span>Создано смет</span><strong data-admin-metric="quotes">${count(stats.quotes)}</strong><small>за всё время</small></div>
        <div><span>Оплачено</span><strong data-admin-metric="revenue_kopecks">${rub(stats.revenue_kopecks)}</strong><small>успешные платежи без возвратов</small></div>
      </div>
      <div class="admin-ops-metrics" aria-label="Операционные показатели">
        <div><span>Активны за 24 часа</span><strong data-admin-metric="active_24h">${count(stats.active_24h)}</strong></div>
        <div><span>Активны за 30 дней</span><strong data-admin-metric="active_30d">${count(stats.active_30d)}</strong></div>
        <div><span>Новые за сутки</span><strong data-admin-metric="new_users_24h">${count(stats.new_users_24h)}</strong></div>
        <div><span>Сметы за сутки</span><strong data-admin-metric="new_quotes_24h">${count(stats.new_quotes_24h)}</strong></div>
        <div><span>Рабочие пространства</span><strong data-admin-metric="workspaces">${count(stats.workspaces)}</strong></div>
        <div><span>Проекты / задачи</span><strong data-admin-metric="projects">${count(stats.projects)} / ${count(stats.tasks)}</strong></div>
        <div><span>Файлы</span><strong data-admin-metric="files">${count(stats.files)}</strong></div>
        <div><span>Платежи в ожидании</span><strong data-admin-metric="payments_pending">${count(stats.payments_pending)}</strong></div>
        <div><span>Выручка за 24 часа</span><strong data-admin-money="revenue_24h_kopecks">${rub(stats.revenue_24h_kopecks)}</strong></div>
        <div><span>Выручка за 30 дней</span><strong data-admin-money="revenue_30d_kopecks">${rub(stats.revenue_30d_kopecks)}</strong></div>
        <div><span>Поддержка / человек</span><strong data-admin-metric="support_open">${count(stats.support_open)} / ${count(stats.support_human)}</strong></div>
        <div><span>Задачи ИИ за 30 дней</span><strong data-admin-metric="assistant_jobs_30d">${count(stats.assistant_jobs_30d)}</strong></div>
        <div><span>Клиенты</span><strong data-admin-metric="clients">${count(stats.clients)}</strong></div>
        <div><span>Заказы / лиды</span><strong data-admin-metric="leads">${count(stats.leads)} / ${count(stats.marketplace_leads)}</strong></div>
        <div><span>Расходы / поступления</span><strong data-admin-metric="expenses">${count(stats.expenses)} / ${count(stats.payments_recorded)}</strong></div>
        <div><span>Позиции каталога</span><strong data-admin-metric="catalog_items">${count(stats.catalog_items)}</strong></div>
        <div><span>Документы / версии</span><strong data-admin-metric="documents">${count(stats.documents)} / ${count(stats.quote_versions)}</strong></div>
        <div><span>Согласование / утверждено</span><strong data-admin-metric="quotes_awaiting_approval">${count(stats.quotes_awaiting_approval)} / ${count(stats.quotes_approved)}</strong></div>
        <div><span>Чаты / сообщения</span><strong data-admin-metric="conversations">${count(stats.conversations)} / ${count(stats.messages)}</strong></div>
        <div><span>Участники сообществ</span><strong data-admin-metric="community_members">${count(stats.community_members)}</strong></div>
        <div><span>Активные TEAM</span><strong data-admin-metric="team_workspaces">${count(stats.team_workspaces)}</strong></div>
        <div><span>Сбои задач ИИ</span><strong data-admin-metric="failed_assistant_jobs_30d">${count(stats.failed_assistant_jobs_30d)}</strong></div>
        <div><span>Возвраты</span><strong data-admin-metric="refunds_succeeded">${count(stats.refunds_succeeded)}</strong></div>
      </div>
      <nav class="admin-tabs" aria-label="Разделы администрирования">
        <button data-admin-section="users" type="button">Пользователи</button>
        <button data-admin-section="revenue" type="button">Выручка и активация</button>
        <button data-admin-section="support" type="button">Поддержка <span>${count(state.overview.tickets.filter(t=>t.status==='open').length)}</span></button>
        <button data-admin-section="payments" type="button">Платежи</button>
        <button data-admin-section="audit" type="button">Журнал</button>
      </nav><section id="admin-section" class="admin-section" aria-live="polite"></section>
      <dialog id="admin-dialog" class="admin-dialog" aria-labelledby="admin-dialog-title"></dialog>`;
  }

  function userRows() {
    return state.users.map(u => {
      const activePro = u.entitlement_until > Date.now()/1000;
      return `<tr><td><div class="admin-person"><span class="admin-avatar" aria-hidden="true">${label((u.name||u.email||'?').slice(0,1).toUpperCase())}</span><span><strong>${label(u.name||'Без имени')}</strong><small>${label(u.email)} · ID ${label(u.public_id||'—')}${u.role==='admin'?' · Администратор':''}</small></span></div></td>
        <td><span class="admin-state ${u.blocked?'admin-state-red':'admin-state-green'}"><i></i>${u.blocked?'Заблокирован':'Активен'}</span></td>
        <td><span class="admin-plan ${activePro?'is-pro':''}">${activePro?'Про':'Старт'}</span>${activePro?`<small class="admin-subline">до ${time(u.entitlement_until)}</small>`:''}</td>
        <td class="admin-date">${time(u.created_at)}</td>
        <td class="admin-row-action"><button type="button" data-admin-manage="${label(u.id)}" aria-label="Управлять аккаунтом ${label(u.email)}">Управлять <span aria-hidden="true">↗</span></button></td></tr>`;
    }).join('');
  }

  function renderUserResults() {
    const results = document.querySelector('#admin-user-results');
    if (!results) return;
    results.innerHTML = state.users.length
      ? `<div class="admin-table-scroll"><table class="admin-table admin-users-table"><thead><tr><th scope="col">Пользователь</th><th scope="col">Статус</th><th scope="col">Тариф</th><th scope="col">Регистрация</th><th scope="col"><span class="sr-only">Действия</span></th></tr></thead><tbody>${userRows()}</tbody></table></div>`
      : empty('Ничего не найдено','Измените запрос или фильтр и попробуйте ещё раз.');
    const footer = document.querySelector('#admin-user-pages');
    footer.innerHTML = `<span>${state.total ? `${count(state.offset+1)}–${count(Math.min(state.offset+state.users.length,state.total))} из ${count(state.total)}` : '0 пользователей'}</span><div><button type="button" data-admin-page="previous" ${state.offset?'':'disabled'} aria-label="Предыдущая страница">←</button><button type="button" data-admin-page="next" ${state.offset+state.users.length<state.total?'':'disabled'} aria-label="Следующая страница">→</button></div>`;
  }

  async function loadUsers() {
    const current = ++state.request;
    const results = document.querySelector('#admin-user-results');
    if (results) results.innerHTML = '<p class="admin-loading">Загружаем пользователей…</p>';
    try {
      const params = new URLSearchParams({q:state.search,status:state.status,offset:String(state.offset)});
      const data = await api('/admin/users?' + params);
      if (current !== state.request || state.section !== 'users') return;
      state.users = data.users; state.total = data.total;
      renderUserResults();
    } catch (error) {
      if (current === state.request && results) results.innerHTML = `<p class="admin-error">${label(error.message)}</p>`;
    }
  }

  function usersSection() {
    return `<div class="admin-section-head"><div><span class="admin-section-index">01 / АККАУНТЫ</span><h2>Пользователи</h2><p>Поиск по имени и почте. Изменения доступа записываются в журнал.</p></div><span class="admin-section-count">${count(state.overview.stats.users)} аккаунтов</span></div>
      <div class="admin-controls"><label class="admin-search"><span class="sr-only">Найти пользователя</span><span aria-hidden="true">⌕</span><input id="admin-user-search" type="search" placeholder="Поиск по имени или почте" maxlength="100" value="${label(state.search)}" autocomplete="off"></label>
        <label class="admin-filter"><span class="sr-only">Фильтр пользователей</span><select id="admin-user-filter"><option value="all">Все</option><option value="active">Активные</option><option value="blocked">Заблокированные</option><option value="pro">Доступ Про</option></select></label></div>
      <div id="admin-user-results"></div><div id="admin-user-pages" class="admin-pagination"></div>`;
  }

  function supportSection() {
    const tickets = state.overview.tickets.filter(t=>t.status===state.support);
    const selected=state.overview.tickets.find(t=>t.id===state.selectedSupportId);
    return `<div class="admin-section-head"><div><span class="admin-section-index">02 / ОБРАЩЕНИЯ</span><h2>Поддержка</h2><p>Переписки пользователей, ответы ИИ и запросы на подключение сотрудника.</p></div><span class="admin-section-count">${count(tickets.length)} в списке · ${count(state.overview.stats.support_human)} ждут сотрудника</span></div>
      <div class="admin-switch" role="group" aria-label="Статус обращения"><button type="button" data-admin-support-filter="open" class="${state.support==='open'?'active':''}">Открытые</button><button type="button" data-admin-support-filter="closed" class="${state.support==='closed'?'active':''}">Закрытые</button></div>
      <div class="admin-support-workspace">
        <div class="admin-ticket-list">${tickets.length?tickets.map(t=>`<article class="admin-ticket ${t.id===state.selectedSupportId?'is-selected':''} ${t.needs_human?'is-escalated':''}">
          <button class="admin-ticket-open" type="button" data-admin-chat-open="${label(t.id)}">
            <span class="admin-ticket-top"><strong>${label(t.subject||'Вопрос в поддержку')}</strong><time>${time(t.updated_at||t.created_at)}</time></span>
            <span class="admin-ticket-requester">${label(t.user_name||t.email)} · ${label(t.public_id||'')}</span>
            <span class="admin-ticket-message-preview">${label(t.message)}</span>
            <span class="admin-ticket-flags"><small class="${t.needs_human?'is-human':''}">${t.needs_human?'⚑ Нужен сотрудник':t.ai_state==='resolved'?'Решено':'ИИ-поддержка'}</small><small>${label(t.priority||'normal')}</small></span>
          </button>
          <div class="admin-ticket-actions"><button type="button" data-admin-ticket="${label(t.id)}" data-status="${t.status==='open'?'closed':'open'}">${t.status==='open'?'Закрыть обращение':'Открыть снова'}</button></div>
        </article>`).join(''):empty(state.support==='open'?'Открытых обращений нет':'Закрытых обращений нет','Новые сообщения появятся здесь.')}</div>
        <section class="admin-support-chat" id="admin-support-chat" aria-live="polite">${selected?'<div class="admin-loading">Загружаем переписку…</div>':empty('Выберите обращение','Переписка появится здесь. Сообщения других пользователей не выводятся.')}</section>
      </div>`;
  }

  function renderSupportChat(ticket,messages) {
    const pane=document.querySelector('#admin-support-chat');if(!pane)return;
    pane.innerHTML=`<header class="admin-support-chat-head"><div><span class="admin-section-index">${ticket.needs_human?'ЭСКАЛАЦИЯ':'ОБРАЩЕНИЕ'} · ${label(ticket.public_id||'')}</span><h3>${label(ticket.subject||'Вопрос в поддержку')}</h3><p>${label(ticket.user_name||'Пользователь')} · ${label(ticket.user_email||'')}</p></div><span class="admin-state ${ticket.needs_human?'admin-state-amber':'admin-state-blue'}"><i></i>${ticket.needs_human?'Ждёт сотрудника':ticket.status==='closed'?'Закрыто':'В работе'}</span></header>
      <div class="admin-support-messages" id="admin-support-messages">${messages.length?messages.map(m=>`<article class="admin-support-message ${m.sender_role==='admin'?'is-admin':m.sender_role==='ai'?'is-ai':m.sender_role==='system'?'is-system':''}"><div><strong>${label(m.sender_name||({ai:'ИИ-помощник',system:'Сметра'}[m.sender_role]||'Пользователь'))}</strong><time>${time(m.created_at)}</time></div><p>${label(m.body).replace(/\n/g,'<br>')}</p></article>`).join(''):'<p class="admin-loading">Сообщений пока нет.</p>'}</div>
      <form id="admin-support-reply" class="admin-support-reply"><textarea name="message" rows="2" maxlength="4000" required placeholder="Ответить пользователю…"></textarea><button class="btn primary" type="submit">Отправить ответ ↗</button></form>`;
    const root=pane.querySelector('#admin-support-messages');if(root)root.scrollTop=root.scrollHeight;
    pane.querySelector('#admin-support-reply').onsubmit=async event=>{
      event.preventDefault();const form=event.currentTarget,button=form.querySelector('button'),input=form.querySelector('textarea'),message=input.value.trim();
      if(button.disabled||!message)return;button.disabled=true;
      try{
        await api('/admin/support/'+encodeURIComponent(ticket.id)+'/messages',{method:'POST',body:JSON.stringify({message})});
        if(tab!=='admin'||state.section!=='support'||state.selectedSupportId!==ticket.id)return;
        state.overview=await api('/admin/overview');
        const target=document.querySelector('#admin-section');
        if(target)target.innerHTML=supportSection();
        await loadSupportChat(ticket.id);
      }catch(error){notify(error.message);if(button.isConnected)button.disabled=false;}
    };
  }
  async function loadSupportChat(id) {
    const pane=document.querySelector('#admin-support-chat');if(!pane||!id)return;
    const owner=user;
    pane.innerHTML='<div class="admin-loading">Загружаем переписку…</div>';
    try{
      const result=await api('/admin/support/'+encodeURIComponent(id)+'/messages?refresh='+Date.now());
      if(user!==owner||tab!=='admin'||state.section!=='support'||state.selectedSupportId!==id)return;
      renderSupportChat(result.ticket,result.messages||[]);
    }catch(error){if(user===owner&&pane.isConnected)pane.innerHTML='<p class="admin-error">'+label(error.message)+'</p>';}
  }

  function paymentsSection() {
    const rows = state.overview.payments || [];
    return `<div class="admin-section-head"><div><span class="admin-section-index">03 / ОПЛАТЫ</span><h2>Платежи</h2><p>Последние 50 операций по подписке.</p></div><span class="admin-section-count">${count(rows.length)} операций</span></div>
      ${rows.length?`<div class="admin-table-scroll"><table class="admin-table admin-payments-table"><thead><tr><th scope="col">Дата</th><th scope="col">Покупатель</th><th scope="col">Тариф</th><th scope="col">Сумма</th><th scope="col">Статус</th></tr></thead><tbody>${rows.map(p=>`<tr><td>${time(p.created_at)}</td><td class="admin-email">${label(p.email)}</td><td>${p.plan==='pro_year'?'Про · год':'Про · месяц'}</td><td class="admin-money">${rub(p.amount_kopecks)}</td><td><span class="admin-state ${p.status==='succeeded'?'admin-state-green':p.status==='refunded'?'admin-state-red':''}"><i></i>${label(paymentNames[p.status]||p.status)}</span></td></tr>`).join('')}</tbody></table></div>`:empty('Платежей пока нет','Когда клиенты начнут оплачивать тариф, операции появятся здесь.')}
      <p class="admin-footnote">Сверяйте успешные платежи с ЮKassa. Чеки самозанятого оформляются в «Мой налог»; отметки о чеках эта панель не хранит.</p>`;
  }

  function auditSection() {
    const rows = state.overview.audit;
    return `<div class="admin-section-head"><div><span class="admin-section-index">04 / ИСТОРИЯ</span><h2>Журнал действий</h2><p>Последние 100 административных событий.</p></div><span class="admin-section-count">${count(rows.length)} событий</span></div>
      ${rows.length?`<div class="admin-audit-list">${rows.map(a=>`<div class="admin-audit"><span class="admin-audit-mark" aria-hidden="true"></span><div><strong>${label(auditNames[a.action]||a.action)}</strong><small>${label(a.actor_email||'Система')} · ${label(a.target)}${a.detail?' · '+label(a.detail):''}</small></div><time>${time(a.created_at)}</time></div>`).join('')}</div>`:empty('Действий пока нет','Записи появятся после управления доступом и обращениями.')}`;
  }

  function chatsSection() {
    return `<div class="admin-section-head"><div><span class="admin-section-index">03 / КОММУНИКАЦИИ</span><h2>Переписки</h2><p>Поиск по личным чатам, обсуждениям смет, объектам и сообществам. Просмотр сообщений фиксируется в журнале.</p></div><span class="admin-section-count">${count(state.conversations.length)} переписок</span></div>
      <div class="admin-controls"><label class="admin-search"><span class="sr-only">Поиск переписки</span><span aria-hidden="true">⌕</span><input id="admin-chat-search" type="search" maxlength="80" placeholder="Название, ID или категория" value="${label(state.conversationSearch)}" autocomplete="off"></label>
      <label class="admin-filter"><span class="sr-only">Тип переписки</span><select id="admin-chat-kind"><option value="all">Все личные и рабочие чаты</option><option value="direct">Личные</option><option value="quote">Сметы</option><option value="workspace">Объекты TEAM</option><option value="community">Сообщества</option></select></label><button class="btn small" type="button" data-admin-chats-refresh>Обновить</button></div>
      <div class="admin-comms-workspace"><div id="admin-chat-results" class="admin-chat-results"><p class="admin-loading">Загружаем переписки…</p></div><section id="admin-chat-transcript" class="admin-chat-transcript" aria-live="polite">${empty('Выберите переписку','Содержание появится после выбора. Это только чтение; платёжные реквизиты сюда не попадают.')}</section></div>`;
  }

  async function loadAdminChats() {
    const target=document.querySelector('#admin-chat-results');
    if(!target||state.section!=='chats')return;
    const owner=user,request=++state.request;
    target.innerHTML='<p class="admin-loading">Ищем переписки…</p>';
    try{
      const params=new URLSearchParams({q:state.conversationSearch,kind:state.conversationKind,refresh:String(Date.now())});
      const result=await api('/admin/conversations?'+params);
      if(user!==owner||tab!=='admin'||state.section!=='chats'||request!==state.request)return;
      state.conversations=result.items||[];
      target.innerHTML=state.conversations.length?state.conversations.map(item=>'<button type="button" class="admin-chat-row '+(item.id===state.selectedConversationId?'is-selected':'')+'" data-admin-conversation="'+label(item.id)+'">'+
        '<span class="admin-chat-row-icon">'+({direct:'↗',quote:'▤',workspace:'▦',community:'◎'}[item.kind]||'○')+'</span>'+
        '<span class="admin-chat-row-copy"><strong>'+label(item.title||({direct:'Личный чат',quote:'Обсуждение сметы',workspace:'Чат объекта',community:'Сообщество'}[item.kind]||'Переписка'))+'</strong>'+
        '<small>'+label(({direct:'Личный чат',quote:'Обсуждение сметы',workspace:'Объект TEAM',community:'Сообщество'}[item.kind]||item.kind))+' · '+count(item.participant_count)+' участников · '+count(item.message_count)+' сообщений</small>'+
        '<small>'+label(item.category||item.id)+' · последнее сообщение '+time(item.last_message_at||item.updated_at)+'</small></span></button>').join(''):empty('Переписок нет','Проверьте другой фильтр или дождитесь первого сообщения.');
      const kind=document.querySelector('#admin-chat-kind');if(kind)kind.value=state.conversationKind;
      if(state.selectedConversationId&&state.conversations.some(item=>item.id===state.selectedConversationId))await loadAdminTranscript(state.selectedConversationId);
      else if(!state.conversations.length){state.selectedConversationId=null;const pane=document.querySelector('#admin-chat-transcript');if(pane)pane.innerHTML=empty('Выберите переписку','Содержание появится после выбора.');}
    }catch(error){if(user===owner&&state.section==='chats'&&request===state.request)target.innerHTML='<p class="admin-error">'+label(error.message)+'</p>';}
  }

  async function loadAdminTranscript(id) {
    const pane=document.querySelector('#admin-chat-transcript');if(!pane||!id)return;
    const owner=user;pane.innerHTML='<p class="admin-loading">Загружаем переписку…</p>';
    try{
      const result=await api('/admin/conversations/'+encodeURIComponent(id)+'/messages?refresh='+Date.now());
      if(user!==owner||tab!=='admin'||state.section!=='chats'||state.selectedConversationId!==id)return;
      const conversation=result.conversation||{};
      pane.innerHTML='<header class="admin-chat-transcript-head"><div><span class="admin-section-index">ТОЛЬКО ЧТЕНИЕ · '+label(conversation.kind)+'</span><h3>'+label(conversation.title||conversation.id)+'</h3><p>'+label(conversation.id)+'</p></div><span class="admin-state admin-state-blue"><i></i>Доступ записан</span></header>'+
       '<div class="admin-chat-participants"><span>Участники</span>'+(result.participants||[]).map(person=>'<span class="admin-chat-participant"><strong>'+label(person.name)+'</strong><small>'+label(person.public_id||'ID недоступен')+' · '+label(person.role)+'</small></span>').join('')+'</div>'+
       '<div class="admin-chat-transcript-messages">'+((result.messages||[]).length?(result.messages||[]).map(message=>'<article class="admin-support-message '+(message.sender_role==='ai'?'is-ai':message.sender_role==='system'?'is-system':message.sender_role==='admin'?'is-admin':'')+'"><div><strong>'+label(message.sender_name||({ai:'Помощник Сметры',system:'Сметра'}[message.sender_role]||'Участник'))+'</strong><time>'+time(message.created_at)+'</time></div><p>'+label(message.body).replace(/\\n/g,'<br>')+'</p></article>').join(''):'<p class="admin-loading">Сообщений пока нет.</p>')+'</div>'+
       '<p class="admin-footnote">Содержание переписки доступно только администратору. Просмотр записан в журнале действий.</p>';
      const messages=pane.querySelector('.admin-chat-transcript-messages');if(messages)messages.scrollTop=messages.scrollHeight;
    }catch(error){if(user===owner&&pane.isConnected)pane.innerHTML='<p class="admin-error">'+label(error.message)+'</p>';}
  }

  function renderSection() {
    const target = document.querySelector('#admin-section');
    if (!target) return;
    document.querySelectorAll('[data-admin-section]').forEach(button=>{
      const active = button.dataset.adminSection===state.section;
      button.classList.toggle('active',active);
      button.setAttribute('aria-current',active?'page':'false');
    });
    if(state.section==='revenue'){
      target.innerHTML='<p class="admin-loading">Считаем подтверждённые оплаты и воронку…</p>';
      const owner=user,current=++state.request;
      api('/admin/revenue').then(data=>{if(user!==owner||tab!=='admin'||state.section!=='revenue'||current!==state.request)return;target.innerHTML=revenueSection(data)}).catch(error=>{if(user===owner&&state.section==='revenue'&&current===state.request)target.innerHTML=`<p class="admin-error">${label(error.message)}</p>`});return;
    }
    target.innerHTML = ({users:usersSection,support:supportSection,chats:chatsSection,payments:paymentsSection,audit:auditSection})[state.section]();
    if(state.section==='support'&&state.selectedSupportId)loadSupportChat(state.selectedSupportId);
    if(state.section==='chats')loadAdminChats();
    if (state.section==='users') {
      document.querySelector('#admin-user-filter').value = state.status;
      loadUsers();
    }
  }

  function revenueSection(data){
    const percentage=value=>value===null||value===undefined?'—':count(value)+'%';
    const money=value=>value===null||value===undefined?'—':rub(value);
    const metrics=[['Сегодня',money(data.revenue_today)],['7 дней',money(data.revenue_7d)],['30 дней',money(data.revenue_30d)],['MRR эквивалент',money(data.mrr_kopecks)],['ARR эквивалент',money(data.arr_kopecks)],['Платящий Про',count(data.paid_users)],['Бесплатный доступ',count(data.free_users)],['Free → Paid',percentage(data.free_to_paid_pct)],['ARPU · 30 дней',money(data.arpu_kopecks)],['ARPPU · 30 дней',money(data.arppu_kopecks)],['Успех завершённых оплат',percentage(data.payment_success_pct)],['Checkout → оплата',percentage(data.checkout_conversion_pct)],['Paywall → оплата',percentage(data.paywall_conversion_pct)],['Новые подписки · 30 дней',count(data.funnel.subscription_started)],['Продления · 30 дней',count(data.funnel.subscription_renewed)],['Истёкшие подписки',count(data.expired_subscriptions)],['Отток доступа · 30 дней',percentage(data.churn_pct)],['LTV',money(data.ltv_kopecks)]];
    const eventNames={activated:'Активация',estimate_created:'Полезная смета',estimate_shared:'Отправка клиенту',estimate_approved:'Согласование',product_visit:'Вернулись к работе',paywall_viewed:'Просмотр Про',upgrade_clicked:'Выбор Про',checkout_started:'Начало оплаты',payment_success:'Подтверждённая оплата',checkout_cancelled:'Отмена оплаты',checkout_failed:'Ошибка checkout'};
    const sources={ai_limit:'Ассистент',quote_limit:'Лимит смет',project_limit:'Проекты',pdf_export:'PDF',file_analysis:'Файлы',documents:'Документы',pricing_page:'Страница Про',settings:'Настройки',other:'Другие'};
    return `<div class="admin-section-head"><div><span class="admin-section-index">ВЫРУЧКА / УДЕРЖАНИЕ</span><h2>Результат реальной работы</h2><p>Тестовые платежи и выданный вручную доступ не считаются выручкой.</p></div><time>${time(data.as_of)}</time></div><div class="admin-revenue-metrics">${metrics.map(([name,value])=>`<div><span>${name}</span><strong>${value}</strong></div>`).join('')}</div>
      <p class="admin-footnote">MRR и ARR — эквивалент активного оплаченного доступа, не обещание будущих списаний: автопродления нет. «—» означает отсутствие данных или неприменимую метрику. ARPU считается по пользователям, работавшим за 30 дней. Старые платежи без проверенного режима магазина выделены отдельно: ${count(data.unclassified_payments)}.</p>
      <h3>Воронка · 30 дней</h3><div class="admin-growth-funnel">${Object.entries(eventNames).map(([name,title])=>`<div><span>${title}</span><strong>${count(data.funnel[name])}</strong></div>`).join('')}</div><p class="admin-footnote">Уникальные пользователи каждого события. Регистрация сама по себе не считается активацией. Регистрация → смета: ${percentage(data.signup_to_estimate_pct)} · смета → отправка: ${percentage(data.estimate_to_share_pct)} · отправка → согласование: ${percentage(data.share_to_approval_pct)}.</p><p class="admin-footnote">Первая смета: ${data.first_estimate.mean_seconds===null?'нет данных':count(data.first_estimate.mean_seconds)+' сек. в среднем'} · успели за 3 минуты: ${percentage(data.first_estimate.under_3m_pct)}.</p>
      <h3>Удержание и оплата когорт</h3><div class="admin-table-scroll"><table class="admin-table"><thead><tr><th>День</th><th>Созревшая когорта</th><th>Вернулись</th><th>Free → Paid</th></tr></thead><tbody>${data.cohorts.map(c=>`<tr><td>D${c.day}</td><td>${count(c.eligible)}</td><td>${percentage(c.retention_pct)}</td><td>${percentage(c.paid_pct)}</td></tr>`).join('')}</tbody></table></div>
      <h3>Дата регистрации → результат первого дня</h3><div class="admin-table-scroll"><table class="admin-table"><thead><tr><th>Регистрация · UTC</th><th>Пользователи</th><th>Активация D0</th><th>D1</th><th>Оплата 1 д.</th><th>D7</th><th>Оплата 7 д.</th><th>D30</th><th>Оплата 30 д.</th></tr></thead><tbody>${data.signup_cohorts.map(c=>`<tr><td>${time(c.signup_day*86400)}</td><td>${count(c.signups)}</td><td>${count(c.activation_d0)}</td>${[1,7,30].map(day=>`<td>${percentage(c["retention_d"+day])}</td><td>${percentage(c["paid_pct_d"+day])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
      <h3>Что приводит к оплате</h3><div class="admin-table-scroll"><table class="admin-table"><thead><tr><th>Источник</th><th>Ценовая когорта</th><th>Просмотры Про</th><th>Начало оплаты</th><th>Оплаты</th><th>Выручка</th></tr></thead><tbody>${data.sources.map(c=>`<tr><td>${label(sources[c.source]||c.source)}</td><td>${label(c.variant)}</td><td>${count(c.views||0)}</td><td>${count(c.checkouts)}</td><td>${count(c.paid)}</td><td>${rub(c.revenue_kopecks)}</td></tr>`).join('')}</tbody></table></div>
      <h3>Экономика · 30 дней</h3><div class="admin-growth-funnel">${[['Выручка',data.economics.revenue_kopecks],['AI',data.economics.ai_cost_kopecks],['Комиссии',data.economics.payment_fees_kopecks],['Инфраструктура',data.economics.infrastructure_kopecks],['Хранение',data.economics.storage_kopecks],['Расчётный остаток',data.economics.gross_margin_kopecks]].map(([name,value])=>`<div><span>${name}</span><strong>${data.economics.costs_configured?money(value):name==='Выручка'?money(value):'—'}</strong></div>`).join('')}</div><p class="admin-footnote">${data.economics.costs_configured?'Расходы рассчитаны по заданным оператором ставкам. Это оценка, а не бухгалтерский отчёт.':'Для расчёта прибыли задайте ставки AI, комиссии, хранение и инфраструктуру в серверных переменных. Нулевой тариф API не означает отсутствие остальных расходов.'}</p><h3>Экономика пользователей</h3><div class="admin-table-scroll"><table class="admin-table"><thead><tr><th>Пользователь</th><th>Выручка</th><th>AI</th><th>Комиссии</th></tr></thead><tbody>${data.unit_users.map(p=>`<tr><td>${label(p.name||p.id)}</td><td>${money(p.revenue_kopecks)}</td><td>${data.economics.costs_configured?money(p.ai_cost_kopecks):'—'}</td><td>${data.economics.costs_configured?money(p.payment_fees_kopecks):'—'}</td></tr>`).join('')}</tbody></table></div>`;
  }

  function manage(id) {
    const selected = state.users.find(item=>item.id===id);
    if (!selected) return;
    const dialog = document.querySelector('#admin-dialog');
    const activePro = selected.entitlement_until > Date.now()/1000;
    const actions = [selected.blocked?'unblock':'block',activePro?'revoke':'grant'];
    dialog.innerHTML = `<div class="admin-dialog-top"><span class="admin-section-index">УПРАВЛЕНИЕ ДОСТУПОМ</span><button type="button" data-dialog-close aria-label="Закрыть">×</button></div><h2 id="admin-dialog-title">${label(selected.name||selected.email)}</h2><p class="admin-dialog-email">${label(selected.email)}</p>
      <div class="admin-dialog-facts"><div><span>Статус</span><strong>${selected.blocked?'Заблокирован':'Активен'}</strong></div><div><span>Тариф</span><strong>${activePro?'Про до '+time(selected.entitlement_until):'Старт'}</strong></div></div>
      <label for="admin-reason">Причина изменения</label><textarea id="admin-reason" maxlength="200" rows="2" placeholder="Кратко для журнала действий" required></textarea><p class="admin-dialog-hint">Действие сохранится в журнале. Блокировка завершит все сеансы пользователя.</p>
      <div class="admin-dialog-actions">${actions.map(action=>`<button type="button" class="${action==='block'||action==='revoke'?'danger':''}" data-admin-action="${action}" ${action==='block'&&selected.id===user.id?'disabled title="Нельзя заблокировать себя"':''}>${actionNames[action]}</button>`).join('')}</div><p id="admin-dialog-error" role="alert"></p>`;
    dialog.querySelector('[data-dialog-close]').onclick=()=>dialog.close();
    dialog.querySelectorAll('[data-admin-action]').forEach(button=>button.onclick=async()=>{
      const reason=dialog.querySelector('#admin-reason').value.trim();
      if (!reason) {dialog.querySelector('#admin-dialog-error').textContent='Укажите причину изменения';dialog.querySelector('#admin-reason').focus();return;}
      dialog.querySelectorAll('button').forEach(item=>item.disabled=true);
      try {
        await api('/admin/users/'+encodeURIComponent(id),{method:'PATCH',body:JSON.stringify({action:button.dataset.adminAction,reason})});
        await loadUsers();
        dialog.close();notify('Изменение сохранено');
        state.overview=await api('/admin/overview');
        await window.SmetraAdmin(state.overview);
      } catch(error) {
        dialog.querySelector('#admin-dialog-error').textContent=error.message;
        dialog.querySelectorAll('button').forEach(item=>item.disabled=item.dataset.adminAction==='block'&&selected.id===user.id);
      }
    });
    dialog.showModal();dialog.querySelector('#admin-reason').focus();
  }

  function syncMetrics(data) {
    const stats=data.stats||{};
    for(const key of ['users','subscriptions','quotes','active_24h','active_30d','new_users_24h','new_quotes_24h','workspaces','files','payments_pending','support_open','support_human','assistant_jobs_30d','clients','catalog_items','documents','quote_versions','quotes_awaiting_approval','quotes_approved','conversations','messages','community_members','team_workspaces','failed_assistant_jobs_30d','refunds_succeeded']) {
      const element=document.querySelector('[data-admin-metric="'+key+'"]');
      if(element)element.textContent=count(stats[key]||0);
    }
    const compositeMetrics={
      projects:count(stats.projects)+' / '+count(stats.tasks),
      leads:count(stats.leads)+' / '+count(stats.marketplace_leads),
      expenses:count(stats.expenses)+' / '+count(stats.payments_recorded),
      documents:count(stats.documents)+' / '+count(stats.quote_versions),
      quotes_awaiting_approval:count(stats.quotes_awaiting_approval)+' / '+count(stats.quotes_approved)
    };
    for(const [key,value] of Object.entries(compositeMetrics)){
      const element=document.querySelector('[data-admin-metric="'+key+'"]');
      if(element)element.textContent=value;
    }
    for(const key of ['revenue_kopecks','revenue_24h_kopecks','revenue_30d_kopecks']){
      const element=document.querySelector('[data-admin-metric="'+key+'"],[data-admin-money="'+key+'"]');
      if(element)element.textContent=rub(stats[key]||0);
    }
  }
  let adminRealtimeOff=null;
  async function startAdminRealtime() {
    const owner=user;
    try {
      const config=await api('/realtime/config');
      if(user!==owner||tab!=='admin'||owner?.role!=='admin'||!config.enabled||!config.inbox_topic||!window.SmetraRealtime)return;
      window.SmetraRealtime.configure(config.url,config.key);adminRealtimeOff?.();
      adminRealtimeOff=window.SmetraRealtime.subscribe(config.inbox_topic,async eventName=>{
        if(eventName!=='support_escalated'||user!==owner||tab!=='admin')return;
        try{
          const next=await api('/admin/overview?refresh='+Date.now());if(user!==owner||tab!=='admin')return;
          const previous=state.escalationSeen||new Set(),escalated=(next.tickets||[]).filter(t=>t.status==='open'&&t.needs_human),added=escalated.filter(t=>!previous.has(t.id));
          state.overview=next;syncMetrics(next);state.escalationSeen=new Set(escalated.map(t=>t.id));
          if(added.length)notify('Новый запрос в поддержку: '+(added[0].subject||added[0].user_name||'нужен сотрудник'));
          if(state.section==='support'){const target=document.querySelector('#admin-section');if(target){target.innerHTML=supportSection();if(state.selectedSupportId)loadSupportChat(state.selectedSupportId);}}
        }catch{}
      });
    }catch{}
  }
  function startAdminPolling() {
    if(state.pollTimer)clearInterval(state.pollTimer);
    state.pollTimer=setInterval(async()=>{
      if(user?.role!=='admin'||tab!=='admin'){clearInterval(state.pollTimer);state.pollTimer=null;return;}
      try{
        const next=await api('/admin/overview?refresh='+Date.now());
        if(user?.role!=='admin'||tab!=='admin')return;
        const previous=state.escalationSeen;
        state.overview=next;
        syncMetrics(next);
        const escalated=(next.tickets||[]).filter(ticket=>ticket.status==='open'&&ticket.needs_human);
        if(previous){
          const added=escalated.filter(ticket=>!previous.has(ticket.id));
          if(added.length)notify('Новое обращение просит сотрудника: '+(added[0].subject||added[0].user_name||'поддержка'));
        }
        state.escalationSeen=new Set(escalated.map(ticket=>ticket.id));
        const supportBadge=document.querySelector('[data-admin-section="support"] span');
        if(supportBadge)supportBadge.textContent=count(escalated.length);
        if(state.section==='support'){
          const target=document.querySelector('#admin-section');
          if(target){target.innerHTML=supportSection();if(state.selectedSupportId)loadSupportChat(state.selectedSupportId);}
        }
      }catch{}
    },15000);
  }

  window.SmetraAdmin = async function (overview=null) {
    if (user?.role!=='admin') return;
    const owner=user;
    state.overview = overview || await api('/admin/overview');
    if(user!==owner||tab!=='admin')return;
    view(heading());
    const content = document.querySelector('#content');
    content.querySelector('[data-admin-refresh]').onclick=async event=>{
      const button=event.currentTarget;if(button.disabled)return;button.disabled=true;
      try {state.overview=await api('/admin/overview');await window.SmetraAdmin(state.overview);notify('Данные обновлены');}
      catch(error) {notify(error.message);}
      finally {if(button.isConnected)button.disabled=false;}
    };
    content.querySelector('.admin-tabs').onclick=event=>{
      const button=event.target.closest('[data-admin-section]');if(!button)return;
      state.section=button.dataset.adminSection;renderSection();
    };
    content.querySelector('#admin-section').onclick=async event=>{
      const manageButton=event.target.closest('[data-admin-manage]');
      if(manageButton){manage(manageButton.dataset.adminManage);return;}
      const conversation=event.target.closest('[data-admin-conversation]');
      if(conversation){state.selectedConversationId=conversation.dataset.adminConversation;loadAdminTranscript(state.selectedConversationId);loadAdminChats();return;}
      if(event.target.closest('[data-admin-chats-refresh]')){loadAdminChats();return;}
      const page=event.target.closest('[data-admin-page]');
      if(page){state.offset+=page.dataset.adminPage==='next'?25:-25;loadUsers();return;}
      const openChat=event.target.closest('[data-admin-chat-open]');
      if(openChat){state.selectedSupportId=openChat.dataset.adminChatOpen;renderSection();return;}
      const filter=event.target.closest('[data-admin-support-filter]');
      if(filter){state.support=filter.dataset.adminSupportFilter;renderSection();return;}
      const ticket=event.target.closest('[data-admin-ticket]');
      if(ticket){ticket.disabled=true;try{await api('/admin/support/'+encodeURIComponent(ticket.dataset.adminTicket),{method:'PATCH',body:JSON.stringify({status:ticket.dataset.status})});state.overview=await api('/admin/overview');renderSection();notify('Статус обращения обновлён');}catch(error){ticket.disabled=false;notify(error.message)}}
    };
    let searchTimer;
    content.querySelector('#admin-section').oninput=event=>{
      if(event.target.id==='admin-user-search'){
        clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.search=event.target.value.trim();state.offset=0;loadUsers()},250);
      }else if(event.target.id==='admin-chat-search'){
        clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.conversationSearch=event.target.value.trim();state.selectedConversationId=null;loadAdminChats()},250);
      }
    };
    content.querySelector('#admin-section').onchange=event=>{
      if(event.target.id==='admin-user-filter'){state.status=event.target.value;state.offset=0;loadUsers();}
      else if(event.target.id==='admin-chat-kind'){state.conversationKind=event.target.value;state.selectedConversationId=null;loadAdminChats();}
    };
    renderSection();
    if(!state.escalationSeen)state.escalationSeen=new Set((state.overview.tickets||[]).filter(ticket=>ticket.status==='open'&&ticket.needs_human).map(ticket=>ticket.id));
    startAdminPolling();
    startAdminRealtime();
  };
})();
