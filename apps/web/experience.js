/* Reference-matched motion and interactive estimate. No demo data leaves the page. */
(() => {
  const landing = document.querySelector('#landing');
  if (!landing || new URLSearchParams(location.search).has('quote')) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const fine = matchMedia('(hover: hover) and (pointer: fine)');
  const hero = document.querySelector('.hero');
  const art = document.querySelector('#hero-art');
  const halo = document.querySelector('.cursor-halo');
  const motionButton = document.querySelector('#motion-toggle');
  let manualPause = false, paused = reduced.matches;
  let frame = 0, targetX = 0, targetY = 0, currentX = 0, currentY = 0;
  let pointerX = 0, pointerY = 0, haloX = 0, haloY = 0, pointerVisible = false;
  function animate() {
    frame = 0;
    if (paused || document.hidden) return;
    currentX += (targetX-currentX)*.065;
    currentY += (targetY-currentY)*.065;
    art.style.transform = 'translate3d('+currentX+'px,'+currentY+'px,0) scale(1.015)';
    haloX += (pointerX-haloX)*.22; haloY += (pointerY-haloY)*.22;
    if (pointerVisible) halo.style.transform = 'translate3d('+(haloX-12.5)+'px,'+(haloY-12.5)+'px,0)';
    if (Math.abs(currentX-targetX)>.02 || Math.abs(currentY-targetY)>.02 ||
      (pointerVisible && (Math.abs(haloX-pointerX)>.1 || Math.abs(haloY-pointerY)>.1))) frame=requestAnimationFrame(animate);
  }
  function wake(){if(!frame && !paused && !document.hidden) frame=requestAnimationFrame(animate);}
  function motionState(){
    paused=manualPause||reduced.matches;
    document.body.classList.toggle('motion-paused',paused);
    motionButton.setAttribute('aria-pressed',String(paused));
    const label=reduced.matches?'Анимации отключены в настройках устройства':paused?'Включить анимации':'Выключить анимации';
    motionButton.setAttribute('aria-label',label);motionButton.title=label;motionButton.disabled=reduced.matches;
    motionButton.querySelector('img').src='/assets/icons/'+(paused?'play':'pause')+'.svg';
    if(paused){cancelAnimationFrame(frame);frame=0;currentX=currentY=targetX=targetY=0;art.style.transform='';document.querySelectorAll('[data-magnetic]').forEach(el=>el.style.transform='');}else wake();
  }
  motionButton.addEventListener('click',()=>{manualPause=!manualPause;motionState();});
  reduced.addEventListener('change',motionState);
  document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(frame);frame=0;}else wake();});
  hero.addEventListener('pointermove',event=>{
    if(paused||!fine.matches)return;
    const bounds=hero.getBoundingClientRect();
    targetX=((event.clientX-bounds.left)/bounds.width-.5)*12;
    targetY=((event.clientY-bounds.top)/bounds.height-.5)*9;wake();
  },{passive:true});
  hero.addEventListener('pointerleave',()=>{targetX=targetY=0;wake();});
  document.addEventListener('pointermove',event=>{
    if(paused||!fine.matches)return;
    pointerX=event.clientX;pointerY=event.clientY;
    if(!pointerVisible){haloX=pointerX;haloY=pointerY;}
    pointerVisible=true;halo.classList.add('visible');
    halo.classList.toggle('over-link',Boolean(event.target.closest('a,button,input,summary')));
    wake();
  },{passive:true});
  document.documentElement.addEventListener('pointerleave',()=>{pointerVisible=false;halo.classList.remove('visible');});
  document.querySelectorAll('[data-magnetic]').forEach(button=>{
    button.addEventListener('pointermove',event=>{
      if(paused||!fine.matches)return;
      const bounds=button.getBoundingClientRect();
      button.style.transform='translate('+(event.clientX-bounds.left-bounds.width/2)*.04+'px,'+(event.clientY-bounds.top-bounds.height/2)*.08+'px)';
    });
    button.addEventListener('pointerleave',()=>button.style.transform='');
  });
  const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{
    if(entry.isIntersecting){entry.target.classList.add('revealed');observer.unobserve(entry.target);}
  }),{threshold:.08});
  document.querySelectorAll('[data-reveal]').forEach(el=>{el.classList.add('reveal-ready');observer.observe(el);});

  const checkboxes=[...document.querySelectorAll('[data-price]')];
  const status=document.querySelector('#demo-status');
  const total=document.querySelector('#demo-total');
  const next=document.querySelector('#demo-next');
  const help=document.querySelector('#demo-help');
  const response=document.querySelector('#demo-response');
  let stage='create';
  const labels={create:'Черновик',send:'Отправлено',accept:'Согласовано'};
  function sum(){return checkboxes.reduce((value,input)=>value+(input.checked?Number(input.dataset.price):0),0);}
  function renderStage(value){
    const changed=stage!==value;
    stage=value;
    document.querySelector('#demo-dialog').dataset.stage=stage;
    status.textContent=labels[stage];
    checkboxes.forEach(input=>input.disabled=stage!=='create');
    document.querySelectorAll('[data-step]').forEach(button=>{
      const active=button.dataset.step===stage;button.classList.toggle('active',active);
      if(active)button.setAttribute('aria-current','step');else button.removeAttribute('aria-current');
    });
    response.classList.toggle('hidden',stage!=='accept');
    next.textContent=stage==='create'?'Отправить клиенту':stage==='send'?'Согласовать предложение':'Попробовать ещё раз';
    const icon=document.createElement('img');icon.className='icon';icon.src='/assets/icons/'+(stage==='send'?'check':'arrow-up-right')+'.svg';icon.alt='';next.append(icon);
    next.disabled=stage==='create'&&sum()===0;
    help.textContent=stage==='create'?(sum()?'Выберите работы. Это пример: данные не сохраняются.':'Выберите хотя бы одну работу.') : stage==='send'?'Сейчас вы на стороне клиента. Подтвердите стоимость.':'Согласование появится в кабинете автора. В этом примере ничего не сохраняется.';
    total.textContent=new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:0}).format(sum());
    const insight={create:['ВАША СТОРОНА','Каждая деталь на своём месте.','Отметьте нужные работы. Сумма пересчитается сама.','Всё важное в одной ссылке'],send:['НА СТОРОНЕ КЛИЕНТА','Открыл. Посмотрел. Понял.','Клиент видит состав работ и итоговую стоимость. Регистрация не нужна.','Остаётся подтвердить предложение'],accept:['ВЫ ДОГОВОРИЛИСЬ','Теперь можно начинать.','Согласованная стоимость и состав работ остаются в истории предложения.','Ясность для обеих сторон']}[stage];
    ['insight-label','insight-title','insight-text','insight-note'].forEach((id,index)=>document.getElementById(id).textContent=insight[index]);
    if(changed&&!paused){document.querySelectorAll('.demo-document,.insight-content').forEach(el=>{el.classList.remove('state-enter');void el.offsetWidth;el.classList.add('state-enter');});}
  }
  checkboxes.forEach(input=>input.addEventListener('change',()=>renderStage('create')));
  next.addEventListener('click',()=>{
    if(stage==='accept'){checkboxes.forEach(input=>input.checked=true);renderStage('create');}
    else renderStage(stage==='create'?'send':'accept');
  });
  document.querySelectorAll('[data-step]').forEach(button=>button.addEventListener('click',()=>{
    if(!sum())checkboxes.forEach(input=>input.checked=true);
    renderStage(button.dataset.step);
  }));
  document.querySelectorAll('[data-open]').forEach(button=>button.addEventListener('click',()=>{
    const dialog=document.getElementById(button.dataset.open);
    if(button.dataset.open==='demo-dialog'){
      if(!sum())checkboxes.forEach(input=>input.checked=true);
      renderStage(button.dataset.demoStep||'create');
    }
    dialog.classList.remove('is-closing');
    dialog.showModal();
    document.body.classList.add('modal-open');
  }));
  function closeDialog(dialog){
    if(dialog.classList.contains('is-closing'))return;
    const finish=()=>{dialog.close();dialog.classList.remove('is-closing');if(!document.querySelector('dialog[open]'))document.body.classList.remove('modal-open');};
    if(paused){finish();return;}
    dialog.classList.add('is-closing');
    setTimeout(finish,220);
  }
  document.querySelectorAll('dialog').forEach(dialog=>{
    dialog.querySelector('.close-dialog').addEventListener('click',()=>closeDialog(dialog));
    dialog.addEventListener('cancel',event=>{event.preventDefault();closeDialog(dialog);});
    dialog.addEventListener('close',()=>{dialog.classList.remove('is-closing');if(!document.querySelector('dialog[open]'))document.body.classList.remove('modal-open');});
    dialog.addEventListener('click',event=>{
      if(event.target!==dialog)return;
      const rect=dialog.getBoundingClientRect();
      if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)closeDialog(dialog);
    });
  });
  const previewCopy=[
    ['ИНТЕРАКТИВНЫЙ ЧЕРНОВИК','Не сохранён','Начните с понятной стоимости.','Добавляйте любые услуги, товары и работы. В кабинете доступны скидки, налоги и внутренняя себестоимость.'],
    ['КЛИЕНТСКАЯ ВЕРСИЯ','Предпросмотр','Отправьте одну ссылку.','После сохранения и публикации клиент получит свою страницу с составом работ, стоимостью и условиями. Без регистрации.'],
    ['РЕШЕНИЕ КЛИЕНТА','Обсуждение','Договоритесь о деталях.','Клиент может согласовать предложение, задать вопрос или запросить изменения. Отправленные версии сохраняются в истории.'],
    ['РАБОТА ПО СОГЛАСОВАННОЙ СМЕТЕ','Заказ','Превратите договорённость в работу.','Из согласованной сметы создайте заказ. Разбейте его на этапы, назначьте сроки и добавьте задачи.'],
    ['ДЕНЬГИ ПО ЗАКАЗУ','Учёт поступлений','Видьте, что уже оплачено.','Записывайте фактически полученные оплаты и расходы. Остаток и денежный результат рассчитываются по данным заказа.']
  ];
  document.querySelectorAll('[data-preview-step]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.previewStep),copy=previewCopy[i];document.querySelectorAll('[data-preview-step]').forEach(tab=>{tab.classList.toggle('active',tab===b);tab.setAttribute('aria-pressed',String(tab===b))});['preview-caption','preview-state','preview-context-title','preview-context-text'].forEach((id,n)=>document.getElementById(id).textContent=copy[n]);document.getElementById('preview-number').textContent=`0${i+1} / 05`;const panel=document.querySelector('.preview-context');panel.classList.remove('state-enter');void panel.offsetWidth;panel.classList.add('state-enter')});
  const previewTotal=()=>{const price=Math.max(0,Number(document.getElementById('preview-price').value)||0),quantity=Math.max(0,Number(document.getElementById('preview-quantity').value)||0);document.getElementById('preview-total').textContent=new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:2}).format(Math.round(price*quantity*100)/100)};
  document.getElementById('preview-price')?.addEventListener('input',previewTotal);document.getElementById('preview-quantity')?.addEventListener('input',previewTotal);
  document.getElementById('preview-continue')?.addEventListener('click',()=>{const title=document.getElementById('preview-title').value,name=document.getElementById('preview-name').value,quantity=document.getElementById('preview-quantity').value,unit_price=Math.round(Number(document.getElementById('preview-price').value)*100);if(title||name||unit_price){try{sessionStorage.setItem('smetra.previewDraft',JSON.stringify({title,items:[{name,quantity,unit:'шт.',unit_price:unit_price||0,cost_price:0}]}))}catch{}}location.href='/app?register=1'});
  renderStage('create');motionState();
})();
