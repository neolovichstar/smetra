const assert = require('node:assert/strict');

(async () => {
  const site = 'http://localhost:' + (process.env.SMETRA_TEST_PORT || '8082');
  const debuggerUrl = 'http://127.0.0.1:' + (process.env.SMETRA_CDP_PORT || '9223') + '/json';
  const tabs = await (await fetch(debuggerUrl)).json();
  const ws = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
  await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }));
  let seq = 0;
  const pending = new Map();
  const requests = [];
  ws.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const item = pending.get(message.id);
      pending.delete(message.id);
      if (item) message.error ? item.reject(message.error) : item.resolve(message.result);
    } else if (message.method === 'Network.requestWillBeSent') {
      requests.push(message.params.request.url);
    }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', {
      expression, returnByValue: true, awaitPromise: true, userGesture: true
    });
    if (result.exceptionDetails) {
      throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    }
    return result.result.value;
  };
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const until = async expression => {
    for (let index = 0; index < 80; index++) {
      if (await evaluate(expression)) return;
      await wait(100);
    }
    throw Error('Timeout waiting for: ' + expression);
  };

  await send('Page.enable');
  await send('Runtime.enable');
  await send('Network.enable');
  await send('Network.setCacheDisabled', { cacheDisabled: true });
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1440, height: 1050, deviceScaleFactor: 1, mobile: false
  });
  await send('Emulation.setEmulatedMedia', {
    features: [{ name: 'prefers-reduced-motion', value: 'no-preference' }]
  });
  await send('Page.navigate', { url: site + '/?ref=landing-motion-qa' });
  await until("document.querySelector('[data-motion-scene] .motion-orbit-one')");
  await until("document.querySelector('#preview-document table')");
  await wait(150);

  assert.equal(
    await evaluate("sessionStorage.getItem('smetra.referral')"),
    'landing-motion-qa',
    'Referral attribution is retained by the lean landing runtime'
  );
  assert.equal(
    requests.some(url => new URL(url).pathname === '/app.js' || new URL(url).pathname === '/workspace.js'),
    false,
    'A regular landing visit must not eagerly download the cabinet runtime'
  );
  assert.equal(
    await evaluate("getComputedStyle(document.querySelector('.motion-orbit-one')).animationName"),
    'motion-orbit-drift',
    'The hero scene uses CSS-composited motion'
  );

  const rect = await evaluate("(function(){const r=document.querySelector('[data-motion-scene]').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})()");
  await send('Input.dispatchMouseEvent', {
    type: 'mouseMoved',
    x: rect.x + rect.width * 0.78,
    y: rect.y + rect.height * 0.34
  });
  await until("document.querySelector('[data-motion-scene]').style.getPropertyValue('--scene-x') !== ''");
  assert.notEqual(
    await evaluate("document.querySelector('[data-motion-scene]').style.getPropertyValue('--scene-x')"),
    '0.00px',
    'Desktop pointer movement should drive subtle parallax'
  );

  await send('Emulation.setEmulatedMedia', {
    features: [{ name: 'prefers-reduced-motion', value: 'reduce' }]
  });
  await wait(100);
  assert.equal(
    await evaluate("getComputedStyle(document.querySelector('.motion-orbit-one')).animationName"),
    'none',
    'Reduced-motion preference disables orbit animation'
  );
  assert.equal(
    await evaluate("getComputedStyle(document.querySelector('[data-motion-scene]')).transitionDuration"),
    '0s',
    'Reduced-motion preference disables pointer transitions'
  );
  ws.close();
  process.stdout.write('Landing motion: PASS (lazy cabinet loading, referral persistence, pointer parallax, reduced motion)\\n');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
