/* Owner console: compact, task-oriented, and deliberately separate from the customer workspace. */
(() => {
  const state = {section:'users', search:'', status:'all', offset:0, support:'open', overview:null, users:[], total:0, request:0};
  const actionNames = {block:'Заблокировать', unblock:'Разблокировать', grant:'Выдать Про на 31 день', revoke:'Отозвать Про'};
  const auditNames = {'admin.block':'Блокировка','admin.unblock':'Разблокировка','admin.grant':'Доступ Про выдан','admin.revoke':'Доступ Про отозван','admin.support.open':'Обращение открыто','admin.support.closed':'Обращение закрыто'};
  const paymentNames = {pending:'Ожидает',succeeded:'Оплачен',canceled:'Отменён',refunded:'Возврат'};
  const time = seconds => seconds ? date(seconds) : '—';
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
        <div><span>Пользователи</span><strong>${count(stats.users)}</strong><small>всего активных аккаунтов</small></div>
        <div><span>Доступ Про</span><strong>${count(stats.subscriptions)}</strong><small>действует сейчас</small></div>
        <div><span>Создано смет</span><strong>${count(stats.quotes)}</strong><small>за всё время</small></div>
        <div><span>Оплачено</span><strong>${rub(stats.revenue_kopecks)}</strong><small>успешные платежи без возвратов</small></div>
      </div>
      <nav class="admin-tabs" aria-label="Разделы администрирования">
        <button data-admin-section="users" type="button">Пользователи</button>
        <button data-admin-section="support" type="button">Поддержка <span>${count(state.overview.tickets.filter(t=>t.status==='open').length)}</span></button>
        <button data-admin-section="payments" type="button">Платежи</button>
        <button data-admin-section="audit" type="button">Журнал</button>
      </nav><section id="admin-section" class="admin-section" aria-live="polite"></section>
      <dialog id="admin-dialog" class="admin-dialog" aria-labelledby="admin-dialog-title"></dialog>`;
  }

  function userRows() {
    return state.users.map(u => {
      const activePro = u.entitlement_until > Date.now()/1000;
      return `<tr><td><div class="admin-person"><span class="admin-avatar" aria-hidden="true">${label((u.name||u.email||'?').slice(0,1).toUpperCase())}</span><span><strong>${label(u.name||'Без имени')}</strong><small>${label(u.email)}${u.role==='admin'?' · Администратор':''}</small></span></div></td>
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
    return `<div class="admin-section-head"><div><span class="admin-section-index">02 / ОБРАЩЕНИЯ</span><h2>Поддержка</h2><p>Очередь обращений за последнее время.</p></div><span class="admin-section-count">${count(tickets.length)} в списке</span></div>
      <div class="admin-switch" role="group" aria-label="Статус обращения"><button type="button" data-admin-support-filter="open" class="${state.support==='open'?'active':''}">Открытые</button><button type="button" data-admin-support-filter="closed" class="${state.support==='closed'?'active':''}">Закрытые</button></div>
      <div class="admin-ticket-list">${tickets.length?tickets.map(t=>`<article class="admin-ticket"><div class="admin-ticket-top"><span>${label(t.email)}</span><time>${time(t.created_at)}</time></div><p>${label(t.message)}</p><div class="admin-ticket-actions"><span class="admin-state ${t.status==='open'?'admin-state-blue':''}"><i></i>${t.status==='open'?'Требует ответа':'Закрыто'}</span><button type="button" data-admin-ticket="${label(t.id)}" data-status="${t.status==='open'?'closed':'open'}">${t.status==='open'?'Закрыть обращение':'Открыть снова'} <span aria-hidden="true">↗</span></button></div></article>`).join(''):empty(state.support==='open'?'Открытых обращений нет':'Закрытых обращений нет','Новые сообщения появятся здесь.')}</div>`;
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

  function renderSection() {
    const target = document.querySelector('#admin-section');
    if (!target) return;
    document.querySelectorAll('[data-admin-section]').forEach(button=>{
      const active = button.dataset.adminSection===state.section;
      button.classList.toggle('active',active);
      button.setAttribute('aria-current',active?'page':'false');
    });
    target.innerHTML = ({users:usersSection,support:supportSection,payments:paymentsSection,audit:auditSection})[state.section]();
    if (state.section==='users') {
      document.querySelector('#admin-user-filter').value = state.status;
      loadUsers();
    }
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
        dialog.close();notify('Изменение сохранено');
        state.overview=await api('/admin/overview');
        await window.SmetraAdmin();
      } catch(error) {
        dialog.querySelector('#admin-dialog-error').textContent=error.message;
        dialog.querySelectorAll('button').forEach(item=>item.disabled=item.dataset.adminAction==='block'&&selected.id===user.id);
      }
    });
    dialog.showModal();dialog.querySelector('#admin-reason').focus();
  }

  window.SmetraAdmin = async function () {
    if (user?.role!=='admin') return;
    state.overview = state.overview || await api('/admin/overview');
    view(heading());
    const content = document.querySelector('#content');
    content.querySelector('[data-admin-refresh]').onclick=async event=>{
      event.currentTarget.disabled=true;
      try {state.overview=await api('/admin/overview');await window.SmetraAdmin();notify('Данные обновлены');} catch(error) {notify(error.message);event.currentTarget.disabled=false;}
    };
    content.querySelector('.admin-tabs').onclick=event=>{
      const button=event.target.closest('[data-admin-section]');if(!button)return;
      state.section=button.dataset.adminSection;renderSection();
    };
    content.querySelector('#admin-section').onclick=async event=>{
      const manageButton=event.target.closest('[data-admin-manage]');
      if(manageButton){manage(manageButton.dataset.adminManage);return;}
      const page=event.target.closest('[data-admin-page]');
      if(page){state.offset+=page.dataset.adminPage==='next'?25:-25;loadUsers();return;}
      const filter=event.target.closest('[data-admin-support-filter]');
      if(filter){state.support=filter.dataset.adminSupportFilter;renderSection();return;}
      const ticket=event.target.closest('[data-admin-ticket]');
      if(ticket){ticket.disabled=true;try{await api('/admin/support/'+encodeURIComponent(ticket.dataset.adminTicket),{method:'PATCH',body:JSON.stringify({status:ticket.dataset.status})});state.overview=await api('/admin/overview');renderSection();notify('Статус обращения обновлён');}catch(error){ticket.disabled=false;notify(error.message)}}
    };
    let searchTimer;
    content.querySelector('#admin-section').oninput=event=>{
      if(event.target.id!=='admin-user-search')return;
      clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.search=event.target.value.trim();state.offset=0;loadUsers()},250);
    };
    content.querySelector('#admin-section').onchange=event=>{
      if(event.target.id==='admin-user-filter'){state.status=event.target.value;state.offset=0;loadUsers();}
    };
    renderSection();
  };
})();
