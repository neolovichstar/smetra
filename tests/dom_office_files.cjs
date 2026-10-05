/* Interaction/security checks in an in-process DOM; this does not verify layout. */
const assert=require('node:assert/strict'),fs=require('node:fs'),{execFileSync}=require('node:child_process');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
(async()=>{
 const fixtures=JSON.parse(execFileSync(process.env.SMETRA_PYTHON||'python',['-c',
  "import json; from tests.office_fixtures import docx,xlsx; from backend.office_documents import preview,DOCX,XLSX,CSV; print(json.dumps([preview(docx('<img src=x onerror=alert(1)>', [['Price','15000']]),DOCX),preview(xlsx(),XLSX),preview(b'Name,Price\\nWork,15000',CSV)]))"
 ],{encoding:'utf8'}));
 const dom=new JSDOM('<!doctype html><html><body></body></html>',{url:'http://localhost/app',runScripts:'outside-only'}),{window}=dom;
 window.HTMLDialogElement.prototype.showModal=function(){this.open=true};
 window.HTMLDialogElement.prototype.close=function(){this.open=false;window.setTimeout(()=>this.dispatchEvent(new window.Event('close')),0)};
 const document=window.document,downloads=[];
 window.Workspace={download:async(path,name)=>downloads.push({path,name})};
 const requests=[];window.fetch=async(url,options)=>{requests.push({url,options});const index=Number(url.match(/files\/(\d+)/)[1]);return {ok:true,json:async()=>fixtures[index]}};
 window.eval(fs.readFileSync('apps/web/file-preview.js','utf8'));
 const types=['application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','text/csv'];
 await window.SmetraFilePreview.open({id:'0',name:'brief.docx',mime:types[0]},'workspace-fixture');
 assert.equal(requests[0].options.headers['X-Workspace-Id'],'workspace-fixture');
 assert.equal(document.querySelectorAll('.file-office-content img,.file-office-content script').length,0);
 assert.ok(document.querySelector('.file-office-content').textContent.includes('<img src=x onerror=alert(1)>'));
 const search=()=>document.querySelector('.file-office-toolbar input');
 const filter=text=>{search().value=text;search().dispatchEvent(new window.Event('input'))};
 filter('15000');assert.equal(document.querySelector('.file-office-content').textContent.includes('<img'),false);assert.equal(document.querySelector('mark').textContent,'15000');
 filter('not-found');assert.equal(document.querySelector('.file-office-content').textContent,'Совпадений нет');
 window.SmetraFilePreview.close();assert.equal(document.querySelector('.file-preview-body').childNodes.length,0);
 await window.SmetraFilePreview.open({id:'1',name:'prices.xlsx',mime:types[1]},'workspace-fixture');
 await new Promise(resolve=>window.setTimeout(resolve,10)); // Native close event arrives after the next open.
 assert.equal(document.querySelectorAll('.file-office-table col').length,4); // Only populated columns.
 assert.ok(document.querySelector('.file-office-content').textContent.includes('Формула (не рассчитана)'));
 document.querySelector('[aria-label="Сортировать столбец B"]').click();
 assert.equal(document.querySelector('.file-office-table tbody tr td:nth-child(3)').textContent,'2000');
 assert.equal(document.querySelector('thead th:nth-child(3)').getAttribute('aria-sort'),'ascending');
 const handle=document.querySelector('[aria-label="Ширина столбца B"]');handle.dispatchEvent(new window.KeyboardEvent('keydown',{key:'ArrowRight'}));
 assert.equal(document.querySelector('colgroup').children[2].style.width,'170px');
 filter('Покраска');assert.equal(document.querySelectorAll('tbody tr').length,1);filter('');
 const sheet=document.querySelector('select');sheet.value='1';sheet.dispatchEvent(new window.Event('change'));
 assert.ok(document.querySelector('.file-office-content').textContent.includes('Краска'));assert.equal(document.querySelectorAll('tbody tr').length,1);
 await document.querySelector('.file-preview-save').onclick();assert.deepEqual(downloads,[{path:'/files/1',name:'prices.xlsx'}]);
 window.SmetraFilePreview.close();await window.SmetraFilePreview.open({id:'2',name:'prices.csv',mime:types[2]},'workspace-fixture');
 await new Promise(resolve=>window.setTimeout(resolve,10));
 assert.equal(document.querySelectorAll('tbody tr').length,2);assert.equal(document.querySelectorAll('col').length,3);
 let finishOld;window.fetch=()=>new Promise(resolve=>{finishOld=resolve});
 const oldOpen=window.SmetraFilePreview.open({id:'0',name:'old.docx',mime:types[0]},'workspace-fixture');
 window.fetch=async()=>({ok:true,json:async()=>fixtures[2]});
 await window.SmetraFilePreview.open({id:'2',name:'prices.csv',mime:types[2]},'workspace-fixture');
 finishOld({ok:false,json:async()=>({error:'Stale request error'})});await oldOpen;
 assert.ok(document.querySelector('.file-office-table'));assert.equal(document.querySelector('.file-preview-name').textContent,'prices.csv');
 window.fetch=async()=>({ok:false,json:async()=>({error:'No access'})});await window.SmetraFilePreview.open({id:'2',name:'prices.csv',mime:types[2]},'foreign-workspace');
 assert.equal(document.querySelector('.file-preview-body').textContent,'No access');assert.equal(document.querySelector('.file-preview-save').disabled,true);
 window.SmetraFilePreview.close();dom.window.close();console.log('PASS: real office parser -> DOM preview; literal HTML, filtering/highlighting, sheets, numeric sorting, keyboard resize, download binding and access-error handling');
})().catch(error=>{console.error(error);process.exit(1)});
