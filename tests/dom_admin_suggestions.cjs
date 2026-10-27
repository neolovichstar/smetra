// Owner suggestions board: loading, filtering, triage, navigation and XSS safety.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM } = require(process.env.SMETRA_JSDOM_MODULE || 'jsdom');
const tick = () => new Promise(resolve => setTimeout(resolve, 0));

(async () => {
  const dom = new JSDOM('<main id="content"></main>', {
    url: 'https://smetra.test/app',
    runScripts: 'dangerously'
  });
  const w = dom.window;
  const doc = w.document;
  const requested = [];
  const opened = [];
  const updated = [];
  const source = '<img src=x onerror=alert(1)>';
  const sample = {
    id: '1234567890abcdef1234567890abcdef',
    conversation_id: 'abcdefabcdefabcdefabcdefabcdefab',
    title: 'Добавить шаблоны',
    body: source,
    status: 'new',
    email: 'tester@example.test',
    created_at: 1793000000
  };
  w.eval("var user = { id: 'owner', role: 'admin' }, tab = 'admin';");
  w.view = html => { doc.querySelector('#content').innerHTML = html; };
  w.date = seconds => String(seconds);
  w.rub = value => String(value || 0);
  w.escapeHtml = input => String(input).replace(/[&<>"']/g, ch =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[ch]));
  w.notify = () => {};
  w.SmetraCommunication = {openTicket: async id => { opened.push(id); }};
  w.api = async (path, options = {}) => {
    requested.push(path);
    if (path.startsWith('/admin/communication/suggestions/') && options.method === 'PATCH') {
      updated.push(JSON.parse(options.body));
      return {ok:true};
    }
    if (path.startsWith('/admin/communication/suggestions?'))
      return { suggestions: [sample].filter(s =>
        new URL('https://smetra.test' + path).searchParams.get('status') === 'all' ||
        new URL('https://smetra.test' + path).searchParams.get('status') === s.status) };
    if (path.startsWith('/admin/users?')) return {users:[],total:0};
    return {};
  };
  const script = doc.createElement('script');
  script.textContent = fs.readFileSync('apps/web/admin.js', 'utf8');
  doc.head.append(script);
  assert.equal(typeof w.SmetraAdmin, 'function', 'Admin module must parse and register');
  await w.SmetraAdmin({
    stats:{users:1,subscriptions:0,quotes:1,revenue_kopecks:0},
    tickets:[],payments:[],audit:[]
  });
  const ideas = doc.querySelector('[data-admin-section="ideas"]');
  assert.ok(ideas, 'Suggestions navigation exists');
  ideas.click();
  await tick();
  assert.match(doc.querySelector('#admin-section').textContent,/Добавить шаблоны/);
  assert.match(doc.querySelector('#admin-section').textContent,/<img src=x/);
  assert.equal(doc.querySelector('#admin-section img'),null,'User body must be escaped');
  assert.ok(requested.includes('/admin/communication/suggestions?status=all'));
  const link = doc.querySelector('[data-admin-open-support]');
  assert.equal(link.dataset.adminOpenSupport,sample.conversation_id);
  link.click();
  await tick();
  assert.deepEqual(opened,[sample.conversation_id]);
  const selection = doc.querySelector('[data-admin-idea]');
  selection.value='planned';
  selection.dispatchEvent(new w.Event('change',{bubbles:true}));
  await tick();
  assert.deepEqual(updated,[{status:'planned'}]);
  assert.ok(requested.some(path=>path.endsWith('/'+sample.id)));
  const filter=doc.querySelector('#admin-idea-filter');
  filter.value='planned';
  filter.dispatchEvent(new w.Event('change',{bubbles:true}));
  await tick();
  assert.ok(requested.includes('/admin/communication/suggestions?status=planned'));
  doc.querySelector('[data-admin-section="users"]').click();
  await tick();
  assert.ok(doc.querySelector('#admin-user-results'));
  dom.window.close();
  console.log('PASS: suggestions board renders safely and supports triage without breaking admin');
})().catch(err => { console.error(err); process.exitCode=1; });
