/* Captures real screens of the Smetra app through the Chrome DevTools Protocol.
   In CI it drives the debug APK's WebView inside an Android emulator (adb forwards
   the WebView devtools socket) and takes device screenshots with `adb screencap`,
   so status bar, insets and the native shell are in the picture. Locally it can
   drive any Chrome with --remote-debugging-port for a quick dry run.

   Env: SMETRA_CDP (http://127.0.0.1:9222), SMETRA_ORIGIN (page origin),
        SMETRA_SESSION (fixture session token), SMETRA_SCREENS_DIR (output),
        SMETRA_SCREENCAP=adb to capture the whole device screen. */
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const CDP = process.env.SMETRA_CDP || 'http://127.0.0.1:9222';
const ORIGIN = (process.env.SMETRA_ORIGIN || 'http://10.0.2.2:8090').replace(/\/$/, '');
const SESSION = (process.env.SMETRA_SESSION || '').trim();
const OUT = path.resolve(process.env.SMETRA_SCREENS_DIR || 'data/android-screens');
const ADB = process.env.SMETRA_SCREENCAP === 'adb';

// Every screen is a real route of the app with data from the isolated fixture.
const SCREENS = [
  { id: '01-dashboard', hash: 'dashboard', title: 'Главная' },
  { id: '02-quotes', hash: 'quotes', title: 'Сметы' },
  { id: '04-construction', hash: 'construction', title: 'Объекты', wait: '.construction-object' },
  { id: '05-object', hash: 'construction', title: 'Помещения и объёмы', wait: '.construction-object', click: '.construction-object', settle: 1800 },
  { id: '06-calculators', hash: 'calculators', title: 'Калькуляторы' },
  { id: '07-projects', hash: 'projects', title: 'Заказы и этапы' },
  { id: '08-clients', hash: 'clients', title: 'Клиенты' },
  { id: '09-finance', hash: 'finance', title: 'Деньги' },
  { id: '10-tokens', hash: 'billing', title: 'Токены ИИ', wait: '[data-billing-tab="tokens"]', click: '[data-billing-tab="tokens"]', settle: 1500 },
  // Last on purpose: the emulator has died on this screen, and the rest must still be captured.
  { id: '03-assistant', hash: 'assistant', title: 'ИИ-ассистент', wait: '.assistant-message, .assistant-thread, #assistant-input' },
];

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function target() {
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      const list = await (await fetch(CDP + '/json')).json();
      const page = list.find(item => item.type === 'page' && item.webSocketDebuggerUrl && item.url.startsWith(ORIGIN))
        || list.find(item => item.type === 'page' && item.webSocketDebuggerUrl);
      if (page) return page;
    } catch {}
    await sleep(1000);
  }
  throw Error('No debuggable page at ' + CDP);
}

function connect(url) {
  const socket = new WebSocket(url);
  const waiting = new Map(), events = [];
  let id = 0;
  socket.onmessage = message => {
    const data = JSON.parse(message.data);
    if (data.id && waiting.has(data.id)) {
      const { resolve, reject } = waiting.get(data.id);
      waiting.delete(data.id);
      data.error ? reject(Error(data.error.message)) : resolve(data.result);
    } else if (data.method) events.push(data);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const key = ++id;
    waiting.set(key, { resolve, reject });
    socket.send(JSON.stringify({ id: key, method, params }));
  });
  return new Promise((resolve, reject) => {
    socket.onopen = () => resolve({ send, events, close: () => socket.close() });
    socket.onerror = () => reject(Error('CDP socket failed'));
  });
}

async function evaluate(cdp, expression) {
  const result = await cdp.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || 'evaluate failed');
  return result.result.value;
}

async function until(cdp, expression, timeout = 15000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    try { if (await evaluate(cdp, expression)) return Date.now() - started; } catch {}
    await sleep(150);
  }
  return -1;
}

