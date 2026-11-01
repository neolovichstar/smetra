/* Partner catalog files: Yandex Market YML (XML) and CSV/Excel exports turned into
   Partner API products. Parsing only — every product still goes through the same
   validation and the server, which accepts links to the partner's own domain only. */
window.SmetraPartnerImport = (() => {
  "use strict";
  const SKU_RE = /^[A-Za-z0-9_.:-]{1,80}$/;
  const MAX_NAME = 200;

  // Russian exports are often Windows-1251: honour an XML declaration, otherwise try UTF-8 first.
  function decode(buffer) {
    const bytes = new Uint8Array(buffer);
    const head = new TextDecoder("ascii").decode(bytes.subarray(0, 200));
    const declared = (head.match(/encoding=["']([A-Za-z0-9_-]+)["']/) || [])[1]?.toLowerCase();
    if (declared && /^(windows-1251|cp1251)$/.test(declared)) return new TextDecoder("windows-1251").decode(bytes);
    try { return new TextDecoder("utf-8", { fatal: true }).decode(bytes).replace(/^﻿/, ""); }
    catch { return new TextDecoder("windows-1251").decode(bytes); }
  }

  // "1 890,50 ₽" → 189050. Null when the text is not a price.
  function kopecks(text) {
    const clean = String(text ?? "").replace(/[\s ₽]|руб\.?|р\.$/gi, "").replace(",", ".");
    if (!/^\d+(\.\d{1,2})?$/.test(clean)) return null;
    return Math.round(Number(clean) * 100);
  }
  const shorten = name => {
    const text = String(name ?? "").replace(/\s+/g, " ").trim();
    return text.length > MAX_NAME ? text.slice(0, MAX_NAME - 1).trimEnd() + "…" : text;
  };

  /* ---------- YML ---------- */
  function parseYml(text) {
    const doc = new DOMParser().parseFromString(text, "application/xml");
    if (doc.getElementsByTagName("parsererror").length) return { error: "Файл не читается как XML. Проверьте, что это выгрузка YML." };
    const offers = [...doc.getElementsByTagName("offer")];
    if (!offers.length) return { error: "В файле нет товаров: не найдено ни одного элемента <offer>." };
    const child = (node, name) => node.getElementsByTagName(name)[0]?.textContent.trim() ?? "";
    const categories = new Map();
    for (const node of doc.getElementsByTagName("category")) {
      categories.set(node.getAttribute("id"), { id: node.getAttribute("id"), parent: node.getAttribute("parentId") || null, name: node.textContent.trim() || "Без названия", count: 0 });
    }
    // The top-level ancestor groups offers for the choice of what to import.
    const rootOf = id => {
      let current = categories.get(id), guard = 0;
      while (current?.parent && categories.has(current.parent) && guard++ < 50) current = categories.get(current.parent);
      return current?.id ?? null;
    };
    const items = [], problems = [];
    offers.forEach((offer, index) => {
      const sku = (offer.getAttribute("id") || child(offer, "vendorCode")).trim();
      const name = shorten(child(offer, "name") || [child(offer, "typePrefix"), child(offer, "vendor"), child(offer, "model")].filter(Boolean).join(" "));
      const currency = child(offer, "currencyId").toUpperCase();
      const price = kopecks(child(offer, "price"));
      const where = `Товар ${index + 1}${sku ? ` (${sku})` : ""}: `;
      if (currency && currency !== "RUR" && currency !== "RUB") { problems.push(where + `цена в ${currency}, нужны рубли`); return; }
      if (price === null) { problems.push(where + "нет цены или она не число"); return; }
      const root = rootOf(child(offer, "categoryId"));
      if (root) categories.get(root).count++;
      items.push({ sku, name, price_kopecks: price, url: child(offer, "url"), available: offer.getAttribute("available") !== "false", category: root, row: index });
    });
    const groups = [...categories.values()].filter(c => !c.parent || !categories.has(c.parent)).filter(c => c.count).sort((a, b) => b.count - a.count);
    return { items, problems, groups, total: offers.length, shop: child(doc, "name") || child(doc, "company") };
  }

  /* ---------- CSV ---------- */
  function rowsOf(text) {
    const end = text.search(/\r?\n/), firstLine = end < 0 ? text : text.slice(0, end);
    const delimiter = [";", "\t", ","].map(d => [d, firstLine.split(d).length]).sort((a, b) => b[1] - a[1])[0][0];
    const rows = [];
    let row = [], field = "", quoted = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (quoted) {
        if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
        else if (ch === '"') quoted = false;
        else field += ch;
      } else if (ch === '"' && !field) quoted = true;
      else if (ch === delimiter) { row.push(field); field = ""; }
      else if (ch === "\n" || ch === "\r") {
        if (ch === "\r" && text[i + 1] === "\n") i++;
        row.push(field); field = "";
        if (row.some(cell => cell.trim())) rows.push(row);
        row = [];
      } else field += ch;
    }
    row.push(field);
    if (row.some(cell => cell.trim())) rows.push(row);
    return rows;
  }
  const COLUMNS = {
    sku: ["sku", "артикул", "id", "код", "код товара", "vendorcode", "vendor_code"],
    name: ["name", "название", "наименование", "товар", "title"],
    price: ["price", "цена", "цена, ₽", "цена, руб", "цена, руб.", "стоимость", "розничная цена"],
    price_kopecks: ["price_kopecks"],
    url: ["url", "ссылка", "link", "адрес", "ссылка на товар"],
    available: ["available", "наличие", "в наличии", "availability", "доступность"],
  };
  const NO = /^(0|false|нет|no|не в наличии|нет в наличии|отсутствует|под заказ)$/i;
  function parseCsv(text) {
    const rows = rowsOf(text.replace(/^﻿/, ""));
    if (rows.length < 2) return { error: "В файле нет строк с товарами: нужна строка заголовков и хотя бы одна строка данных." };
    const header = rows[0].map(cell => cell.trim().toLowerCase());
    const index = {};
    for (const [key, names] of Object.entries(COLUMNS)) index[key] = header.findIndex(cell => names.includes(cell));
    const missing = [["sku", "артикул (sku)"], ["name", "название (name)"], ["url", "ссылка (url)"]].filter(([key]) => index[key] < 0).map(([, label]) => label);
    if (index.price < 0 && index.price_kopecks < 0) missing.push("цена (price)");
    if (missing.length) return { error: `Не найдены колонки: ${missing.join(", ")}. В файле есть: ${rows[0].map(c => c.trim()).filter(Boolean).join(", ") || "—"}.` };
    const items = [], problems = [];
    rows.slice(1).forEach((cells, i) => {
      const value = key => (index[key] >= 0 ? (cells[index[key]] ?? "").trim() : "");
      const sku = value("sku");
      const price = index.price_kopecks >= 0 && /^\d+$/.test(value("price_kopecks")) ? Number(value("price_kopecks")) : kopecks(value("price"));
      if (price === null) { problems.push(`Строка ${i + 2}${sku ? ` (${sku})` : ""}: цена не число`); return; }
      items.push({ sku, name: shorten(value("name")), price_kopecks: price, url: value("url"), available: !NO.test(value("available")), row: i });
    });
    return { items, problems, total: rows.length - 1 };
  }

  // Which links point elsewhere: the usual cause is www. or a second shop domain.
  function foreignHosts(items, host) {
    const counts = new Map();
    for (const item of items) {
      let name = "";
      try { name = new URL(item.url).hostname.toLowerCase(); } catch { continue; }
      if (name !== host) counts.set(name, (counts.get(name) || 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }

  return { decode, kopecks, parseYml, parseCsv, foreignHosts, SKU_RE };
})();
