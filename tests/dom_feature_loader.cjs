'use strict';
// Regression coverage for a partially evaluated cached lazy script.
// The assistant should open without optional quote previews / knowledge.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const source=fs.readFileSync('apps/web/features.js','utf8');

function harness(handle){
  const loads=[];
  const win={};
  const doc={
    createElement:tag=>{
      assert.equal(tag,'script');
      return {src:'',async:true,onload:null,onerror:null,remove(){}};
    },
    head:{append(script){
      loads.push(script.src);
      queueMicrotask(()=>handle(script,win,loads));
    }},
  };
  vm.runInNewContext(source,{
    window:win,document:doc,
    setTimeout,clearTimeout,
  },{filename:'features.js'});
  return {win,loads};
}

(async()=>{
  {
    let chatLoads=0;
    const {win,loads}=harness((script,w)=>{
      if(script.src.includes('chat-markdown.js'))w.SmetraMarkdown={};
      if(script.src.includes('assistant-chat.js')&&++chatLoads===2)w.SmetraAssistant=async()=>{};
      script.onload();
    });
    await win.SmetraLoadFeature('assistant');
    assert.equal(chatLoads,2,'a fulfilled but unevaluated script must be reloaded automatically');
    assert.ok(loads.some(x=>x.includes('assistant-chat.js')&&x.includes('recovery=2')));
    assert.equal(loads.some(x=>x.includes('quote-visual-core.js')),false,'quote preview must never block opening chat');
    assert.equal(loads.some(x=>x.includes('ai-workspace.js')),false,'knowledge must load on demand');
    assert.ok(typeof win.SmetraLoadFeature==='function');
  }
  {
    let fails=0;
    const {win,loads}=harness((script,w)=>{
      if(script.src.includes('chat-markdown.js'))w.SmetraMarkdown={};
      if(script.src.includes('assistant-chat.js')){
        if(fails++===0){script.onerror();return}
        w.SmetraAssistant=async()=>{};
      }
      script.onload();
    });
    await assert.rejects(win.SmetraLoadFeature('assistant'),/Не удалось загрузить/);
    await win.SmetraLoadFeature('assistant');
    assert.equal(fails,2);
    assert.ok(loads.some(x=>x.includes('assistant-chat.js')&&x.includes('recovery=2')));
  }
  console.log('PASS: assistant lazy module retries and nonblocking optional features');
})().catch(error=>{console.error(error);process.exitCode=1});
