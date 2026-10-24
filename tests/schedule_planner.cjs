'use strict';
/* Deterministic scheduling: workdays vs calendar pauses, source filtering, no currency. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('apps/web/schedule-planner.js','utf8');
const sandbox={window:{},Date,Intl};
vm.runInNewContext(source,sandbox,{filename:'schedule-planner.js'});
const {calculate,category}=sandbox.window.SmetraSchedulePlanner;
const item=(name,quantity,unit='м²',extra={})=>({name,quantity,unit,included:true,...extra});
const select=(r,key)=>r.tasks.filter(t=>t.type===key);
const defaults={start:'2026-10-23',rates:{plaster:20,screed:35,tile:10,paint:40,laminate:35}};
const exam=calculate([
 item('Штукатурка стен',40),
 item('Покраска стен',80)
],{...defaults,plasterPause:7});
assert.equal(exam.workCount,2);
assert.equal(exam.tasks.length,3);
assert.equal(exam.tasks[0].start,'2026-10-23');
assert.equal(exam.tasks[0].end,'2026-10-26'); // Friday + Monday
assert.equal(exam.tasks[1].type,'pause');
assert.equal(exam.tasks[1].start,'2026-10-27');
assert.equal(exam.tasks[1].end,'2026-11-02'); // includes weekends
assert.equal(exam.tasks[2].start,'2026-11-03');
assert.equal(exam.tasks[2].end,'2026-11-04');
assert.equal(exam.last,'2026-11-04');
assert.equal(exam.calendarDays,13);

const everyDay=calculate([item('Плитка на стенах',20)],{...defaults,workdays:false});
assert.equal(everyDay.tasks[0].start,'2026-10-23');
assert.equal(everyDay.tasks[0].end,'2026-10-24');
const skipped=calculate([item('Плитка на стенах',20)],{...defaults});
assert.equal(skipped.tasks[0].end,'2026-10-26');
const startSaturday=calculate([item('Плитка на стенах',10)],{...defaults,start:'2026-10-24'});
assert.equal(startSaturday.tasks[0].start,'2026-10-26');
assert.equal(category('Устройство цементной стяжки'),'screed');
assert.equal(category('Шпаклёвка стен'),'general');

const exclude=calculate([
 item('Материал: плитка',15,'м²'),
 item('Смесь',2,'мешок',{category:'Материалы'}),
 item('Покраска',100,'м²',{included:false}),
 item('Штукатурка',-5),
 item('Покраска',80)
],{...defaults});
assert.equal(exclude.workCount,1);
assert.ok(exclude.issues.some(x=>x.includes('некорректное количество')));
assert.ok(exclude.issues.every(x=>typeof x==='string'));
assert.ok(exclude.issues.some(x=>x.includes('условно')===false)||exclude.issues.length===0);
assert.equal(calculate([],defaults).tasks.length,0);
assert.equal(select(exam,'pause').length,1);

for(const [items,settings] of [
 [[item('Покраска',10)],{...defaults,start:'2026-02-30'}],
 [[item('Покраска',10)],{...defaults,plasterPause:-1}],
 [[item('Покраска',10)],{...defaults,plasterPause:1.25}],
 [[item('Покраска',10)],{...defaults,rates:{paint:0}}],
 [null,defaults]
])assert.throws(()=>calculate(items,settings),{name:'Error'});
const ambiguous=calculate([item('Укладка плитки',2,'пог. м')],defaults);
assert.equal(ambiguous.workCount,1);
assert.equal(ambiguous.tasks[0].days,1);
assert.ok(ambiguous.issues.some(x=>x.includes('условно')));
const noPause=calculate([item('Стяжка пола',50)],defaults);
assert.ok(noPause.issues.some(x=>x.includes('Пауза после стяжки')));
const clean=calculate([item('Покраска стен',80)],{start:'2026-10-26',rates:{paint:40}});
assert.equal(clean.workCount,1);
assert.equal(clean.tasks[0].end,'2026-10-27');
assert.equal(clean.issues.length,0);
const long=calculate(Array.from({length:120},(_,i)=>item('Работа '+i,1,'шт')),defaults);
assert.equal(long.workCount,60);
assert.ok(long.issues.some(x=>x.includes('60 работ')));
console.log('PASS: schedule staging, verified-only pauses, weekends, invalid inputs, no material double count, work caps');
