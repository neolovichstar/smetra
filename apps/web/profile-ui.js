'use strict';

window.SmetraProfile=(()=>{
  const field=(name,label,value,placeholder='',max=120)=>`<label>${label}<input name="${name}" value="${escapeHtml(value)}" maxlength="${max}" placeholder="${placeholder}" autocomplete="${name==='first_name'?'given-name':name==='last_name'?'family-name':name==='company'?'organization':'off'}"></label>`;
  const saveForm=(form,active,after)=>{
    form.onsubmit=async event=>{
      event.preventDefault();if(form.dataset.saving==='true'||!active())return;
      const values=Object.fromEntries(new FormData(form));if(form.elements.namedItem('memory_enabled'))values.memory_enabled=form.elements.namedItem('memory_enabled').checked?1:0;
      form.dataset.saving='true';const button=form.querySelector('[type=submit]'),status=form.querySelector('[role=status]');button.disabled=true;status.textContent='Сохраняем…';
      form.querySelectorAll('input,textarea,select').forEach(control=>control.disabled=true);
      try{await api('/profile',{method:'PATCH',body:JSON.stringify(values)});if(!active())return;await after?.();if(active())status.textContent='Сохранено'}
      catch(error){if(active())status.textContent=error.message}
      finally{delete form.dataset.saving;if(button.isConnected){button.disabled=false;form.querySelectorAll('input,textarea,select').forEach(control=>control.disabled=false)}}
    };
  };
  const addPublicIdStyles=()=>{
    if(document.querySelector('#profile-public-id-styles'))return;
    const style=document.createElement('style');style.id='profile-public-id-styles';
    style.textContent='.profile-public-id{display:flex;align-items:center;justify-content:space-between;gap:22px;margin:22px 0;padding:20px 22px;border:1px solid var(--line,rgba(128,128,128,.18));border-radius:16px;background:rgba(128,128,128,.035)}.profile-public-id-copy{min-width:0}.profile-public-id h2{margin:5px 0 7px;font-size:17px;letter-spacing:-.025em}.profile-public-id p{margin:0 0 12px;max-width:600px;font-size:12px;line-height:1.6;opacity:.65}.profile-public-id code{display:inline-block;padding:8px 10px;border:1px solid var(--line,rgba(128,128,128,.15));border-radius:9px;font-size:12px;letter-spacing:.045em;overflow-wrap:anywhere}.profile-public-id-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;flex:none}@media(max-width:600px){.profile-public-id{align-items:flex-start;flex-direction:column;padding:16px}.profile-public-id-actions{width:100%}.profile-public-id-actions .btn{flex:1}}';
    document.head.append(style);
  };
  const render=async(active=()=>true)=>{
    addPublicIdStyles();
    const [result,identity]=await Promise.all([api('/profile'),api('/profile/id')]);if(!active())return;const p=result.profile;
    view(`<section class="profile-page"><header><h1>Профиль</h1><p>Расскажите о себе — ассистент учтёт это в работе.</p></header><section class="profile-public-id"><div class="profile-public-id-copy"><span class="overline">Рабочие контакты</span><h2>Ваш ID в Сметре</h2><p>Передайте его коллеге или клиенту, чтобы вас нашли в поиске и начали личный чат. ID не открывает доступ к вашим сметам.</p><code id="profile-public-id-value">${escapeHtml(identity.public_id||'—')}</code></div><div class="profile-public-id-actions"><button class="btn" id="profile-copy-public-id" type="button">Скопировать ID</button><button class="btn primary" id="profile-open-chats" type="button">Открыть чаты</button></div></section><div class="profile-layout"><aside class="profile-summary"><span class="profile-avatar">${escapeHtml((p.first_name||user.name).slice(0,1).toUpperCase())}</span><div><h2 id="profile-display-name">${escapeHtml(user.name)}</h2><p>${escapeHtml(user.email)}</p></div></aside><form id="profile-form"><section><h3>Как к вам обращаться</h3><div class="profile-fields">${field('first_name','Имя',p.first_name,'Ваше имя',80)}${field('last_name','Фамилия',p.last_name,'Ваша фамилия',80)}</div></section><section><h3>Ваша работа</h3><div class="profile-fields">${field('profession','Чем занимаетесь',p.profession,'Например, дизайнер интерьера')}${field('company','Компания',p.company,'Название или команда')}</div></section><section><label>О себе<textarea name="about" maxlength="2000" rows="5" placeholder="Какие проекты ведёте, что важно в вашей работе…">${escapeHtml(p.about)}</textarea></label><p class="profile-hint">Необязательно. Эти данные доступны вам и вашему ассистенту.</p></section><footer><button class="btn primary" type="submit">Сохранить профиль</button><span role="status"></span></footer></form></div></section>`);
    saveForm(document.querySelector('#profile-form'),active,async()=>{const current=await api('/me');if(!active())return;Object.assign(user,current.user);document.querySelector('#header-user').textContent=user.name;document.querySelector('#profile-display-name').textContent=user.name});
    const publicId=identity.public_id||'';
    document.querySelector('#profile-copy-public-id')?.addEventListener('click',async()=>{
      if(!publicId)return;
      try{await navigator.clipboard.writeText(publicId);notify('Публичный ID скопирован')}
      catch{const value=document.querySelector('#profile-public-id-value');if(value){const selection=window.getSelection(),range=document.createRange();range.selectNodeContents(value);selection.removeAllRanges();selection.addRange(range);notify('Выделите ID и скопируйте его вручную')}}
    });
    document.querySelector('#profile-open-chats')?.addEventListener('click',()=>window.SmetraCommunication?.open('direct'));
  };
  const settings=async(active)=>{
    const result=await api('/profile');if(!active())return;const p=result.profile,root=document.querySelector('#settings-personalization');
    root.innerHTML=`<div class="personalization-settings"><div><h3>Ассистент</h3><p>Ответы и личная память.</p></div><form id="personalization-form"><label>Стиль ответа<select name="response_style"><option value="concise" ${p.response_style==='concise'?'selected':''}>Кратко и по делу</option><option value="balanced" ${p.response_style==='balanced'?'selected':''}>С пояснениями</option><option value="detailed" ${p.response_style==='detailed'?'selected':''}>Подробно</option></select></label><label class="memory-setting"><span><strong>Личная память</strong><small>Ассистент запоминает полезные факты из разговора. Записи можно изменить в окне знаний.</small></span><input type="checkbox" name="memory_enabled" ${p.memory_enabled?'checked':''}></label><div class="profile-save-row"><button class="btn primary" type="submit">Сохранить настройки</button><span role="status"></span></div></form></div>`;
    saveForm(root.querySelector('form'),active);
  };
  return {render,settings};
})();
