/* SMETRA / Smart construction timeline (PRO Plus/TEAM, backend-authoritative). */
(() => {
  'use strict';
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const isoDay=()=>{const d=new Date();return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-')};
  const daysBetween=(start,end)=>Math.round((Date.parse(end+'T00:00:00Z')-Date.parse(start+'T00:00:00Z'))/86400000);
  let stages=[],serial=0;
  const newStage=()=>({id:'phase_'+(++serial),name:'',quantity:'',daily_output:'',duration_days:'',curing_days:'0',delay_days:'0',parallel:false});
  const fromQuote=lines=>{
    if(!Array.isArray(lines))throw Error('Позиции сметы недоступны.');
    const found=lines.filter(x=>x?.included!==false&&String(x.name||'').trim()).slice(0,40);
    if(!found.length)throw Error('В смете нет включённых работ.');
    return found.map(line=>({...newStage(),name:String(line.name).slice(0,120),quantity:String(line.quantity??'').replace(',','.'),unit:String(line.unit||'').slice(0,25)}));
  };
  const dataPayload=(date,weekdays,list)=>{
    const picked=list.map((x,i)=>{
      const obj={id:x.id,name:x.name,depends_on:i>0&&!x.parallel?[list[i-1].id]:[],curing_days:x.curing_days,delay_days:x.delay_days};
      if(String(x.duration_days).trim())obj.duration_days=x.duration_days;
      else {obj.quantity=x.quantity;obj.daily_output=x.daily_output}
      return obj;
    });
    return {start_date:date,workdays_only:weekdays,stages:picked};
  };
  async function render(active=()=>true){
    const rights=await api('/workspace');
    if(!active())return;
    const access=rights.entitlements?.features?.smart_timeline===true;
    view('<section id="smetra-timeline" class="stl"><header class="stl-head"><div><span class="stl-eyebrow">ПЛАНИРОВАНИЕ / PRO ПЛЮС И TEAM</span>'+
      '<h1>Умный календарь</h1><p>Прогнозируйте этапы по фактическим объёмам и выработке бригады. Задержка одного этапа пересчитывает зависящие от него сроки.</p></div></header>'+
      (access?'<div class="stl-layout"><section class="stl-pane"><div class="stl-section-title"><span>01 / ИСХОДНЫЕ ДАННЫЕ</span><h2>Работы и зависимости</h2></div>'+
      '<div class="stl-grid"><label>Смета для импорта<select id="stl-quote"><option value="">Без сметы / вручную</option></select></label>'+
      '<label>Дата начала<input id="stl-start" type="date" value="'+isoDay()+'"></label></div>'+
      '<label class="stl-checkbox"><input type="checkbox" id="stl-workdays" checked> Планировать выполнение только по будням</label>'+
      '<div id="stl-rows"></div><button type="button" class="stl-add" id="stl-add">+ Добавить этап</button>'+
      '<p class="stl-footnote">Объём / выработка за день определяют длительность. Можно вместо этого указать точное число дней. Паузы после работ берутся из ваших данных, не из ИИ.</p>'+
      '<button type="button" class="btn primary stl-run" id="stl-run">Рассчитать график</button><p id="stl-error" class="stl-error" role="alert" hidden></p></section>'+
      '<aside class="stl-pane stl-results"><div class="stl-section-title"><span>02 / ПРОГНОЗ</span><h2>График работ</h2></div>'+
      '<div id="stl-report" aria-live="polite"><p class="stl-empty">Укажите длительности или дневную выработку и нажмите «Рассчитать график».</p></div></aside></div>':
      '<section class="stl-locked"><h2>Планирование для профессионалов</h2><p>График работ доступен в PRO Плюс и TEAM. Сроки рассчитываются на сервере; данные клиентов не передаются в сторонние нейросети.</p><button type="button" class="btn primary" id="stl-plans">Посмотреть тарифы</button></section>')+
      '</section>');
    const root=document.querySelector('#smetra-timeline');if(!root)return;
    if(!access){
      root.querySelector('#stl-plans').onclick=()=>document.querySelector('[data-tab="billing"]')?.click();
      return;
    }
    const $=query=>root.querySelector(query);
    stages=[{...newStage(),name:'Подготовка основания'},{...newStage(),name:'Отделочные работы'}];
    function cards(){
      const holder=$('#stl-rows');
      holder.innerHTML=stages.map((s,i)=>'<article class="stl-stage" data-stage="'+esc(s.id)+'"><div class="stl-stage-head"><strong>Этап '+(i+1)+'</strong>'+
        '<button type="button" data-stl-remove="'+esc(s.id)+'" aria-label="Удалить этап '+(i+1)+'" '+(stages.length===1?'disabled':'')+'><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M5 12h14"/></svg></button></div>'+
        '<label>Работа<input data-stl-field="name" value="'+esc(s.name)+'" maxlength="120" required></label>'+
        '<div class="stl-grid"><label>Объём '+(s.unit?'('+esc(s.unit)+')':'')+'<input data-stl-field="quantity" inputmode="decimal" value="'+esc(s.quantity)+'" placeholder="100"></label>'+
        '<label>Выработка в день<input data-stl-field="daily_output" inputmode="decimal" value="'+esc(s.daily_output)+'" placeholder="20"></label></div>'+
        '<div class="stl-grid stl-grid-three"><label>Или точных дней<input data-stl-field="duration_days" inputmode="numeric" value="'+esc(s.duration_days)+'" placeholder="—"></label>'+
        '<label>Пауза после, дней<input data-stl-field="curing_days" inputmode="numeric" value="'+esc(s.curing_days)+'"></label>'+
        '<label>Задержка, дней<input data-stl-field="delay_days" inputmode="numeric" value="'+esc(s.delay_days)+'"></label></div>'+
        (i>0?'<label class="stl-checkbox"><input type="checkbox" data-stl-field="parallel" '+(s.parallel?'checked':'')+'> Начинать параллельно (без зависимости от предыдущего этапа)</label>':'')+
        '</article>').join('');
    }
    function setError(message){const field=$('#stl-error');field.hidden=!message;field.textContent=message||''}
    function report(result){
      const end=result.end_date,start=result.start_date;
      const interval=Math.max(1,daysBetween(start,end)+1);
      const bars=result.stages.map(s=>{
        const left=daysBetween(start,s.start_date)/interval*100;
        const width=Math.max(.4,(daysBetween(s.start_date,s.end_date)+1)/interval*100);
        return '<li class="stl-timeline-row"><div><strong>'+esc(s.name)+'</strong><span>'+esc(s.start_date)+' — '+esc(s.end_date)+'</span></div>'+
          '<div class="stl-track"><span class="stl-bar" style="left:'+left.toFixed(3)+'%;width:'+Math.min(width,100-left).toFixed(3)+'%"></span></div>'+
          '<small>'+s.duration_days+' раб. дн.'+(s.curing_days?' · Пауза '+s.curing_days+' кал. дн.':'')+
          (s.delay_days?' · Задержка '+s.delay_days+' дн.':'')+'</small></li>';
      }).join('');
      $('#stl-report').innerHTML='<div class="stl-summary"><span>Прогноз завершения</span><strong>'+esc(end)+'</strong>'+
        '<small>С '+esc(start)+' · '+result.calendar_days+' календарных дней</small></div>'+
        '<ol class="stl-chart">'+bars+'</ol><p class="stl-disclaimer">'+esc(result.disclaimer)+'</p>';
    }
    $('#stl-rows').addEventListener('input',event=>{
      const card=event.target.closest('[data-stage]'),field=event.target.dataset.stlField;
      if(!card||!field)return;
      const item=stages.find(s=>s.id===card.dataset.stage);if(!item)return;
      item[field]=event.target.type==='checkbox'?event.target.checked:event.target.value;
    });
    $('#stl-rows').addEventListener('change',event=>{
      if(event.target.dataset.stlField==='parallel'){
        const card=event.target.closest('[data-stage]'),item=stages.find(s=>s.id===card?.dataset.stage);
        if(item)item.parallel=event.target.checked;
      }
    });
    $('#stl-rows').addEventListener('click',event=>{
      const button=event.target.closest('[data-stl-remove]');if(!button||stages.length<=1)return;
      stages=stages.filter(s=>s.id!==button.dataset.stlRemove);cards();
    });
    $('#stl-add').onclick=()=>{if(stages.length>=40){setError('Максимум 40 этапов.');return;}stages.push(newStage());setError('');cards()};
    $('#stl-run').onclick=async()=>{
      const button=$('#stl-run');button.disabled=true;setError('');
      try{
        const result=await api('/timeline/preview',{method:'POST',body:JSON.stringify(dataPayload($('#stl-start').value,$('#stl-workdays').checked,stages))});
        if(root.isConnected&&active())report(result);
      }catch(err){if(root.isConnected)setError(err.message||'Не удалось рассчитать график.')}finally{if(root.isConnected)button.disabled=false;}
    };
    cards();
    try{
      const result=await api('/quotes');
      if(!root.isConnected||!active())return;
      const items=(result.quotes||[]).slice(0,40);
      $('#stl-quote').innerHTML='<option value="">Без сметы / вручную</option>'+
        items.map(q=>'<option value="'+esc(q.id)+'">'+esc(q.title||'Смета')+'</option>').join('');
    }catch(err){if(root.isConnected)setError('Список смет недоступен: '+err.message);}
    $('#stl-quote').onchange=async event=>{
      const id=event.target.value;if(!id)return;
      try{
        const result=await api('/quotes/'+encodeURIComponent(id));
        if(!root.isConnected||!active()||$('#stl-quote').value!==id)return;
        stages=fromQuote(result.quote?.items);setError('');cards();$('#stl-report').innerHTML='<p class="stl-empty">Позиции загружены. Укажите выработку в день либо точную длительность каждого этапа.</p>';
      }catch(err){if(root.isConnected)setError(err.message||'Не удалось загрузить смету.')}
    };
  }
  window.SmetraSmartTimeline=Object.freeze({render,fromQuote,dataPayload});
})();
