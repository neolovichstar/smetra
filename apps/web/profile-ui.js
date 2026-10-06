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
  const render=async(active=()=>true)=>{
    const result=await api('/profile');if(!active())return;const p=result.profile;
    view(`<section class="profile-page"><header><h1>Профиль</h1><p>Расскажите о себе — ассистент учтёт это в работе.</p></header><div class="profile-layout"><aside class="profile-summary"><span class="profile-avatar">${escapeHtml((p.first_name||user.name).slice(0,1).toUpperCase())}</span><div><h2 id="profile-display-name">${escapeHtml(user.name)}</h2><p>${escapeHtml(user.email)}</p></div></aside><form id="profile-form"><section><h3>Как к вам обращаться</h3><div class="profile-fields">${field('first_name','Имя',p.first_name,'Ваше имя',80)}${field('last_name','Фамилия',p.last_name,'Ваша фамилия',80)}</div></section><section><h3>Ваша работа</h3><div class="profile-fields">${field('profession','Чем занимаетесь',p.profession,'Например, дизайнер интерьера')}${field('company','Компания',p.company,'Название или команда')}</div></section><section><label>О себе<textarea name="about" maxlength="2000" rows="5" placeholder="Какие проекты ведёте, что важно в вашей работе…">${escapeHtml(p.about)}</textarea></label><p class="profile-hint">Необязательно. Эти данные доступны вам и вашему ассистенту.</p></section><footer><button class="btn primary" type="submit">Сохранить профиль</button><span role="status"></span></footer></form></div></section>`);
    saveForm(document.querySelector('#profile-form'),active,async()=>{const current=await api('/me');if(!active())return;Object.assign(user,current.user);document.querySelector('#header-user').textContent=user.name;document.querySelector('#profile-display-name').textContent=user.name});
  };
  const settings=async(active)=>{
    const result=await api('/profile');if(!active())return;const p=result.profile,root=document.querySelector('#settings-personalization');
    root.innerHTML=`<div class="personalization-settings"><div><h3>Ассистент</h3><p>Ответы и личная память.</p></div><form id="personalization-form"><label>Стиль ответа<select name="response_style"><option value="concise" ${p.response_style==='concise'?'selected':''}>Кратко и по делу</option><option value="balanced" ${p.response_style==='balanced'?'selected':''}>С пояснениями</option><option value="detailed" ${p.response_style==='detailed'?'selected':''}>Подробно</option></select></label><label class="memory-setting"><span><strong>Личная память</strong><small>Ассистент запоминает полезные факты из разговора. Записи можно изменить в окне знаний.</small></span><input type="checkbox" name="memory_enabled" ${p.memory_enabled?'checked':''}></label><div class="profile-save-row"><button class="btn primary" type="submit">Сохранить настройки</button><span role="status"></span></div></form></div>`;
    saveForm(root.querySelector('form'),active);
  };
  return {render,settings};
})();
