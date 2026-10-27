/* One email method at a time; bounded OTP entry and stale-response protection. */
'use strict';
(function(){
 const flow=document.querySelector('#email-code-flow');if(!flow)return;
 const auth=document.querySelector('#auth'),startForm=document.querySelector('#email-code-start'),
 confirmForm=document.querySelector('#email-code-confirm'),err=document.querySelector('#email-code-error'),
 email=document.querySelector('#email-code-address'),name=document.querySelector('#email-code-name'),
 nameField=document.querySelector('#email-code-name-field'),cells=[...document.querySelectorAll('.email-code-cells input')],
 send=document.querySelector('#email-code-start-button'),confirm=document.querySelector('#email-code-confirm-button'),
 resend=document.querySelector('#email-code-resend'),timer=document.querySelector('#email-code-countdown'),
 consent=document.querySelector('#legal-consent');
 const sendLabel=send.innerHTML,confirmLabel=confirm.innerHTML;
 let challenge='',destination=null,end=0,resendAt=0,loading=false,lastState='',revision=0,controller=null;
 const register=()=>auth.dataset.mode==='register';
 const active=()=>auth.dataset.emailMethod==='code'&&!auth.classList.contains('hidden');
 const state=()=>auth.dataset.mode+':'+auth.dataset.emailMethod;
 const current=(attempt,key)=>attempt===revision&&key===state()&&active();
 function countdown(){
  const ready=active(),remaining=Math.max(0,Math.ceil((end-Date.now())/1000)),wait=Math.max(0,Math.ceil((resendAt-Date.now())/1000));
  timer.textContent=remaining?'Код действует ещё '+Math.floor(remaining/60)+':'+String(remaining%60).padStart(2,'0'):'Срок кода истёк. Запросите новый.';
  send.disabled=loading||!ready||(register()&&!consent.checked);
  confirm.disabled=loading||!ready||!challenge||remaining===0;
  resend.disabled=loading||!ready||!challenge||wait>0;
  resend.textContent=wait?'Повторно через '+wait+' с':'Отправить ещё раз';
  email.disabled=!ready||loading||!!challenge;email.required=ready&&!challenge;
  name.disabled=!ready||loading||!!challenge||!register();name.required=ready&&register()&&!challenge;
  startForm.setAttribute('aria-busy',String(loading));confirmForm.setAttribute('aria-busy',String(loading));
  send.innerHTML=loading&&!challenge?'Отправляем код…':sendLabel;
  confirm.innerHTML=loading&&challenge?'Подождите…':confirmLabel;
 }
 function reset(){
  revision++;controller?.abort();controller=null;loading=false;challenge='';destination=null;end=0;resendAt=0;
  cells.forEach(cell=>cell.value='');startForm.classList.remove('hidden');confirmForm.classList.add('hidden');err.textContent='';countdown();
 }
 function sync(){
  if(state()!==lastState){lastState=state();reset();}
  nameField.classList.toggle('hidden',!register());countdown();
 }
 function fill(value,index){
  const digits=String(value||'').replace(/\D/g,'').slice(0,6);if(!digits)return;
  digits.split('').forEach((digit,j)=>{if(cells[index+j])cells[index+j].value=digit});
  cells[Math.min(index+digits.length,5)].focus();
 }
 cells.forEach((cell,i)=>{
  cell.addEventListener('input',()=>{
   const digits=cell.value.replace(/\D/g,'');cell.value='';
   if(digits.length>1){fill(digits,i);return;}
   cell.value=digits.slice(-1);if(cell.value&&i<5)cells[i+1].focus();err.textContent='';
  });
  cell.addEventListener('paste',event=>{
   const digits=(event.clipboardData?.getData('text')||'').replace(/\D/g,'');
   if(!digits)return;event.preventDefault();
   if(digits.length===6){cells.forEach(input=>input.value='');fill(digits,0);}else fill(digits,i);
   err.textContent='';
  });
  cell.addEventListener('keydown',event=>{
   if(event.key==='Backspace'&&!cell.value&&i>0){cells[i-1].value='';cells[i-1].focus();event.preventDefault();}
   if(event.key==='ArrowLeft'&&i>0){cells[i-1].focus();event.preventDefault();}
   if(event.key==='ArrowRight'&&i<5){cells[i+1].focus();event.preventDefault();}
  });
 });
 setInterval(countdown,1000);
 async function request(resending=false){
  if(loading||!active())return;
  if(!resending&&(!email.reportValidity()||(register()&&!name.reportValidity())))return;
  if(register()&&!consent.checked){err.textContent='Примите условия использования';consent.focus();return;}
  const payload=resending?destination:{email:email.value.trim(),intent:register()?'register':'login',
   ...(register()?{name:name.value.trim(),legal_acceptance:true,legal_version:'2026-10-19-registration-v1'}:{})};
  if(!payload)return;
  const attempt=++revision,key=state();controller=new AbortController();loading=true;err.textContent='';countdown();
  try{
   const data=await api('/auth/email/start',{method:'POST',signal:controller.signal,body:JSON.stringify(payload)});
   if(!current(attempt,key))return;
   if(typeof data?.challenge_id!=='string'||!data.challenge_id)throw new Error('Не удалось получить код. Повторите попытку.');
   challenge=data.challenge_id;destination=payload;end=Date.now()+(data.expires_in||600)*1000;
   resendAt=Date.now()+Math.max(60,data.retry_after||60)*1000;
   document.querySelector('#email-code-destination').textContent=payload.email;
   startForm.classList.add('hidden');confirmForm.classList.remove('hidden');cells.forEach(cell=>cell.value='');cells[0].focus();
  }catch(error){if(current(attempt,key)&&error.name!=='AbortError')err.textContent=error.message||'Не удалось отправить письмо';}
  finally{if(current(attempt,key)){loading=false;controller=null;countdown();}}
 }
 startForm.addEventListener('submit',event=>{event.preventDefault();void request();});
 confirmForm.addEventListener('submit',async event=>{
  event.preventDefault();if(loading||!active()||!challenge)return;
  const code=cells.map(cell=>cell.value).join('');
  if(!/^\d{6}$/.test(code)){err.textContent='Введите все шесть цифр';return;}
  if(Date.now()>=end){err.textContent='Код истёк. Запросите новый.';return;}
  const attempt=++revision,key=state();controller=new AbortController();loading=true;err.textContent='';countdown();
  try{
   const data=await api('/auth/email/confirm',{method:'POST',signal:controller.signal,body:JSON.stringify({challenge_id:challenge,code})});
   if(!current(attempt,key))return;
   if(!data?.user)throw new Error('Не удалось завершить вход');
   await window.SmetraCompleteAuth(data.user);
  }catch(error){if(current(attempt,key)&&error.name!=='AbortError'){err.textContent=error.message||'Неверный код';cells.forEach(cell=>cell.value='');cells[0].focus();}}
  finally{if(current(attempt,key)){loading=false;controller=null;countdown();}}
 });
 document.querySelector('#email-code-back').addEventListener('click',()=>{reset();email.focus();});
 resend.addEventListener('click',()=>{if(!resend.disabled)void request(true);});
 document.addEventListener('smetra:auth-method',sync);
 document.addEventListener('smetra:auth-reset',reset);
 consent.addEventListener('change',countdown);
 new MutationObserver(sync).observe(auth,{attributes:true,attributeFilter:['data-mode','data-email-method','class']});
 sync();
})();
