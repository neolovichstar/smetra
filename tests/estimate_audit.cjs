/* Антисмета — deterministic, read-only checks and UI regression. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('apps/web/estimate-audit.js','utf8');
const isolated={window:{}};
vm.runInNewContext(source,isolated,{filename:'estimate-audit.js'});
const scan=isolated.window.SmetraEstimateAudit.scan;
const row=(name,quantity='1',unit='м²',unit_price=10000,extra={})=>({name,quantity,unit,unit_price,optional:false,included:true,...extra});
const flags=result=>result.issues.map(i=>i.code);
const same=(actual,expected)=>assert.deepEqual(JSON.parse(JSON.stringify(actual)),expected);
let tested=0;
const run=(name,fn)=>{fn();tested++;console.log('PASS:',name)};
run('clean quote produces no warnings and does not change input',()=>{
 const rows=[row('Грунтовка стен'),row('Покраска стен')],before=JSON.stringify(rows),r=scan(rows);
 assert.equal(r.errorCount,0);assert.equal(r.warningCount,0);assert.equal(r.tipCount,0);
 assert.equal(JSON.stringify(rows),before);
});
run('duplicate names with equivalent area units are reported exactly once',()=>{
 const r=scan([row('Штукатурка стен','3','м²'),row('  ШТУКАТУРКА    СТЕН ','3','м2')]);
 assert.equal(flags(r).filter(x=>x==='duplicate').length,1);
 assert.equal(r.issues.find(x=>x.code==='duplicate').rowIndex,1);
 assert.equal(r.errorCount,0);
});
run('same name in genuinely different measurement units is a warning',()=>{
 const r=scan([row('Работа','1','шт'),row('работа','2','м²')]);
 assert.ok(flags(r).includes('inconsistent-unit'));
 assert.ok(!flags(r).includes('duplicate'));
});
run('empty fields, bad quantities, raw price edits and negative prices are caught',()=>{
 const r=scan([row('','0','',-1),row('Демонтаж','1','шт',0,{_raw:{quantity:'abc',unit_price:'broken'}})]);
 for(const code of ['empty-name','empty-unit','invalid-quantity','invalid-price'])assert.ok(flags(r).includes(code),code);
 assert.equal(flags(r).filter(x=>x==='invalid-price').length,2);
});
run('zero is a possible free position, not a blocking error',()=>{
 const paid=scan([row('Доставка','1','усл.',0)]);
 assert.equal(paid.errorCount,0);assert.ok(flags(paid).includes('zero-price'));
 const excluded=scan([row('Доставка','1','усл.',0,{optional:false,included:false})]);
 assert.ok(!flags(excluded).includes('zero-price'));
});
run('decimal and scientific numbers are supported while invalid extremes fail',()=>{
 assert.ok(!flags(scan([row('Производство','1,25','шт',2500)])).includes('invalid-quantity'));
 assert.ok(flags(scan([row('Производство','1e309','шт',2500)])).includes('invalid-quantity'));
 assert.ok(flags(scan([row('Производство','-2','шт',2500)])).includes('invalid-quantity'));
 assert.ok(flags(scan([row('Производство','2','шт',2500,{_raw:{unit_price:''}})])).includes('invalid-price'));
});
run('missing work suggestions are advisory, and description can suppress them',()=>{
 const paint=[row('Покраска стен','20','м²'),row('Укладка плитки','10','м²'),row('Укладка ламината','18','м²')];
 const result=scan(paint);
 assert.equal(flags(result).filter(x=>x==='possible-omission').length,3);
 assert.equal(result.errorCount,0);
 const described=scan(paint,{description:'Грунтовка, затирка и подложка включены в стоимость'});
 assert.equal(flags(described).filter(x=>x==='possible-omission').length,0);
});
run('intentional separate work is advisory, not blocked',()=>{
 const r=scan([row('Покраска потолка','15','шт')]);
 assert.ok(flags(r).includes('area-unit'));
 assert.equal(r.errorCount,0);
});
run('untrusted input never becomes executable audit markup',()=>{
 const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
 const dom=new JSDOM('<!doctype html><div id="audit"></div>',{url:'https://example.test',runScripts:'dangerously'});
 dom.window.eval(source);
 let rows=[row('<img src=x onerror=alert(1)>','3','м²',0)];
 let clicked=null;
 const panel=dom.window.document.querySelector('#audit');
 const mounted=dom.window.SmetraEstimateAudit.mount(panel,()=>({items:rows}),(...args)=>{clicked=args});
 assert.equal(panel.querySelectorAll('img').length,0);
 assert.ok(panel.textContent.includes('цена равна нулю'));
 const link=panel.querySelector('[data-audit-row][data-audit-field="unit_price"]');
 assert.ok(link);link.click();same(clicked,[0,'unit_price']);
 rows=[row('Грунтовка стен'),row('Покраска стен')];mounted.refreshNow();
 assert.equal(panel.querySelectorAll('.anti-issue').length,0);
 assert.match(panel.textContent,/не найдено/);
 mounted.destroy();dom.window.close();
});
console.log('PASS: Антисмета / '+tested+' suites');
