/* Partner catalog files: YML (Windows-1251, categories, vendor.model) and CSV (quotes, ";", Russian headers). */
const assert = require('node:assert/strict'), fs = require('node:fs');
const { JSDOM } = require(process.env.SMETRA_JSDOM_MODULE || 'jsdom');
const dom = new JSDOM('<body></body>', { runScripts: 'outside-only' });
dom.window.TextDecoder = TextDecoder;
dom.window.eval(fs.readFileSync('apps/web/partner-import.js', 'utf8'));
const tool = dom.window.SmetraPartnerImport;
const iconv = (text, table) => Buffer.from([...text].map(ch => ch.charCodeAt(0) < 128 ? ch.charCodeAt(0) : table[ch]));
// Minimal Windows-1251 encoder for Cyrillic: А..я are 0xC0..0xFF, Ё/ё are 0xA8/0xB8.
const cp1251 = {};
for (let i = 0; i < 64; i++) cp1251[String.fromCharCode(0x410 + i)] = 0xC0 + i;
cp1251['Ё'] = 0xA8; cp1251['ё'] = 0xB8;

const yml = `<?xml version="1.0" encoding="windows-1251"?>
<yml_catalog><shop><name>Магазин</name>
<categories><category id="1">Стройматериалы</category><category id="2" parentId="1">Плитка</category><category id="4">Техника</category></categories>
<offers>
<offer id="TILE3060" available="true"><url>https://shop.test/p/tile</url><price>1890.50</price><currencyId>RUR</currencyId><categoryId>2</categoryId><name>Плитка 30&#215;60</name></offer>
<offer id="PRIMER10" available="false"><url>https://shop.test/p/primer</url><price>890</price><categoryId>2</categoryId><typePrefix>Грунтовка</typePrefix><vendor>Церезит</vendor><model>CT 17</model></offer>
<offer id="FRIDGE1"><url>https://www.shop.test/p/fridge</url><price>45990</price><categoryId>4</categoryId><name>Холодильник</name></offer>
<offer id="USD1"><url>https://shop.test/p/usd</url><price>10</price><currencyId>USD</currencyId><name>Импорт</name></offer>
<offer id="NOPRICE"><url>https://shop.test/p/n</url><name>Без цены</name></offer>
</offers></shop></yml_catalog>`;
const text = tool.decode(iconv(yml, cp1251));
assert.match(text, /Стройматериалы/, 'Windows-1251 declared in XML is decoded');
const parsed = tool.parseYml(text);
assert.equal(parsed.total, 5);
assert.deepEqual(JSON.parse(JSON.stringify(parsed.items.map(i => [i.sku, i.name, i.price_kopecks, i.available]))), [
  ['TILE3060', 'Плитка 30×60', 189050, true],
  ['PRIMER10', 'Грунтовка Церезит CT 17', 89000, false],
  ['FRIDGE1', 'Холодильник', 4599000, true],
]);
assert.equal(parsed.problems.length, 2, 'foreign currency and missing price are reported, not guessed');
assert.deepEqual(JSON.parse(JSON.stringify(parsed.groups.map(g => [g.name, g.count]))), [['Стройматериалы', 2], ['Техника', 1]], 'offers roll up to top categories');
assert.deepEqual(JSON.parse(JSON.stringify(tool.foreignHosts(parsed.items, 'shop.test'))), [['www.shop.test', 1]]);
assert.ok(tool.parseYml('<not-xml').error);
assert.ok(tool.parseYml('<yml_catalog/>').error);

const csv = '﻿Артикул;Название;Цена, ₽;Ссылка;Наличие\r\nLAM-8;Ламинат;"1 290,00";https://shop.test/p/l;да\r\nPAINT;"Краска ""Белая""; 9 л";2 450;https://shop.test/p/p;нет\r\nBAD;Без цены;;https://shop.test/p/x;\r\n';
const table = tool.parseCsv(tool.decode(Buffer.from(csv, 'utf8')));
assert.deepEqual(JSON.parse(JSON.stringify(table.items.map(i => [i.sku, i.name, i.price_kopecks, i.available]))), [
  ['LAM-8', 'Ламинат', 129000, true], ['PAINT', 'Краска "Белая"; 9 л', 245000, false]]);
assert.equal(table.problems.length, 1);
const legacy = tool.parseCsv(tool.decode(iconv('Артикул,Название,Цена,Ссылка\nA1,Плитка,100,https://shop.test/a\n', cp1251)));
assert.equal(legacy.items[0].name, 'Плитка', 'Windows-1251 CSV without a declaration falls back from UTF-8');
assert.match(tool.parseCsv('a;b\n1;2').error, /Не найдены колонки/);
assert.equal(tool.kopecks('1 890,5 ₽'), 189050);
assert.equal(tool.kopecks('abc'), null);
console.log('PASS: YML (cp1251, categories, vendor.model, currency) and CSV (quotes, Russian headers, cp1251) parse into partner products');
