/* The page receives only the server's filtered document. No original snapshot. */
(() => {
  'use strict';
  const token=location.hash.slice(1),host=document.querySelector('#protected-content');
  const e=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const states={sent:'Отправлена заказчику',viewed:'Просмотрена',changes_requested:'Запрошены изменения',approved:'Принята',rejected:'Отклонена'};
  const dates=value=>new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric',timeZone:'Europe/Moscow'}).format(new Date(value*1000));
  const money=(value,currency)=>new Intl.NumberFormat('ru-RU',{style:'currency',currency,maximumFractionDigits:2}).format(value/100);
  let viewToken='',current=null,identity=null,refreshing=false,sequence=0,expiryTimer,storeKey='',stopped=false;
  document.querySelector('#protected-theme').onclick=()=>{const next=document.documentElement.dataset.theme==='light'?'dark':'light';document.documentElement.dataset.theme=next;try{localStorage.setItem('smetra_theme',next)}catch{}};
  async function request(action,extra={}){
    const response=await fetch('/api/public/protected/'+action,{method:'POST',credentials:'same-origin',cache:'no-store',referrerPolicy:'no-referrer',headers:{'Content-Type':'application/json'},body:JSON.stringify({token,...(viewToken?{view_token:viewToken}:{}),...extra})});
    if(!response.ok){const data=await response.json().catch(()=>({}));const error=Error(data.error||'Не удалось проверить доступ. Повторите попытку.');error.status=response.status;throw error}
    return action==='pdf'||action==='xlsx'?response.blob():response.json();
  }
  function forgetView(){viewToken='';try{sessionStorage.removeItem(storeKey)}catch{}}
  function gate(message,code=false){
    sequence++;current=null;clearTimeout(expiryTimer);document.body.classList.add('export-disabled');
    host.innerHTML=`<section class="protected-gate"><span class="eyebrow">ЗАЩИЩЁННОЕ ПРЕДЛОЖЕНИЕ</span><h1>${code?'Введите код доступа':'Доступ к смете'}</h1><p>${e(message)}</p>${code?'<form id="protected-code-form"><label for="protected-code">Код от исполнителя</label><input id="protected-code" type="password" autocomplete="off" minlength="6" maxlength="64" required><p class="form-error" role="alert"></p><button class="btn primary" type="submit">Открыть предложение</button></form>':'<button class="btn" type="button" id="protected-retry">Проверить доступ</button>'}</section>`;
    document.querySelector('#protected-retry')?.addEventListener('click',()=>open());
    const form=document.querySelector('#protected-code-form');
    if(form)form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('button');button.disabled=true;try{await open(form.querySelector('input').value)}finally{if(button.isConnected)button.disabled=false}};
  }
  async function account(){
    try{const response=await fetch('/api/me',{credentials:'same-origin',cache:'no-store'});identity=response.ok?(await response.json()).user:null}catch{identity=null}
  }
  async function open(code=''){
    if(stopped)return;
    try{
      const result=await request(viewToken?'view':'open',code?{access_code:code}:{});
      if(result.view_token){viewToken=result.view_token;try{sessionStorage.setItem(storeKey,viewToken)}catch{}}
      await account();render(result.document);
    }catch(error){if(error.status===401){forgetView();gate(error.message,true)}else gate(error.message)}
  }
  function render(doc){
    current=doc;document.title=doc.title+' · Защищённое предложение';
    document.body.classList.toggle('export-disabled',!doc.permissions.allow_pdf);
    document.body.classList.toggle('protected-no-copy',!doc.permissions.allow_copy);
    const columns=['<th scope="col">Наименование</th>'];
    if(doc.permissions.show_quantities)columns.push('<th scope="col" class="numeric">Количество</th><th scope="col">Ед.</th>');
    if(doc.permissions.show_prices){if(doc.permissions.show_quantities)columns.push('<th scope="col" class="numeric">Цена</th>');columns.push('<th scope="col" class="numeric">Стоимость</th>')}
    let rows='';
    if(doc.sections)rows=`<table class="protected-table"><thead><tr><th scope="col">Раздел</th><th scope="col" class="numeric">Стоимость</th></tr></thead><tbody>${doc.sections.map(row=>`<tr><td>${e(row.name)}</td><td class="numeric">${e(money(row.amount_kopecks,doc.currency))}</td></tr>`).join('')}</tbody></table>`;
    else if(doc.items?.length)rows=`<table class="protected-table"><thead><tr>${columns.join('')}</tr></thead><tbody>${doc.items.map(row=>`<tr><td>${e(row.name)}${row.category?`<small>${e(row.category)}</small>`:''}</td>${doc.permissions.show_quantities?`<td class="numeric">${e(new Intl.NumberFormat('ru-RU',{maximumFractionDigits:4}).format(Number(row.quantity)))}</td><td>${e(row.unit)}</td>`:''}${doc.permissions.show_prices?`${doc.permissions.show_quantities?`<td class="numeric">${e(money(row.unit_price,doc.currency))}</td>`:''}<td class="numeric">${e(money(row.subtotal,doc.currency))}</td>`:''}</tr>`).join('')}</tbody></table>`;
    const pending=['sent','viewed'].includes(doc.status)&&doc.decisions_available;
    host.innerHTML=`<div class="protected-toolbar"><span class="protected-status">${e(states[doc.status]||doc.status)}</span><span>Доступ до ${e(dates(doc.expires_at))}</span><div class="protected-export-actions">${doc.permissions.allow_pdf?'<button class="btn small" type="button" data-export="pdf">Скачать PDF</button>':''}${doc.permissions.allow_excel?'<button class="btn small" type="button" data-export="xlsx">Скачать Excel</button>':''}</div></div>
      <article class="protected-document" aria-label="Коммерческое предложение">
        <header class="protected-document-heading"><div class="protected-document-meta"><span>${e(doc.contractor)}</span><span>${e(doc.number)} · версия ${e(doc.version)}</span></div><p class="protected-date">${e(dates(doc.created_at))}</p><h1>${e(doc.title)}</h1>${doc.alternative_label?`<p>${e(doc.alternative_label)} · Принимается один вариант предложения</p>`:''}${doc.recipient?`<p class="protected-recipient">Подготовлено для ${e(doc.recipient)}</p>`:''}</header>
        ${rows?`<div class="protected-table-scroll" tabindex="0" aria-label="Состав предложения">${rows}</div>`:''}
        <section class="protected-total"><span>Итоговая стоимость</span><strong>${e(money(doc.amount_kopecks,doc.currency))}</strong></section>
        ${doc.due_date?`<p class="protected-due">Срок: ${e(doc.due_date)}</p>`:''}
        ${doc.terms?`<section class="protected-terms"><h2>Условия предложения</h2><p>${e(doc.terms)}</p></section>`:''}
        ${Object.entries({included:"Включено в стоимость",excluded:"Не включено в стоимость",customer:"Обеспечивает заказчик",clarifications:"Требует уточнения"}).filter(([key])=>doc.scope?.[key]?.length).map(([key,label])=>`<section class="protected-terms"><h2>${label}</h2><ul>${doc.scope[key].map(text=>`<li>${e(text)}</li>`).join('')}</ul></section>`).join('')}
        ${doc.notice?`<p class="protected-document-notice">${e(doc.notice)}</p>`:''}
        <div class="protected-document-foot"><span>Сметра · защищённое предложение</span><span>Просмотр ${e(doc.view_id.slice(0,8))}</span></div>
        ${doc.watermark?`<div class="protected-watermarks" aria-hidden="true">${Array.from({length:10},()=>`<span>${e(doc.watermark)}</span>`).join('')}</div>`:''}
      </article>
      <section class="protected-response"><h2>${pending?'Ваше решение':'Статус предложения'}</h2><p>${e(doc.decision_notice)}</p>${doc.version_notice?`<p>${e(doc.version_notice)}</p>`:''}${pending?`${!identity?'<div class="protected-identity-note"><p>Для ответа войдите в Сметру с подтверждённой почтой, которую указал исполнитель. Пересланной ссылки недостаточно.</p><a class="btn" href="/app" target="_blank" rel="noopener noreferrer">Войти в Сметру</a><button class="btn" type="button" id="protected-signed-in">Я вошёл — проверить</button></div>':''}<div class="protected-decision-actions"><button class="btn primary" type="button" data-decision="approved">Принять предложение</button><button class="btn" type="button" data-decision="changes_requested">Запросить изменения</button><button class="btn" type="button" data-decision="rejected">Отклонить</button></div>`:`<strong>${e(states[doc.status]||doc.status)}</strong>`}<p id="protected-response-error" class="form-error" role="alert"></p></section>`;
    document.querySelector('#protected-signed-in')?.addEventListener('click',()=>open());
    host.querySelectorAll('[data-export]').forEach(button=>button.onclick=async()=>{
      button.disabled=true;try{const blob=await request(button.dataset.export);const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='smetra-protected.'+button.dataset.export;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(error){if([401,410].includes(error.status))gate(error.message);else document.querySelector('#protected-response-error').textContent=error.message}finally{if(button.isConnected)button.disabled=false}
    });
    host.querySelectorAll('[data-decision]').forEach(button=>button.onclick=()=>decision(button.dataset.decision));
    clearTimeout(expiryTimer);expiryTimer=setTimeout(()=>gate('Срок доступа истёк. Обратитесь к исполнителю.'),Math.min(2147483647,Math.max(0,doc.expires_at*1000-Date.now())));
  }
  function decision(action){
    if(!current)return;
    const doc=current,dialog=document.querySelector('#protected-decision-dialog');
    const title={approved:'Принять предложение?',changes_requested:'Что нужно изменить?',rejected:'Отклонить предложение?'}[action];
    dialog.innerHTML=`<form><h2 id="decision-title">${e(title)}</h2><p>${e(doc.title)} · ${e(money(doc.amount_kopecks,doc.currency))} · версия ${e(doc.version)}</p><label for="protected-comment">Комментарий${action==='changes_requested'?' (обязательно)':''}</label><textarea id="protected-comment" rows="4" maxlength="3000" ${action==='changes_requested'?'required':''}></textarea><label class="protected-checkbox"><input type="checkbox" required><span>Подтверждаю это решение по указанной версии предложения. ${e(doc.decision_notice)}</span></label><p class="form-error" role="alert"></p><div class="protected-decision-actions"><button class="btn primary" type="submit">Подтвердить решение</button><button class="btn" type="button" data-cancel>Отмена</button></div></form>`;
    dialog.querySelector('[data-cancel]').onclick=()=>dialog.close();dialog.showModal();
    dialog.querySelector('form').onsubmit=async event=>{
      event.preventDefault();const button=dialog.querySelector('[type=submit]');button.disabled=true;
      try{await request('respond',{action,comment:dialog.querySelector('textarea').value,confirmation:true,snapshot_sha256:doc.snapshot_sha256,permissions_revision:doc.permissions_revision});dialog.close();await refresh()}
      catch(error){dialog.querySelector('[role=alert]').textContent=error.message;if(error.status===410){dialog.close();gate(error.message)}else if(error.status===401){await account();dialog.close();render(doc);document.querySelector('#protected-response-error').textContent=error.message}}
      finally{if(button.isConnected)button.disabled=false}
    };
  }
  async function refresh(){
    if(refreshing||!viewToken||stopped||document.hidden)return;
    refreshing=true;const mine=sequence;
    try{const result=await request('view');if(mine===sequence&&(!current||result.document.permissions_revision>=current.permissions_revision)){
      // Keep an in-progress confirmation form intact. The server checks its
      // permission revision again before applying any decision.
      if(!document.querySelector('#protected-decision-dialog').open)render(result.document);
    }}catch(error){if(mine===sequence){if(error.status===401)forgetView();gate(error.message,error.status===401)}}finally{refreshing=false}
  }
  for(const name of ['copy','cut','contextmenu','selectstart','dragstart'])document.addEventListener(name,event=>{if(current&&!current.permissions.allow_copy&&event.target.closest?.('.protected-document'))event.preventDefault()});
  document.addEventListener('keydown',event=>{if(!current)return;const key=event.key.toLowerCase();if((event.ctrlKey||event.metaKey)&&((!current.permissions.allow_pdf&&['p','s'].includes(key))||(!current.permissions.allow_copy&&['c','x','a'].includes(key)&&event.target.closest?.('.protected-document'))))event.preventDefault()});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){sequence++;current=null;host.replaceChildren();document.querySelector('#protected-decision-dialog').close();document.body.classList.add('export-disabled')}else if(viewToken)refresh();else open()});
  window.addEventListener('focus',()=>refresh());
  window.addEventListener('pagehide',()=>{stopped=true;sequence++;current=null;host.replaceChildren();clearTimeout(expiryTimer)});
  window.addEventListener('pageshow',event=>{if(event.persisted){stopped=false;open()}});
  setInterval(refresh,5000);
  (async()=>{if(!/^[A-Za-z0-9_-]{43}$/.test(token)){gate('Ссылка неполная или недействительна. Запросите новую у исполнителя.');return}
    try{const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(token));storeKey='smetra.protected.'+Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join('');viewToken=sessionStorage.getItem(storeKey)||''}catch{}
    await open();
  })();
})();
