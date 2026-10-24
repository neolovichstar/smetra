/* SMETRA / Антисмета: read-only draft audit, no AI and no API calls. */
(() => {
  'use strict';
  const normalize = value => String(value == null ? '' : value).normalize('NFKC').toLocaleLowerCase('ru-RU').replace(/\s+/g, ' ').trim();
  const nameKey = value => normalize(value).replace(/[.,;:!?]+$/g, '');
  const unitKind = value => {
    const u = normalize(value).replace(/[\s._-]/g, '').replace('кв', 'кв');
    if (['м²', 'м2', 'м^2', 'квм', 'квметр', 'квметра'].includes(u)) return 'area';
    if (['м³', 'м3', 'м^3', 'кубм', 'кубметр'].includes(u)) return 'volume';
    if (['м', 'погм', 'пм', 'метр', 'метров'].includes(u)) return 'length';
    if (['шт', 'штук', 'штука', 'ед', 'компл', 'комплект'].includes(u)) return 'pieces';
    if (['кг', 'килограмм'].includes(u)) return 'weight';
    if (['л', 'литр', 'литров'].includes(u)) return 'liquid';
    return u ? 'other' : 'empty';
  };
  const numberInput = raw => {
    const value = String(raw == null ? '' : raw).trim().replace(',', '.');
    if (!value || !/^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value)) return NaN;
    return Number(value);
  };
  const rowNumber = (row, field) => {
    const raw = row && row._raw && Object.prototype.hasOwnProperty.call(row._raw, field) ? row._raw[field] : row?.[field];
    return numberInput(raw);
  };
  const rawPrice = row => {
    const raw = row?._raw;
    if (raw && Object.prototype.hasOwnProperty.call(raw, 'unit_price')) return numberInput(raw.unit_price) * 100;
    return Number(row?.unit_price);
  };
  const issue = (level, code, title, description, rowIndex, field) =>
    ({level, code, title, description, rowIndex, field});

  function scan(rows, context={}) {
    if (!Array.isArray(rows)) return {issues:[], errorCount:0, warningCount:0, tipCount:0, checked:0};
    const issues=[], names=new Map(), pairs=new Map(), named=[];
    for (let index=0; index<Math.min(rows.length, 200); index++) {
      const row=rows[index] || {};
      const name=nameKey(row.name), unit=normalize(row.unit), display=index+1;
      const included=row.included!==false || row.optional!==true;
      const add=(level,code,title,description,field)=>issues.push(issue(level,code,title,description,index,field));
      if (!name) {
        add('error','empty-name','Позиция '+display+': нет названия','Добавьте название работы или материала.','name');
      } else {
        named.push(name);
        const key=name+'|'+unitKind(unit);
        if (pairs.has(key)) {
          add('warning','duplicate','Позиции '+(pairs.get(key)+1)+' и '+display+' могут повторяться',
            'Названия и единицы совпадают. Это может быть намеренным разделением по помещениям — проверьте количество.','name');
        } else pairs.set(key,index);
        if (names.has(name) && names.get(name).kind!==unitKind(unit)) {
          add('warning','inconsistent-unit','Позиция '+display+': разные единицы у одной работы',
            'Такое же название используется с другой единицей. Убедитесь, что это разные виды затрат.','unit');
        } else if (!names.has(name)) names.set(name,{index,kind:unitKind(unit)});
      }
      if (!unit) add('error','empty-unit','Позиция '+display+': не указана единица','Выберите единицу измерения для этой позиции.','unit');
      const quantity=rowNumber(row,'quantity');
      if (!Number.isFinite(quantity) || quantity<=0 || quantity>1000000) {
        add('error','invalid-quantity','Позиция '+display+': проверьте количество',
          'Количество должно быть положительным числом в допустимом диапазоне.','quantity');
      }
      const price=rawPrice(row);
      if (!Number.isFinite(price) || price<0 || price>1000000000000) {
        add('error','invalid-price','Позиция '+display+': некорректная цена',
          'Проверьте стоимость единицы: требуется неотрицательное число.','unit_price');
      } else if (name && included && price===0) {
        add('warning','zero-price','Позиция '+display+': цена равна нулю',
          'Если работа бесплатная или включена в другую позицию, нулевую цену можно оставить.','unit_price');
      }
      if (name && unit && !/материал|доставка|аренд|расходник/.test(name)) {
        if (/(покраск|окраск|штукатурк|шпаклевк|шпаклёвк|грунтовк|облицовк|укладк.{0,20}(плитк|ламинат)|гидроизоляц)/.test(name) &&
          unitKind(unit)!=='area' && unitKind(unit)!=='other') {
          add('tip','area-unit','Позиция '+display+': проверьте единицу измерения',
            'Для такой работы часто используют м², но ваш способ расчёта может отличаться.','unit');
        }
      }
    }
    const all=named.join(' | ');
    const suggestions=[
      {use:/(покраск|окраск|штукатурк|шпаклевк|шпаклёвк)/,has:/(грунтовк|грунтован|грунт глубок)/,title:'Возможно, нужна грунтовка',description:'Для отделки иногда учитывают грунтование отдельной работой. Проверьте состав работ.'},
      {use:/(укладк.{0,25}плитк|облицовк.{0,25}плитк)/,has:/(затирк|фуговк)/,title:'Проверьте затирку швов',description:'При облицовке плиткой затирку иногда учитывают отдельной позицией.'},
      {use:/(укладк.{0,25}ламинат|настил.{0,25}ламинат)/,has:/(подложк)/,title:'Проверьте подложку',description:'Для ламината может потребоваться подложка; её стоимость не всегда включена.'}
    ];
    for (const suggestion of suggestions) {
      if (suggestion.use.test(all) && !suggestion.has.test(all)) {
        const rowIndex=named.length ? rows.findIndex(r=>suggestion.use.test(nameKey(r?.name))) : -1;
        issues.push(issue('tip','possible-omission',suggestion.title,suggestion.description,rowIndex,'name'));
      }
    }
    const order={error:0,warning:1,tip:2};
    issues.sort((a,b)=>order[a.level]-order[b.level] || a.rowIndex-b.rowIndex);
    return {
      issues,
      errorCount:issues.filter(i=>i.level==='error').length,
      warningCount:issues.filter(i=>i.level==='warning').length,
      tipCount:issues.filter(i=>i.level==='tip').length,
      checked:Math.min(rows.length,200)
    };
  }

  const escape = text => String(text).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function mount(root, getData, navigate) {
    if (!root || typeof getData!=='function') throw Error('Антисмета: не задан редактор.');
    let timer=null, disposed=false, latest=null, expanded=false;
    root.innerHTML='<div class="anti-estimate-head"><div><span class="anti-estimate-kicker">ПРОВЕРКА ЧЕРНОВИКА</span>'+
      '<h3>Антисмета</h3><p>Замечания к составу работ и введённым данным.</p></div>'+
      '<span class="anti-estimate-symbol" aria-hidden="true">✓</span></div>'+
      '<div class="anti-estimate-stats" id="anti-estimate-stats" role="status" aria-live="polite"></div>'+
      '<div id="anti-estimate-issues"></div>'+
      '<p class="anti-estimate-disclaimer">Проверка автоматическая и ориентировочная. Не заменяет экспертизу сметы. Никакие позиции не меняются.</p>';
    const summary=root.querySelector('#anti-estimate-stats');
    const list=root.querySelector('#anti-estimate-issues');
    function paint() {
      if (disposed || !root.isConnected) return;
      const source=getData();
      latest=scan(source?.items||[],source?.context||{});
      const result=latest;
      const key=result.errorCount+'|'+result.warningCount+'|'+result.tipCount;
      if (summary.dataset.key!==key) {
        summary.dataset.key=key;
        summary.innerHTML='<span class="anti-count anti-errors"><strong>'+result.errorCount+'</strong> ошибок</span>'+
          '<span class="anti-count anti-warnings"><strong>'+result.warningCount+'</strong> замечаний</span>'+
          '<span class="anti-count anti-tips"><strong>'+result.tipCount+'</strong> советов</span>';
      }
      const shown=expanded?result.issues:result.issues.slice(0,6);
      list.innerHTML=shown.length?'<ol class="anti-issue-list">'+shown.map(x=>
        '<li class="anti-issue anti-'+x.level+'"><span class="anti-issue-dot" aria-hidden="true"></span><div>'+
        (x.rowIndex>=0?'<button type="button" data-audit-row="'+x.rowIndex+'" data-audit-field="'+escape(x.field)+'">'+escape(x.title)+'</button>':
        '<strong>'+escape(x.title)+'</strong>')+
        '<p>'+escape(x.description)+'</p></div></li>').join('')+'</ol>':
        '<p class="anti-estimate-ok">Ошибок и предупреждений по доступным правилам не найдено.</p>';
      if (result.issues.length>6) {
        const more=document.createElement('button');
        more.type='button';more.className='anti-estimate-more';
        more.dataset.auditExpand='1';
        more.textContent=expanded?'Свернуть':'Показать ещё '+(result.issues.length-6);
        list.append(more);
      }
    }
    const onClick=event=>{
      const toggle=event.target.closest('[data-audit-expand]');
      if (toggle){expanded=!expanded;paint();return;}
      const button=event.target.closest('[data-audit-row]');
      if (!button||!root.contains(button)||!latest)return;
      const index=Number(button.dataset.auditRow),field=button.dataset.auditField;
      if (!Number.isSafeInteger(index)||index<0||!latest.issues.some(x=>x.rowIndex===index&&x.field===field))return;
      if (typeof navigate==='function')navigate(index,field);
    };
    root.addEventListener('click',onClick);
    const refresh=()=>{if(disposed)return;clearTimeout(timer);timer=setTimeout(paint,110);};
    paint();
    return Object.freeze({
      refresh,
      refreshNow(){clearTimeout(timer);paint();},
      destroy(){disposed=true;clearTimeout(timer);root.removeEventListener('click',onClick);}
    });
  }
  window.SmetraEstimateAudit=Object.freeze({scan,mount});
})();