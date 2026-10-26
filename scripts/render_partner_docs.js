"use strict";
// Build-time Markdown rendering: no network and no runtime browser fetch.
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const web = path.join(root, "apps", "web");
const dest = path.join(root, "dist", "web");
const markdown = fs.readFileSync(path.join(web, "partner-docs.md"), "utf8");
const md = require(path.join(web, "vendor", "markdown-it-15.0.2.min.js"))({
  html: false, linkify: true, typographer: true
});
const rendered = md.render(markdown);
if (!rendered.includes("<h1>Smetra Partner API</h1>")) {
  throw new Error("Markdown renderer did not produce the expected documentation");
}
const template = fs.readFileSync(path.join(web, "partner-docs.html"), "utf8");
const pattern = /<article id="documentation"[^>]*>[\s\S]*?<\/article>/;
if (!pattern.test(template)) throw new Error("Partner docs template has changed");
const result = template
  .replace(pattern, '<article id="documentation" class="docs-body">\n' + rendered + '\n</article>')
  .replace('<script src="/vendor/markdown-it-15.0.2.min.js" defer></script>', "")
  .replace('<script src="/partner-docs.js" defer></script>', "");
for (const filename of ["docs.html", "partner-docs.html"]) {
  fs.writeFileSync(path.join(dest, filename), result, "utf8");
}
process.stdout.write("Pre-rendered partner documentation to static HTML\n");
