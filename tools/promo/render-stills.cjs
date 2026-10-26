// Renders the promo stills to tools/promo/stills/NN.png. Usage: node render-stills.cjs [index ...]
const { chromium } = require('playwright'); const fs = require('fs');
(async () => {
  const b = await chromium.launch(process.env.SOFTWARE_GL ? { args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] } : { args: ['--ignore-gpu-blocklist', '--enable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1080, height: 1350 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await p.goto((process.env.ORIGIN || 'http://localhost:8000') + '/tools/promo/stills.html');
  await p.waitForFunction(() => window.READY === true, null, { timeout: 60000 });
  const n = await p.evaluate(() => STILL_COUNT), list = process.argv.slice(2).map(Number);
  fs.mkdirSync(__dirname + '/stills', { recursive: true });
  for (const i of list.length ? list : [...Array(n).keys()]) {
    await p.evaluate(i => renderStill(i), i);
    await (await p.$('#out')).screenshot({ path: `${__dirname}/stills/${String(i + 1).padStart(2, '0')}.png` });
    console.log('still', i + 1);
  }
  if (errs.length) console.log(errs.join('\n'));
  await b.close();
})();
