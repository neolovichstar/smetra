/* Regression test for inline speech recognition in the assistant composer. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
(async()=>{
 const dom=new JSDOM('<body class="workspace-page"><main id="content"></main></body>',{url:'https://example.test/app',runScripts:'dangerously',pretendToBeVisual:true});
 const w=dom.window;let recognition;
 w.load=source=>{const script=w.document.createElement('script');script.textContent=source;w.document.head.append(script)};
 w.load("var user={id:'qa'},tab='assistant'; var escapeHtml=s=>String(s??''); var view=html=>document.querySelector('#content').innerHTML=html;");
 w.sessionStorage.setItem('workspace_id','qa-workspace');w.Workspace={currentWorkspaceId:()=> 'qa-workspace'};
 w.notify=()=>{};w.scrollTo=()=>{};w.TextDecoder=TextDecoder;
 w.SpeechRecognition=class FakeSpeechRecognition{constructor(){recognition=this;this.lang='';this.interimResults=false;this.continuous=false}start(){this.onstart?.()}stop(){this.onend?.()}};
 const quota={remaining:3,limit:3,plan:'free',resets_at:2000000000};
 w.api=async path=>{if(path==='/assistant')return {available:true,quota,messages:[],actions:[]};if(path==='/assistant/conversations')return {items:[]};if(path==='/assistant/jobs')return {enabled:false,jobs:[]};throw Error('Unexpected path: '+path)};
 for(const file of ['vendor/markdown-it-15.0.2.min.js','chat-markdown.js','assistant-chat.js'])w.load(fs.readFileSync('apps/web/'+file,'utf8'));
 await w.SmetraAssistant();await tick();
 const input=w.document.querySelector('#assistant-input'),send=w.document.querySelector('#assistant-send'),form=w.document.querySelector('#assistant-form');
 assert.ok(input&&send&&form,'assistant composer mounts');let submitted=0;form.onsubmit=event=>{event.preventDefault();submitted++};
 send.click();
 assert.equal(send.type,'button','microphone remains a button while recording');assert.equal(send.disabled,false,'microphone remains enabled while recording');
 assert.equal(send.getAttribute('aria-label'),'Остановить голосовой ввод');assert.equal(send.getAttribute('aria-pressed'),'true');
 const result=[{transcript:'Проверить голосовой ввод'}];result.isFinal=false;recognition.onresult({results:[result],resultIndex:0});
 assert.equal(input.value,'Проверить голосовой ввод','interim speech text appears in composer while recording');assert.equal(send.type,'button','interim text does not turn the mic into submit');
 send.click();assert.equal(submitted,0,'stopping the microphone does not submit the form');assert.equal(input.value,'Проверить голосовой ввод','stopping recognition keeps the transcript');assert.equal(send.type,'submit','recognized draft can be sent normally');assert.equal(send.getAttribute('aria-label'),'Отправить сообщение');
 console.log('PASS: live speech text stays in composer; mic remains stoppable; recognized draft becomes sendable');dom.window.close();
})().catch(error=>{console.error(error);process.exitCode=1});