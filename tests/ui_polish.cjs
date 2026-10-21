const assert = require('node:assert/strict');
const fs = require('node:fs');

const html = fs.readFileSync('apps/web/app.html', 'utf8');
const css = fs.readFileSync('apps/web/workspace-polish.css', 'utf8');
const server = fs.readFileSync('backend/app.py', 'utf8');
const appJs = fs.readFileSync('apps/web/app.js', 'utf8');
const workflow = fs.readFileSync('.github/workflows/ci.yml', 'utf8');

const foundationLink = html.indexOf('/ui-foundation.css');
const polishLink = html.indexOf('/workspace-polish.css?v=20261021-polish-v1');
assert.match(html, /src="\/app\.js\?v=20261021-nav-v5"/,
  'navigation script cache key changes with shipped navigation behavior');
assert.ok(foundationLink >= 0, 'shared UI foundation is linked');
assert.ok(polishLink > foundationLink, 'polish layer loads after the existing UI layers');

assert.match(server, /"\/workspace-polish\.css":\s*\("workspace-polish\.css",\s*"text\/css"\)/,
  'server serves the new stylesheet through the explicit static allowlist');

assert.match(html, /id="command-open"[^>]*aria-label="Найти в Сметре"/,
  'icon-only command search exposes a stable accessible name');
assert.match(html, /id="command-open"[^>]*aria-keyshortcuts="Control\+K Meta\+K"/,
  'command search advertises supported keyboard shortcuts');
assert.match(html, /<nav class="sidebar-scroll" aria-label="Разделы рабочего пространства">/,
  'workspace sections are exposed as a named navigation landmark');
assert.match(appJs, /setAttribute\('aria-current','page'\)/,
  'the active workspace destination is communicated to assistive technology');
assert.match(appJs, /removeAttribute\('aria-current'\)/,
  'stale current-page state is removed when navigating between sections');

for (const selector of [
  '.workspace-page .main',
  '.workspace-page .main .field',
  '.workspace-page .main th',
  '.workspace-page .main td',
  '.workspace-page .main .panel',
  '.workspace-page .main .toolbar',
]) {
  assert.ok(css.includes(selector), 'shared polish covers ' + selector);
}

assert.match(css, /@media\s*\(prefers-reduced-motion:\s*reduce\)/,
  'animations respect reduced-motion preferences');
assert.match(css, /max-width:\s*800px[\s\S]*?#sidebar\s*\{\s*top:\s*64px/,
  'tablet drawer aligns with the single-row header');
assert.match(css, /max-width:\s*700px[\s\S]*?#sidebar\s*\{\s*top:\s*112px/,
  'phone drawer aligns with the two-row header');
assert.match(workflow, /node tests\/ui_polish\.cjs/,
  'the UI polish contract runs in CI');

console.log('UI polish contract PASS');
