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
    await evaluate(`document.querySelector('#name').value='Проверка расценок';document.querySelector('#email').value='bulk-browser-${Date.now()}@test.invalid';document.querySelector('#password').value='long secure password';document.querySelector('#auth-submit').click()`);
  }
  await until("document.querySelector('[data-work=quote-new]')");
  assert.deepEqual(await evaluate("Promise.all(['/construction.js','/construction.css','/ai-workspace.js','/file-editor.js','/file-editor.css'].map(path=>fetch(path).then(response=>response.status)))"), [200,200,200,200,200]);
  const objectId = await evaluate(`(async()=>{
    const object=(await api('/construction/objects',{method:'POST',body:JSON.stringify({name:'Проверка расценок'})})).object;
    const zone=(await api('/construction/objects/'+object.id+'/zones',{method:'POST',body:JSON.stringify({name:'Комната',length:'5',width:'4'})})).zone;
    for(const [title,unit_price] of [['Покраска',10000],['Штукатурка',20000]])await api('/construction/objects/'+object.id+'/quantities',{method:'POST',body:JSON.stringify({zone_id:zone.id,kind:'work',title,formula:'area',unit_price})});
    return object.id;
  })()`);
  await evaluate("document.querySelector('[data-tab=construction]').click()");
  await until("document.querySelector('.construction-object')");
  await evaluate("document.querySelector('.construction-object').click()");
  await until("document.querySelectorAll('.construction-price-select').length===2");
  assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'), true);
  await evaluate("document.querySelector('#construction-price-all').click();document.querySelector('#construction-prices [type=submit]').click()");
  await until("document.querySelector('#construction-price-apply')");
  assert.match(await evaluate("document.querySelector('#construction-price-preview').innerText"), /108|216/);
  assert.equal((await evaluate(`api('/construction/objects/${objectId}').then(r=>r.quantities.map(x=>x.unit_price).sort((a,b)=>a-b))`)).join(','), '10000,20000');
  await evaluate("document.querySelector('#construction-price-apply').click()");
  await until("document.querySelector('#construction-price-undo')");
  assert.equal((await evaluate(`api('/construction/objects/${objectId}').then(r=>r.quantities.map(x=>x.unit_price).sort((a,b)=>a-b))`)).join(','), '10800,21600');
  await evaluate("document.querySelector('#construction-price-undo').click()");
  await until("!document.querySelector('#construction-price-undo')");
  assert.equal((await evaluate(`api('/construction/objects/${objectId}').then(r=>r.quantities.map(x=>x.unit_price).sort((a,b)=>a-b))`)).join(','), '10000,20000');
  assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'), true);
  assert.deepEqual(errors, []);
  console.log('PASS: mobile price preview, apply and undo; no horizontal overflow or browser errors');
  ws.close();
})().catch(error => {console.error(error);process.exit(1)});
