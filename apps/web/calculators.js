/* SMETRA / free, client-side construction material calculators. No quotes or prices are changed. */
(() => {
  'use strict';

  const kinds = Object.freeze({
    tile: {
      name: 'Плитка', description: 'Площадь облицовки, запас и количество упаковок.',
      note: 'Учитывайте подрезку, раскладку и запас на бой. Площадь упаковки возьмите с этикетки.',
      fields: [
        ['length', 'Длина поверхности', 'м', '4', 0.01, 10000],
        ['width', 'Ширина поверхности', 'м', '3', 0.01, 10000],
        ['openings', 'Необлицовываемая площадь', 'м²', '0', 0, 100000000],
        ['waste', 'Запас на подрезку', '%', '10', 0, 100],
        ['pack', 'В одной упаковке', 'м²', '1.44', 0.001, 100000]
      ]
    },
    laminate: {
      name: 'Ламинат', description: 'Площадь пола с запасом и число целых упаковок.',
      note: 'Запас зависит от рисунка и способа укладки. Точные размеры упаковки проверьте у производителя.',
      fields: [
        ['length', 'Длина комнаты', 'м', '5', 0.01, 10000],
        ['width', 'Ширина комнаты', 'м', '4', 0.01, 10000],
        ['waste', 'Запас на подрезку', '%', '8', 0, 100],
        ['pack', 'В одной упаковке', 'м²', '2.2', 0.001, 100000]
      ]
    },
    paint: {
      name: 'Краска', description: 'Площадь, количество слоёв и объём краски.',
      note: 'Укрывистость зависит от основания и материала. Расход на этикетке имеет приоритет.',
      fields: [
        ['length', 'Длина стены', 'м', '5', 0.01, 10000],
        ['height', 'Высота стены', 'м', '2.7', 0.01, 10000],
        ['openings', 'Площадь проёмов', 'м²', '0', 0, 100000000],
        ['coats', 'Количество слоёв', 'шт.', '2', 1, 20],
        ['coverage', 'Укрывистость одного слоя', 'м²/л', '10', 0.01, 1000],
        ['waste', 'Дополнительный запас', '%', '10', 0, 100],
        ['pack', 'Объём одной банки', 'л', '2.5', 0.01, 10000]
      ]
    },
    plaster: {
      name: 'Штукатурка', description: 'Расход смеси по толщине слоя и количеству мешков.',
      note: 'Реальный расход зависит от неровности стены. Норму кг/м² на 10 мм берите с упаковки.',
      fields: [
        ['length', 'Длина стены', 'м', '5', 0.01, 10000],
        ['height', 'Высота стены', 'м', '2.7', 0.01, 10000],
        ['openings', 'Площадь проёмов', 'м²', '0', 0, 100000000],
        ['thickness', 'Средняя толщина слоя', 'мм', '10', 0.1, 1000],
        ['rate', 'Норма расхода на 10 мм', 'кг/м²', '9', 0.01, 1000],
        ['waste', 'Запас', '%', '10', 0, 100],
        ['pack', 'Вес одного мешка', 'кг', '30', 0.1, 1000]
      ]
    },
    concrete: {
      name: 'Бетон', description: 'Объём заливки с выбранным запасом.',
      note: 'Калькулятор считает геометрический объём, а не состав смеси. Для заказа учитывайте реальную геометрию и потери.',
      fields: [
        ['length', 'Длина участка', 'м', '5', 0.01, 10000],
        ['width', 'Ширина участка', 'м', '3', 0.01, 10000],
        ['thickness', 'Толщина заливки', 'см', '10', 0.1, 10000],
        ['waste', 'Запас', '%', '5', 0, 100]
      ]
    }
  });

  let selected = 'tile';

  function readNumber(value, field) {
    const source = String(value == null ? '' : value).trim().replace(',', '.');
    if (!/^(?:\d+)(?:\.\d+)?$/.test(source)) {
      throw new Error('Проверьте поле «' + field[1] + '»: требуется число.');
    }
    const number = Number(source);
    if (!Number.isFinite(number) || number < field[4] || number > field[5]) {
      throw new Error('Проверьте поле «' + field[1] + '»: допустимый диапазон от ' + field[4] + ' до ' + field[5] + '.');
    }
    return number;
  }

  function calculate(kind, raw) {
    const spec = kinds[kind];
    if (!spec) throw new Error('Неизвестный калькулятор.');
    const v = {};
    for (const field of spec.fields) v[field[0]] = readNumber(raw[field[0]], field);
    const factor = 1 + v.waste / 100;
    let area, primary, secondary, description;
    if (kind === 'tile' || kind === 'laminate') {
      area = v.length * v.width - (v.openings || 0);
      if (area <= 0) throw new Error('Площадь исключаемых участков должна быть меньше общей.');
      primary = {label: 'Материал с запасом', value: area * factor, unit: 'м²'};
      secondary = {label: 'Целых упаковок', value: Math.ceil(primary.value / v.pack - 1e-10), unit: 'шт.'};
      description = 'Чистая площадь ' + format(area) + ' м² × (1 + ' + format(v.waste) + '% запаса).';
    } else if (kind === 'paint') {
      area = v.length * v.height - v.openings;
      if (area <= 0) throw new Error('Площадь проёмов должна быть меньше площади стены.');
      primary = {label: 'Краска с запасом', value: area * v.coats / v.coverage * factor, unit: 'л'};
      secondary = {label: 'Целых банок', value: Math.ceil(primary.value / v.pack - 1e-10), unit: 'шт.'};
      description = 'Площадь ' + format(area) + ' м² × ' + format(v.coats) + ' сл. ÷ ' + format(v.coverage) + ' м²/л × запас.';
    } else if (kind === 'plaster') {
      area = v.length * v.height - v.openings;
      if (area <= 0) throw new Error('Площадь проёмов должна быть меньше площади стены.');
      primary = {label: 'Сухая смесь с запасом', value: area * (v.thickness / 10) * v.rate * factor, unit: 'кг'};
      secondary = {label: 'Целых мешков', value: Math.ceil(primary.value / v.pack - 1e-10), unit: 'шт.'};
      description = 'Площадь ' + format(area) + ' м² × ' + format(v.thickness / 10) + ' × ' + format(v.rate) + ' кг/м² × запас.';
    } else {
      primary = {label: 'Бетон с запасом', value: v.length * v.width * (v.thickness / 100) * factor, unit: 'м³'};
      secondary = {label: 'Без запаса', value: v.length * v.width * (v.thickness / 100), unit: 'м³'};
      description = 'Длина × ширина × (толщина в см ÷ 100) × запас.';
    }
    if (!Number.isFinite(primary.value) || !Number.isFinite(secondary.value) || secondary.value > Number.MAX_SAFE_INTEGER) {
      throw new Error('Результат слишком велик. Проверьте размеры.');
    }
    return {kind, area, primary, secondary, description, note: spec.note};
  }

  function format(value) {
    return new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 3}).format(value);
  }

  // Hand off quantity only. The user enters the unit price and client in the editor;
  // this helper never calculates money or sends requests to the backend.
  function estimateDraft(kind, raw, mode='material') {
    const result=calculate(kind,raw);
    if (!['material','packages'].includes(mode)) throw new Error('Выберите способ учёта материала.');
    if (mode==='packages' && kind==='concrete') throw new Error('Бетон учитывается по объёму в м³.');
    const packageUnits={tile:'упак.',laminate:'упак.',paint:'банка',plaster:'мешок'};
    const byPackage=mode==='packages';
    const quantity=byPackage?result.secondary.value:Math.ceil(result.primary.value*10000-1e-9)/10000;
    if (!Number.isFinite(quantity)||quantity<=0||quantity>1000000) {
      throw new Error('Количество для сметы выходит за допустимые пределы. Измените размеры.');
    }
    const unit=byPackage?packageUnits[kind]:result.primary.unit;
    const name='Материал: '+kinds[kind].name;
    const method=byPackage?'Целые упаковки по введённому объёму упаковки.':'Материал с учётом запаса.';
    const description=[result.description,method,result.note].join(' ');
    return {
      title:'Расчёт материалов · '+kinds[kind].name,
      client:'',
      description:'Позиция создана из калькулятора «'+kinds[kind].name+'». Уточните объёмы, клиента и цену за '+unit+'.',
      items:[{
        name, description, quantity:String(quantity), unit,
        unit_price:0, cost_price:0, tax:'0', discount:'0', markup:'0',
        coefficient:'1', category:'Материалы', optional:false, included:true
      }]
    };
  }

  function fieldsHtml(spec) {
    return spec.fields.map(field =>
      '<label class="smcalc-field"><span>' + field[1] + ' <small>' + field[2] + '</small></span>' +
      '<input inputmode="decimal" autocomplete="off" spellcheck="false" name="' + field[0] + '" ' +
      'aria-label="' + field[1] + ', ' + field[2] + '" value="' + field[3] + '"></label>'
    ).join('');
  }

  function render() {
    view('<section id="smetra-calculators" class="smcalc">' +
      '<header class="smcalc-header"><div><span class="smcalc-kicker">ИНСТРУМЕНТЫ / БЕСПЛАТНО</span>' +
      '<h1>Калькуляторы</h1><p>Быстрый расчёт количества материалов без ИИ, лимитов и создания сметы.</p></div></header>' +
      '<nav class="smcalc-tabs" aria-label="Вид расчёта">' +
      Object.entries(kinds).map(pair =>
        '<button type="button" class="smcalc-tab" data-calc-kind="' + pair[0] + '" aria-pressed="' + (pair[0] === selected) + '">' +
        pair[1].name + '</button>'
      ).join('') + '</nav>' +
      '<div class="smcalc-layout"><section class="smcalc-card" aria-labelledby="smcalc-heading">' +
      '<div class="smcalc-title"><span>01 / ПАРАМЕТРЫ</span><h2 id="smcalc-heading"></h2><p id="smcalc-description"></p></div>' +
      '<form id="smcalc-form" novalidate><div class="smcalc-fields" id="smcalc-fields"></div></form>' +
      '</section><aside class="smcalc-card smcalc-result" aria-labelledby="smcalc-result-title">' +
      '<div class="smcalc-title"><span>02 / РЕЗУЛЬТАТ</span><h2 id="smcalc-result-title">Расчёт материала</h2>' +
      '<p>Результат изменяется автоматически при вводе параметров.</p></div>' +
      '<div id="smcalc-error" class="smcalc-error" role="alert" hidden></div>' +
      '<div id="smcalc-values" aria-live="polite"><div class="smcalc-metric"><span id="smcalc-primary-label"></span>' +
      '<strong><span id="smcalc-primary"></span> <small id="smcalc-primary-unit"></small></strong></div>' +
      '<div class="smcalc-metric smcalc-secondary"><span id="smcalc-secondary-label"></span>' +
      '<strong><span id="smcalc-secondary"></span> <small id="smcalc-secondary-unit"></small></strong></div></div>' +
      '<p class="smcalc-formula" id="smcalc-formula"></p>' +
      '<p class="smcalc-note" id="smcalc-note"></p>' +
      '<div class="smcalc-transfer" id="smcalc-transfer">' +
      '<span class="smcalc-transfer-label">ПОЗИЦИЯ ДЛЯ СМЕТЫ</span>' +
      '<label class="smcalc-transfer-method" for="smcalc-unit-mode">Как учитывать материал' +
      '<select id="smcalc-unit-mode" aria-label="Единица учёта материала">' +
      '<option value="material">По площади, весу или объёму</option>' +
      '<option value="packages">По целым упаковкам</option></select></label>' +
      '<div class="smcalc-transfer-preview" aria-live="polite"><span>В новую смету</span>' +
      '<strong id="smcalc-draft-name"></strong><span id="smcalc-draft-qty"></span></div>' +
      '<p class="smcalc-transfer-note">Цена за единицу остаётся нулевой. Перед сохранением укажите цену и клиента в редакторе. Существующие сметы не изменятся.</p>' +
      '<button type="button" class="btn primary smcalc-draft" id="smcalc-draft">Открыть в новой смете</button></div>' +
      '<button type="button" class="btn smcalc-copy" id="smcalc-copy">Скопировать расчёт</button>' +
      '</aside></div></section>');

    const root = document.querySelector('#smetra-calculators');
    const $ = selector => root.querySelector(selector);
    const form = $('#smcalc-form');
    let copyText = '',draft=null;
    const update = () => {
      const values = Object.fromEntries(new FormData(form).entries());
      try {
        const result = calculate(selected, values);
        draft=estimateDraft(selected,values,$('#smcalc-unit-mode').value);
        $('#smcalc-error').hidden = true;
        $('#smcalc-values').hidden = false;
        $('#smcalc-primary-label').textContent = result.primary.label;
        $('#smcalc-primary').textContent = format(result.primary.value);
        $('#smcalc-primary-unit').textContent = result.primary.unit;
        $('#smcalc-secondary-label').textContent = result.secondary.label;
        $('#smcalc-secondary').textContent = format(result.secondary.value);
        $('#smcalc-secondary-unit').textContent = result.secondary.unit;
        $('#smcalc-formula').textContent = result.description;
        $('#smcalc-note').textContent = result.note;
        $('#smcalc-copy').disabled = false;
        $('#smcalc-draft').disabled = false;
        $('#smcalc-draft-name').textContent=draft.items[0].name;
        $('#smcalc-draft-qty').textContent=format(Number(draft.items[0].quantity))+' '+draft.items[0].unit+' · цена 0';
        copyText = kinds[selected].name + '\n' +
          result.primary.label + ': ' + format(result.primary.value) + ' ' + result.primary.unit + '\n' +
          result.secondary.label + ': ' + format(result.secondary.value) + ' ' + result.secondary.unit + '\n' +
          result.description + '\n' + result.note;
      } catch (error) {
        draft=null;
        $('#smcalc-error').textContent = error.message;
        $('#smcalc-error').hidden = false;
        $('#smcalc-values').hidden = true;
        $('#smcalc-formula').textContent = '';
        $('#smcalc-note').textContent = '';
        $('#smcalc-copy').disabled = true;
        $('#smcalc-draft').disabled = true;
        $('#smcalc-draft-name').textContent='—';
        $('#smcalc-draft-qty').textContent='Исправьте параметры расчёта';
        copyText = '';
      }
    };
    const activate = kind => {
      if (!kinds[kind]) return;
      selected = kind;
      root.querySelectorAll('[data-calc-kind]').forEach(button => {
        button.setAttribute('aria-pressed', String(button.dataset.calcKind === kind));
      });
      $('#smcalc-heading').textContent = kinds[kind].name;
      $('#smcalc-description').textContent = kinds[kind].description;
      $('#smcalc-fields').innerHTML = fieldsHtml(kinds[kind]);
      $('#smcalc-unit-mode').value='material';
      $('#smcalc-unit-mode').disabled=kind==='concrete';
      $('#smcalc-transfer').dataset.calcKind=kind;
      update();
    };
    root.querySelectorAll('[data-calc-kind]').forEach(button => {
      button.addEventListener('click', () => activate(button.dataset.calcKind));
    });
    form.addEventListener('input', update);
    $('#smcalc-unit-mode').addEventListener('change',update);
    $('#smcalc-draft').addEventListener('click',async()=>{
      if(!draft)return;
      const next=structuredClone(draft);
      const button=$('#smcalc-draft');
      button.disabled=true;
      try{
        if(typeof window.Workspace?.editor!=='function')throw Error('Редактор сметы недоступен. Обновите страницу.');
        await window.Workspace.editor(next);
      }catch(error){
        if(root.isConnected)notify(error.message||'Не удалось открыть редактор сметы.');
      }finally{if(root.isConnected)button.disabled=false;}
    });
    $('#smcalc-copy').addEventListener('click', async () => {
      if (!copyText) return;
      try {
        await navigator.clipboard.writeText(copyText);
        if (document.contains(root)) notify('Расчёт скопирован');
      } catch {
        if (document.contains(root)) notify('Не удалось скопировать. Проверьте разрешение браузера.');
      }
    });
    activate(selected);
  }

  window.SmetraCalculators = Object.freeze({calculate, estimateDraft, render, kinds: Object.keys(kinds)});
})();
