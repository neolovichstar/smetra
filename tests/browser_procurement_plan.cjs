/* Run with an isolated Smetra server and Chrome CDP. Exercises price editing in the real web UI. */
const assert = require('node:assert/strict');
(async () => {
  const site = 'http://localhost:' + (process.env.SMETRA_TEST_PORT || '8082');
  const debuggerUrl = 'http://127.0.0.1:' + (process.env.SMETRA_CDP_PORT || '9223') + '/json';
  const tabs = await (await fetch(debuggerUrl)).json();
  const ws = new WebSocket(tabs.find(item => item.type === 'page').webSocketDebuggerUrl);
  await new Promise(resolve => ws.addEventListener('open', resolve, {once:true}));
  let seq = 0;
  const pending = new Map(), errors = [];
  ws.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const task = pending.get(message.id);
      pending.delete(message.id);
      message.error ? task.reject(message.error) : task.resolve(message.result);
    } else if (message.method === 'Runtime.exceptionThrown') {
      errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
    }
  });
  const send = (method, params={}) => new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, {resolve, reject});
    ws.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const response = await send('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true, userGesture:true});
    if (response.exceptionDetails) throw Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);
    return response.result.value;
  };
  const until = async expression => {
    for (let attempt=0; attempt<100; attempt++) {
      if (await evaluate(expression)) return;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw Error('Timeout: ' + expression + '\n' + await evaluate('document.body.innerText.slice(-1000)'));
  };
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride', {width:390,height:844,deviceScaleFactor:1,mobile:true});
  await send('Page.navigate', {url:site + '/app?register=1'});
  await until("(document.querySelector('#auth')&&!document.querySelector('#auth').classList.contains('hidden'))||document.querySelector('[data-work=quote-new]')");
  if (await evaluate("!document.querySelector('#auth').classList.contains('hidden')")) {
    await evaluate("fetch('/api/auth/register',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Проверка расценок',email:'procurement-browser-'+Date.now()+'@test.invalid',password:'long secure password',legal_acceptance:true,legal_version:'2026-10-19-registration-v1'})}).then(r=>r.status)");await send('Page.navigate',{url:site+'/app#dashboard'});
  }
  await until("document.querySelector('[data-work=quote-new]')");
  assert.deepEqual(await evaluate("Promise.all(['/construction.js','/ui/modules.css','/ai-workspace.js','/file-editor.js','/ui/components.css'].map(path=>fetch(path).then(response=>response.status)))"), [200,200,200,200,200]);
  const objectId = await evaluate(`(async()=>{
    const object=(await api('/construction/objects',{method:'POST',body:JSON.stringify({name:'План закупок / проверка'})})).object;
    const base='/construction/objects/'+object.id;
    const materials=[];
    for(const [name,quantity,cost] of [['Кухня','5',1000],['Гостиная','15',1200]]){
      const zone=(await api(base+'/zones',{method:'POST',body:JSON.stringify({name,length:'5',width:'4'})})).zone;
      const material=(await api(base+'/quantities',{method:'POST',body:JSON.stringify({zone_id:zone.id,kind:'material',title:'Краска <strong>белая</strong>',unit:'л',formula:quantity,unit_price:2000,cost_price:cost})})).quantity;
      materials.push(material.id);
    }
    for(const [material_id,quantity,price,status,day] of [[materials[0],'12',1100,'received','2026-11-07'],[materials[1],'2',1300,'ordered','2026-11-08']])await api(base+'/purchases',{method:'POST',body:JSON.stringify({material_id,quantity,unit_price_kopecks:price,status,purchased_on:day})});
    const closed=(await api(base+'/quantities',{method:'POST',body:JSON.stringify({kind:'material',title:'Клей',unit:'кг',formula:'2',unit_price:900,cost_price:500})})).quantity;
    await api(base+'/purchases',{method:'POST',body:JSON.stringify({material_id:closed.id,quantity:'2',unit_price_kopecks:500,status:'received',purchased_on:'2026-11-08'})});
    return object.id;
  })()`);
  await evaluate("document.querySelector('[data-tab=construction]').click()");
  await until(`document.querySelector('.construction-object[data-id="${objectId}"]')`);
  await evaluate(`document.querySelector('.construction-object[data-id="${objectId}"]').click()`);
  await until("document.querySelectorAll('.procurement-material').length===2");
  assert.match(await evaluate("document.querySelector('.procurement-summary').innerText"), /2 групп материалов из 3 позиций/);
  assert.match(await evaluate("document.querySelector('.procurement-material').innerText"), /Докупить 6 л/);
  assert.equal(await evaluate("document.querySelector('.procurement-material header strong').textContent"), 'Краска <strong>белая</strong>');
  assert.equal(await evaluate("document.querySelector('.procurement-material header strong strong')===null"), true);
  assert.match(await evaluate("document.querySelector('.procurement-material').innerText"), /Кухня.*Гостиная|Гостиная.*Кухня/s);
  assert.match(await evaluate("document.querySelector('.procurement-budget').innerText"), /246,00/);
  await evaluate("document.querySelector('[data-procurement-filter]').click()");
  await until("document.querySelectorAll('.procurement-material').length===1");
  await evaluate("const input=document.querySelector('.procurement-scenario input');input.value='10';input.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('.procurement-scenario [type=submit]').click()");
  await until("document.querySelector('.procurement-budget')?.innerText.includes('253,80')");
  const unchanged=await evaluate(`api('/construction/objects/${objectId}').then(r=>({prices:r.purchases.map(p=>p.unit_price_kopecks).sort((a,b)=>a-b),quantities:r.quantities.map(q=>q.quantity).sort()}))`);
  assert.deepEqual(unchanged.prices,[500,1100,1300]);
  assert.deepEqual(unchanged.quantities,['15.0000','2.0000','5.0000']);
  await evaluate("document.querySelector('[data-procurement-reset]').click()");
  await until("document.querySelector('.procurement-budget')?.innerText.includes('246,00')");
  assert.equal(await evaluate("document.querySelector('#construction-material [name=unit]').value"),'л');
  assert.equal(await evaluate("document.querySelector('#construction-quantity [name=unit]').value"),'м²');
  assert.equal(await evaluate("Array.from(document.querySelector('#construction-material [name=unit]').options).some(o=>o.value==='кг')"),true);
  // The UI download must actually reach the authenticated XLSX endpoint.
  let exports=0;
  ws.addEventListener('message',event=>{const msg=JSON.parse(event.data);if(msg.method==='Network.responseReceived'&&msg.params.response.url.includes('/procurement-plan.xlsx')&&msg.params.response.status===200)exports++});
  await evaluate("document.querySelector('[data-procurement-export]').click()");
  for(let i=0;i<50&&!exports;i++)await new Promise(resolve=>setTimeout(resolve,100));
  assert.equal(exports,1);
  fs.mkdirSync('data/qa',{recursive:true});
  for(const width of [320,390,1440]){
    await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width<700});
    await evaluate("document.querySelector('#construction-procurement-plan').scrollIntoView({block:'start'})");
    assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'Overflow at '+width);
    const screenshot=await send('Page.captureScreenshot',{format:'png'});
    fs.writeFileSync('data/qa/procurement-'+width+'.png',Buffer.from(screenshot.data,'base64'));
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: pooled materials across rooms, retained purchase costs, future-price scenario/reset, supplier download, escaped names, selectable units and 320/390/1440px layouts');
  ws.close();
})().catch(error=>{console.error(error);process.exit(1)});
