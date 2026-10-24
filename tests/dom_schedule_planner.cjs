'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
(async()=>{
 const w=new JSDOM('<!doctype html><body><div id="content"></div></body>',{url:'https://smetra.test/app#schedule',runScripts:'dangerously'}).window;
 const source=fs.readFileSync('apps/web/schedule-planner.js','utf8');
 const calls=[],owner={id:'qa-user'};
 w.user=owner;w.tab='schedule';
 w.view=html=>w.document.querySelector('#content').innerHTML=html;
 w.api=async path=>{
  calls.push(path);
  if(path==='/quotes')return {quotes:[{id:'quote-a',title:'Квартира'}]};
  if(path==='/quotes/quote-a')return {quote:{title:'Квартира',items:[
   {name:'Штукатурка стен',quantity:'40',unit:'м²'},
   {name:'Покраска стен',quantity:'80',unit:'м²'}
  ]}};
  throw Error('Unexpected API request: '+path);
 };
 w.eval(source);
 await w.SmetraSchedulePlanner.render(()=>true);
 const $=selector=>w.document.querySelector(selector);
 assert.ok($('#sp-quote'));
 assert.equal($('#sp-result').textContent,'','Scheduling does not run without user input');
 assert.deepEqual(calls,['/quotes']);
 const change=(selector,value,type='input')=>{const e=$(selector);e.value=value;e.dispatchEvent(new w.Event(type,{bubbles:true}))};
 change('#sp-quote','quote-a','change');
 change('#sp-date','2026-10-23','change');
 change('#sp-plaster-pause','7','change');
 $('#sp-build').click();
 await new Promise(resolve=>setImmediate(resolve));
 assert.ok($('#sp-result .sp-gantt'),'Schedule must render timeline');
 assert.ok($('#sp-result').textContent.includes('4 нояб.'),'Calendar finish must account for drying and weekends');
 assert.equal(w.document.querySelectorAll('#sp-result .sp-task').length,3);
 assert.ok($('#sp-result').textContent.includes('7 дн.'));
 assert.ok(!calls.some(s=>s!=='/quotes'&&s!=='/quotes/quote-a'),'Read-only plan uses GET only');
 assert.equal(calls.filter(p=>p==='/quotes/quote-a').length,1);
 // After initial quote retrieval changing only settings must not send another request.
 change('#sp-plaster-pause','0','change');
 $('#sp-build').click();
 await new Promise(resolve=>setImmediate(resolve));
 assert.ok($('#sp-result').textContent.includes('Пауза после штукатурки не задана'));
 assert.equal(calls.filter(p=>p==='/quotes/quote-a').length,1);
 w.close();
 console.log('PASS: read-only schedule screen, on-demand quote loading, no writes, dry-time changes');
})().catch(error=>{console.error(error);process.exitCode=1});
