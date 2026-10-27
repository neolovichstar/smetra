(() => {
'use strict';
const $=(s,r=document)=>r.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const publicId=/^SM-[A-F0-9]{32}$/i;
const profilePath=/^\/u\/(?:[a-z][a-z0-9_]{2,31}|SM-[a-f0-9]{32})$/i;
const safeAvatar=url=>/^\/api\/public\/avatars\/SM-[A-F0-9]{32}\/[a-f0-9]{64}\.webp$/i.test(url)||/^https:\/\/avatars\.yandex\.net\/get-yapic\/[A-Za-z0-9_/-]{1,150}\/islands-200$/.test(url);
const avatar=p=>'<span class="public-avatar" aria-hidden="true"><span class="user-avatar-fallback">'+esc(String(p.name||p.display_name||'С').trim().slice(0,1).toLocaleUpperCase('ru'))+'</span>'+(safeAvatar(p.avatar_url||'')?'<img class="user-avatar-image" src="'+esc(p.avatar_url)+'" alt="" decoding="async" referrerpolicy="no-referrer">':'')+'</span>';
let resuming=false;
const dialogs=new Set();
async function request(path,options={}){
 const response=await fetch('/api'+path,{credentials:'same-origin',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
 let data={};try{data=await response.json()}catch{}
 if(!response.ok)throw Error(data.error||'Не удалось загрузить профиль');
 return data;
}
function status(node,message,error=false){if(!node)return;node.textContent=message;node.classList.toggle('is-error',error)}
function makeDialog(title,markup){
 const dialog=document.createElement('dialog');dialog.className='profile-dialog';
 const titleId='profile-dialog-'+Math.random().toString(36).slice(2);
 dialog.setAttribute('aria-labelledby',titleId);dialog.innerHTML='<h2 id="'+titleId+'">'+esc(title)+'</h2>'+markup;
 document.body.append(dialog);dialogs.add(dialog);
 const dispose=()=>dialog.close();
 const onClose=()=>{dialogs.delete(dialog);document.removeEventListener('smetra:before-view',dispose);dialog.remove()};
 dialog.addEventListener('close',onClose,{once:true});document.addEventListener('smetra:before-view',dispose);
 dialog.showModal();
 return dialog;
}
function card(p,{preview=false}={}){
 const name=p.name||p.display_name||'Ваше имя',handle=p.handle?'@'+p.handle:p.public_id;
 const href='/app?person='+encodeURIComponent(p.public_id)+'&intent=';
 return '<article class="public-card"><div class="public-card-top"><div class="public-identity">'+avatar({...p,name})+'<div class="public-identity-copy">'+(preview?'<h3 class="public-preview-name">':'<h1>')+esc(name)+(preview?'</h3>':'</h1>')+'<p class="public-handle">'+esc(handle)+'</p></div></div>'
 +(p.headline?'<p class="public-headline">'+esc(p.headline)+'</p>':'')+(p.city?'<p class="public-city">'+esc(p.city)+'</p>':'')+'</div>'
 +(p.bio?'<div class="public-about"><h2>О себе</h2><p>'+esc(p.bio)+'</p></div>':'')
 +(preview?'':'<div class="public-card-actions"><a class="public-button" '+(p.allow_messages?'href="'+href+'message#chats"':'aria-disabled="true"')+'>'+(p.allow_messages?'Написать':'Сообщения закрыты')+'</a><a class="public-button public-button-secondary" '+(p.allow_quotes?'href="'+href+'quote#chats"':'aria-disabled="true"')+'>'+(p.allow_quotes?'Отправить смету':'Приём смет закрыт')+'</a><button class="public-button public-button-secondary public-copy" id="public-copy-link" type="button">Ссылка</button></div>')+'</article>';
}
async function copy(value,node){
 try{await navigator.clipboard.writeText(value);if(node){const old=node.textContent;node.textContent='Скопировано';setTimeout(()=>{if(node.isConnected)node.textContent=old},1800)}}
 catch{const dialog=makeDialog('Ссылка на профиль','<p>Скопируйте адрес:</p><label class="public-field"><span>Адрес</span><input readonly value="'+esc(value)+'"></label><div class="profile-dialog-actions"><button type="button" class="btn" data-close>Закрыть</button></div>');$('input',dialog).select();$('[data-close]',dialog).onclick=()=>dialog.close()}
}
function personCard(p){
 return '<a class="public-person" href="'+esc(profilePath.test(p.url||'')?p.url:'/people')+'">'+avatar(p)+'<div><h3>'+esc(p.name)+'</h3><p>'+esc(p.headline||p.city||'Профиль в Сметре')+'</p></div><small>'+esc(p.handle?'@'+p.handle:p.public_id)+'</small><span class="public-person-bottom"><span>'+esc(p.city||'Открыть профиль')+'</span><span aria-hidden="true">↗</span></span></a>';
}
async function directory(root){
 const q=new URLSearchParams(location.search).get('q')||'';
 root.innerHTML='<div class="public-intro"><p class="public-eyebrow">Люди в Сметре</p><h1>Знакомьтесь.<br>Обсуждайте. Работайте.</h1><p>Найдите специалиста или клиента, напишите ему и отправьте смету — всё через профиль.</p></div><form class="public-search" id="public-search"><label class="sr-only" for="public-search-q">Имя, @ник или публичный ID</label><input type="search" id="public-search-q" maxlength="80" placeholder="Имя, @ник или ID" autocomplete="off" value="'+esc(q)+'"><button type="submit" class="public-button">Найти</button></form><div id="public-results" aria-live="polite"><p class="public-loading">Ищем профили…</p></div>';
 const results=$('#public-results',root);let revision=0;
 async function load(value){
  const attempt=++revision;results.setAttribute('aria-busy','true');
  try{const data=await request('/public/profiles?q='+encodeURIComponent(value));if(attempt!==revision||!root.isConnected)return;
   results.innerHTML='<div class="public-result-heading"><h2>'+esc(value?'Результаты поиска':'Открытые профили')+'</h2><span>'+data.profiles.length+'</span></div>'+(data.profiles.length?'<div class="public-grid">'+data.profiles.map(personCard).join('')+'</div>':'<div class="public-empty"><h2>'+(value?'Никого не нашли':'Здесь будут открытые профили')+'</h2><p>'+(value?'Попробуйте другое имя, короткий адрес или публичный ID.':'Создайте свою страницу, чтобы вас могли найти клиенты и коллеги.')+'</p><a class="public-button public-button-secondary" href="/app#profile">Настроить свой профиль</a></div>');
  }catch(error){if(attempt===revision)results.innerHTML='<div class="public-empty"><h2>Не удалось выполнить поиск</h2><p>'+esc(error.message)+'</p></div>'}
  finally{if(attempt===revision)results.setAttribute('aria-busy','false')}
 }
 $('#public-search',root).onsubmit=event=>{event.preventDefault();const value=$('#public-search-q',root).value.trim();history.replaceState({},'','/people'+(value?'?q='+encodeURIComponent(value):''));void load(value)};
 await load(q);
}
async function publicPage(){
 const root=$('#public-profile-page');if(!root)return;
 document.addEventListener('error',event=>{if(event.target?.matches?.('.public-avatar img'))event.target.remove()},true);
 if(location.pathname==='/people'){await directory(root);return}
 const slug=decodeURIComponent(location.pathname.split('/').pop()||'');
 try{const {profile:p}=await request('/public/profiles/'+encodeURIComponent(slug));document.title=p.name+' · Сметра';
  root.innerHTML='<div class="public-profile-wrap"><a class="public-back" href="/people">← Все профили</a>'+card(p)+'<p class="public-profile-caption">Напишите человеку или отправьте смету через свой аккаунт Сметры. Почта и личные данные в профиле не раскрываются.</p></div>';
  $('#public-copy-link',root).onclick=event=>copy(location.origin+p.url,event.currentTarget);
 }catch(error){root.innerHTML='<div class="public-profile-wrap"><a class="public-back" href="/people">← Все профили</a><div class="public-empty"><h2>Профиль недоступен</h2><p>'+esc(error.message)+'</p><a class="public-button public-button-secondary" href="/people">Найти человека</a></div></div>'}
}
async function mountSettings({host,user,api,active=()=>true}){
 if(!host)return;
 const alive=()=>active()&&host.isConnected;
 host.innerHTML='<p class="muted">Загружаем публичный профиль…</p>';
 let saved;
 try{saved=(await api('/profile/public')).profile;if(!alive())return}
 catch(error){if(alive()){host.innerHTML='<p class="public-status is-error">'+esc(error.message)+'</p><button type="button" class="btn" data-retry>Повторить</button>';$('[data-retry]',host).onclick=()=>mountSettings({host,user,api,active})}return}
 host.innerHTML='<div class="public-settings"><form class="public-form hub-card" id="public-profile-form"><label class="public-toggle"><input type="checkbox" name="published" '+(saved.published?'checked':'')+'><span><strong>Показывать мой профиль всем</strong><small>Профиль появится в поиске по имени и адресу. Доступны только имя, фото и поля ниже. Почта, сметы и данные компании остаются закрыты.</small></span></label><div class="public-form-grid">'
 +'<label class="public-field"><span>Имя в публичном профиле</span><input name="display_name" maxlength="80" autocomplete="name" required value="'+esc(saved.display_name)+'"></label>'
 +'<label class="public-field"><span>Короткий адрес</span><input name="handle" maxlength="32" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="ivan_stroitel" value="'+esc(saved.handle)+'"><small>От 3 до 32 латинских букв, цифр и _. Начните с буквы.</small></label>'
 +'<label class="public-field"><span>Специализация</span><input name="headline" maxlength="120" placeholder="Например, отделка квартир" value="'+esc(saved.headline)+'"></label>'
 +'<label class="public-field"><span>Город</span><input name="city" maxlength="80" autocomplete="address-level2" placeholder="Например, Москва" value="'+esc(saved.city)+'"></label>'
 +'<label class="public-field public-full"><span>О себе</span><textarea name="bio" maxlength="800" rows="4" placeholder="Расскажите о своей работе и опыте">'+esc(saved.bio)+'</textarea><small>До 800 символов. Публикуйте только то, чем готовы поделиться.</small></label></div>'
 +'<div class="public-permissions"><label class="public-toggle"><input name="allow_messages" type="checkbox" '+(saved.allow_messages?'checked':'')+'><span><strong>Принимать новые сообщения</strong><small>Пользователи Сметры смогут начать личную переписку.</small></span></label><label class="public-toggle"><input name="allow_quotes" type="checkbox" '+(saved.allow_quotes?'checked':'')+'><span><strong>Принимать сметы</strong><small>Опубликованные предложения придут в отдельный чат по смете.</small></span></label></div>'
 +'<div class="public-save-row"><button class="btn primary" id="public-save" type="submit">Сохранить профиль</button><span class="public-status" role="status" id="public-save-status"></span></div></form>'
 +'<section class="hub-card"><h2>Ссылка на ваш профиль</h2><p id="public-visibility-note"></p><div class="public-link-row"><code id="public-own-url"></code><button type="button" class="btn small" id="public-own-copy">Скопировать</button><a class="btn small" id="public-own-open" target="_blank" rel="noopener">Открыть ↗</a></div><a class="public-back" href="/people" target="_blank" rel="noopener">Найти людей в Сметре ↗</a></section>'
 +'<section><p class="public-preview-label">Так вас увидят другие</p><div id="public-profile-preview"></div></section></div>';
 const form=$('#public-profile-form',host),feedback=$('#public-save-status',host),save=$('#public-save',host);
 function values(){const fields=new FormData(form);return {...Object.fromEntries(['display_name','handle','headline','city','bio'].map(k=>[k,String(fields.get(k)||'').trim()])),...Object.fromEntries(['published','allow_messages','allow_quotes'].map(k=>[k,fields.has(k)])),revision:saved.revision}}
 function preview(){const v=values();$('#public-profile-preview',host).innerHTML=card({...v,avatar_url:user.avatar_url,public_id:saved.public_id},{preview:true});save.textContent=v.published&&!saved.published?'Опубликовать профиль':'Сохранить профиль'}
 function updateLink(){const link=location.origin+saved.url;$('#public-own-url',host).textContent=link;$('#public-own-open',host).href=saved.url;$('#public-own-open',host).setAttribute('aria-disabled',String(!saved.published));$('#public-own-copy',host).disabled=!saved.published;$('#public-visibility-note',host).textContent=saved.published?'Профиль опубликован. Этой ссылкой можно поделиться.':'Сейчас профиль скрыт. Включите видимость и сохраните изменения.'}
 form.addEventListener('input',()=>{status(feedback,'');preview()});
 form.onsubmit=async event=>{event.preventDefault();if(save.disabled)return;save.disabled=true;status(feedback,'Сохраняем…');try{const result=await api('/profile/public',{method:'PATCH',body:JSON.stringify(values())});if(!alive())return;saved=result.profile;form.elements.handle.value=saved.handle;status(feedback,saved.published?'Профиль опубликован':'Профиль сохранён и скрыт');updateLink();preview()}catch(error){if(alive())status(feedback,error.message,true)}finally{if(alive())save.disabled=false}};
 $('#public-own-copy',host).onclick=event=>copy(location.origin+saved.url,event.currentTarget);preview();updateLink();
}
function mountAvatar({host,user,api,active=()=>true,onChange=()=>{},notify=()=>{}}){
 if(!host)return;
 host.innerHTML='<input class="avatar-file-input" type="file" accept="image/jpeg,image/png,image/webp" aria-label="Выбрать фото профиля"><button class="btn" type="button" data-avatar-upload>Загрузить фото</button><button class="btn small" type="button" data-avatar-remove>Удалить фото</button><span class="avatar-upload-status" role="status"></span>';
 const input=$('input',host),upload=$('[data-avatar-upload]',host),remove=$('[data-avatar-remove]',host),feedback=$('.avatar-upload-status',host);
 const alive=()=>active()&&host.isConnected;let busy=false;
 const buttons=on=>{busy=on;upload.disabled=on;remove.disabled=on||!user.avatar_url};
 const change=url=>{user.avatar_url=url;onChange(url);remove.disabled=!url;const preview=$('#public-profile-preview .public-avatar');if(preview)preview.outerHTML=avatar({...user,name:$('#public-profile-form [name=display_name]')?.value||user.name});};
 remove.disabled=!user.avatar_url;upload.onclick=()=>input.click();
 remove.onclick=async()=>{if(busy||!alive())return;buttons(true);status(feedback,'Удаляем…');try{const d=await api('/profile/avatar',{method:'DELETE'});if(alive()){change(d.avatar_url);status(feedback,'Фото удалено')}}catch(error){if(alive())status(feedback,error.message,true)}finally{if(alive())buttons(false)}};
 input.onchange=async()=>{
  const file=input.files?.[0];input.value='';if(!file||busy||!alive())return;
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>12*1024*1024){status(feedback,'Выберите JPEG, PNG или WebP до 12 МБ',true);return}
  buttons(true);status(feedback,'Готовим фото…');let bitmap;
  try{
   bitmap=await createImageBitmap(file,{imageOrientation:'from-image'});
   if(!alive()){bitmap.close();return}
   if(Math.min(bitmap.width,bitmap.height)<16||bitmap.width*bitmap.height>40_000_000)throw Error('Выберите фото размером от 16 пикселей и до 40 мегапикселей');
   const dialog=makeDialog('Фото профиля','<p>Настройте масштаб. Это фото будет видно в переписках и в опубликованном профиле.</p><canvas width="384" height="384" aria-label="Предпросмотр фото"></canvas><label class="profile-crop-zoom">Масштаб<input type="range" min="1" max="2.5" step="0.01" value="1"></label><div class="profile-dialog-error" role="status"></div><div class="profile-dialog-actions"><button class="btn" type="button" data-cancel>Отмена</button><button class="btn primary" type="button" data-save>Сохранить фото</button></div>');
   const canvas=$('canvas',dialog),ctx=canvas.getContext('2d'),zoom=$('input',dialog),save=$('[data-save]',dialog),cancel=$('[data-cancel]',dialog);dialog.addEventListener('cancel',event=>{if(save.disabled)event.preventDefault()});
   const draw=()=>{const edge=Math.min(bitmap.width,bitmap.height)/Number(zoom.value);ctx.clearRect(0,0,384,384);ctx.drawImage(bitmap,(bitmap.width-edge)/2,(bitmap.height-edge)/2,edge,edge,0,0,384,384)};draw();zoom.oninput=draw;
   cancel.onclick=()=>dialog.close();dialog.addEventListener('close',()=>{bitmap.close();if(alive()){buttons(false);if(feedback.textContent==='Готовим фото…')status(feedback,'')}},{once:true});
   save.onclick=async()=>{if(save.disabled||!alive())return;save.disabled=true;cancel.disabled=true;zoom.disabled=true;status($('.profile-dialog-error',dialog),'Сохраняем…');try{const content_base64=canvas.toDataURL('image/webp',.88).split(',')[1];const d=await api('/profile/avatar',{method:'POST',body:JSON.stringify({content_base64})});if(alive()){change(d.avatar_url);status(feedback,'Фото сохранено');notify('Фото профиля обновлено')}dialog.close()}catch(error){if(alive())status($('.profile-dialog-error',dialog),error.message,true)}finally{if(dialog.isConnected){save.disabled=false;cancel.disabled=false;zoom.disabled=false}}};
  }catch(error){bitmap?.close?.();if(alive()){buttons(false);status(feedback,error.message||'Не удалось открыть фото',true)}}
 };
}
function captureIntent(){
 try{const params=new URLSearchParams(location.search),person=params.get('person'),intent=params.get('intent');if(publicId.test(person||'')&&['message','quote'].includes(intent)){sessionStorage.setItem('smetra.profileIntent',JSON.stringify({person,intent}));params.delete('person');params.delete('intent');history.replaceState({},'',location.pathname+(params.size?'?'+params:'')+location.hash)}}catch{}
}
async function resume({api,active=()=>true,notify=()=>{},user}){
 if(resuming||!active())return;
 let pending;try{pending=JSON.parse(sessionStorage.getItem('smetra.profileIntent')||'null')}catch{}
 if(!pending||!publicId.test(pending.person)||!['message','quote'].includes(pending.intent))return;
 sessionStorage.removeItem('smetra.profileIntent');resuming=true;
 try{
  if(user&&'SM-'+user.id.replaceAll('-','').toUpperCase()===pending.person.toUpperCase()){notify('Это ваш профиль. Его можно изменить в настройках.');return}
  const {profile:p}=await api('/public/profiles/'+encodeURIComponent(pending.person));if(!active())return;
  if(pending.intent==='message'){
   if(!p.allow_messages)throw Error('Пользователь отключил новые сообщения');
   const result=await api('/profile/chats',{method:'POST',body:JSON.stringify({public_id:p.public_id})});
   if(active())await window.SmetraCommunication?.showChat(result.chat.id);
   return;
  }
  if(!p.allow_quotes)throw Error('Пользователь отключил получение смет');
  const data=await api('/profile/shareable-quotes');if(!active())return;
  const quotes=data.quotes||[];
  const dialog=makeDialog('Отправить смету','<p>Получатель: '+esc(p.name)+'. Будет отправлена клиентская ссылка на опубликованную смету.</p>'+(quotes.length?'<label class="public-field"><span>Выберите смету</span><select id="profile-quote-select">'+quotes.map(q=>'<option value="'+esc(q.id)+'">'+esc(q.title)+' · версия '+q.published_version+'</option>').join('')+'</select></label>':'<p>Пока нет доступных смет. Опубликуйте смету для согласования в разделе «Сметы», затем вернитесь к профилю.</p><a class="btn" href="/app#quotes" data-quotes>Перейти к сметам</a>')+'<div class="profile-dialog-error" role="status"></div><div class="profile-dialog-actions"><button type="button" class="btn" data-cancel>Отмена</button>'+(quotes.length?'<button type="button" class="btn primary" data-send>Отправить смету</button>':'')+'</div>');
  $('[data-cancel]',dialog).onclick=()=>dialog.close();$('[data-quotes]',dialog)?.addEventListener('click',()=>dialog.close());
  const send=$('[data-send]',dialog);if(send)send.onclick=async()=>{if(send.disabled||!active())return;const selected=quotes.find(q=>q.id===$('#profile-quote-select',dialog).value);if(!selected)return;send.disabled=true;try{const result=await api('/profile/quote-chats',{method:'POST',body:JSON.stringify({quote_id:selected.id,public_id:p.public_id,version:selected.published_version})});dialog.close();if(active()){await window.SmetraCommunication?.showChat(result.chat.id);notify('Смета отправлена в чат')}}catch(error){if(active())status($('.profile-dialog-error',dialog),error.message,true)}finally{if(send.isConnected)send.disabled=false}};
 }catch(error){if(active())notify(error.message)}finally{resuming=false}
}
window.SmetraPublicProfile={mountSettings,mountAvatar,captureIntent,resume,reset:()=>{for(const dialog of dialogs)dialog.close();resuming=false}};
if($('#public-profile-page'))void publicPage();
})();
