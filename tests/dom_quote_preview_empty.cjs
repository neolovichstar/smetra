/* New AI-first quote previews stay empty until real model progress arrives. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');

(async()=>{
  const dom=new JSDOM('<!doctype html><html><body><div class="assistant-studio"><textarea id="assistant-input"></textarea><div id="preview-host"></div></div></body></html>',{
    url:'https://example.test/app',runScripts:'dangerously',pretendToBeVisual:true
  });
  try{
    const {window:w}=dom,doc=w.document;
    w.localStorage.setItem('smetra.preview.width','560');
    w.eval(fs.readFileSync('apps/web/quote-visual-core.js','utf8'));
    const ctrl=w.SmetraQuoteVisuals.mountAssistant({
      host:doc.querySelector('#preview-host'),
      fetchQuote:async()=>{throw Error('No draft should be fetched before generation')},
      listQuotes:async()=>[],
      getUserId:()=> 'test-user'
    });
    ctrl.startNew();
    const panel=doc.querySelector('#smetra-quote-preview');
    assert.equal(panel.hidden,false,'Panel stays open');
    assert.equal(panel.querySelector('h2').textContent,'Новая смета');
    assert.equal(panel.querySelector('.smetra-quote-preview-content').textContent.trim(),'','No templated descriptions or fake quotes');
    assert.equal(panel.querySelectorAll('.smetra-draft-example').length,0);
    assert.equal(panel.querySelector('.smetra-quote-preview-close')!==null,true);
    assert.equal(panel.querySelector('.smetra-quote-preview-expand')!==null,true);

    ctrl.progress('Составляю смету…');
    const progress=panel.querySelector('.smetra-draft-status');
    assert.equal(progress.hidden,false,'Actual generation status is visible');
    assert.equal(progress.textContent,'Составляю смету…');

    await ctrl.propose({
      id:'test-proposal',tool:'create_quotes',arguments:{},
      preview:{kind:'quote_draft',title:'Проверенная смета',currency:'RUB',counts:{lines:0},sections:[],total:0}
    });
    assert.match(panel.querySelector('.smetra-quote-preview-content').textContent,/Проверенная смета/,'Real AI draft still renders');
    assert.equal(panel.querySelectorAll('.smetra-draft-example').length,0);

    const studio=doc.querySelector('.assistant-studio');
    const savedWidth=studio.style.getPropertyValue('--preview-saved-w');
    assert.equal(savedWidth,'560px','Resized width is saved separately from live grid width');
    assert.equal(studio.style.getPropertyValue('--preview-w'),'','The grid must never retain an inline width override');
    assert.equal(studio.classList.contains('has-quote-preview'),true);
    const close=panel.querySelector('.smetra-quote-preview-close');
    close.focus();
    close.click();
    assert.equal(ctrl.visible,false);
    assert.equal(studio.classList.contains('has-quote-preview'),false,'Closing restores the full chat/composer grid');
    assert.equal(studio.style.getPropertyValue('--preview-w'),'','No empty column remains');
    assert.equal(studio.style.getPropertyValue('--preview-saved-w'),savedWidth,'Keep resize preference for next open');
    assert.equal(panel.getAttribute('aria-hidden'),'true');
    assert.equal(panel.classList.contains('is-closing'),true,'Exit animation begins before panel is hidden');
    assert.equal(panel.hidden,false,'Panel remains mounted while sliding away');
    assert.equal(doc.activeElement.id,'assistant-input','Keyboard focus returns to the chat');

    // Reopening while closing must cancel the pending hide, not hide the new panel.
    ctrl.open();
    assert.equal(ctrl.visible,true);
    assert.equal(panel.hidden,false);
    assert.equal(panel.classList.contains('is-closing'),false);
    assert.equal(studio.classList.contains('has-quote-preview'),true);
    await new Promise(resolve=>setTimeout(resolve,280));
    assert.equal(panel.hidden,false,'A cancelled close cannot hide the reopened panel');

    ctrl.close();
    await new Promise(resolve=>setTimeout(resolve,280));
    assert.equal(panel.hidden,true,'Panel is hidden after the exit animation');
    assert.equal(studio.classList.contains('has-quote-preview'),false);
    ctrl.open();
    assert.equal(studio.style.getPropertyValue('--preview-saved-w'),savedWidth,'Reopen keeps user-resized width');
    ctrl.destroy();

    const html=fs.readFileSync('apps/web/app.html','utf8');
    const css=fs.readFileSync('apps/web/ui/tools.css','utf8');
    const workspace=fs.readFileSync('apps/web/ui/workspace.css','utf8');
    const assistantCss=fs.readFileSync('apps/web/ui/assistant.css','utf8');
    assert.match(assistantCss,/\.assistant-studio\.has-quote-preview\{--preview-w:var\(--preview-saved-w,/,
      'Saved width is applied only when the panel is open');
    assert.match(assistantCss,/\.smetra-quote-preview\.is-closing\{/,'Exit transition is styled');
    assert.match(assistantCss,/prefers-reduced-motion:reduce/,'Reduced-motion users do not get forced animation');
    assert.match(html,/tools\.css\?v=20261108-controls3/,'Number controls must ship with the final design-system CSS');
    assert.doesNotMatch(html,/precision-controls\.css/,'No extra stylesheet layer');
    assert.match(css,/::-webkit-inner-spin-button/,'WebKit number spinner override');
    assert.match(css,/-moz-appearance:\s*textfield/,'Firefox number spinner override');
    assert.match(workspace,/width:calc\(50% - 4px\)/,'Valid billing thumb width');
    assert.doesNotMatch(workspace,/calc\(\(100% - 8px\)\/2\)/,'Unsupported division should not return');
    console.log('PASS: empty AI quote panel, real progress and draft, browser number controls and billing slider');
  }finally{dom.window.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
