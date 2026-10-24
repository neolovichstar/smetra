/* SMETRA / preview-only, deterministic dependency schedule. No server writes. */
(() => {
  'use strict';
  const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const defaultRates=Object.freeze({plaster:20,screed:35,tile:10,paint:40,laminate:35,general:1});
  const labels=Object.freeze({plaster:'Штукатурка',screed:'Стяжка',tile:'Облицовка',paint:'Покраска',laminate:'Напольное покрытие',general:'Прочие работы'});
  const day=24*60*60*1000;
  function toUtc(value){
    if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))throw Error('Введите дату начала в формате ГГГГ-ММ-ДД.');
    const d=new Date(value+'T00:00:00Z');
    if(!Number.isFinite(d.getTime())||d.toISOString().slice(0,10)!==value)throw Error('Укажите действительную дату начала.');
    return d;
  }
  const iso=d=>d.toISOString().slice(0,10);
  const plus=(d,n)=>new Date(d.getTime()+n*day);
  const workday=d=>![0,6].includes(d.getUTCDay());
  function nextDay(date,workdays){
    let d=date;
    while(workdays&&!workday(d))d=plus(d,1);
    return d;
  }
  function endOfWork(start,count,weekdays){
    let date=start;
    for(let i=1;i<count;i++)date=nextDay(plus(date,1),weekdays);
    return date;
  }
  function category(name){
    const s=String(name||'').toLocaleLowerCase('ru-RU');
    if(/стяжк|заливк.{0,20}пол/.test(s))return 'screed';
    if(/штукатур/.test(s))return 'plaster';
    if(/плитк|облицовк|керамогранит/.test(s))return 'tile';
    if(/покраск|окраск|малярн/.test(s))return 'paint';
    if(/ламинат|линолеум|паркет|напольн/.test(s))return 'laminate';
    return 'general';
  }
  function isMaterial(item){
    const name=String(item.name||'').toLocaleLowerCase('ru-RU');
    const group=String(item.category||'').toLocaleLowerCase('ru-RU');
    return /^материал\s*:/.test(name)||/(^|\b)(материалы|сырьё|сырье)(\b|$)/.test(group);
  }
  function numeric(value,field,min,max){
    const n=Number(String(value??'').trim().replace(',','.'));
    if(!Number.isFinite(n)||n<min||n>max)throw Error('Проверьте поле «'+field+'»: допустимо от '+min+' до '+max+'.');
    return n;
  }
  function calculate(items,settings={}){
    if(!Array.isArray(items))throw Error('Не найдены позиции сметы.');
    const start=toUtc(settings.start||'2026-01-01');
    const weekdays=settings.workdays!==false;
    const rates={};
    for(const kind of Object.keys(defaultRates))rates[kind]=numeric(settings.rates?.[kind]??defaultRates[kind],'Производительность — '+labels[kind],.01,100000);
    const pauses={
      plaster:numeric(settings.plasterPause??0,'Высыхание штукатурки',0,365),
      screed:numeric(settings.screedPause??0,'Выдержка стяжки',0,365)
    };
    if(!Number.isInteger(pauses.plaster)||!Number.isInteger(pauses.screed))throw Error('Технологические паузы укажите целым числом календарных дней.');
    const tasks=[],issues=[],source=items.slice(0,100);
    let cursor=nextDay(start,weekdays),calendarDays=0;
    for(let i=0;i<source.length;i++){
      const item=source[i]||{},name=String(item.name||'').trim(),kind=category(name);
      if(!name||isMaterial(item)||item.included===false)continue;
      const quantity=Number(String(item.quantity??'').trim().replace(',','.'));
      if(!Number.isFinite(quantity)||quantity<=0||quantity>1000000){
        issues.push('Позиция '+(i+1)+': некорректное количество, не включена в график.');
        continue;
      }
      const unit=String(item.unit||'').toLowerCase().trim().replace(/\s+/g,'');
      const isArea=['м²','м2','кв.м','кв.м.'].includes(unit);
      const chosenRate=kind==='general'?rates.general:rates[kind];
      const measured=(kind!=='general'&&isArea);
      const duration=measured?Math.ceil(quantity/chosenRate):1;
      if(!measured)issues.push('Позиция '+(i+1)+': срок установлен условно (1 рабочий день); уточните производительность для «'+name.slice(0,70)+'».');
      if(tasks.length>=60){issues.push('В этом предварительном графике учитываются первые 60 работ.');break;}
      const begin=nextDay(cursor,weekdays),end=endOfWork(begin,duration,weekdays);
      tasks.push({type:'work',kind,name,sourceIndex:i,quantity,unit,days:duration,start:iso(begin),end:iso(end)});
      cursor=plus(end,1);
      const pause=pauses[kind];
      if(pause){
        const pauseStart=cursor,pauseEnd=plus(cursor,pause-1);
        tasks.push({type:'pause',kind,name:'Технологическая пауза после «'+name+'»',sourceIndex:i,days:pause,start:iso(pauseStart),end:iso(pauseEnd)});
        cursor=plus(pauseEnd,1);
      }
    }
    if(items.length>100)issues.push('Исходная смета содержит более 100 позиций — график ограничен для предварительного просмотра.');
    if(tasks.some(x=>x.kind==='plaster')&&!pauses.plaster)issues.push('Пауза после штукатурки не задана. Уточните её по материалу, толщине, влажности и условиям объекта.');
    if(tasks.some(x=>x.kind==='screed')&&!pauses.screed)issues.push('Пауза после стяжки не задана. Срок до укладки покрытия определяйте по измерениям и требованиям производителя.');
    if(!tasks.length)issues.push('Нет работ с корректным количеством. Материалы сами по себе не задают срок выполнения.');
    const first=tasks[0]?.start||iso(start),last=tasks.at(-1)?.end||null;
    calendarDays=last?Math.round((toUtc(last)-toUtc(first))/day)+1:0;
    return {tasks,issues,first,last,calendarDays,workCount:tasks.filter(t=>t.type==='work').length};
  }
  const dateText=value=>value?new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short',timeZone:'UTC'}).format(toUtc(value)):'—';
  const daysBetween=(a,b)=>Math.round((toUtc(b)-toUtc(a))/day);
  let generation=0;
  async function render(active=()=>true){
    const mine=++generation,owner=user,guard=()=>mine===generation&&owner===user&&active()&&tab==='schedule';
    view('<section id="smetra-schedule" class="sp-shell"><header class="sp-heading"><span class="sp-kicker">ОБЪЕКТЫ / ПРЕДВАРИТЕЛЬНЫЙ ПЛАН</span><h1>График работ</h1><p>Постройте последовательность работ по смете, учтите технологические перерывы и просмотрите загрузку по дням. Данные не отправляются клиенту автоматически.</p></header><div id="sp-body" role="status">Загружаем список смет…</div></section>');
    let quotes=[];
    try{const result=await api('/quotes');if(!guard())return;quotes=result.quotes||[];}catch(error){if(guard())document.querySelector('#sp-body').textContent=error.message;return;}
    const root=document.querySelector('#smetra-schedule');if(!root||!guard())return;
    const body=root.querySelector('#sp-body');
    const today=new Date().toISOString().slice(0,10);
    body.removeAttribute('role');
    body.innerHTML='<section class="sp-controls"><div class="sp-fields"><label>Смета<select id="sp-quote"><option value="">Выберите смету</option>'+quotes.map(q=>'<option value="'+esc(q.id)+'">'+esc(q.title||'Без названия')+'</option>').join('')+'</select></label>'+
      '<label>Дата начала<input type="date" id="sp-date" value="'+today+'"></label>'+
      '<label>Рабочий календарь<select id="sp-days"><option value="weekdays">Пн–пт, без выходных</option><option value="daily">Все календарные дни</option></select></label></div>'+
      '<details class="sp-advanced"><summary>Производительность и технологические перерывы</summary>'+
      '<p>Значения производительности — условные стартовые примеры, не нормативы. Укажите фактическую скорость бригады. Паузы берите из паспорта материала и результатов контроля влажности.</p>'+
      '<div class="sp-fields">'+Object.entries(labels).filter(([k])=>k!=='general').map(([key,label])=>'<label>'+esc(label)+' · м²/раб. день<input type="number" min="0.01" step="0.01" max="100000" value="'+defaultRates[key]+'" data-sp-rate="'+key+'"></label>').join('')+
      '<label>Штукатурка · пауза, календ. дни<input id="sp-plaster-pause" type="number" min="0" max="365" value="0"></label><label>Стяжка · пауза, календ. дни<input id="sp-screed-pause" type="number" min="0" max="365" value="0"></label></div></details>'+
      '<div class="sp-control-footer"><button class="btn primary" id="sp-build" type="button">Рассчитать предварительный график</button><p>Предпросмотр без изменений сметы, задач и сроков на сервере.</p></div></section><section id="sp-result" aria-live="polite"></section>';
    const $=query=>root.querySelector(query);
    const button=$('#sp-build');
    let quote=null,stamp='';
    $('#sp-quote').addEventListener('change',()=>{quote=null;stamp='';$('#sp-result').replaceChildren()});
    button.addEventListener('click',async()=>{
      const quoteId=$('#sp-quote').value;
      if(!quoteId){$('#sp-result').textContent='Выберите смету для расчёта.';return;}
      button.disabled=true;
      try{
        if(!quote||stamp!==quoteId){const result=await api('/quotes/'+encodeURIComponent(quoteId));if(!guard()||$('#sp-quote').value!==quoteId)return;quote=result.quote;stamp=quoteId;}
        const settings={start:$('#sp-date').value,workdays:$('#sp-days').value==='weekdays',
          plasterPause:$('#sp-plaster-pause').value,screedPause:$('#sp-screed-pause').value,rates:{}};
        root.querySelectorAll('[data-sp-rate]').forEach(input=>settings.rates[input.dataset.spRate]=input.value);
        const plan=calculate(quote.items||[],settings);
        if(!guard())return;
        const visualSpan=Math.max(1,plan.calendarDays),maxWidth=900;
        const warnings=plan.issues.length?'<details class="sp-notes" open><summary>Требует уточнения · '+plan.issues.length+'</summary><ul>'+plan.issues.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul></details>':'';
        $('#sp-result').innerHTML='<div class="sp-result-head"><div><span class="sp-kicker">РАСЧЁТ / БЕЗ ИИ</span><h2>'+esc(quote.title||'Смета')+'</h2><p>Время работы и перерывы рассчитаны последовательно по введённым параметрам.</p></div>'+
          '<div class="sp-result-metrics"><span>'+plan.workCount+' работ</span><strong>'+esc(plan.last?dateText(plan.last):'Не определено')+'</strong><small>Предварительная дата завершения</small></div></div>'+
          (plan.tasks.length?'<div class="sp-gantt"><div class="sp-gantt-axis"><span>Начало: '+esc(dateText(plan.first))+'</span><span>Конец: '+esc(dateText(plan.last))+'</span></div>'+
          plan.tasks.map(task=>{const offset=daysBetween(plan.first,task.start),span=daysBetween(task.start,task.end)+1;return '<div class="sp-task '+(task.type==='pause'?'sp-pause':'')+'"><div class="sp-task-name"><strong>'+esc(task.name)+'</strong><small>'+task.days+' дн. · '+esc(dateText(task.start))+' — '+esc(dateText(task.end))+'</small></div><div class="sp-track" aria-label="'+esc(task.name+': '+task.days+' дней')+'"><div class="sp-bar" style="left:'+Math.min(100,Math.max(0,offset/visualSpan*100))+'%;width:'+Math.max(0.4,Math.min(100,span/visualSpan*100))+'%"></div></div></div>'}).join('')+'</div>':'<p class="sp-empty">Нет работ для построения графика.</p>')+warnings+
          '<p class="sp-disclaimer">Это предварительная модель, а не нормативное заключение и не обещание срока. Последовательность строк принята как последовательность выполнения; реальную параллельность, ресурсы, погоду и ограничения объекта уточняйте отдельно.</p>';
      }catch(error){if(guard())$('#sp-result').textContent=error.message||'Не удалось рассчитать график.'}
      finally{if(guard())button.disabled=false;}
    });
  }
  window.SmetraSchedulePlanner=Object.freeze({calculate,category,render});
})();