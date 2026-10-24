/* Smetra: passwordless email login, mobile-friendly six digit entry. */
'use strict';
(function(){
 const flow=document.querySelector('#email-code-flow');if(!flow)return;
 const auth=document.querySelector('#auth'),startForm=document.querySelector('#email-code-start'),
 confirmForm=document.querySelector('#email-code-confirm'),err=document.querySelector('#email-code-error'),
 email=document.querySelector('#email-code-address'),name=document.querySelector('#email-code-name'),
 nameField=document.querySelector('#email-code-name-field'),cells=[...document.querySelectorAll('.email-code-cells input')],
 send=document.querySelector('#email-code-start-button'),confirm=document.querySelector('#email-code-confirm-button'),
 resend=document.querySelector('#email-code-resend'),timer=document.querySelector('#email-code-countdown');
 let challenge='',end=0,resendAt=0,loading=false,lastMode='';
 const register=()=>auth?.dataset.mode==='register';
 function reset(){
  challenge='';end=0;resendAt=0;cells.forEach(x=>x.value='');
  startForm.classList.remove('hidden');confirmForm.classList.add('hidden');err.textContent='';
 }
 function sync(){
  const mode=register()?'register':'login',ready=window.SmetraEmailCodeAvailable===true,
  resetMode=new URLSearchParams(location.search).has('reset');
  flow.classList.toggle('hidden',!ready||resetMode);
  document.body.classList.toggle('email-password-login',ready&&!resetMode&&mode==='login');
  nameField.classList.toggle('hidden',mode!=='register');
  name.required=mode==='register';
  if(mode!==lastMode){lastMode=mode;reset();const details=document.querySelector('#email-disclosure');if(details&&ready)details.open=false}
 }
 function fill(value,index){
  const digits=String(value||'').replace(/\D/g,'').slice(0,6);if(!digits)return;
  digits.split('').forEach((digit,j)=>{if(cells[index+j])cells[index+j].value=digit});
  cells[Math.min(index+digits.length,5)].focus();
 }
 cells.forEach((cell,i)=>{
  cell.addEventListener('input',()=>{
   const d=cell.value.replace(/\D/g,'');cell.value='';
   if(d.length>1){fill(d,i);return}
   cell.value=d.slice(-1);if(cell.value&&i<5)cells[i+1].focus();err.textContent='';
  });
  cell.addEventListener('paste',e=>{
   const d=(e.clipboardData?.getData('text')||'').replace(/\D/g,'');
   if(!d)return;e.preventDefault();
   if(d.length===6){cells.forEach(x=>x.value='');fill(d,0)}else fill(d,i);
  });
  cell.addEventListener('keydown',e=>{
   if(e.key==='Backspace'&&!cell.value&&i>0){cells[i-1].value='';cells[i-1].focus();e.preventDefault()}
   if(e.key==='ArrowLeft'&&i>0){cells[i-1].focus();e.preventDefault()}
   if(e.key==='ArrowRight'&&i<5){cells[i+1].focus();e.preventDefault()}
  });
 });
 function countdown(){
  if(!challenge)return;
  const remaining=Math.max(0,Math.ceil((end-Date.now())/1000)),wait=Math.max(0,Math.ceil((resendAt-Date.now())/1000));
  timer.textContent=remaining?'Код действует ещё '+Math.floor(remaining/60)+':'+String(remaining%60).padStart(2,'0'):'Срок кода истёк. Запросите новый.';
  resend.disabled=loading||wait>0;
  resend.textContent=wait?'Повторно через '+wait+' с':'Отправить ещё раз';
 }
 setInterval(countdown,1000);
 async function request(){
  if(loading||!email.reportValidity())return;
  if(register()&&!name.value.trim()){err.textContent='Укажите имя';name.focus();return}
  if(register()&&!document.querySelector('#legal-consent')?.checked){err.textContent='Примите условия использования';return}
  loading=true;send.disabled=true;resend.disabled=true;err.textContent='';
  try{
   const payload={email:email.value.trim(),intent:register()?'register':'login'};
   if(register())Object.assign(payload,{name:name.value.trim(),legal_acceptance:true,legal_version:'2026-10-19-registration-v1'});
   const data=await api('/auth/email/start',{method:'POST',body:JSON.stringify(payload)});
   challenge=data.challenge_id;end=Date.now()+(data.expires_in||600)*1000;resendAt=Date.now()+Math.max(60,data.retry_after||60)*1000;
   document.querySelector('#email-code-destination').textContent=payload.email;
   startForm.classList.add('hidden');confirmForm.classList.remove('hidden');
   cells.forEach(x=>x.value='');cells[0].focus();
  }catch(e){err.textContent=e.message||'Не удалось отправить письмо'}
  finally{loading=false;send.disabled=false;countdown()}
 }
 startForm.addEventListener('submit',e=>{e.preventDefault();void request()});
 confirmForm.addEventListener('submit',async e=>{
  e.preventDefault();if(loading)return;
  const code=cells.map(x=>x.value).join('');
  if(!/^\d{6}$/.test(code)){err.textContent='Введите все шесть цифр';return}
  if(Date.now()>=end){err.textContent='Код истёк. Запросите новый.';return}
  loading=true;confirm.disabled=true;err.textContent='';
  try{
   const data=await api('/auth/email/confirm',{method:'POST',body:JSON.stringify({challenge_id:challenge,code})});
   if(!data?.user)throw new Error('Не удалось завершить вход');
   await window.SmetraCompleteAuth(data.user);
  }catch(e){err.textContent=e.message||'Неверный код';cells.forEach(x=>x.value='');cells[0].focus()}
  finally{loading=false;confirm.disabled=false;countdown()}
 });
 document.querySelector('#email-code-back').addEventListener('click',()=>{reset();email.focus()});
 resend.addEventListener('click',()=>{if(!resend.disabled){reset();void request()}});
 document.addEventListener('smetra:email-capability',sync);
 new MutationObserver(sync).observe(auth,{attributes:true,attributeFilter:['data-mode']});
 sync();
})();
