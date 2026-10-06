const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const context={window:{},URL,atob,escapeHtml:value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))};
vm.createContext(context);
context.window=context;
vm.runInContext(fs.readFileSync('apps/web/vendor/markdown-it-15.0.2.min.js','utf8'),context);
vm.runInContext(fs.readFileSync('apps/web/chat-markdown.js','utf8'),context);
vm.runInContext(fs.readFileSync('apps/web/assistant-chat.js','utf8'),context);

const html=context.assistantMarkdown('# Смета\n\n**Итог:** 10 000 ₽\n- Работа\n- Материалы\n\n```js\n<script>alert(1)</script>\n```\n[Документы](https://example.org/terms?a=1&b=2)');
assert.match(html,/<h3>Смета<\/h3>/);
assert.match(html,/<strong>Итог:<\/strong>/);
assert.match(html,/<ul>\s*<li>Работа<\/li>\s*<li>Материалы<\/li>\s*<\/ul>/);
assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
assert.match(html, /href="https:\/\/example.org\/terms\?a=1&amp;b=2"/);

const attack=context.assistantMarkdown('<img src=x onerror=alert(1)>\n\n[нажми](javascript:alert(1))');
assert.doesNotMatch(attack,/<img|href="javascript:/);
assert.match(attack,/&lt;img/);
console.log('PASS: Markdown blocks, safe links and HTML escaping');
const advanced=context.assistantMarkdown('## План\n\n3. Первый\n   - Вложенный **пункт**\n4. Второй\n\n- [x] Готово\n- [ ] Проверить\n\n> **Важно**\n>\n> ~~Старая цена~~\n\n| Работа | Цена |\n| :--- | ---: |\n| `a \\| b` | **200** |\n\n~~~js\nconst x = "<img>";\n~~~\n\n[Ссылка][doc]\n\n[doc]: https://example.org/docs');
assert.match(advanced,/<ol start="3">/);assert.match(advanced,/<ul>\s*<li>Вложенный <strong>пункт/);
assert.match(advanced,/assistant-task is-done/);assert.match(advanced,/aria-label="Не выполнено"/);
assert.match(advanced,/<blockquote>[\s\S]*<s>Старая цена<\/s>/);assert.match(advanced,/class="align-right"/);
assert.match(advanced,/<code>a \| b<\/code>/);assert.match(advanced,/data-copy-code/);assert.match(advanced,/&lt;img&gt;/);
assert.match(advanced,/href="https:\/\/example.org\/docs"/);
for(const input of ['[x](data:text/html,evil)','[x](javascript&#58;alert(1))','[x](file:///etc/passwd)','<svg onload=alert(1)>','![x](https://example.org/tracker.png)']){
 const rendered=context.assistantMarkdown(input);assert.doesNotMatch(rendered,/<(?:img|svg|script)|href="(?:data:|javascript:|file:)/);
}
const partial=context.assistantMarkdown('**Начало**\n\n```js\nconst partial = "<script>');
assert.match(partial,/<strong>Начало/);assert.match(partial,/&lt;script&gt;/);
console.log('PASS: nested/start-number lists, tasks, quotes, strikethrough, tables, reference links, safe incomplete fences and code controls');
const diff=context.assistantEditPreview({kind:'quote_items',currency:'RUB',before_total:10005,after_total:11006,
  rows:[{row:1,name:'<img src=x onerror=alert(1)>',field:'unit_price',before:10005,after:11006}]});
assert.doesNotMatch(diff,/<img/);assert.match(diff,/&lt;img/);
assert.match(diff,/100,05/);assert.match(diff,/110,06/);assert.match(diff,/Итого по смете/);
assert.equal(context.assistantEditValue('quantity','2.5'),'2.5');
assert.equal(context.assistantEditValue('notes',null),'—');
const large=context.assistantEditPreview({rows:Array.from({length:8},(_,i)=>({field:'name',before:'До',after:'После '+i}))});
assert.match(large,/<details><summary>Ещё 3 изменений/);assert.match(large,/После 7/);
console.log('PASS: safe before/after diff, exact kopecks, long edit disclosure');