// "Smetra UI Critic": layout and accessibility checks on the live DOM of each screen.
const CRITIC = `(() => {
  const vw = innerWidth, vh = innerHeight, issues = [];
  const visible = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && Number(s.opacity) > 0.05 && r.bottom > 0 && r.top < vh; };
  const scroller = el => { for (let node = el.parentElement; node && node !== document.body; node = node.parentElement) { const x = getComputedStyle(node).overflowX; if (x === 'auto' || x === 'scroll' || x === 'hidden') return true; } return false; };
  const label = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.classList.length ? '.' + [...el.classList].slice(0, 2).join('.') : '');
  if (document.documentElement.scrollWidth > vw + 1) issues.push({ rule: 'horizontal-scroll', detail: document.documentElement.scrollWidth + 'px > ' + vw + 'px' });
  const wide = [...document.querySelectorAll('#content *')].filter(el => visible(el) && el.getBoundingClientRect().right > vw + 2
    && !scroller(el));
  if (wide.length) issues.push({ rule: 'overflow-x', detail: wide.slice(0, 5).map(label).join(', '), count: wide.length });
  const small = [...document.querySelectorAll('button, [role=button], a.btn, input, select, textarea')].filter(el => {
    if (!visible(el) || el.closest('p, li')) return false;
    const r = el.getBoundingClientRect();
    return Math.min(r.width, r.height) < 32;
  });
  if (small.length) issues.push({ rule: 'tap-target<32px', detail: small.slice(0, 5).map(label).join(', '), count: small.length });
  const nameless = [...document.querySelectorAll('button, [role=button]')].filter(el => visible(el) && !(el.textContent.trim() || el.getAttribute('aria-label') || el.title));
  if (nameless.length) issues.push({ rule: 'button-without-name', detail: nameless.slice(0, 5).map(label).join(', '), count: nameless.length });
  const broken = [...document.images].filter(img => visible(img) && img.complete && !img.naturalWidth);
  if (broken.length) issues.push({ rule: 'broken-image', count: broken.length });
  const rgb = value => (value.match(/[\\d.]+/g) || []).map(Number);
  const lum = ([r, g, b]) => { const f = c => (c /= 255) <= .03928 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
  const background = el => { for (let node = el; node; node = node.parentElement) { const c = rgb(getComputedStyle(node).backgroundColor); if (c.length >= 3 && (c[3] === undefined || c[3] > .9)) return c; } return [10, 10, 11]; };
  let lowContrast = [];
  for (const el of document.querySelectorAll('#content p, #content span, #content small, #content strong, #content h1, #content h2, #content h3, #content button, #content label, #content td')) {
    if (!visible(el) || !el.childNodes.length || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    const s = getComputedStyle(el), fg = rgb(s.color);
    if (fg[3] !== undefined && fg[3] < 1) continue;
    const a = lum(fg), b = lum(background(el)), ratio = (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
    const large = parseFloat(s.fontSize) >= 24 || (parseFloat(s.fontSize) >= 18.6 && Number(s.fontWeight) >= 700);
    if (ratio < (large ? 3 : 4.5)) lowContrast.push(label(el) + ' ' + ratio.toFixed(2));
  }
  if (lowContrast.length) issues.push({ rule: 'contrast', detail: lowContrast.slice(0, 5).join(', '), count: lowContrast.length });
  const alerts = [...document.querySelectorAll('.toast.error, .error-state, [role=alert]')].filter(visible).map(el => el.textContent.trim()).filter(Boolean);
  if (alerts.length) issues.push({ rule: 'error-visible', detail: alerts.slice(0, 3).join(' | ') });
  const text = (document.querySelector('#content')?.innerText || '').trim();
  if (text.length < 40) issues.push({ rule: 'empty-screen', detail: text.length + ' chars of content' });
  return { viewport: vw + 'x' + vh, dpr: devicePixelRatio, theme: document.documentElement.dataset.theme || 'dark', issues };
})()`;

async function capture(cdp, file) {
  if (ADB) {
    execFileSync('adb', ['shell', 'screencap', '-p', '/sdcard/smetra-shot.png'], { timeout: 30000 });
    execFileSync('adb', ['pull', '/sdcard/smetra-shot.png', file], { timeout: 30000 });
    return;
  }
  const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(file, Buffer.from(shot.data, 'base64'));
}

