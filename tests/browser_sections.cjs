/* All workspace routes, using only an isolated fixture and owned QA Chrome. */
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
  const site='http://localhost:'+(process.env.SMETRA_TEST_PORT||'8084');
  const tabs=await(await fetch('http://127.0.0.1:'+(process.env.SMETRA_CDP_PORT||'9223')+'/json')).json();
  const ws=new WebSocket(tabs.find(tab=>tab.type==='page').webSocketDebuggerUrl);
  await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}));
  let seq=0;const pending=new Map(),errors=[],assetFailures=[],requested=new Set();
  ws.addEventListener('message',event=>{const data=JSON.parse(event.data);if(data.id){const request=pending.get(data.id);pending.delete(data.id);data.error?request.reject(data.error):request.resolve(data.result)}else if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.text)});
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
  ws.addEventListener('message',event=>{const data=JSON.parse(event.data);if(data.method==='Network.requestWillBeSent')requested.add(new URL(data.params.request.url).pathname);if(data.method==='Network.responseReceived'&&data.params.response.status>=400){const response=data.params.response;if(/\.(js|css|woff2?|ttf|png|svg|webmanifest)$/.test(new URL(response.url).pathname))assetFailures.push(response.status+' '+response.url)}});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,userGesture:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value};
  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const until=async expression=>{for(let attempt=0;attempt<100;attempt++){if(await evaluate(expression))return;await wait(100)}throw Error('Timeout: '+expression)};
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await send('Network.deleteCookies',{name:'session',url:site});
  await send('Page.navigate',{url:site+'/app'});
  await until("document.querySelector('#auth-form')?.onsubmit");
  await evaluate("document.querySelector('#email').value='android-design@test.invalid';document.querySelector('#password').value='android design test only';document.querySelector('#auth-submit').click()");
  await until("document.querySelector('.workspace-home')");
  for(const file of ['assistant-chat.js','ai-workspace.js','profile-ui.js','admin.js','construction.js','vendor/markdown-it-15.0.2.min.js'])assert.equal(requested.has('/'+file),false,'Initial screen should defer '+file);
  const testTask=await evaluate("api('/tasks',{method:'POST',body:JSON.stringify({name:'Mobile deadline check',due_date:'2026-10-06'})}).then(result=>result.item)");
  fs.mkdirSync('data/qa',{recursive:true});
  const routes=['dashboard','clients','quotes','projects','construction','leads','tasks','calendar','assistant','finance','catalog','files','documents','team','notifications','billing','support','profile','settings','activity'];
  if(await evaluate("user.role==='admin'"))routes.push('admin');
  for(const route of routes){
    await evaluate(`tab=${JSON.stringify(route)};render()`);
    await until(`document.querySelector('#content').dataset.section===${JSON.stringify(route)}`);
    assert.equal(await evaluate("!!document.querySelector('#retry')"),false,route+' failed to load');
    for(const width of [320,360,375,390,412,430,768,1440]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<701});
      await evaluate('window.scrollTo({top:0,behavior:"instant"})');await wait(200);
      assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,route+' overflows at '+width);
      if([390,1440].includes(width))fs.writeFileSync(`data/qa/section-${route}-${width}.png`,Buffer.from((await send('Page.captureScreenshot')).data,'base64'));
    }
    if(route==='clients')assert.equal(await evaluate("!!document.querySelector('.contact-group .contact-monogram')"),true);
    if(route==='construction'){
      await send('Emulation.setDeviceMetricsOverride',{width:390,height:900,deviceScaleFactor:1,mobile:true});
      await evaluate("document.querySelector('.construction-object').click()");
      await until("document.querySelector('.construction-entry')");
      assert.equal(await evaluate("document.querySelector('.construction-entry').open"),false);
      await evaluate("document.querySelector('.construction-entry summary').click()");
      assert.equal(await evaluate("document.querySelector('.construction-entry').open"),true);
      assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true);
    }
    if(route==='tasks'){
      assert.equal(await evaluate("!!document.querySelector('.task-group')"),true);
      await evaluate(`document.querySelector('[data-work=task-toggle][data-id="${testTask.id}"]').click()`);
      await until(`document.querySelector('[data-work=task-toggle][data-id="${testTask.id}"]').getAttribute('aria-checked')==='true'`);
      assert.equal(await evaluate(`api('/tasks/${testTask.id}').then(result=>result.item.status)`),'done');
      await evaluate(`document.querySelector('[data-work=task-toggle][data-id="${testTask.id}"]').click()`);
      await until(`document.querySelector('[data-work=task-toggle][data-id="${testTask.id}"]').getAttribute('aria-checked')==='false'`);
    }
    if(route==='calendar')assert.equal(await evaluate("!!document.querySelector('.agenda-day')"),true);
    if(route==='support'){
      await evaluate("document.querySelector('[data-support-topic]').click()");
      assert.equal(await evaluate("document.querySelector('#message').value.length>0"),true);
    }
  }
  assert.deepEqual(errors,[]);assert.deepEqual(assetFailures,[]);console.log('PASS: '+routes.length+' routes at 320/360/375/390/412/430/768/1440px; initial scripts deferred; contact directory, task groups, calendar, support topics; no overflow, missing assets or browser errors');ws.close();
})().catch(error=>{console.error(error);process.exit(1)});
