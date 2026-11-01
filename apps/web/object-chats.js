/* Messages are rendered as text; workspace/session changes cancel outstanding work. */
window.SmetraObjectChats=(()=>{
 let close=()=>{};
 function stop(){close();close=()=>{}}
 async function render(active){
  stop();const owner=user,revision=typeof authRevision==='number'?authRevision:0,e=escapeHtml;
  const alive=()=>active()&&user===owner&&(typeof authRevision!=='number'||authRevision===revision);
  const space=await api('/workspace');if(!alive())return;
  if(!space.entitlements?.features?.object_chats){
   view('<section class="panel"><h1>Чаты объектов</h1><p>Рабочая переписка команды доступна в TEAM. Владелец и четыре сотрудника общаются рядом со сметами и замерами.</p><a class="btn primary" href="#billing">Посмотреть тарифы</a></section>');return;
  }
  const [threads,objects]=await Promise.all([api('/object-chats'),api('/construction/objects')]);if(!alive())return;
  const back=(window.SmetraIcons?window.SmetraIcons.svg('arrow-left',18):'←');
  view('<section class="object-chat-page"><div class="section-top"><div><span class="overline">КОМАНДА</span><h1>Чаты объектов</h1></div><button class="btn small" id="chat-refresh">Обновить</button></div>'
   +'<div class="object-chat-layout" id="object-chat-layout"><aside class="object-chat-list" aria-label="Чаты"><div class="object-chat-picker"><label for="chat-object">Открыть чат объекта</label><select id="chat-object"><option value="">Выберите объект</option>'+objects.items.map(o=>'<option value="'+e(o.id)+'">'+e(o.name)+'</option>').join('')+'</select></div>'
   +'<div id="chat-threads" class="object-chat-threads">'+(threads.items.length?threads.items.map(t=>'<button type="button" class="object-chat-thread" data-thread="'+e(t.id)+'"><span class="object-chat-avatar" aria-hidden="true">'+e((t.object_name||t.title||'О').trim().charAt(0).toUpperCase())+'</span><span class="object-chat-thread-name">'+e(t.object_name||t.title)+'</span></button>').join(''):'<p class="object-chat-empty">Чатов пока нет. Выберите объект выше — переписка появится здесь.</p>')+'</div></aside>'
   +'<section class="object-chat-room" aria-labelledby="chat-room-title"><header class="object-chat-head"><button type="button" class="icon-button object-chat-back" id="chat-back" aria-label="К списку чатов">'+back+'</button><div><h2 id="chat-room-title">Рабочая переписка</h2><p id="chat-connection" class="object-chat-status" role="status">Выберите объект слева.</p></div></header>'
   +'<div id="object-messages" class="object-chat-messages" role="log" aria-live="polite"></div>'
   +'<form id="object-message-form" class="object-chat-composer" hidden><label class="sr-only" for="object-message">Сообщение команде</label><textarea id="object-message" rows="1" maxlength="4000" required placeholder="Написать команде…"></textarea><button class="btn primary object-chat-send" type="submit" aria-label="Отправить">'+(window.SmetraIcons?window.SmetraIcons.svg('arrow-up',18):'↑')+'</button><p id="object-chat-error" class="object-chat-error" role="alert"></p></form></section></div></section>');
  const layout=document.querySelector('#object-chat-layout');
  document.querySelector('#chat-back').onclick=()=>layout.classList.remove('is-room');
  let disposed=false,socket,timer,heartbeat,selection=0,thread=null,sequence=0,loading=false,pendingKey=null,pendingBody=null;
  const valid=()=>!disposed&&alive()&&document.querySelector('#object-messages');
  const disconnect=()=>{clearTimeout(timer);clearInterval(heartbeat);if(socket){socket.onclose=null;socket.close();socket=null}};
  close=()=>{disposed=true;disconnect()};
  const error=message=>{if(valid())document.querySelector('#object-chat-error').textContent=message};
  const append=items=>{
   const root=document.querySelector('#object-messages');
   for(const message of items){if(message.sequence<=sequence)continue;const article=document.createElement('article');article.className='object-chat-message'+(message.sender_id===owner?.id?' is-own':'');
    const author=document.createElement('strong');author.textContent=message.sender_name||'Участник';
    const text=document.createElement('p');text.textContent=message.body;
    const time=document.createElement('small');const at=new Date(message.created_at*1000);time.textContent=at.toDateString()===new Date().toDateString()?at.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'}):at.toLocaleString('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
    article.append(author,text,time);root.append(article);sequence=message.sequence;
   }
   // Keep the live DOM bounded; older messages remain in PostgreSQL.
   while(root.children.length>200)root.firstElementChild.remove();root.scrollTop=root.scrollHeight;
  };
  async function refresh(){
   if(!valid()||!thread||loading)return;loading=true;const mine=selection,current=thread;
   try{let more=true;for(let i=0;i<10&&more;i++){
    const result=await api('/object-chats/'+encodeURIComponent(current)+'/messages?after='+sequence);
    if(!valid()||mine!==selection)return;append(result.items);more=result.items.length===100&&sequence<result.latest_sequence;
   }}catch(err){if(valid()&&mine===selection)error(err.message)}
   finally{if(mine===selection)loading=false}
  }
  async function connect(mine){
   disconnect();if(!valid()||mine!==selection)return;
   try{
    const ticket=await api('/object-chats/'+encodeURIComponent(thread)+'/realtime');if(!valid()||mine!==selection)return;
    if(!ticket.configured){document.querySelector('#chat-connection').textContent='История сохранена. Для новых сообщений нажмите «Обновить».';return}
    const endpoint=new URL(ticket.url);endpoint.protocol='wss:';endpoint.pathname='/realtime/v1/websocket';endpoint.search=new URLSearchParams({apikey:ticket.api_key,vsn:'1.0.0'}).toString();
    socket=new WebSocket(endpoint.href);let ref=0;
    const topic='realtime:'+ticket.topic;
    const send=(event,payload,target=topic)=>{if(socket?.readyState===WebSocket.OPEN)socket.send(JSON.stringify({topic:target,event,payload,ref:String(++ref)}))};
    socket.onopen=()=>{send('phx_join',{config:{broadcast:{self:false,ack:false},presence:{enabled:false},private:true},access_token:ticket.access_token});heartbeat=setInterval(()=>send('heartbeat',{},'phoenix'),25000)};
    socket.onmessage=event=>{if(!valid()||mine!==selection)return;try{const value=JSON.parse(event.data);
     if(value.event==='phx_reply'&&value.payload?.status==='ok'){document.querySelector('#chat-connection').textContent='Изменения поступают в реальном времени';refresh()}
     if(value.event==='broadcast'&&value.payload?.event==='changed')refresh();
    }catch{}};
    socket.onclose=()=>{clearInterval(heartbeat);if(valid()&&mine===selection){document.querySelector('#chat-connection').textContent='Восстанавливаем соединение…';timer=setTimeout(()=>connect(mine),3000)}};
    timer=setTimeout(()=>connect(mine),Math.max(1000,(ticket.expires_at-Date.now()/1000-15)*1000));
   }catch(err){if(valid()&&mine===selection){document.querySelector('#chat-connection').textContent='Соединение недоступно. Историю можно обновить вручную.'}}
  }
  async function open(id,title,show=true){
   ++selection;disconnect();thread=id;sequence=0;loading=false;pendingKey=null;pendingBody=null;
   document.querySelector('#object-messages').replaceChildren();document.querySelector('#chat-room-title').textContent=title||'Объект';
   document.querySelectorAll('[data-thread]').forEach(button=>button.setAttribute('aria-current',String(button.dataset.thread===id)));if(show)layout.classList.add('is-room');
   document.querySelector('#object-message-form').hidden=false;document.querySelector('#object-message').value='';error('');
   await refresh();if(valid())connect(selection);
  }
  document.querySelectorAll('[data-thread]').forEach(button=>button.onclick=()=>open(button.dataset.thread,button.querySelector('.object-chat-thread-name').textContent));
  document.querySelector('#chat-object').onchange=async event=>{
   if(!event.target.value)return;const selected=event.target.value,title=event.target.selectedOptions[0].textContent;
   try{const result=await api('/object-chats',{method:'POST',body:JSON.stringify({object_id:selected})});if(valid())await open(result.thread.id,title)}
   catch(err){if(valid())document.querySelector('#chat-connection').textContent=err.message}
  };
  document.querySelector('#chat-refresh').onclick=refresh;
  const input=document.querySelector('#object-message');
  input.addEventListener('input',()=>{input.style.setProperty('height','auto');input.style.setProperty('height',Math.min(input.scrollHeight,140)+'px')});
  input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!matchMedia('(pointer:coarse)').matches){event.preventDefault();document.querySelector('#object-message-form').requestSubmit()}});
  document.querySelector('#object-message-form').onsubmit=async event=>{
   event.preventDefault();if(!valid()||!thread)return;const form=event.currentTarget,button=form.querySelector('button'),input=document.querySelector('#object-message'),body=input.value.trim();
   if(!body||button.disabled)return;button.disabled=true;const mine=selection,current=thread;
   if(pendingBody!==body){pendingKey=crypto.randomUUID();pendingBody=body}
   try{await api('/object-chats/'+encodeURIComponent(current)+'/messages',{method:'POST',headers:{'Idempotency-Key':pendingKey},body:JSON.stringify({body})});
    if(!valid()||mine!==selection)return;input.value='';pendingKey=null;pendingBody=null;error('');await refresh();
   }catch(err){if(valid()&&mine===selection)error(err.message)}
   finally{if(button.isConnected)button.disabled=false}
  };
  if(threads.items.length)await open(threads.items[0].id,threads.items[0].object_name||threads.items[0].title,false);
 }
 return {render,stop};
})();
