/* Owner console: compact, task-oriented, and deliberately separate from the customer workspace. */
(() => {
  const state = {section:'users', search:'', status:'all', offset:0, support:'open', ideaStatus:'all', ideas:[], overview:null, users:[], total:0, request:0};
  const auditNames = {'admin.block':'Блокировка','admin.unblock':'Разблокировка','admin.grant':'Доступ Про выдан','admin.revoke':'Доступ Про отозван','admin.tokens':'Изменение токенов','admin.sessions_revoke':'Сеансы завершены','admin.role.admin':'Выданы права администратора','admin.role.user':'Сняты права администратора','admin.set_plan.free':'Тариф: Старт','admin.set_plan.pro_solo':'Тариф: PRO Solo','admin.set_plan.pro_plus':'Тариф: PRO Plus','admin.set_plan.team':'Тариф: Team','admin.support.open':'Обращение открыто','admin.support.closed':'Обращение закрыто'};
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
        <button data-admin-section="revenue" type="button">Выручка и активация</button>
        <button data-admin-section="support" type="button">Поддержка <span>${count(state.overview.tickets.filter(t=>t.status==='open').length)}</span></button>
        <button data-admin-section="ideas" type="button">Предложения</button>
        <button data-admin-section="payments" type="button">Платежи</button>
        <button data-admin-section="audit" type="button">Журнал</button>
      </nav><section id="admin-section" class="admin-section" aria-live="polite"></section>
`;
  }

  function userRows() {
    return state.users.map(u => {
      const activePro = u.entitlement_until > Date.now()/1000;
      return `<tr><td><div class="admin-person"><span class="admin-avatar" aria-hidden="true">${u.id===user?.id&&window.SmetraUserAvatar?window.SmetraUserAvatar(user):label((u.name||u.email||'?').slice(0,1).toUpperCase())}</span><span><strong>${label(u.name||'Без имени')}</strong><small>${label(u.email)}${u.role==='admin'?' · Администратор':''}</small></span></div></td>
        <td><span class="admin-state ${u.blocked?'admin-state-red':'admin-state-green'}"><i></i>${u.blocked?'Заблокирован':'Активен'}</span></td>
        <td><span class="admin-plan ${activePro?'is-pro':''}">${activePro?'Про':'Старт'}</span>${activePro?`<small class="admin-subline">до ${time(u.entitlement_until)}</small>`:''}</td>
        <td class="admin-date">${time(u.created_at)}</td>
        <td class="admin-row-action"><button type="button" data-admin-manage="${label(u.id)}" aria-label="Управлять аккаунтом ${label(u.email)}"><span>Управлять</span>${window.SmetraIcons ? window.SmetraIcons.svg('arrow-up-right', 14) : ''}</button></td></tr>`;
    }).join('');
  }

  function renderUserResults() {
    const results = document.querySelector('#admin-user-results');
    if (!results) return;
    results.innerHTML = state.users.length
      ? `<div class="admin-table-scroll"><table class="admin-table admin-users-table"><thead><tr><th scope="col">Пользователь</th><th scope="col">Статус</th><th scope="col">Тариф</th><th scope="col">Регистрация</th><th scope="col"><span class="sr-only">Действия</span></th></tr></thead><tbody>${userRows()}</tbody></table></div>`
      : empty('Ничего не найдено','Измените запрос или фильтр и попробуйте ещё раз.');
    const footer = document.querySelector('#admin-user-pages');
    footer.innerHTML = `<span>${state.total ? `${count(state.offset+1)}–${count(Math.min(state.offset+state.users.length,state.total))} из ${count(state.total)}` : '0 пользователей'}</span><div><button type="button" data-admin-page="previous" ${state.offset?'':'disabled'} aria-label="Предыдущая страница">${window.SmetraIcons ? window.SmetraIcons.svg('arrow-left', 16) : '←'}</button><button type="button" data-admin-page="next" ${state.offset+state.users.length<state.total?'':'disabled'} aria-label="Следующая страница">${window.SmetraIcons ? window.SmetraIcons.svg('arrow-right', 16) : '→'}</button></div>`;
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
      <div class="admin-controls"><label class="admin-search"><span class="sr-only">Найти пользователя</span>${window.SmetraIcons ? window.SmetraIcons.svg('search', 16) : ''}<input id="admin-user-search" type="search" placeholder="Поиск по имени или почте" maxlength="100" value="${label(state.search)}" autocomplete="off"></label>
        <label class="admin-filter"><span class="sr-only">Фильтр пользователей</span><select id="admin-user-filter"><option value="all">Все</option><option value="active">Активные</option><option value="blocked">Заблокированные</option><option value="pro">Доступ Про</option></select></label></div>
      <div id="admin-user-results"></div><div id="admin-user-pages" class="admin-pagination"></div>`;
  }

  function supportSection() {
    const tickets = state.overview.tickets.filter(t=>t.status===state.support);
    return `<div class="admin-section-head"><div><span class="admin-section-index">02 / ОБРАЩЕНИЯ</span><h2>Поддержка</h2><p>Очередь обращений за последнее время.</p></div><span class="admin-section-count">${count(tickets.length)} в списке</span></div>
      <div class="admin-switch" role="group" aria-label="Статус обращения"><button type="button" data-admin-support-filter="open" class="${state.support==='open'?'active':''}">Открытые</button><button type="button" data-admin-support-filter="closed" class="${state.support==='closed'?'active':''}">Закрытые</button></div>
      <div class="admin-ticket-list">${tickets.length?tickets.map(t=>`<article class="admin-ticket"><div class="admin-ticket-top"><span>${label(t.email)}</span><time>${time(t.created_at)}</time></div><p>${label(t.message)}</p><div class="admin-ticket-actions"><span class="admin-state ${t.status==='open'?'admin-state-blue':''}"><i></i>${t.status==='open'?'Требует ответа':'Закрыто'}</span><button type="button" data-admin-ticket="${label(t.id)}" data-status="${t.status==='open'?'closed':'open'}">${t.status==='open'?'Закрыть обращение':'Открыть снова'} <span aria-hidden="true">↗</span></button></div></article>`).join(''):empty(state.support==='open'?'Открытых обращений нет':'Закрытых обращений нет','Новые сообщения появятся здесь.')}</div>`;
  }

  function ideasSection() {
    const names={new:'Новое',reviewing:'На рассмотрении',planned:'В планах',done:'Реализовано',declined:'Отклонено'};
    return '<div class="admin-section-head"><div><span class="admin-section-index">ПРОДУКТ / ОБРАТНАЯ СВЯЗЬ</span><h2>Предложения</h2><p>Идеи пользователей, обнаруженные ИИ поддержки. Каждая запись сохраняет исходный текст и ссылку на обращение.</p></div><span class="admin-section-count">'+count(state.ideas.length)+' предложений</span></div>'
      +'<div class="admin-controls"><label class="admin-filter">Статус <select id="admin-idea-filter"><option value="all">Все</option>'+Object.entries(names).map(([id,title])=>'<option value="'+id+'"'+(state.ideaStatus===id?' selected':'')+'>'+title+'</option>').join('')+'</select></label></div>'
      +'<div class="admin-ticket-list">'+(state.ideas.length?state.ideas.map(s=>'<article class="admin-ticket"><div class="admin-ticket-top"><span>'+label(s.email)+'</span><time>'+time(s.created_at)+'</time></div><h3>'+label(s.title)+'</h3><p>'+label(s.body)+'</p><div class="admin-ticket-actions"><a class="btn small" href="#admin" data-admin-open-support="'+label(s.conversation_id)+'">Обращение #'+label(s.conversation_id.slice(0,8))+'</a><label class="admin-filter"><span class="sr-only">Статус идеи</span><select data-admin-idea="'+label(s.id)+'">'+Object.entries(names).map(([id,title])=>'<option value="'+id+'"'+(s.status===id?' selected':'')+'>'+title+'</option>').join('')+'</select></label></div></article>').join(''):empty('Предложений пока нет','Когда пользователи предложат новые функции или улучшения, они появятся здесь.'))+'</div>';
  }

  async function loadIdeas() {
    const current=++state.request,owner=user;
    const target=document.querySelector('#admin-section');
    if(target)target.innerHTML='<p class="admin-loading">Загружаем предложения…</p>';
    try {
      const data=await api('/admin/communication/suggestions?status='+encodeURIComponent(state.ideaStatus));
      if(current!==state.request||user!==owner||tab!=='admin'||state.section!=='ideas')return;
      state.ideas=Array.isArray(data.suggestions)?data.suggestions:[];
      target.innerHTML=ideasSection();
    } catch(error) {
      if(current===state.request&&target)target.innerHTML='<p class="admin-error">'+label(error.message)+'</p>';
    }
  }

  function paymentsSection() {
    const rows = state.overview.payments || [];
    return `<div class="admin-section-head"><div><span class="admin-section-index">03 / ОПЛАТЫ</span><h2>Платежи</h2><p>Последние 50 операций по подписке.</p></div><span class="admin-section-count">${count(rows.length)} операций</span></div>
      ${rows.length?`<div class="admin-table-scroll"><table class="admin-table admin-payments-table"><thead><tr><th scope="col">Дата</th><th scope="col">Покупатель</th><th scope="col">Тариф</th><th scope="col">Сумма</th><th scope="col">Статус</th></tr></thead><tbody>${rows.map(p=>`<tr><td>${time(p.created_at)}</td><td class="admin-email">${label(p.email)}</td><td>${/^tokens_\d+m$/.test(p.plan)?'Токены · '+label(p.plan.slice(7,-1))+' млн':p.plan.endsWith('year')?'Про · год':'Про · месяц'}</td><td class="admin-money">${rub(p.amount_kopecks)}</td><td><span class="admin-state ${p.status==='succeeded'?'admin-state-green':p.status==='refunded'?'admin-state-red':''}"><i></i>${label(paymentNames[p.status]||p.status)}</span></td></tr>`).join('')}</tbody></table></div>`:empty('Платежей пока нет','Когда клиенты начнут оплачивать тариф, операции появятся здесь.')}
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
    state.userId = null;
    document.querySelector('#content')?.classList.remove('is-admin-user');
    document.querySelectorAll('[data-admin-section]').forEach(button=>{
      const active = button.dataset.adminSection===state.section;
      button.classList.toggle('active',active);
      button.setAttribute('aria-current',active?'page':'false');
    });
    if(state.section==='ideas'){loadIdeas();return;}
    if(state.section==='revenue'){
      target.innerHTML='<p class="admin-loading">Считаем подтверждённые оплаты и воронку…</p>';
      const owner=user,current=++state.request;
      api('/admin/revenue').then(data=>{if(user!==owner||tab!=='admin'||state.section!=='revenue'||current!==state.request)return;target.innerHTML=revenueSection(data)}).catch(error=>{if(user===owner&&state.section==='revenue'&&current===state.request)target.innerHTML=`<p class="admin-error">${label(error.message)}</p>`});return;
    }
    target.innerHTML = ({users:usersSection,support:supportSection,payments:paymentsSection,audit:auditSection})[state.section]();
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

  const tokenCount = value => {
    const n = Number(value || 0), abs = Math.abs(n);
    if (abs >= 1e6) return (n/1e6).toLocaleString('ru-RU',{maximumFractionDigits:2})+' млн';
    if (abs >= 1e4) return (n/1e3).toLocaleString('ru-RU',{maximumFractionDigits:1})+' тыс.';
    return count(n);
  };
  const ledgerNames = {purchase:'Покупка токенов',assistant:'Ответ ассистента',admin_adjust:'Изменение администратором',ad_reward:'Награда за видео',legacy_purchase_bonus:'Бонус покупки',legacy_ad_reward:'Бонус за видео',refund_revoke:'Возврат платежа'};
  const icon = (name, size=16) => window.SmetraIcons ? window.SmetraIcons.svg(name, size) : '';

  function userPage(d) {
    const u = d.user, t = d.tokens;
    const usedShare = t.monthly_limit ? Math.min(100, Math.round(t.monthly_used / t.monthly_limit * 100)) : 0;
    const personal = d.workspaces.find(w=>w.personal) || d.workspaces[0];
    const planOf = w => { const active = w.tier!=='starter' && w.entitlement_until > Date.now()/1000; return active ? `${label(d.plans[w.plan]||w.plan)} · до ${time(w.entitlement_until)}` : 'Старт'; };
    return `<div class="admin-user" data-admin-user="${label(u.id)}">
      <button type="button" class="admin-back" data-admin-back>${icon('arrow-left')}<span>Все пользователи</span></button>
      <header class="admin-user-head">
        <span class="admin-avatar admin-avatar-lg" aria-hidden="true">${label((u.name||u.email||'?').slice(0,1).toUpperCase())}</span>
        <div><h2>${label(u.name||'Без имени')}</h2><p>${label(u.email)} · с ${time(u.created_at)}</p>
          <div class="admin-user-badges"><span class="admin-state ${u.blocked?'admin-state-red':'admin-state-green'}"><i></i>${u.blocked?'Заблокирован':'Активен'}</span>${u.role==='admin'?'<span class="admin-plan">Администратор</span>':''}<span class="admin-plan ${personal&&personal.tier!=='starter'?'is-pro':''}">${personal?planOf(personal):'Старт'}</span></div></div>
        <dl class="admin-user-counts"><div><dt>Сметы</dt><dd>${count(d.counts.quotes)}</dd></div><div><dt>Сеансы</dt><dd>${count(d.counts.sessions)}</dd></div><div><dt>Обращения</dt><dd>${count(d.counts.support)}</dd></div></dl>
      </header>
      <div class="admin-user-grid">
        <section class="admin-card" aria-labelledby="admin-plan-title">
          <h3 id="admin-plan-title">Подписка</h3>
          <ul class="admin-list">${d.workspaces.map(w=>`<li><span><strong>${label(w.name)}</strong><small>${w.personal?'Личное пространство · ':''}${count(w.members)} участн.</small></span><span>${planOf(w)}</span></li>`).join('')||'<li>Нет пространств</li>'}</ul>
          <form class="admin-form" id="admin-plan-form">
            <label>Пространство<select name="workspace_id">${d.workspaces.map(w=>`<option value="${label(w.id)}" ${w.personal?'selected':''}>${label(w.name)}</option>`).join('')}</select></label>
            <label>Тариф<select name="plan">${Object.entries(d.plans).map(([code,name])=>`<option value="${code}" ${(personal&&personal.tier!=='starter'?personal.plan:'pro_solo')===code?'selected':''}>${label(name)}</option>`).join('')}</select></label>
            <label>Срок, дней<input name="days" type="number" min="1" max="3660" value="30" inputmode="numeric"></label>
            <div class="admin-chips" role="group" aria-label="Быстрый срок">${[30,90,365].map(n=>`<button type="button" data-days="${n}">${n} дн.</button>`).join('')}</div>
            <label class="admin-form-wide">Причина<input name="reason" maxlength="200" placeholder="Для журнала действий"></label>
            <button class="btn primary" type="submit">Применить тариф</button>
          </form>
        </section>
        <section class="admin-card" aria-labelledby="admin-tokens-title">
          <h3 id="admin-tokens-title">Токены ассистента</h3>
          <div class="admin-token-total"><strong>${tokenCount(t.remaining)}</strong><span>доступно сейчас</span></div>
          <div class="admin-meter" role="img" aria-label="Использовано ${usedShare}% месячного лимита"><span data-share="${usedShare}"></span></div>
          <dl class="admin-facts"><div><dt>Месяц</dt><dd>${tokenCount(t.monthly_used)} из ${tokenCount(t.monthly_limit)}</dd></div><div><dt>Кошелёк</dt><dd>${tokenCount(t.wallet)}</dd></div><div><dt>Сброс</dt><dd>${time(t.resets_at)}</dd></div></dl>
          <form class="admin-form" id="admin-tokens-form">
            <label>Изменить кошелёк<input name="delta" type="number" step="1000" placeholder="+100000 или −5000" inputmode="numeric" required></label>
            <div class="admin-chips" role="group" aria-label="Быстрое пополнение">${[50000,250000,1000000].map(n=>`<button type="button" data-delta="${n}">+${tokenCount(n)}</button>`).join('')}</div>
            <label class="admin-form-wide">Причина<input name="reason" maxlength="200" placeholder="Компенсация, бонус…"></label>
            <button class="btn primary" type="submit">Сохранить баланс</button>
          </form>
          <h4>История</h4>
          <ul class="admin-list admin-ledger">${d.ledger.length?d.ledger.map(l=>`<li><span><strong>${label(ledgerNames[l.reason]||l.reason)}</strong><small>${time(l.created_at)}${l.actor_email?' · '+label(l.actor_email):''}${l.note?' · '+label(l.note):''}</small></span><span class="${l.delta<0?'is-minus':'is-plus'}">${l.delta>0?'+':''}${tokenCount(l.delta)}</span></li>`).join(''):'<li class="admin-muted">Операций пока нет</li>'}</ul>
        </section>
        <section class="admin-card" aria-labelledby="admin-access-title">
          <h3 id="admin-access-title">Доступ</h3>
          <div class="admin-access-actions">
            <button type="button" class="btn ${u.blocked?'':'danger'}" data-user-action="${u.blocked?'unblock':'block'}" ${!u.blocked&&u.id===user.id?'disabled title="Нельзя заблокировать себя"':''}>${icon(u.blocked?'check':'x')}<span>${u.blocked?'Разблокировать':'Заблокировать'}</span></button>
            <button type="button" class="btn" data-user-action="sessions_revoke">${icon('arrow-right')}<span>Завершить все сеансы</span></button>
            <button type="button" class="btn" data-user-action="role" data-role="${u.role==='admin'?'user':'admin'}" ${u.id===user.id?'disabled title="Свою роль менять нельзя"':''}>${icon('key')}<span>${u.role==='admin'?'Снять права администратора':'Сделать администратором'}</span></button>
          </div>
          <p class="admin-footnote">Блокировка сразу завершает все сеансы. Каждое действие записывается в журнал вместе с причиной.</p>
          <h4>Платежи</h4>
          <ul class="admin-list">${d.payments.length?d.payments.map(p=>`<li><span><strong>${rub(p.amount_kopecks)}</strong><small>${time(p.created_at)} · ${label(p.plan)}</small></span><span class="admin-state ${p.refunded?'admin-state-red':p.status==='succeeded'?'admin-state-green':''}"><i></i>${p.refunded?'Возврат':label(paymentNames[p.status]||p.status)}</span></li>`).join(''):'<li class="admin-muted">Платежей нет</li>'}</ul>
          <h4>Журнал по пользователю</h4>
          <ul class="admin-list">${d.audit.length?d.audit.map(a=>`<li><span><strong>${label(auditNames[a.action]||a.action)}</strong><small>${time(a.created_at)} · ${label(a.actor_email||'Система')}${a.detail?' · '+label(a.detail):''}</small></span></li>`).join(''):'<li class="admin-muted">Записей нет</li>'}</ul>
        </section>
      </div>
    </div>`;
  }

  async function openUser(id) {
    const target = document.querySelector('#admin-section');
    if (!target) return;
    state.userId = id;
    // A full page of its own: the platform summary steps aside.
    document.querySelector('#content')?.classList.add('is-admin-user');
    target.innerHTML = '<p class="admin-loading">Загружаем аккаунт…</p>';
    window.scrollTo?.({top:0});
    target.closest('#content')?.scrollTo?.({top:0});
    let data;
    try { data = await api('/admin/users/'+encodeURIComponent(id)); }
    catch (error) { if (state.userId===id) target.innerHTML = `<p class="admin-error">${label(error.message)}</p>`; return; }
    if (state.userId!==id || tab!=='admin') return;
    target.innerHTML = userPage(data);
    const root = target.querySelector('.admin-user');
    root.querySelectorAll('[data-share]').forEach(bar=>bar.style.setProperty('--share', bar.dataset.share+'%'));
    const run = async (body, button) => {
      if (button) button.disabled = true;
      try {
        await api('/admin/users/'+encodeURIComponent(id),{method:'PATCH',body:JSON.stringify(body)});
        notify('Изменение сохранено');
        await openUser(id);
      } catch (error) { notify(error.message); if (button?.isConnected) button.disabled = false; }
    };
    root.querySelector('[data-admin-back]').onclick = () => { state.userId = null; renderSection(); };
    root.querySelectorAll('[data-days]').forEach(b=>b.onclick=()=>{root.querySelector('#admin-plan-form [name=days]').value=b.dataset.days});
    root.querySelectorAll('[data-delta]').forEach(b=>b.onclick=()=>{root.querySelector('#admin-tokens-form [name=delta]').value=b.dataset.delta});
    const planForm = root.querySelector('#admin-plan-form'), field = (form, name) => form.querySelector('[name='+name+']');
    const syncDays = () => { field(planForm,'days').disabled = field(planForm,'plan').value==='free'; };
    field(planForm,'plan').onchange = syncDays; syncDays();
    planForm.onsubmit = async event => {
      event.preventDefault();
      const plan = field(planForm,'plan').value, days = Number(field(planForm,'days').value);
      const name = data.plans[plan];
      if (!await window.SmetraDialog.confirm({title:'Установить тариф?', message: plan==='free' ? 'Пространство перейдёт на «Старт».' : `${name} на ${count(days)} дн. с сегодняшнего дня.`, confirmLabel:'Применить'})) return;
      run({action:'set_plan', workspace_id:field(planForm,'workspace_id').value, plan, days: plan==='free'?undefined:days, reason:field(planForm,'reason').value.trim()}, planForm.querySelector('[type=submit]'));
    };
    const tokenForm = root.querySelector('#admin-tokens-form');
    tokenForm.onsubmit = async event => {
      event.preventDefault();
      const delta = Math.trunc(Number(field(tokenForm,'delta').value));
      if (!delta) { notify('Укажите число токенов'); return; }
      if (!await window.SmetraDialog.confirm({title: delta>0?'Начислить токены?':'Списать токены?', message:`${delta>0?'+':''}${count(delta)} токенов в кошелёк пользователя.`, confirmLabel:'Сохранить', danger: delta<0})) return;
      run({action:'tokens', delta, reason:field(tokenForm,'reason').value.trim()}, tokenForm.querySelector('[type=submit]'));
    };
    root.querySelectorAll('[data-user-action]').forEach(button => button.onclick = async () => {
      const action = button.dataset.userAction;
      const titles = {block:'Заблокировать пользователя?', unblock:'Разблокировать пользователя?', sessions_revoke:'Завершить все сеансы?', role: button.dataset.role==='admin' ? 'Выдать права администратора?' : 'Снять права администратора?'};
      const reason = await window.SmetraDialog.prompt({title:titles[action], message:'Укажите причину — она попадёт в журнал действий.', label:'Причина', confirmLabel:'Подтвердить', danger: action==='block'});
      if (reason === null || reason === undefined) return;
      run({action, role: button.dataset.role, reason: String(reason).trim()}, button);
    });
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
      if(manageButton){openUser(manageButton.dataset.adminManage);return;}
      const page=event.target.closest('[data-admin-page]');
      if(page){state.offset+=page.dataset.adminPage==='next'?25:-25;loadUsers();return;}
      const filter=event.target.closest('[data-admin-support-filter]');
      if(filter){state.support=filter.dataset.adminSupportFilter;renderSection();return;}
      const support=event.target.closest('[data-admin-open-support]');
      if(support){event.preventDefault();if(window.SmetraCommunicationCenter?.open)window.SmetraCommunicationCenter.open('support');else notify('Откройте очередь поддержки в центре общения');return;}
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
      if(event.target.id==='admin-idea-filter'){state.ideaStatus=event.target.value;loadIdeas();}
      const idea=event.target.closest('[data-admin-idea]');
      if(idea){idea.disabled=true;try{await api('/admin/communication/suggestions/'+encodeURIComponent(idea.dataset.adminIdea),{method:'PATCH',body:JSON.stringify({status:idea.value})});notify('Статус предложения обновлён');}catch(error){notify(error.message);await loadIdeas();}finally{if(idea.isConnected)idea.disabled=false;}}
    };
    renderSection();
  };
})();
