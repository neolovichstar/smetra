'use strict';

window.SmetraProfile=(()=>{
  const field=(name,label,value,placeholder='',max=120)=>`<label>${label}<input name="${name}" value="${escapeHtml(value)}" maxlength="${max}" placeholder="${placeholder}" autocomplete="${name==='first_name'?'given-name':name==='last_name'?'family-name':name==='company'?'organization':'off'}"></label>`;
  const saveForm=(form,active,after)=>{
    form.onsubmit=async event=>{
      event.preventDefault();if(form.dataset.saving==='true'||!active())return;
      const values=Object.fromEntries(new FormData(form));if(form.elements.namedItem('memory_enabled'))values.memory_enabled=form.elements.namedItem('memory_enabled').checked?1:0;
      form.dataset.saving='true';const button=form.querySelector('[type=submit]'),status=form.querySelector('[role=status]');if(!button||!status||!form.isConnected)return;button.disabled=true;status.textContent='Сохраняем…';
      form.querySelectorAll('input,textarea,select').forEach(control=>control.disabled=true);
      try{await api('/profile',{method:'PATCH',body:JSON.stringify(values)});if(!active())return;await after?.();if(active())status.textContent='Сохранено'}
      catch(error){if(active())status.textContent=error.message}
      finally{delete form.dataset.saving;if(button.isConnected){button.disabled=false;form.querySelectorAll('input,textarea,select').forEach(control=>control.disabled=false)}}
    };
  };
  const render=async(active=()=>true,host=null)=>{
    const result=await api('/profile');if(!active())return;const p=result.profile;
    const form=`<form id="profile-form" class="hub-card profile-form"><section><h3>Как к вам обращаться</h3><div class="profile-fields">${field('first_name','Имя',p.first_name,'Ваше имя',80)}${field('last_name','Фамилия',p.last_name,'Ваша фамилия',80)}</div></section><section><h3>Ваша работа</h3><div class="profile-fields">${field('profession','Чем занимаетесь',p.profession,'Например, мастер по отделке')}${field('company','Компания',p.company,'Название или команда')}</div></section><section><label>О себе<textarea name="about" maxlength="2000" rows="5" placeholder="Какие объекты ведёте, что важно в вашей работе…">${escapeHtml(p.about)}</textarea></label><p class="profile-hint">Необязательно. Эти данные видите только вы и ваш ассистент.</p></section><footer><button class="btn primary" type="submit">Сохранить профиль</button><span role="status"></span></footer></form>`;
    if(host){if(!host.isConnected)return;host.innerHTML=`<h2 class="visually-hidden" id="profile-display-name">${escapeHtml(user.name)}</h2>`+form;}
    else view(`<section class="profile-page"><header><h1>Профиль</h1><p>Расскажите о себе — ассистент учтёт это в работе.</p></header><div class="profile-layout"><aside class="profile-summary"><span class="profile-avatar">${window.SmetraUserAvatar?.(user)||escapeHtml((p.first_name||user.name).slice(0,1).toUpperCase())}</span><div><h2 id="profile-display-name">${escapeHtml(user.name)}</h2><p>${escapeHtml(user.email)}</p></div></aside>${form}</div></section>`);
    saveForm(document.querySelector('#profile-form'),active,async()=>{const current=await api('/me');if(!active())return;Object.assign(user,current.user);const displayName=document.querySelector('#profile-display-name');if(displayName)displayName.textContent=user.name;document.querySelectorAll('.hub-identity strong').forEach(node=>node.textContent=user.name);const name=document.querySelector('#sidebar-profile-name');if(name)name.textContent=user.name;const avatar=document.querySelector('#sidebar-avatar');if(avatar)avatar.innerHTML=window.SmetraUserAvatar?.(user)||escapeHtml(user.name.slice(0,1))});
  };
  const settings=async(active)=>{
    const result=await api('/profile');if(!active())return;const p=result.profile;
    let root=document.querySelector('#settings-personalization');
    if(!root){
      const content=document.querySelector('#content');
      const settingsPage=content?.querySelector('.settings-page');
      if(!content||!settingsPage||!active())return;
      root=document.createElement('section');root.id='settings-personalization';
      const exportRoot=settingsPage.querySelector('#settings-export');
      if(exportRoot)settingsPage.insertBefore(root,exportRoot);else settingsPage.append(root);
    }
    if(!active()||!root?.isConnected||!root.closest('.settings-page'))return;
    if(!root||!root.isConnected)return;
    root.innerHTML=`<div class="personalization-settings hub-card"><form id="personalization-form"><label>Стиль ответа<select name="response_style"><option value="concise" ${p.response_style==='concise'?'selected':''}>Кратко и по делу</option><option value="balanced" ${p.response_style==='balanced'?'selected':''}>С пояснениями</option><option value="detailed" ${p.response_style==='detailed'?'selected':''}>Подробно</option></select></label><label class="memory-setting"><span><strong>Личная память</strong><small>Ассистент запоминает полезные факты из разговора. Записи можно изменить в окне знаний.</small></span><input type="checkbox" name="memory_enabled" ${p.memory_enabled?'checked':''}></label><div class="profile-save-row"><button class="btn primary" type="submit">Сохранить настройки</button><span role="status"></span></div></form></div>`;
    const form=root.querySelector('form');if(form)saveForm(form,active);
  };
  const number=value=>Number(value||0).toLocaleString('ru-RU');
  const amount=(value,currency)=>new Intl.NumberFormat('ru-RU',{style:'currency',currency,maximumFractionDigits:2,minimumFractionDigits:0}).format(Number(value||0)/100);
  const shortMonth=value=>new Intl.DateTimeFormat('ru-RU',{month:'short'}).format(new Date(value+'-15T12:00:00'));
  const overview=async(parentActive=()=>true,mountHost=null)=>{
    const owner=user,workspace=sessionStorage.getItem('workspace_id');
    const active=()=>parentActive()&&owner===user&&workspace===sessionStorage.getItem('workspace_id');
    const markup=`<section class="profile-overview" aria-label="Мой профиль">
      <header class="profile-hero"><div class="profile-hero-person"><span class="profile-hero-avatar">${window.SmetraUserAvatar?.(owner)||escapeHtml(owner.name.slice(0,1))}</span><div><p class="profile-overline">МОЙ ПРОФИЛЬ</p><h1>${escapeHtml(owner.name)}</h1><p data-profile-description></p><span class="profile-private-id" data-profile-id></span></div></div><a class="btn" href="#settings" data-profile-edit>${window.SmetraIcons?.svg('gear',18)||''}Настройки</a></header>
      <div data-profile-summary aria-live="polite" aria-busy="true"><div class="profile-loading">Загружаю статистику…</div></div>
    </section>`;
    if(mountHost)mountHost.innerHTML=markup;else view(markup);
    const root=document.querySelector('.profile-overview');
    const openSettings=section=>{try{sessionStorage.setItem('smetra.settings.tab',section)}catch{};return window.SmetraNavigateTo(section==='usage'?'usage':'settings');};
    root.querySelector('[data-profile-edit]').onclick=event=>{event.preventDefault();openSettings('details');};
    const results=await Promise.allSettled([api('/profile'),api('/profile-summary'),api('/profile/id'),api('/usage')]);
    if(!active()||!root.isConnected)return;
    const personal=results[0].status==='fulfilled'?results[0].value.profile:null;
    root.querySelector('[data-profile-description]').textContent=[personal?.profession,personal?.company].filter(Boolean).join(' · ');
    root.querySelector('[data-profile-id]').textContent=results[2].status==='fulfilled'?results[2].value.public_id||'':'';
    const host=root.querySelector('[data-profile-summary]');host.removeAttribute('aria-busy');
    if(results[1].status!=='fulfilled'){
      host.innerHTML='<div class="profile-error" role="alert"><h2>Статистика недоступна</h2><p>Не удалось загрузить данные. Попробуйте ещё раз.</p><button class="btn" type="button" data-profile-retry>Повторить</button></div>';
      host.querySelector('button').onclick=()=>{if(active())overview(parentActive,mountHost);};return;
    }
    const data=results[1].value,usage=results[3].status==='fulfilled'?results[3].value:null;
    let selected=data.money?.currencies?.[0]?.currency||data.workspace.currency,period='all';
    const statuses=[['draft','Черновики'],['waiting','На согласовании'],['approved','Согласованы'],['completed','Завершены']];
    const states={...data.quote_states,waiting:['sent','viewed','changes_requested'].reduce((n,key)=>n+(data.quote_states[key]||0),0)};
    const stat=(label,value,href,icon)=>`<a class="profile-stat" href="#${href}"><span class="profile-stat-icon">${window.SmetraIcons?.svg(icon,20)||''}</span><strong>${number(value)}</strong><span>${label}</span></a>`;
    host.innerHTML=`<div class="profile-section-title"><div><h2>Моя работа</h2><p>${escapeHtml(data.workspace.name)} · данные текущего пространства</p></div></div>
      <div class="profile-stats">${stat('Всего смет',data.counts.quotes,'quotes','file-text')}${stat('Объектов',data.counts.objects,'construction','buildings')}${stat('Заказов в работе',data.counts.active_projects,'projects','briefcase')}${stat('Завершено заказов',data.counts.completed_projects,'projects','check')}${stat('Клиентов',data.counts.clients,'clients','users')}${stat('Моих диалогов с ИИ',data.counts.conversations,'assistant','chat')}</div>
      <section class="profile-finance" aria-labelledby="profile-finance-title"><header class="profile-section-title"><h2 id="profile-finance-title">Деньги</h2>${data.money?`<div class="profile-switch" aria-label="Период"><button type="button" data-profile-period="all" aria-pressed="true">За всё время</button><button type="button" data-profile-period="month" aria-pressed="false">Этот месяц</button></div>`:''}</header><div data-profile-money></div></section>
      <div class="profile-bottom-grid"><section class="profile-card"><header class="profile-section-title"><h2>Сметы по статусам</h2><a href="#quotes">Все сметы ${window.SmetraIcons?.svg('arrow-up-right',16)||'↗'}</a></header><div class="profile-statuses">${statuses.map(([key,label])=>`<div><span><i class="profile-status-dot is-${key}"></i>${label}</span><strong>${number(states[key])}</strong></div>`).join('')}</div></section>
      <section class="profile-card"><header class="profile-section-title"><h2>Мой тариф</h2><a href="#billing">Тарифы ${window.SmetraIcons?.svg('arrow-up-right',16)||'↗'}</a></header><strong class="profile-plan-name">${escapeHtml(usage?.plan?.name||'Тариф недоступен')}</strong>${usage?.tokens?`<p class="profile-plan-note">Токены ассистента: ${number(Number(usage.tokens.remaining||0)+Number(usage.tokens.wallet||0))} осталось</p><a class="profile-text-link" href="#settings" data-profile-usage>Использование и лимиты</a>`:'<p class="profile-plan-note">Откройте тарифы, чтобы проверить подписку.</p>'}</section></div>
      <section class="profile-card profile-recent"><header class="profile-section-title"><h2>Последние сметы</h2><a href="#quotes">Открыть сметы ${window.SmetraIcons?.svg('arrow-up-right',16)||'↗'}</a></header>${data.recent_quotes.length?`<div class="profile-recent-list">${data.recent_quotes.map(q=>`<a class="profile-recent-row" href="#quotes"><span><strong>${escapeHtml(q.title||'Смета без названия')}</strong><small>${escapeHtml(q.client||'Клиент не указан')}</small></span><b>${escapeHtml(amount(q.amount_kopecks,q.currency))}</b></a>`).join('')}</div>`:'<div class="profile-empty"><p>Смет пока нет</p><a class="btn" href="#assistant">Перейти к ассистенту</a></div>'}</section>
      <p class="profile-privacy-note">Эту статистику видите вы. В публичном профиле финансов нет.</p>`;
    host.querySelector('[data-profile-usage]')?.addEventListener('click',event=>{event.preventDefault();openSettings('usage');});
    const renderMoney=()=>{
      const target=host.querySelector('[data-profile-money]');
      if(!data.money){target.innerHTML='<p class="profile-empty">Финансовая статистика доступна участникам с правом просмотра финансов.</p>';return;}
      const item=data.money.currencies.find(row=>row.currency===selected)||data.money.currencies[0],suffix=period==='month'?'_month':'';
      const metric=(label,key,note)=>`<div class="profile-money-metric"><span>${label}</span><strong${item[key+suffix]<0?' class="is-negative"':''}>${escapeHtml(amount(item[key+suffix],item.currency))}</strong><small>${note}</small></div>`;
      const expanded=target.querySelector(".profile-chart-details")?.open;
      target.innerHTML=`${data.money.currencies.length>1?`<div class="profile-currencies" aria-label="Валюта">${data.money.currencies.map(row=>`<button class="btn small" type="button" data-profile-currency="${escapeHtml(row.currency)}" aria-pressed="${row.currency===selected}">${escapeHtml(row.currency)}</button>`).join('')}</div>`:''}<div class="profile-money-grid">${metric('Получено','received','Записанные оплаты клиентов')}${metric('Расходы','spent','Учтённые расходы по заказам')}${metric('После расходов','balance','Поступления минус учтённые расходы')}</div>
        <details class="mobile-disclosure profile-chart-details" data-mobile-disclosure ${expanded?'data-mobile-expanded':''} open><summary>Поступления по месяцам</summary><div class="mobile-disclosure-body"><div class="profile-chart"><header><h3>Поступления по месяцам</h3><span>Последние 6 месяцев · ${escapeHtml(item.currency)}</span></header><div class="profile-chart-bars" role="img" aria-label="${escapeHtml(item.months.map(m=>shortMonth(m.month)+': '+amount(m.received,item.currency)).join('; '))}">${item.months.map(m=>`<div class="profile-chart-column"><span class="profile-chart-value">${escapeHtml(new Intl.NumberFormat('ru-RU',{notation:'compact',maximumFractionDigits:1}).format(m.received/100))}</span><div class="profile-chart-track"><span data-profile-bar="${m.received}"></span></div><span class="profile-chart-month">${escapeHtml(shortMonth(m.month))}</span></div>`).join('')}</div></div>
        <p class="profile-money-note">По оплатам и расходам, записанным по ${new Date(data.money.as_of+'T12:00:00').toLocaleDateString('ru-RU')}. Сумма сметы не считается полученной оплатой.</p></div></details>`;
      const max=Math.max(1,...item.months.map(m=>m.received));
      target.querySelectorAll('[data-profile-bar]').forEach(bar=>{bar.style.height=Number(bar.dataset.profileBar)?Math.max(4,Number(bar.dataset.profileBar)/max*100)+'%':'2px';});
      target.querySelectorAll('[data-profile-currency]').forEach(button=>button.onclick=()=>{selected=button.dataset.profileCurrency;renderMoney();});
    };
    host.querySelectorAll('[data-profile-period]').forEach(button=>button.onclick=()=>{period=button.dataset.profilePeriod;host.querySelectorAll('[data-profile-period]').forEach(node=>node.setAttribute('aria-pressed',String(node===button)));renderMoney();});
    renderMoney();
  };

  return {render,settings,overview};
})();
