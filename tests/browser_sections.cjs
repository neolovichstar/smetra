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
  await until("document.querySelector('link[rel=\\\"prefetch\\\"][href*=\\\"/assistant-chat.js\\\"]')");
  for(const file of ['assistant-chat.js','ai-workspace.js','profile-ui.js','admin.js','construction.js','vendor/markdown-it-15.0.2.min.js']){
    const state=await evaluate(`(()=>({executed:!!document.querySelector('script[src*=${JSON.stringify('/'+file)}]'),prefetched:!!document.querySelector('link[rel="prefetch"][href*=${JSON.stringify('/'+file)}]')}))()`);
    assert.equal(state.executed,false,'Initial screen must not execute '+file);
    if(['assistant-chat.js','ai-workspace.js','profile-ui.js','admin.js','construction.js','vendor/markdown-it-15.0.2.min.js'].includes(file))assert.equal(state.prefetched,true,'Idle-prefetch should warm '+file+' without executing it');
  }
  assert.equal(await evaluate("typeof window.SmetraAssistant"),'undefined','Assistant stays uninitialized until its section opens');
  const testTask=await evaluate("api('/tasks',{method:'POST',body:JSON.stringify({name:'Mobile deadline check',due_date:'2026-10-06'})}).then(result=>result.item)");
  fs.mkdirSync('data/qa',{recursive:true});
  const routes=process.env.SMETRA_REVENUE_QA==='1'?['billing']:['dashboard','clients','quotes','projects','construction','calculators','timeline','leads','tasks','calendar','assistant','finance','catalog','files','documents','team','notifications','billing','support','profile','settings','activity'];
  if(await evaluate("user.role==='admin'"))routes.push('admin');
  for(const route of routes){
    await evaluate(`tab=${JSON.stringify(route)};render()`);
    await until(`document.querySelector('#content').dataset.section===${JSON.stringify(route)}`);
    assert.equal(await evaluate("!!document.querySelector('#retry')"),false,route+' failed to load');
    for(const width of [320,360,375,390,412,430,768,1440]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<701});
      await evaluate('window.scrollTo({top:0,behavior:"instant"})');await wait(200);
      assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,route+' overflows at '+width);
      if(route==='assistant'){
        const layout=await evaluate(`(()=>{const c=document.querySelector('.assistant-content'),p=document.querySelector('.assistant-composer'),s=document.querySelector('.assistant-studio'),m=document.querySelector('.main'),r=e=>{const x=e.getBoundingClientRect(),z=getComputedStyle(e);return {top:Math.round(x.top),bottom:Math.round(x.bottom),height:Math.round(x.height),minHeight:z.minHeight,heightCss:z.height,position:z.position,flex:z.flex,overflow:z.overflow}};return {viewport:innerHeight,content:r(c),composer:r(p),studio:r(s),main:r(m),scrollHeight:document.documentElement.scrollHeight}})()`);
        assert.equal(layout.content.bottom<=layout.composer.top+1&&layout.composer.bottom<=900+1,true,'Assistant composer overlaps content or viewport at '+width+': '+JSON.stringify(layout));
        await evaluate("document.querySelector('.assistant-content').scrollTop=document.querySelector('.assistant-content').scrollHeight");
        assert.equal(await evaluate(`(()=>{const job=document.querySelector('.assistant-job'),form=document.querySelector('#assistant-form'),composer=document.querySelector('.assistant-composer');return !job||(form.contains(job)&&job.getBoundingClientRect().top>=composer.getBoundingClientRect().top&&job.getBoundingClientRect().bottom<=form.getBoundingClientRect().bottom+1)})()`),true,'Background jobs must stay attached to the composer and visible at '+width);
      }
      if([390,1440].includes(width))fs.writeFileSync(`data/qa/section-${route}-${width}.png`,Buffer.from((await send('Page.captureScreenshot')).data,'base64'));
    }
    if(route==='quotes')assert.equal(await evaluate(`(()=>{const sheet=document.querySelector('.quotes-document'),heading=document.querySelector('#quotes-register-title'),search=document.querySelector('#workspace-search'),list=document.querySelector('#records');return !!sheet&&!!heading&&!!search&&!!list&&list.classList.contains('quotes-document-list')})()`),true,'Quotes page must render as a document register');
    if(route==='assistant'){
      assert.equal(await evaluate("(()=>{const rail=document.querySelector('.assistant-toolrail'),workbar=document.querySelector('#assistant-workbar'),toggle=document.querySelector('#assistant-toolrail-toggle'),main=document.querySelector('.assistant-main-column');return !!rail&&!!workbar&&!!toggle&&!!main&&rail.contains(workbar)&&rail.getBoundingClientRect().right<=main.getBoundingClientRect().left+1})()"),true,'Conversation controls must live in the left sub-sidebar');
      await evaluate("document.querySelector('#assistant-toolrail-toggle').click()");
      assert.equal(await evaluate("document.querySelector('.assistant-studio').classList.contains('assistant-tools-collapsed')"),true,'Left sub-sidebar should collapse to an icon rail');
      await evaluate("document.querySelector('#assistant-toolrail-toggle').click()");
      assert.equal(await evaluate("document.querySelector('#assistant-toolrail-toggle').getAttribute('aria-expanded')"),'true','Left sub-sidebar toggle must restore full width');
      assert.equal(await evaluate("(()=>{const m=document.querySelector('.assistant-message.assistant');return !m||['copy','refresh','up','down'].every(k=>!!m.querySelector('.assistant-action-'+k+' svg'))})()"),true,'AI answer actions use SVG icons');
    }
    if(route==='assistant'&&await evaluate("matchMedia('(min-width:801px)').matches")){
      assert.equal(await evaluate("document.querySelectorAll('#sidebar .sidebar-group button[data-tab] .sidebar-item-icon').length>=15"),true,'Main navigation should use a complete set of SVG icons');
      assert.equal(await evaluate("Array.from(document.querySelectorAll('#sidebar .sidebar-group button[data-tab]')).every(b=>b.querySelectorAll('svg').length===1&&b.querySelectorAll('.sidebar-item-icon').length===1)"),true,'Each main navigation item must have exactly one SVG icon');
      await evaluate("(()=>{const b=document.querySelector('#sidebar .sidebar-group button[data-tab]');const extra=document.createElementNS('http://www.w3.org/2000/svg','svg');extra.classList.add('legacy-sidebar-icon');b.append(extra)})()");
      await until("document.querySelector('#sidebar .sidebar-group button[data-tab]').querySelectorAll('svg').length===1");
      assert.equal(await evaluate("(()=>{const s=document.querySelector('#logout svg'),p=document.querySelector('#sidebar-profile'),a=document.querySelector('#sidebar-avatar'),sidebar=document.querySelector('#sidebar');return !!s&&s.getBoundingClientRect().width<=20&&s.getBoundingClientRect().height<=20&&!!p&&!!a&&parseFloat(getComputedStyle(sidebar).width)>=240})()"),true,'ChatGPT-like sidebar keeps its profile row and bounded logout SVG');
      await evaluate("document.querySelector('#sidebar-collapse').click()");
      assert.equal(await evaluate("document.body.classList.contains('sidebar-compact')"),true,'Main sidebar should collapse to icon rail');
      await evaluate("document.querySelector('#sidebar-collapse').click()");
      assert.equal(await evaluate("document.body.classList.contains('sidebar-compact')"),false,'Main sidebar should expand again');
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
  if(await evaluate("user.role==='admin'")){
    await evaluate("tab='admin';render()");await until("document.querySelector('[data-admin-section=revenue]')");
    await evaluate("document.querySelector('[data-admin-section=revenue]').click()");await until("document.querySelector('.admin-revenue-metrics')");
    for(const width of [320,390,1440]){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<701});await wait(200);assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'Revenue overflow '+width)}
    fs.writeFileSync('data/qa/section-revenue-1440.png',Buffer.from((await send('Page.captureScreenshot')).data,'base64'));
  }
  assert.deepEqual(errors,[]);assert.deepEqual(assetFailures,[]);console.log('PASS: '+routes.length+' routes at 320/360/375/390/412/430/768/1440px; initial scripts deferred; contact directory, task groups, calendar, support topics; no overflow, missing assets or browser errors');ws.close();
})().catch(error=>{console.error(error);process.exit(1)});
