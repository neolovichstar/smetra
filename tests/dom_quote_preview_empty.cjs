/* New AI-first quote previews stay empty until real model progress arrives. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');

(async()=>{
  const dom=new JSDOM('<!doctype html><html><body><div class="assistant-studio"><div id="preview-host"></div></div></body></html>',{
    url:'https://example.test/app',runScripts:'dangerously',pretendToBeVisual:true
  });
  try{
    const {window:w}=dom,doc=w.document;
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
    ctrl.destroy();

    const html=fs.readFileSync('apps/web/app.html','utf8');
    const css=fs.readFileSync('apps/web/ui/precision-controls.css','utf8');
    const workspace=fs.readFileSync('apps/web/ui/workspace.css','utf8');
    assert.match(html,/precision-controls\.css\?v=20261108-r2/,'Control stylesheet must load in deployed HTML');
    assert.match(css,/::-webkit-inner-spin-button/,'WebKit number spinner override');
    assert.match(css,/-moz-appearance:\s*textfield\s*!important/,'Firefox number spinner override');
    assert.match(workspace,/width:calc\(50% - 4px\)/,'Valid billing thumb width');
    assert.doesNotMatch(workspace,/calc\(\(100% - 8px\)\/2\)/,'Unsupported division should not return');
    console.log('PASS: empty AI quote panel, real progress and draft, browser number controls and billing slider');
  }finally{dom.window.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
