(() => {
  const host=document.querySelector('#change');
  const token=new URLSearchParams(location.search).get('token')||'';
  const escape=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const money=value=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB'}).format(Number(value)/100);
  const states={sent:'Ожидает решения',approved:'Согласовано',changes_requested:'Запрошены изменения',declined:'Отклонено'};
  async function api(path,options){const response=await fetch('/api/public/'+path,options);const result=await response.json();if(!response.ok)throw Error(result.error||'Не удалось выполнить запрос');return result}
  async function render(){
    try{if(!token)throw Error('Ссылка не содержит код согласования');
      const {change}=await api('change?token='+encodeURIComponent(token));
      const expired=change.status==='sent'&&change.expires_at&&change.expires_at<=Date.now()/1000;
      const canReply=change.status==='sent'&&!expired;
      const state=expired?'Срок ссылки истёк':states[change.status]||change.status;
      host.innerHTML=`<span class="eyebrow">ДОПОЛНИТЕЛЬНЫЕ РАБОТЫ / ВЕРСИЯ ${escape(change.version)}</span><h1 class="title">${escape(change.title)}</h1><p class="lead">${escape(change.description||'Проверьте новые работы и сумму до принятия решения.')}</p><div class="meta"><span>Статус · <strong>${escape(state)}</strong></span>${change.deadline_days?`<span>Изменение срока · <strong>+${escape(change.deadline_days)} дн.</strong></span>`:''}${change.sent_at?`<span>Отправлено · <strong>${new Date(change.sent_at*1000).toLocaleDateString('ru-RU')}</strong></span>`:''}</div><div class="grid"><section><h2>Состав работ</h2>${change.items.map(item=>`<div class="line"><div><strong>${escape(item.name)}</strong><small>${escape(item.quantity)} ${escape(item.unit)} × ${money(item.unit_price)}${item.description?' · '+escape(item.description):''}</small></div><b>${money(item.subtotal)}</b></div>`).join('')}<div class="total"><span>Дополнительно к основной смете</span><strong>${money(change.amount_kopecks)}</strong></div></section><aside class="decision"><h2>Решение клиента</h2>${canReply?`<p>Ваш ответ относится только к этой версии дополнительных работ.</p><form id="change-response"><label>Ваше имя<input name="name" required maxlength="120" autocomplete="name"></label><label>Комментарий<textarea name="comment" maxlength="2000" placeholder="При необходимости уточните условия"></textarea></label><div class="actions"><button class="primary" type="button" data-action="approved">Согласовать</button><button type="button" data-action="changes_requested">Нужны изменения</button><button type="button" data-action="declined">Отклонить</button></div><p class="error" role="alert"></p></form>`:`<p class="state"><strong>${escape(state)}.</strong> ${change.response_name?'Ответил(а): '+escape(change.response_name)+'.':''} ${escape(change.response_comment)}</p>`}</aside></div>`;
      const form=host.querySelector('#change-response');if(form)form.querySelectorAll('[data-action]').forEach(button=>button.onclick=async()=>{if(!form.reportValidity())return;
        const action=button.dataset.action,comment=form.elements.comment.value.trim();if(action==='changes_requested'&&!comment){form.querySelector('.error').textContent='Опишите необходимые изменения';form.elements.comment.focus();return}
        form.querySelectorAll('button').forEach(item=>item.disabled=true);form.querySelector('.error').textContent='';
        try{await api('change/respond',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token,action,name:form.elements.name.value.trim(),comment})});await render()}
        catch(error){form.querySelector('.error').textContent=error.message;form.querySelectorAll('button').forEach(item=>item.disabled=false)}
      });
    }catch(error){host.innerHTML=`<h1 class="title">Ссылка недоступна</h1><p class="lead">${escape(error.message)}</p><button class="retry" type="button">Повторить</button>`;host.querySelector('.retry').onclick=render}
  }
  render();
})();
