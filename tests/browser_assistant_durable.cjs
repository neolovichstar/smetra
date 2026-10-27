/* Durable-by-default chat against an isolated API with a controlled slow provider. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require(process.env.SMETRA_PLAYWRIGHT_MODULE||'playwright');
const base=process.env.SMETRA_TEST_ORIGIN||'http://localhost:8085';
assert(['localhost','127.0.0.1'].includes(new URL(base).hostname),'Use an isolated local fixture');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.SMETRA_CHROME_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const cx=await browser.newContext({viewport:{width:390,height:844}}),p=await cx.newPage(),errors=[],checks=[];
 p.on('pageerror',e=>errors.push(e.message));fs.mkdirSync('data/qa',{recursive:true});
 const login=await cx.request.post(base+'/api/auth/login',{data:{email:'android-design@test.invalid',password:'android design test only'}});
 const account=await login.json();assert(account.token);await cx.addCookies([{name:'session',value:account.token,url:base,httpOnly:true,sameSite:'Lax'}]);
 const api=async(path,body)=>{
  const response=await cx.request[body===undefined?'get':'post'](base+'/api'+path,body===undefined?{}:{headers:{Origin:base},data:body});
  assert(response.ok(),path+' '+response.status()+' '+await response.text());return response.json();
 };
 const until=async check=>{for(let i=0;i<100;i++){const value=await check();if(value)return value;await new Promise(r=>setTimeout(r,100))}throw Error('Condition did not settle')};
 const open=async id=>{
  await p.goto(base+'/app#assistant');await p.locator('#assistant-input').waitFor();
  await p.evaluate(async id=>{sessionStorage.setItem('smetra.assistant.conversation',id);await window.SmetraAssistant()},id);
  assert.equal(await p.locator('#assistant-background').count(),0);
 };
 const submit=async text=>{
  await p.locator('#assistant-input').fill(text);
  const response=p.waitForResponse(r=>new URL(r.url()).pathname==='/api/assistant/jobs'&&r.request().method()==='POST');
  await p.locator('#assistant-send').click();return (await (await response).json()).job;
 };
 const first=(await api('/assistant/conversations',{title:'Продолжение после ухода'})).conversation;
 await open(first.id);
 const saved=await submit('UI durable question');
 await p.locator('.assistant-message.assistant').filter({hasText:'Поток начат.'}).waitFor();
 assert.equal(await p.locator('#assistant-new-thread').isEnabled(),true);
 await p.screenshot({path:'data/qa/assistant-durable-stream-mobile.png'});
 await p.goto(base+'/app#profile');await p.locator('#profile-form').waitFor();
 const finished=await until(async()=>{const j=(await api('/assistant/jobs/'+saved.id)).job;return j.status==='completed'?j:false});
 assert.equal(finished.result.answer,'Поток начат. Ответ сохранён.');
 const history=(await api('/assistant/conversations/'+first.id)).messages;
 assert.equal(history.length,2);assert.equal(history[1].content,finished.result.answer);
 await open(first.id);await p.getByText('Поток начат. Ответ сохранён.',{exact:true}).first().waitFor();
 const before=(await api('/assistant')).quota.used;
 const replay=await cx.request.post(base+'/api/assistant/stream',{headers:{Origin:base},data:{job_id:saved.id}});
 assert(replay.ok());assert((await replay.text()).includes('event: done'));assert.equal((await api('/assistant')).quota.used,before);
 checks.push('live SSE continues after leaving the page; one saved answer and one token charge');
 const second=(await api('/assistant/conversations',{title:'Явная остановка'})).conversation;
 await open(second.id);const cancelled=await submit('UI cancel durable question');
 await p.locator('.assistant-message.assistant').filter({hasText:'Поток начат.'}).waitFor();
 await p.locator('#assistant-stop').click();
 await until(async()=>((await api('/assistant/jobs/'+cancelled.id)).job.status==='cancelled'));
 assert.equal((await api('/assistant/conversations/'+second.id)).messages.length,0);
 assert.equal(await p.locator('#assistant-input').inputValue(),'UI cancel durable question');
 checks.push('Stop cancels the durable job and restores the draft without saved partial history');
 const third=(await api('/assistant/conversations',{title:'Фото в сохранённом запросе'})).conversation;
 await open(third.id);
 const image=fs.readFileSync(process.env.SMETRA_VAULT_IMAGE||'data/durable-photo.png');
 await p.locator('#assistant-attach-input').setInputFiles({name:'Объект.png',mimeType:'image/png',buffer:image});
 await p.locator('.assistant-attachment-tile').waitFor();const photo=await submit('Посмотри прикреплённое фото');
 await until(async()=>((await api('/assistant/jobs/'+photo.id)).job.status==='completed'));
 assert.equal(await p.locator('.assistant-attachment-tile').count(),0);
 assert((await api('/files?type=images&archived=0')).items.some(file=>file.name==='Объект.png'));
 checks.push('photos are saved once and referenced by the durable vision request');
 for(const width of [320,390,768,1440]){
  await p.setViewportSize({width,height:900});assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Overflow '+width);
 }
 assert.deepEqual(errors,[]);fs.writeFileSync('data/qa/assistant-durable-browser-result.json',JSON.stringify({checks,errors},null,2));
 console.log(JSON.stringify({checks,errors}));await browser.close();
})().catch(error=>{console.error(error.stack);process.exit(1)});
