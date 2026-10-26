"use strict";
// Build-time Markdown rendering: no network and no runtime browser fetch.
// The page is complete without JavaScript: navigation, anchors and code blocks
// are produced here; partner-docs-ui.js only adds copy buttons and scroll-spy.
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const web = path.join(root, "apps", "web");
const dest = path.join(root, "dist", "web");
const markdown = fs.readFileSync(path.join(web, "partner-docs.md"), "utf8");
const md = require(path.join(web, "vendor", "markdown-it-15.0.2.min.js"))({
  html: false, linkify: true, typographer: true,
});
let rendered = md.render(markdown);
if (!rendered.includes("<h1>Smetra Partner API</h1>")) {
  throw new Error("Markdown renderer did not produce the expected documentation");
}

const SECTIONS = {
  "Введение": "intro", "Быстрый старт": "quick-start", "Авторизация": "auth", "API-ключи": "keys",
  "Партнёрские ссылки": "links", "Подтверждение домена": "domain", "Каталог": "catalog",
  "Аналитика": "analytics", "Комиссии": "commissions", "События": "events", "SDK": "sdk",
  "Ошибки": "errors", "Ограничения": "limits", "Безопасность": "security", "Changelog": "changelog",
};
const LATIN = { а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z", и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "h", ц: "c", ч: "ch", ш: "sh", щ: "sch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya" };
const text = html => html.replace(/<[^>]+>/g, "").replace(/&[a-z]+;|&#\d+;/g, " ").trim();
const slugify = value => text(value).toLowerCase().split("").map(ch => LATIN[ch] ?? ch).join("").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

const nav = [];
const toc = {};
const used = new Set();
let section = "";
rendered = rendered.replace(/<h([23])>([\s\S]*?)<\/h\1>/g, (_, level, inner) => {
  const title = text(inner);
  let id = level === "2" ? SECTIONS[title] : section + "-" + slugify(inner);
  if (!id) throw new Error("Docs section is not in the sidebar map: " + title);
  while (used.has(id)) id += "-x";
  used.add(id);
  if (level === "2") { section = id; nav.push([id, title]); toc[id] = []; }
  else toc[section].push([id, title]);
  return `<h${level} id="${id}"><a class="pd-anchor" href="#${id}" aria-hidden="true" tabindex="-1">#</a>${inner}</h${level}>`;
});
const missing = Object.values(SECTIONS).filter(id => !used.has(id));
if (missing.length) throw new Error("Docs sections missing: " + missing.join(", "));

const LANGS = { bash: "Shell", http: "HTTP", html: "HTML", js: "JavaScript", python: "Python", text: "Текст", json: "JSON" };
rendered = rendered.replace(/<pre><code(?: class="language-([a-z]+)")?>([\s\S]*?)<\/code><\/pre>/g, (_, lang, code) =>
  `<div class="p-code"><div class="p-code-head"><span>${LANGS[lang] || "Код"}</span><button class="p-copy" type="button" data-copy hidden>Копировать</button></div><pre><code>${code}</code></pre></div>`);
rendered = rendered.replace(/<table>/g, '<div class="pd-table"><table>').replace(/<\/table>/g, "</table></div>");

const esc = value => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const list = nav.map(([id, title]) => `<li><a href="#${id}">${esc(title)}</a></li>`).join("");
const navHtml = `<details class="pd-nav-mobile"><summary>Разделы</summary><ol>${list}</ol></details><ol class="pd-nav-list">${list}</ol>`;
const tocHtml = `<p class="pd-toc-title">На этой странице</p>` + nav.map(([id]) => toc[id].length
  ? `<ol data-toc-for="${id}">${toc[id].map(([sub, title]) => `<li><a href="#${sub}">${esc(title)}</a></li>`).join("")}</ol>` : "").join("");

const template = fs.readFileSync(path.join(web, "partner-docs.html"), "utf8");
const article = /<article id="documentation"[^>]*>[\s\S]*?<\/article>/;
const navSlot = /<nav class="pd-nav" id="docs-nav"([^>]*)><\/nav>/;
const tocSlot = /<aside class="pd-toc" id="docs-toc"([^>]*)><\/aside>/;
for (const pattern of [article, navSlot, tocSlot]) if (!pattern.test(template)) throw new Error("Partner docs template has changed");
const result = template
  .replace(article, `<article id="documentation" class="pd-body">\n${rendered}\n</article>`)
  .replace(navSlot, (_, attrs) => `<nav class="pd-nav" id="docs-nav"${attrs}>${navHtml}</nav>`)
  .replace(tocSlot, (_, attrs) => `<aside class="pd-toc" id="docs-toc"${attrs}>${tocHtml}</aside>`);
for (const filename of ["docs.html", "partner-docs.html"]) {
  fs.writeFileSync(path.join(dest, filename), result, "utf8");
}
process.stdout.write(`Pre-rendered partner documentation: ${nav.length} sections\n`);
