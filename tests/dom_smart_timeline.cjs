/* Interactive planning UI: no implicit paid calls or quote mutations. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const code=fs.readFileSync('apps/web/smart-timeline.js','utf8');
const make=()=>{
  const dom=new JSDOM('<!doctype html><html><body><main id="content"></main></body></html>',{url:'https://smetra.test/app#timeline',runScripts:'dangerously'});
  dom.window.view=html=>{dom.window.document.querySelector('#content').innerHTML=html};
  dom.window.eval(code);
  return dom;
};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  const guest=make(),guestRequests=[];
  guest.window.api=async path=>{
    guestRequests.push(path);
    if(path==='/workspace')return {entitlements:{features:{smart_timeline:false}}};
    throw Error('Free account must not fetch paid preview');
  };
  await guest.window.SmetraSmartTimeline.render();
  assert.match(guest.window.document.querySelector('#smetra-timeline').textContent,/PRO Плюс/);
  assert.equal(guest.window.document.querySelector('#stl-run'),null);
  assert.deepEqual(guestRequests,['/workspace']);
  guest.window.close();

  const paid=make(),requests=[];
  paid.window.api=async (path,options)=>{
    requests.push({path,options});
    if(path==='/workspace')return {entitlements:{features:{smart_timeline:true}}};
    if(path==='/quotes')return {quotes:[{id:'quote-one',title:'<img src=x onerror=alert(1)>'}]};
    if(path==='/quotes/quote-one')return {quote:{items:[
      {name:'Штукатурка 100 м²',quantity:'100',unit:'м²',included:true},
      {name:'Грунтовка',quantity:'50',unit:'м²',included:true},
      {name:'Исключённая работа',quantity:'2',unit:'шт',included:false}
    ]}};
    if(path==='/timeline/preview'){
      const stages=JSON.parse(options.body).stages;
      assert.equal(stages.length,2);
      assert.equal(stages[0].duration_days,'5');
      assert.equal(stages[1].depends_on[0],stages[0].id);
      return {
        start_date:'2026-10-26',end_date:'2026-11-05',calendar_days:11,
        stages:[{id:stages[0].id,name:stages[0].name,start_date:'2026-10-26',end_date:'2026-10-30',duration_days:5,curing_days:2,delay_days:0},
                {id:stages[1].id,name:stages[1].name,start_date:'2026-11-04',end_date:'2026-11-05',duration_days:2,curing_days:0,delay_days:0}],
        disclaimer:'Предварительный расчёт.'
      };
    }
    throw Error('Unexpected request '+path);
  };
  await paid.window.SmetraSmartTimeline.render();
  const $=s=>paid.window.document.querySelector(s);
  assert.equal($('#stl-rows').querySelectorAll('[data-stage]').length,2);
  assert.equal(paid.window.document.querySelectorAll('img').length,0,'Quote names must be safely escaped');
  assert.equal(requests.some(x=>x.path==='/timeline/preview'),false,'Opening page cannot trigger paid calculation');
  $('#stl-quote').value='quote-one';
  $('#stl-quote').dispatchEvent(new paid.window.Event('change',{bubbles:true}));
  await tick();
  assert.equal($('#stl-rows').querySelectorAll('[data-stage]').length,2);
  assert.ok($('#stl-rows').textContent.includes('Штукатурка'));
  assert.equal($('#stl-rows').textContent.includes('Исключённая работа'),false);
  const first=$('#stl-rows [data-stage]');
  first.querySelector('[data-stl-field=duration_days]').value='5';
  first.querySelector('[data-stl-field=duration_days]').dispatchEvent(new paid.window.Event('input',{bubbles:true}));
  const second=$('#stl-rows [data-stage]:nth-child(2)');
  second.querySelector('[data-stl-field=duration_days]').value='2';
  second.querySelector('[data-stl-field=duration_days]').dispatchEvent(new paid.window.Event('input',{bubbles:true}));
  $('#stl-run').click();
  await tick();
  assert.match($('#stl-report').textContent,/2026-11-05/);
  assert.ok($('#stl-report').querySelector('.stl-chart'));
  assert.equal(requests.filter(x=>x.path==='/timeline/preview').length,1);
  paid.window.close();
  console.log('PASS: smart timeline entitlement gate, quote import, escaped markup, opt-in calculation and Gantt display');
})().catch(error=>{console.error(error);process.exitCode=1});
