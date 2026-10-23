const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const settle=async()=>{for(let i=0;i<8;i++)await tick();};
function setup(){
 const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test/app',runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window,root=w.document.querySelector('#root');
 const notices=[];
 const db={conversations:[],rooms:[
  {id:'community_general',title:'Общий чат',category:'general',members:2,joined:false},
  {id:'community_electrical',title:'Электрика',category:'electrical',members:5,joined:false}
 ],tickets:[],messages:{},people:[{id:'u2',public_id:'SM-0123456789ABCDEF',name:'Прораб Тест',profession:'Прораб',company:'Бригада'}],next:1};
 const user={id:'u1',name:'Тестовый пользователь',public_id:'SM-ABCDEF0123456789'};
 const message=(sender_id,sender_role,body)=>({id:'m'+db.next++,conversation_id:'c1',sender_id,sender_role,sender_name:sender_role==='ai'?'Помощник Сметры':sender_id==='u1'?user.name:'Прораб Тест',body,created_at:Date.now()/1000,payload:{}});
 function ticket(id){
  return db.tickets.find(item=>item.id===id);
 }
 const api=async(path,options={})=>{
  const method=options.method||'GET',clean=path.split('?')[0],body=options.body?JSON.parse(options.body):{};
  if(clean==='/workspace')return {workspace:{id:'w1'}};
  if(clean==='/projects')return {items:[{id:'p1',name:'ЖК Октябрьский'}]};
  if(clean==='/people')return {items:db.people};
  if(clean==='/community')return {items:db.rooms};
  if(clean==='/conversations'&&method==='GET')return {items:db.conversations};
  if(clean==='/conversations'&&method==='POST'){
   const id='c'+db.next++,kind=body.kind||'direct';
   const conversation={id,kind,title:kind==='direct'?'Прораб Тест':kind==='workspace'?'ЖК Октябрьский':'Смета',status:'active',created_at:Date.now()/1000,updated_at:Date.now()/1000};
   db.conversations.unshift(conversation);db.messages[id]=[];
   return {conversation_id:id,created:true};
  }
  const chat=clean.match(/^\/conversations\/([^/]+)\/messages$/);
  if(chat){
   const id=decodeURIComponent(chat[1]),conversation=db.conversations.find(item=>item.id===id);
   if(!conversation)throw Error('Чат не найден');
   if(method==='GET')return {conversation,messages:db.messages[id]||[]};
   db.messages[id].push(message(user.id,'user',body.message));
   return {ok:true,messages:db.messages[id]};
  }
  const join=clean.match(/^\/community\/([^/]+)\/join$/);
  if(join&&method==='POST'){
   const room=db.rooms.find(item=>item.id===decodeURIComponent(join[1]));room.joined=true;
   let conversation=db.conversations.find(item=>item.id===room.id);
   if(!conversation){conversation={...room,kind:'community',status:'active'};db.conversations.unshift(conversation);db.messages[room.id]=[];}
   return {ok:true,conversation_id:room.id,messages:db.messages[room.id]};
  }
  if(clean==='/support'&&method==='GET')return {items:db.tickets.map(item=>({...item,last_message:(db.messages[item.conversation_id]||[]).at(-1)?.body||item.message}))};
  if(clean==='/support'&&method==='POST'){
   const id='t'+db.next++,conversation_id='s'+id;
   const created={id,subject:body.subject||'Вопрос в поддержку',status:'open',priority:'normal',needs_human:false,ai_state:'active',conversation_id,user_id:user.id,created_at:Date.now()/1000,updated_at:Date.now()/1000};
   db.tickets.unshift(created);db.messages[conversation_id]=[message(user.id,'user',body.message),message(null,'ai','Подскажите, пожалуйста, в каком разделе вы увидели ошибку?')];
   db.messages[conversation_id].forEach(item=>item.conversation_id=conversation_id);
   return {ticket:created,messages:db.messages[conversation_id]};
  }
  const st=clean.match(/^\/support\/([^/]+)\/messages$/);
  if(st){
   const id=decodeURIComponent(st[1]),item=ticket(id);if(!item)throw Error('Обращение не найдено');
   if(method==='GET')return {ticket:item,messages:db.messages[item.conversation_id]};
   db.messages[item.conversation_id].push(message(user.id,'user',body.message));
   if(!item.needs_human)db.messages[item.conversation_id].push(message(null,'ai','Спасибо, давайте проверим это вместе.'));
   return {ticket:item,messages:db.messages[item.conversation_id]};
  }
  const escalate=clean.match(/^\/support\/([^/]+)\/escalate$/);
  if(escalate&&method==='POST'){
   const item=ticket(decodeURIComponent(escalate[1]));item.needs_human=true;item.ai_state='human';
   db.messages[item.conversation_id].push(message(null,'system','Сотрудник подключён к обращению.'));
   return {ticket:item,messages:db.messages[item.conversation_id]};
  }
  throw Error('Unexpected mocked API route: '+method+' '+clean);
 };
 w.notify=msg=>notices.push(msg);
 const ctx={api,view:html=>root.innerHTML=html,header:(title,subtitle)=>'<header><h1>'+title+'</h1><p>'+subtitle+'</p></header>',escapeHtml:value=>String(value??''),notify:w.notify,user,active:()=>true,date:()=>''};
 w.eval(fs.readFileSync('apps/web/communications-ui.js','utf8'));
 return {dom,w,root,ctx,db,notices};
}
(async()=>{
 const x=setup();
 try{
  await x.w.SmetraCommunications.messaging(x.ctx);
  assert.ok(x.root.querySelector('.comms-layout'),'Messaging view renders');
  x.root.querySelector('#comms-search').value='SM-0123456789ABCDEF';
  x.root.querySelector('#comms-search-form').dispatchEvent(new x.w.Event('submit',{bubbles:true,cancelable:true}));
  await settle();
  assert.ok(x.root.querySelector('[data-person-open="SM-0123456789ABCDEF"]'),'User can search by public ID');
  x.root.querySelector('[data-person-open]').click();await settle();
  assert.ok(x.root.querySelector('#comms-send-form'),'Opening a direct chat shows a composer');
  x.root.querySelector('#comms-send-form textarea').value='Добрый день, нужен расчёт.';
  x.root.querySelector('#comms-send-form').dispatchEvent(new x.w.Event('submit',{bubbles:true,cancelable:true}));
  await settle();
  assert.ok(x.root.querySelector('.comms-message.is-own'),'Sent messages appear in the active chat');
  x.w.SmetraCommunications.leave();
  await x.w.SmetraCommunications.support(x.ctx);
  x.root.querySelector('#support-new').click();
  x.root.querySelector('#support-create-form input[name="subject"]').value='Не открывается смета';
  x.root.querySelector('#support-create-form textarea[name="message"]').value='После клика открывается пустая страница.';
  x.root.querySelector('#support-create-form').dispatchEvent(new x.w.Event('submit',{bubbles:true,cancelable:true}));
  await settle();
  assert.ok(x.root.querySelector('.comms-chat-head h2').textContent.includes('Не открывается смета'),'New support ticket opens its chat');
  assert.ok([...x.root.querySelectorAll('.comms-message')].some(node=>node.textContent.includes('Помощник Сметры')),'AI replies inside support chat');
  x.root.querySelector('#support-reply-form textarea').value='Проблема повторяется после обновления.';
  x.root.querySelector('#support-reply-form').dispatchEvent(new x.w.Event('submit',{bubbles:true,cancelable:true}));
  await settle();
  assert.ok(x.db.messages[x.db.tickets[0].conversation_id].some(m=>m.body.includes('Проблема повторяется')),'Ticket reply is saved to its conversation');
  x.root.querySelector('#support-escalate').click();await settle();
  assert.ok(x.root.querySelector('#support-escalate').disabled,'Human escalation changes the UI state');
  console.log('PASS: public-ID search, direct chat, send flow, support tickets, AI answer and human escalation');
 }finally{x.w.SmetraCommunications.leave();x.dom.window.close();}
})().catch(error=>{console.error(error);process.exit(1)});
