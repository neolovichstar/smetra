const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const { webcrypto } = require('node:crypto');
const { TextEncoder, TextDecoder } = require('node:util');
const source = fs.readFileSync(path.join(__dirname, '../apps/web/data-export.js'), 'utf8');
const file = Buffer.from('verified export attachment');
const hash = webcrypto.createHash ? webcrypto.createHash('sha256').update(file).digest('hex') : require('node:crypto').createHash('sha256').update(file).digest('hex');
const output = [];
const controls = new Map();
const element = () => ({ innerHTML: '', textContent: '', disabled: false, hidden: true, handlers: {}, addEventListener(name, handler) { this.handlers[name] = handler; } });
for (const selector of ['#settings-export', '#export-start', '#export-cancel', '#export-status']) controls.set(selector, element());
const document = { querySelector: selector => controls.get(selector) || null };
const manifest = {
  format: 'smetra-workspace-export', version: 1, created_at: 1, workspace_id: 'test-workspace',
  tables: [{ name: 'clients', count: 1 }],
  files: [{ id: 'file-1', name: '../../brief.txt', mime: 'text/plain', size: file.length, sha256: hash, client_id: 'client-1' }],
  file_versions: [], total_file_bytes: file.length,
};
async function fetch(url) {
  if (url === '/api/export') return new Response(JSON.stringify(manifest), { headers: { 'content-type': 'application/json' } });
  if (url.startsWith('/api/export/data/clients')) return new Response(JSON.stringify({ items: url.includes('offset=0') ? [{ id: 'client-1', name: 'Fixture' }] : [] }), { headers: { 'content-type': 'application/json' } });
  if (url === '/api/export/files/file-1') return new Response(file);
  throw Error('Unexpected URL in ZIP fixture: ' + url);
}
const window = {
  showSaveFilePicker: async () => ({ createWritable: async () => ({ write: async chunk => output.push(Buffer.from(chunk)), close: async () => {}, abort: async () => {} }) }),
};
const context = { window, document, fetch, TextEncoder, TextDecoder, Blob, Response, URL, crypto: webcrypto, AbortController, DOMException, setTimeout, clearTimeout, sessionStorage: { getItem: key => key === 'workspace_id' ? 'test-workspace' : null }, console };
vm.runInNewContext(source, context);
window.SmetraDataExport.render();
(async () => {
  await controls.get('#export-start').handlers.click();
  if (controls.get('#export-status').textContent !== 'Архив создан. Сохраните его в надёжном месте: внутри могут быть клиентские данные.') throw Error(controls.get('#export-status').textContent);
  fs.writeFileSync(process.argv[2], Buffer.concat(output));
})().catch(error => { console.error(error); process.exitCode = 1; });
