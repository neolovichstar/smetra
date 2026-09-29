const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const context={window:{},URL,escapeHtml:value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))};
vm.createContext(context);
vm.runInContext(fs.readFileSync('apps/web/assistant-chat.js','utf8'),context);

const html=context.assistantMarkdown('# Смета\n\n**Итог:** 10 000 ₽\n- Работа\n- Материалы\n\n```js\n<script>alert(1)</script>\n```\n[Документы](https://example.org/terms?a=1&b=2)');
assert.match(html,/<h3>Смета<\/h3>/);
assert.match(html,/<strong>Итог:<\/strong>/);
assert.match(html,/<ul><li>Работа<\/li><li>Материалы<\/li><\/ul>/);
assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
assert.match(html, /href="https:\/\/example.org\/terms\?a=1&amp;b=2"/);

const attack=context.assistantMarkdown('<img src=x onerror=alert(1)>\n\n[нажми](javascript:alert(1))');
assert.doesNotMatch(attack,/<img|href="javascript:/);
assert.match(attack,/&lt;img/);
console.log('PASS: Markdown blocks, safe links and HTML escaping');
