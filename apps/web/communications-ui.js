'use strict';
window.SmetraCommunications = (() => {
  let timer = null, realtimeUserId = '', realtimeConfig = null, realtimePromise = null;
  const subscriptions = new Set();
  const subscribeTopic = (topic, callback) => {
    if(!topic||!window.SmetraRealtime)return null;
    const off=window.SmetraRealtime.subscribe(topic,callback);
    subscriptions.add(off);
    return ()=>{off();subscriptions.delete(off);};
  };
  async function prepareRealtime(api, user) {
    if(realtimeUserId===user?.id&&realtimeConfig)return realtimeConfig;
    if(realtimeUserId===user?.id&&realtimePromise)return realtimePromise;
    realtimeUserId=user?.id||'';realtimeConfig=null;
    realtimePromise=(async()=>{try{const config=await api('/realtime/config');if(config.enabled&&window.SmetraRealtime)window.SmetraRealtime.configure(config.url,config.key);realtimeConfig=config;return config;}catch{realtimeConfig={enabled:false};return realtimeConfig;}})();
    return realtimePromise;
  }
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const time = value => value ? new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit',day:'2-digit',month:'short'}).format(new Date(Number(value)>1e12?Number(value):Number(value)*1000)) : '';
  const stop = () => { if(timer!==null){clearInterval(timer);timer=null;} for(const off of subscriptions){try{off();}catch{}} subscriptions.clear(); };
  const icon = name => name==='support'?'◌':name==='workspace'?'▦':name==='quote'?'▤':name==='community'?'◎':'↗';
  const roleName = role => ({user:'Вы',admin:'Поддержка',ai:'Помощник Сметры',system:'Сметра'}[role]||'Участник');
  function messageMarkup(messages, ownId, emptyText='Здесь начнётся переписка.') {
    if(!messages?.length)return '<div class="comms-empty"><span>✳</span><strong>Пока тихо</strong><p>'+esc(emptyText)+'</p></div>';
    return messages.map(message=>{
      const own=message.sender_id===ownId;
      const system=['system','ai'].includes(message.sender_role);
      return '<article class="comms-message '+(own?'is-own ':'')+(system?'is-system':'')+'">'+
        '<div class="comms-message-meta"><strong>'+esc(message.sender_name||roleName(message.sender_role))+'</strong><time>'+esc(time(message.created_at))+'</time></div>'+
        '<p>'+esc(message.body).replace(/\n/g,'<br>')+'</p></article>';
    }).join('');
  }
  function bindSend(form, send, active) {
    form.onsubmit=async event=>{
      event.preventDefault();
      const input=form.querySelector('textarea'),button=form.querySelector('button[type="submit"]');
      const message=input.value.trim();
      if(!message||button.disabled||!active())return;
      button.disabled=true;
      try{await send(message);if(active()&&input.value.trim()===message)input.value='';}
      catch(error){if(active())window.notify?.(error.message);}
      finally{if(button.isConnected)button.disabled=false;}
    };
  }
  async function support(ctx) {
    stop();
    const {api,view,header,notify,user,active}=ctx;
    let items=[],selectedId=null,selectedTicket=null,isNew=false,busy=false,realtime=null,ticketOff=null,inboxOff=null,watchedTicketTopic='';
    view(header('Поддержка','Помощник Сметры ответит сразу. Если потребуется человек, передадим обращение сотруднику.')+
      '<div class="comms-support-layout"><aside class="comms-sidebar">'+
        '<div class="comms-sidebar-head"><div><span class="overline">ВАШИ ОБРАЩЕНИЯ</span><h2>Поддержка</h2></div><button class="btn small primary" type="button" id="support-new">Новое</button></div>'+
        '<div class="comms-ticket-list" id="support-ticket-list"><div class="comms-loading">Загружаем обращения…</div></div>'+
        '<p class="comms-privacy-note">Переписка приватная. Не отправляйте пароли, коды входа и платёжные данные.</p></aside>'+
        '<section class="comms-chat-panel" id="support-chat-panel"><div class="comms-empty"><span>✳</span><strong>Решим вопрос вместе</strong><p>Выберите обращение или создайте новое.</p></div></section></div>');
    const list=document.querySelector('#support-ticket-list'),panel=document.querySelector('#support-chat-panel');
    const renderItems=()=>{
      if(!items.length){list.innerHTML='<div class="comms-list-empty">Обращений пока нет</div>';return;}
      list.innerHTML=items.map(item=>'<button type="button" class="comms-ticket-row '+(item.id===selectedId&&!isNew?'is-selected':'')+'" data-support-open="'+esc(item.id)+'">'+
        '<span class="comms-ticket-row-top"><strong>'+esc(item.subject||'Вопрос в поддержку')+'</strong><small>'+esc(time(item.updated_at||item.created_at))+'</small></span>'+
        '<span class="comms-ticket-row-message">'+esc(item.last_message||'Новое обращение')+'</span>'+
        '<span class="comms-ticket-row-bottom"><small class="'+(item.needs_human?'needs-human':'')+'">'+(item.needs_human?'Ожидает сотрудника':item.status==='closed'?'Закрыто':'Помощник онлайн')+'</small></span></button>').join('');
    };
    const composer=(placeholder='Напишите сообщение…')=>'<form class="comms-composer" id="support-reply-form"><textarea name="message" rows="1" maxlength="4000" required placeholder="'+esc(placeholder)+'"></textarea><button class="btn primary" type="submit">Отправить <span aria-hidden="true">↗</span></button></form>';
    function renderNew() {
      isNew=true;selectedTicket=null;
      panel.innerHTML='<header class="comms-chat-head"><span class="comms-chat-avatar">✳</span><div><h2>Новое обращение</h2><p>Опишите вопрос — помощник постарается решить его сразу.</p></div></header>'+
        '<form class="comms-new-ticket" id="support-create-form"><label>Тема<input name="subject" maxlength="100" placeholder="Например, не открывается смета"></label><label>Что произошло?<textarea name="message" rows="5" minlength="5" maxlength="2000" required placeholder="Опишите, что вы делали и какой результат получили…"></textarea></label><button class="btn primary" type="submit">Создать обращение</button></form>';
      list.querySelectorAll('[data-support-open]').forEach(button=>button.classList.remove('is-selected'));
      document.querySelector('#support-create-form').onsubmit=async event=>{
        event.preventDefault();const form=event.currentTarget,button=form.querySelector('button');if(button.disabled||!active())return;
        const data=new FormData(form),message=String(data.get('message')||'').trim(),subject=String(data.get('subject')||'').trim();
        button.disabled=true;
        try{const result=await api('/support',{method:'POST',body:JSON.stringify({subject,message})});if(!active())return;selectedId=result.ticket.id;selectedTicket=result.ticket;isNew=false;await refresh(false);renderItems();renderTicket(result.ticket,result.messages||[]);notify?.('Обращение создано');}
        catch(error){if(active())notify?.(error.message);}
        finally{if(button.isConnected)button.disabled=false;}
      };
    }
    function renderTicket(ticket,messages) {
      selectedTicket=ticket;selectedId=ticket.id;isNew=false;
      if(ticket?.realtime_topic&&ticket.realtime_topic!==watchedTicketTopic){
        ticketOff?.();watchedTicketTopic=ticket.realtime_topic;
        ticketOff=subscribeTopic(watchedTicketTopic,async eventName=>{
          if(eventName!=='message_changed'||!active()||selectedId!==ticket.id)return;
          try{const update=await api('/support/'+encodeURIComponent(ticket.id)+'/messages?refresh='+Date.now());if(active()&&selectedId===ticket.id)renderTicket(update.ticket,update.messages||[]);}catch{}
        });
      }
      panel.innerHTML='<header class="comms-chat-head"><span class="comms-chat-avatar">✳</span><div class="comms-chat-head-copy"><h2>'+esc(ticket.subject||'Вопрос в поддержку')+'</h2><p>'+(ticket.needs_human?'<span class="comms-live-dot warning"></span>Передано сотруднику':ticket.status==='closed'?'Обращение закрыто':'<span class="comms-live-dot"></span>ИИ-помощник онлайн')+'</p></div><button type="button" class="btn small ghost" id="support-escalate" '+(ticket.needs_human||ticket.status==='closed'?'disabled':'')+'>'+(ticket.needs_human?'Сотрудник вызван':'Позвать сотрудника')+'</button></header>'+
        '<div class="comms-messages" id="support-messages" role="log" aria-live="polite">'+messageMarkup(messages,user.id,'Напишите сообщение, чтобы начать.')+'</div>'+
        (ticket.status==='closed'?'<div class="comms-closed-note">Обращение закрыто. Новое сообщение откроет его снова.</div>':'')+composer(ticket.status==='closed'?'Напишите, чтобы снова открыть обращение':'Напишите сообщение…');
      const messagesRoot=document.querySelector('#support-messages');if(messagesRoot)messagesRoot.scrollTop=messagesRoot.scrollHeight;
      const reply=document.querySelector('#support-reply-form');
      if(reply)bindSend(reply,async message=>{
        const result=await api('/support/'+encodeURIComponent(ticket.id)+'/messages',{method:'POST',body:JSON.stringify({message})});
        if(!active())return;selectedTicket=result.ticket;renderTicket(result.ticket,result.messages||[]);
        await refresh(false);renderItems();
      },active);
      document.querySelector('#support-escalate')?.addEventListener('click',async event=>{
        const button=event.currentTarget;if(button.disabled||!active())return;button.disabled=true;
        try{const result=await api('/support/'+encodeURIComponent(ticket.id)+'/escalate',{method:'POST',body:JSON.stringify({})});if(!active())return;renderTicket(result.ticket,result.messages||[]);await refresh(false);renderItems();notify?.('Сотрудник поддержки получил уведомление.');}
        catch(error){if(active()){button.disabled=false;notify?.(error.message)}}
      });
    }
    async function openTicket(id) {
      if(busy||!active())return;busy=true;isNew=false;selectedId=id;renderItems();
      try{const result=await api('/support/'+encodeURIComponent(id)+'/messages?refresh='+Date.now());if(!active()||selectedId!==id)return;renderTicket(result.ticket,result.messages||[]);renderItems();}
      catch(error){if(active())panel.innerHTML='<div class="comms-error">'+esc(error.message)+'</div>';}
      finally{busy=false;}
    }
    async function refresh(openSelected=true) {
      const result=await api('/support?refresh='+Date.now());if(!active())return;
      items=Array.isArray(result.items)?result.items:[];
      if(selectedId&&!items.some(item=>item.id===selectedId)&&!isNew)selectedId=null;
      renderItems();
      if(openSelected&&selectedId&&!isNew)await openTicket(selectedId);
      else if(!selectedId&&!isNew&&items.length){selectedId=items[0].id;await openTicket(selectedId);}
    }
    document.querySelector('#support-new').onclick=()=>{ticketOff?.();ticketOff=null;watchedTicketTopic='';renderNew();};
    list.onclick=event=>{const button=event.target.closest('[data-support-open]');if(button)openTicket(button.dataset.supportOpen);};
    realtime=await prepareRealtime(api,user);
    if(realtime?.inbox_topic)inboxOff=subscribeTopic(realtime.inbox_topic,eventName=>{
      if(['inbox_changed','support_escalated'].includes(eventName)&&active())refresh(false).then(renderItems).catch(()=>{});
    });
    await refresh(true);
    let lastRefresh=0;
    if(active())timer=setInterval(async()=>{
      if(!active()||busy)return;
      try{
        const current=selectedId,now=Date.now(),live=Boolean(selectedTicket?.realtime_topic&&window.SmetraRealtime?.isSubscribed(selectedTicket.realtime_topic));
        if(now-lastRefresh>=(realtime?.enabled?30000:5000)){await refresh(false);lastRefresh=now;}
        if(current&&!isNew&&selectedId===current&&(!live||now-lastRefresh>=30000)){const result=await api('/support/'+encodeURIComponent(current)+'/messages?refresh='+Date.now());if(active()&&selectedId===current)renderTicket(result.ticket,result.messages||[]);}
      }catch{}
    },5000);
  }
  async function messaging(ctx) {
    stop();
    const {api,view,header,notify,user,active}=ctx;
    let chats=[],communities=[],projects=[],activeId=null,activeConversation=null,messages=[],people=[],loading=false,searchTimer=null,workspaceId='',realtime=null,activeOff=null,inboxOff=null,watchedConversationTopic='',lastListRefresh=0,lastMessagesRefresh=0;
    view(header('Почта и чаты','Личные переписки, согласование смет и рабочие чаты объектов — внутри Сметры.')+
      '<div class="comms-layout"><aside class="comms-sidebar">'+
        '<section class="comms-directory"><span class="overline">НАЙТИ ЧЕЛОВЕКА</span><form id="comms-search-form"><input id="comms-search" type="search" maxlength="80" placeholder="Имя или ID · SM-…" aria-label="Поиск людей"><button class="btn small" type="submit">Найти</button></form><div id="comms-people" class="comms-people-results"></div></section>'+
        '<section class="comms-chat-list-section"><div class="comms-sidebar-head"><div><span class="overline">ВАШИ ПЕРЕПИСКИ</span><h2>Сообщения</h2></div><button id="comms-refresh" class="btn small ghost" type="button" aria-label="Обновить переписки">↻</button></div><div id="comms-chat-list" class="comms-chat-list"><div class="comms-loading">Загружаем…</div></div></section>'+
        '<section class="comms-directory comms-team-create"><span class="overline">РАБОЧЕЕ ПРОСТРАНСТВО</span><h3>Чат объекта</h3><p>Доступен при активном TEAM. Участники команды подключаются автоматически.</p><select id="comms-project" aria-label="Выбрать объект"><option value="">Загрузка объектов…</option></select><button id="comms-create-project-chat" class="btn small" type="button">Открыть чат объекта</button></section>'+
        '<section class="comms-community"><div class="comms-sidebar-head"><div><span class="overline">ПРОФ-СООБЩЕСТВО</span><h2>Мастера СНГ</h2></div></div><div id="comms-community-list"></div></section>'+
      '</aside><section class="comms-chat-panel" id="comms-active-panel"><div class="comms-empty"><span>✳</span><strong>Связь начинается здесь</strong><p>Найдите коллегу по публичному ID, выберите переписку или зайдите в сообщество.</p></div></section></div>');
    const chatList=document.querySelector('#comms-chat-list'),communityList=document.querySelector('#comms-community-list'),panel=document.querySelector('#comms-active-panel'),peopleRoot=document.querySelector('#comms-people');
    function kindLabel(kind){return ({direct:'Личный чат',quote:'Обсуждение сметы',workspace:'Чат объекта',community:'Сообщество',support:'Поддержка'})[kind]||'Переписка';}
    function renderChats(){
      chatList.innerHTML=chats.length?chats.map(item=>'<button type="button" class="comms-chat-row '+(item.id===activeId?'is-selected':'')+'" data-chat-open="'+esc(item.id)+'"><span class="comms-row-icon '+esc(item.kind)+'">'+icon(item.kind)+'</span><span class="comms-chat-row-copy"><strong>'+esc(item.title||kindLabel(item.kind))+'</strong><small>'+esc(kindLabel(item.kind))+(item.last_message?' · '+esc(item.last_message):'')+'</small></span>'+(Number(item.unread_count)>0?'<span class="comms-unread">'+esc(item.unread_count)+'</span>':'')+'</button>').join(''):'<div class="comms-list-empty">Здесь появятся личные чаты, сметы и объекты.</div>';
    }
    function renderCommunities(){
      communityList.innerHTML=communities.map(room=>'<div class="comms-community-row"><div><strong>'+esc(room.title)+'</strong><small>'+esc(room.members||0)+' участников</small></div><button class="btn small '+(room.joined?'ghost':'')+'" type="button" data-community-action="'+(room.joined?'open':'join')+'" data-community-id="'+esc(room.id)+'">'+(room.joined?'Открыть':'Войти')+'</button></div>').join('');
    }
    function renderPeople(){
      peopleRoot.innerHTML=people.length?people.map(person=>'<article class="comms-person"><span class="comms-person-avatar">'+esc((person.name||'?').trim().slice(0,1).toUpperCase())+'</span><div><strong>'+esc(person.name)+'</strong><small>'+esc(person.public_id)+(person.profession?' · '+esc(person.profession):'')+'</small></div><button class="btn small" type="button" data-person-open="'+esc(person.public_id)+'">Написать</button></article>').join(''):'';
    }
    function renderActive(){
      if(!activeConversation){panel.innerHTML='<div class="comms-empty"><span>✳</span><strong>Выберите переписку</strong><p>Сообщения останутся в приложении и будут привязаны к вашему аккаунту.</p></div>';return;}
      panel.innerHTML='<header class="comms-chat-head"><span class="comms-chat-avatar">'+icon(activeConversation.kind)+'</span><div class="comms-chat-head-copy"><h2>'+esc(activeConversation.title||kindLabel(activeConversation.kind))+'</h2><p>'+esc(kindLabel(activeConversation.kind))+(activeConversation.quote?' · версия '+esc(activeConversation.quote.published_version||1):'')+'</p></div></header>'+
        '<div id="comms-messages" class="comms-messages" role="log" aria-live="polite">'+messageMarkup(messages,user.id,'Напишите первое сообщение.')+'</div>'+
        composerChat(activeConversation.status==='closed'?'Переписка закрыта':'Напишите сообщение…');
      const root=document.querySelector('#comms-messages');if(root)root.scrollTop=root.scrollHeight;
      const form=document.querySelector('#comms-send-form');
      if(form)bindSend(form,async message=>{
        const result=await api('/conversations/'+encodeURIComponent(activeId)+'/messages',{method:'POST',body:JSON.stringify({message})});
        if(!active()||!activeId)return;
        if(result.messages)messages=result.messages;else messages.push({sender_id:user.id,sender_role:'user',sender_name:user.name,body:message,created_at:Date.now()/1000});
        renderActive();
        await refreshLists(false);
      },()=>active()&&!!activeId);
    }
    function composerChat(placeholder){return '<form class="comms-composer" id="comms-send-form"><textarea name="message" rows="1" maxlength="4000" required placeholder="'+esc(placeholder)+'" '+(activeConversation?.status==='closed'?'disabled':'')+'></textarea><button class="btn primary" type="submit" '+(activeConversation?.status==='closed'?'disabled':'')+'>Отправить <span aria-hidden="true">↗</span></button></form>';}
    function watchConversation(conversation) {
      if(conversation?.realtime_topic&&conversation.realtime_topic===watchedConversationTopic)return;
      activeOff?.();activeOff=null;watchedConversationTopic=conversation?.realtime_topic||'';
      if(!watchedConversationTopic)return;
      activeOff=subscribeTopic(watchedConversationTopic,async eventName=>{
        if(eventName!=='message_changed'||!active()||!activeId)return;
        const current=activeId;
        try{const update=await api('/conversations/'+encodeURIComponent(current)+'/messages?refresh='+Date.now());if(active()&&activeId===current){activeConversation=update.conversation;messages=update.messages||[];renderChats();renderActive();await refreshLists(false);lastMessagesRefresh=Date.now();}}catch{}
      });
    }
    async function openChat(id) {
      if(loading||!active())return;loading=true;activeId=id;renderChats();
      try{const result=await api('/conversations/'+encodeURIComponent(id)+'/messages?refresh='+Date.now());if(!active()||activeId!==id)return;activeConversation=result.conversation;messages=result.messages||[];renderChats();renderActive();watchConversation(activeConversation);lastMessagesRefresh=Date.now();}
      catch(error){if(active())panel.innerHTML='<div class="comms-error">'+esc(error.message)+'</div>';}
      finally{loading=false;}
    }
    async function refreshLists(openSelected=false,withMeta=false) {
      const chatPromise=api('/conversations?refresh='+Date.now());
      const metaPromise=withMeta?Promise.all([
        api('/community?refresh='+Date.now()),
        api('/projects?refresh='+Date.now()).catch(()=>({items:[]})),
        api('/workspace?refresh='+Date.now()).catch(()=>({workspace:null}))
      ]):Promise.resolve(null);
      const [chatData,meta]=await Promise.all([chatPromise,metaPromise]);
      if(!active())return;
      chats=chatData.items||[];
      if(meta){const [communityData,projectData,workspaceData]=meta;
        communities=communityData.items||[];
        projects=projectData.items||projectData.projects||[];
        workspaceId=workspaceData.workspace?.id||workspaceId;
      }
      if(workspaceId)try{sessionStorage.setItem('workspace_id',workspaceId)}catch{}
      renderChats();renderCommunities();
      const selector=document.querySelector('#comms-project');
      if(selector){const previous=selector.value;selector.innerHTML=projects.length?'<option value="">Выберите объект</option>'+projects.map(project=>'<option value="'+esc(project.id)+'">'+esc(project.name)+'</option>').join(''):'<option value="">Нет доступных объектов</option>';if(projects.some(project=>project.id===previous))selector.value=previous;}
      if(openSelected&&activeId&&chats.some(item=>item.id===activeId))await openChat(activeId);
      else if(activeId&&!chats.some(item=>item.id===activeId)){activeId=null;activeConversation=null;messages=[];renderActive();}
    }
    const searchInput=document.querySelector('#comms-search');
    document.querySelector('#comms-search-form').onsubmit=async event=>{
      event.preventDefault();const term=searchInput.value.trim();if(term.length<2){peopleRoot.innerHTML='<small class="comms-search-hint">Введите не менее двух символов.</small>';return}
      const button=event.currentTarget.querySelector('button');button.disabled=true;peopleRoot.innerHTML='<div class="comms-loading">Ищем…</div>';
      try{const result=await api('/people?q='+encodeURIComponent(term)+'&refresh='+Date.now());if(!active())return;people=result.items||[];renderPeople();if(!people.length)peopleRoot.innerHTML='<small class="comms-search-hint">Никого не нашли. Проверьте ID или имя.</small>';}
      catch(error){if(active())peopleRoot.innerHTML='<small class="comms-search-hint">'+esc(error.message)+'</small>';}
      finally{if(button.isConnected)button.disabled=false;}
    };
    document.querySelector('#comms-create-project-chat').onclick=async event=>{
      const button=event.currentTarget,projectId=document.querySelector('#comms-project').value;if(!projectId){notify?.('Сначала выберите объект.');return}if(button.disabled)return;button.disabled=true;
      try{const result=await api('/conversations',{method:'POST',body:JSON.stringify({kind:'workspace',object_id:projectId,workspace_id:workspaceId})});if(!active())return;await refreshLists(false,true);await openChat(result.conversation_id);notify?.('Чат объекта готов');}
      catch(error){if(active())notify?.(error.message);}
      finally{if(button.isConnected)button.disabled=false;}
    };
    chatList.onclick=event=>{const button=event.target.closest('[data-chat-open]');if(button)openChat(button.dataset.chatOpen);};
    peopleRoot.onclick=async event=>{
      const button=event.target.closest('[data-person-open]');if(!button||button.disabled)return;button.disabled=true;
      try{const result=await api('/conversations',{method:'POST',body:JSON.stringify({kind:'direct',target_public_id:button.dataset.personOpen})});if(!active())return;await refreshLists(false,true);await openChat(result.conversation_id);}
      catch(error){if(active())notify?.(error.message);}
      finally{if(button.isConnected)button.disabled=false;}
    };
    communityList.onclick=async event=>{
      const button=event.target.closest('[data-community-action]');if(!button||button.disabled)return;button.disabled=true;
      try{
        let id=button.dataset.communityId;
        if(button.dataset.communityAction==='join'){const result=await api('/community/'+encodeURIComponent(id)+'/join',{method:'POST',body:JSON.stringify({})});id=result.conversation_id;}
        await refreshLists(false,true);await openChat(id);
      }catch(error){if(active())notify?.(error.message);}
      finally{if(button.isConnected)button.disabled=false;}
    };
    document.querySelector('#comms-refresh').onclick=()=>refreshLists(true);
    realtime=await prepareRealtime(api,user);
    if(realtime?.inbox_topic)inboxOff=subscribeTopic(realtime.inbox_topic,eventName=>{
      if(eventName==='inbox_changed'&&active()){refreshLists(false).catch(()=>{});lastListRefresh=Date.now();}
    });
    await refreshLists(true,true);
    if(active())timer=setInterval(async()=>{
      if(!active()||loading)return;
      try{
        const now=Date.now(),current=activeId,live=Boolean(activeConversation?.realtime_topic&&window.SmetraRealtime?.isSubscribed(activeConversation.realtime_topic));
        if(now-lastListRefresh>=(realtime?.enabled?30000:10000)){await refreshLists(false);lastListRefresh=now;}
        if(current&&(!live||now-lastMessagesRefresh>30000)){const result=await api('/conversations/'+encodeURIComponent(current)+'/messages?refresh='+Date.now());if(active()&&activeId===current){activeConversation=result.conversation;messages=result.messages||[];renderActive();watchConversation(activeConversation);lastMessagesRefresh=now;}}
      }catch{}
    },5000);
  }
  return {support,messaging,leave:stop};
})();
