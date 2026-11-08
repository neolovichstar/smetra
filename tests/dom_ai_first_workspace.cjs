/* AI-first navigation and compact read-only memory modal. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM} = require(process.env.SMETRA_JSDOM_MODULE || 'jsdom');

(async()=>{
  const html=fs.readFileSync('apps/web/app.html','utf8');
  const styles=fs.readFileSync('apps/web/ui/assistant.css','utf8');
  const app=fs.readFileSync('apps/web/app.js','utf8');
  assert.match(html,/<button data-tab="assistant" class="active">Ассистент<\/button>/);
  assert.match(html,/data-tab="quotes">Сметы<\/button>/);
  assert.doesNotMatch(html,/<button data-tab="dashboard"/,'Legacy dashboard is no longer in manual navigation');
  for(const section of ['construction','files','documents','changelog'])assert.match(html,new RegExp('data-tab="'+section+'"'),'Useful data and tool pages remain in the navigation');
  for(const section of ['clients','leads','finance','catalog','calculators','chats'])assert.doesNotMatch(html,new RegExp('<button data-tab="'+section+'"'),'Manual bookkeeping pages stay out of primary navigation');
  assert.match(html,/data-tab="billing"/,'Billing remains reachable without AI credits');
  assert.match(html,/data-tab="settings"/,'Account controls remain reachable');
  assert.match(html,/data-tab="support"/,'Support remains reachable');
  assert.match(html,/assistant\.css\?v=20261109-csp1/,'CSP-safe assistant CSS must bypass old cache');
  assert.match(app,/'premium' : 'assistant'/,'Assistant is the default start page');
  assert.match(styles,/height:min\(880px,calc\(100dvh - 28px\)\)/,'Dialog must grow vertically');
  assert.match(styles,/width:min\(980px,calc\(100vw - 24px\)\)/,'Dialog width is not increased');

  const navigation=new JSDOM(html,{url:'https://smetra.test/app',runScripts:'outside-only',pretendToBeVisual:true});
  try{
    navigation.window.eval(fs.readFileSync('apps/web/product-ui.js','utf8'));
    const sidebar=navigation.window.document.querySelector('#sidebar');
    assert.deepEqual([...sidebar.querySelectorAll('.sidebar-disclosure')].map(button=>button.textContent),['Объекты и файлы','Аккаунт'],'Runtime navigation keeps the actual group names');
    for(const section of ['construction','files','documents','changelog'])assert.ok(sidebar.querySelector('[data-tab='+section+']'));
    assert.equal(sidebar.querySelector('[data-tab=calculators]'),null);
    assert.equal(sidebar.querySelector('[data-tab=chats]'),null,'Object chats have one navigation entry through the communication center');
  }finally{navigation.window.close()}

  const dom=new JSDOM('<!doctype html><body><button id="assistant-knowledge"></button><dialog id="assistant-knowledge-panel"></dialog></body>',{
    url:'https://smetra.test/app',runScripts:'dangerously',pretendToBeVisual:true
  });
  const w=dom.window,root=w.document.querySelector('#assistant-knowledge-panel');
  try{
    w.api=async url=>{
      assert.equal(url,'/assistant/memory','No unused team-knowledge CRUD request');
      return {enabled:true,items:[
        {id:'1',title:'Секретный заголовок записи',content:'Делаю отделочные сметы',enabled:1,source:'assistant'},
        {id:'2',title:'Старая запись',content:'Неактивная память',enabled:0},
        {id:'3',title:'HTML',content:'<img src=x onerror=alert(1)>',enabled:1}
      ]};
    };
    w.escapeHtml=text=>String(text).replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
    w.eval(fs.readFileSync('apps/web/ai-workspace.js','utf8'));
    await w.SmetraKnowledgePanel(root);
    assert.match(root.textContent,/Делаю отделочные сметы/,'Saved facts are visible');
    assert.doesNotMatch(root.textContent,/Секретный заголовок записи|Неактивная память/,'No record headings or disabled items');
    assert.equal(root.querySelectorAll('input,textarea,select').length,0,'No manual edit toggles or forms');
    assert.equal(root.querySelectorAll('.memory-fact').length,2);
    assert.equal(root.querySelectorAll('img').length,0,'Saved text must remain escaped');
    assert.equal(root.querySelectorAll('#knowledge-close').length,1,'Dialog retains close control');
    console.log('PASS: AI-first navigation, vertically taller memory overview, no forms or switches');
  }finally{dom.window.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