(async () => {
  if (!SESSION) throw Error('SMETRA_SESSION is required');
  fs.mkdirSync(path.join(OUT, 'raw'), { recursive: true });
  const cdp = await connect((await target()).webSocketDebuggerUrl);
  await cdp.send('Runtime.enable');
  await cdp.send('Network.enable');
  await cdp.send('Page.enable');
  // The fixture session goes in as the same HttpOnly cookie the native login sets.
  await cdp.send('Network.setCookie', { name: 'session', value: SESSION, url: ORIGIN + '/', path: '/', httpOnly: true, sameSite: 'Lax' });
  if (!ADB) {
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: 412, height: 915, deviceScaleFactor: 2.625, mobile: true });
    await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
  }
  // A full load, never a same-document hash change, so no state survives from an earlier session.
  await cdp.send('Page.navigate', { url: 'about:blank' });
  await sleep(300);
  const started = Date.now();
  await cdp.send('Page.navigate', { url: ORIGIN + '/app#dashboard' });
  const ready = await until(cdp, `Boolean(document.querySelector('#content') && document.querySelector('#content').innerText.trim().length > 40 && !document.querySelector('#app-startup:not([aria-hidden="true"])'))`, 30000);
  if (ready < 0) throw Error('Cabinet did not load: ' + await evaluate(cdp, `location.href + ' | ' + (document.querySelector('#content')?.innerText || '').slice(0, 160) + ' | ' + (document.querySelector('#app-startup')?.outerHTML || '').slice(0, 160)`));
  const timing = await evaluate(cdp, `(() => { const n = performance.getEntriesByType('navigation')[0] || {}; return { dom_content_loaded_ms: Math.round(n.domContentLoadedEventEnd || 0), load_ms: Math.round(n.loadEventEnd || 0), transfer_kb: Math.round((performance.getEntriesByType('resource').reduce((sum, r) => sum + (r.transferSize || 0), 0) + (n.transferSize || 0)) / 1024) }; })()`);
  const metrics = { origin: ORIGIN, capture: ADB ? 'adb screencap (device)' : 'CDP (browser)', cabinet_ready_ms: Date.now() - started, ...timing, screens: [] };
  const critic = [];
  for (const screen of SCREENS) {
    const begin = Date.now();
    await evaluate(cdp, `(() => { document.querySelectorAll('dialog[open]').forEach(d => d.close()); const next = ${JSON.stringify(screen.hash)}; if (location.hash.slice(1) === next) { location.hash = 'dashboard'; } return true; })()`);
    await sleep(300);
    await evaluate(cdp, `(location.hash = ${JSON.stringify(screen.hash)}, true)`);
    await until(cdp, `document.querySelector('#content') && document.querySelector('#content').innerText.trim().length > 40 && !document.querySelector('#content .skeleton, #content [aria-busy="true"]')`, 12000);
    if (screen.wait) await until(cdp, `Boolean(document.querySelector(${JSON.stringify(screen.wait)}))`, 12000);
    if (screen.click) await evaluate(cdp, `(document.querySelector(${JSON.stringify(screen.click)})?.click(), true)`);
    await sleep(screen.settle || 1100);
    await evaluate(cdp, '(scrollTo(0, 0), document.activeElement?.blur?.(), true)');
    await sleep(250);
    const rendered = Date.now() - begin;
    const file = path.join(OUT, 'raw', screen.id + '.png');
    await capture(cdp, file);
    const review = await evaluate(cdp, CRITIC);
    critic.push({ screen: screen.id, title: screen.title, ...review });
    metrics.screens.push({ id: screen.id, route: '/app#' + screen.hash, render_ms: rendered });
    console.log(screen.id, rendered + 'ms', review.issues.length ? review.issues.map(issue => issue.rule).join(',') : 'ok');
    fs.writeFileSync(path.join(OUT, 'ui-critic.json'), JSON.stringify({ generated_at: new Date().toISOString(), screens: critic, console_errors: [] }, null, 2));
    fs.writeFileSync(path.join(OUT, 'screens.json'), JSON.stringify(SCREENS.slice(0, SCREENS.indexOf(screen) + 1).map(({ id, title, hash }) => ({ id, title, route: '/app#' + hash, file: 'raw/' + id + '.png' })), null, 2));
  }
  const errors = cdp.events.filter(event => event.method === 'Runtime.exceptionThrown' || (event.method === 'Runtime.consoleAPICalled' && event.params.type === 'error'))
    .map(event => event.params.exceptionDetails?.exception?.description || (event.params.args || []).map(arg => arg.value || arg.description).join(' ')).slice(0, 20);
  metrics.console_errors = errors;
  fs.writeFileSync(path.join(OUT, 'metrics-web.json'), JSON.stringify(metrics, null, 2));
  fs.writeFileSync(path.join(OUT, 'ui-critic.json'), JSON.stringify({ generated_at: new Date().toISOString(), screens: critic, console_errors: errors }, null, 2));
  fs.writeFileSync(path.join(OUT, 'screens.json'), JSON.stringify(SCREENS.map(({ id, title, hash }) => ({ id, title, route: '/app#' + hash, file: 'raw/' + id + '.png' })), null, 2));
  cdp.close();
})().catch(error => { console.error(error); process.exit(1); });
