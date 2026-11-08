/* Appearance changes keep live controls and server-calculated quote values intact. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));

(async()=>{
 const dom=new JSDOM('<!doctype html><html data-theme="dark"><body><div class="assistant-studio"><textarea id="assistant-input"></textarea><div id="preview-host"></div></div></body></html>',{
  url:'https://example.test/app',runScripts:'dangerously',pretendToBeVisual:true
 });
 const w=dom.window,doc=w.document;
 w.matchMedia=()=>({matches:true});
 let modalOpens=0;
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true;modalOpens++;this.querySelector('[autofocus]')?.focus()};
 w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'))};
 for(const file of ['quote-layout-renderer.js','quote-visual-core.js'])w.eval(fs.readFileSync('apps/web/'+file,'utf8'));
 const quote={id:'quote-one',title:'Отделка квартиры',client:'Анна Иванова',currency:'RUB',amount_kopecks:123450,approval_state:'draft',items:[
  {name:'Покраска стен',description:'Два слоя',category:'Отделочные работы',quantity:'10',unit:'м²',unit_price:12345,subtotal:123450},
  {name:'Дополнительные работы',category:'Опции',quantity:'1',unit:'шт.',unit_price:99999,subtotal:99999,included:false},
  {name:'Неизвестная цена',quantity:'2',unit:'шт.',unit_price:null,subtotal:null},
 ]};
 const original=JSON.stringify(quote);
 let user='owner',resolveOld;
 const controller=w.SmetraQuoteVisuals.mountAssistant({host:doc.querySelector('#preview-host'),getUserId:()=>user,
  fetchQuote:async id=>id==='old-quote'?new Promise(resolve=>{resolveOld=resolve}):{quote:{...quote,id}},listQuotes:async()=>[]});
 const clickChoice=(group,value)=>doc.querySelector('.smetra-appearance-settings '+group+' [data-value="'+value+'"]').click();
 const open=()=>{const tune=doc.querySelector('.smetra-quote-preview-tune');tune.focus();tune.click();return doc.querySelector('dialog.smetra-appearance-dialog')};
 try{
  await controller.load(quote.id);
  const parentDocument=doc.querySelector('.smetra-quote-preview-content .smetra-document');
  const dialog=open();
  assert.equal(modalOpens,1,'Open a native modal');assert.equal(dialog.open,true);
  assert.equal(dialog.getAttribute('aria-label'),'Оформление сметы');
  assert.equal(dialog.querySelector('.smetra-appearance-body').firstElementChild.className,'smetra-appearance-preview');
  assert.equal(dialog.querySelector('.smetra-appearance-body').lastElementChild.className,'smetra-appearance-settings');
  assert.equal(doc.querySelector('.smetra-quote-preview-content .smetra-document'),parentDocument,'Opening preserves the parent preview');
  assert.equal(doc.querySelector('.smetra-quote-preview-content .smetra-document-config'),null,'Settings belong to the modal');

  const controls=dialog.querySelector('.smetra-document-config'),firstFields=controls.querySelector('details');firstFields.open=true;
  const title=firstFields.querySelector('input');title.focus();title.value='Смета на отделку';title.dispatchEvent(new w.Event('input',{bubbles:true}));
  assert.equal(doc.activeElement,title,'Typing keeps focus');assert.equal(title.isConnected,true);
  assert.equal(dialog.querySelector('.smetra-document-title h2').textContent,title.value);
  assert.equal(doc.querySelector('.smetra-quote-preview-content .smetra-document-title h2').textContent,title.value);
  clickChoice('.smetra-document-config-styles','minimal');clickChoice('.smetra-document-config-options','light');
  assert.equal(dialog.querySelector('.smetra-document-config'),controls,'Choice changes keep all controls mounted');
  assert.equal(title.isConnected,true);assert.equal(title.value,'Смета на отделку');assert.equal(firstFields.open,true);
  assert(dialog.querySelector('.smetra-appearance-preview .smetra-document--minimal.smetra-document--light'));
  assert.equal(controls.querySelector('[data-value="minimal"]').getAttribute('aria-pressed'),'true');
  assert.equal(controls.querySelector('[data-value="editorial"]').getAttribute('aria-pressed'),'false');
  for(const paper of doc.querySelectorAll('.smetra-document')){
   assert.equal(paper.querySelector('.smetra-document-summary strong').textContent,w.SmetraQuoteVisuals.money(quote.amount_kopecks));
   assert.equal(paper.querySelectorAll('[role=columnheader]').length,4);
   assert.equal(paper.querySelectorAll('.smetra-document-line.is-excluded').length,1);
   assert.equal(paper.querySelector('.smetra-document-terms'),null,'No empty conditions heading on the document');
   assert.match(paper.querySelector('.smetra-document-line.is-excluded').textContent,/Не включено в итог/);
  }
  assert.equal(w.SmetraQuoteVisuals.serverAmounts(quote.items).total,quote.amount_kopecks,'Excluded and unknown rows do not affect the breakdown');
  const stored=w.SmetraQuoteLayout.load('','owner',quote.id);assert.equal(stored.style,'minimal');assert.equal(stored.blocks[0].title,'Смета на отделку');
  const reorder=controls.querySelector('.smetra-document-config-row [data-action="1"]');reorder.click();
  assert.equal(w.SmetraQuoteLayout.load('','owner',quote.id).blocks[1].title,'Смета на отделку','Reordering retains typed text');
  const add=controls.querySelector('.smetra-document-config-add');add.value='notes';add.dispatchEvent(new w.Event('change'));
  assert.equal(controls.querySelectorAll('.smetra-document-config-row').length,6);
  assert.equal(w.SmetraQuoteLayout.load('','owner',quote.id).blocks.at(-1).kind,'notes');
  assert.equal(JSON.stringify(quote),original,'Appearance never mutates quote data');

  dialog.dispatchEvent(new w.Event('cancel',{cancelable:true}));
  assert.equal(doc.querySelector('.smetra-appearance-dialog'),null,'Escape closes and removes the modal');
  assert.equal(doc.activeElement.className,'smetra-quote-preview-tune','Closing restores the tune button focus');
  open().querySelector('.smetra-appearance-close').click();assert.equal(doc.querySelector('dialog'),null);
  const backdrop=open();backdrop.dispatchEvent(new w.MouseEvent('click',{bubbles:true,clientX:-10,clientY:-10}));
  assert.equal(doc.querySelector('dialog'),null,'Clicking outside the dialog closes it');

  open();await controller.load('quote-two');assert.equal(doc.querySelector('dialog'),null,'Changing quotes closes stale controls');
  const other=open();user='another-owner';other.querySelector('[data-value="dark"]').click();
  assert.equal(doc.querySelector('dialog'),null,'An account change invalidates old controls');
  assert.equal(w.localStorage.getItem('smetra.quote.layout.v1::another-owner:quote-two'),null,'Never save under another account');
  assert.equal(open(),null,'A previously loaded quote cannot reopen under another account');
  user='owner';
  const pending=controller.load('old-quote');controller.startNew();resolveOld({quote:{...quote,id:'old-quote'}});await pending;
  assert.equal(controller.currentId,'','A stale response cannot replace a new draft');assert.equal(doc.querySelector('.smetra-document'),null);
  const foreign=w.SmetraQuoteLayout.render({quote,layout:w.SmetraQuoteLayout.base(),pending:{preview:{kind:'quote_items',after_total:1},arguments:{id:'another-quote',items:[{name:'Foreign item',subtotal:1}]}}});
  assert.match(foreign.textContent,/Покраска стен/);assert.doesNotMatch(foreign.textContent,/Foreign item/);
  assert.equal(foreign.querySelector('.smetra-document-summary strong').textContent,w.SmetraQuoteVisuals.money(quote.amount_kopecks),'Another quote proposal cannot change the document');
  await controller.load(quote.id);open();doc.querySelector('#preview-host').remove();await tick();
  assert.equal(doc.querySelector('dialog'),null,'Leaving the assistant removes the body-mounted modal');
  console.log('PASS: native appearance modal, stable live inputs, saved style/order, exact server amounts, excluded rows, accessible close/focus and stale quote/account guards');
 }finally{controller.destroy();dom.window.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
