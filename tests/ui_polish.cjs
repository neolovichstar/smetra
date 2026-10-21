const assert = require('node:assert/strict');
const fs = require('node:fs');

const html = fs.readFileSync('apps/web/app.html', 'utf8');
const css = fs.readFileSync('apps/web/workspace-polish.css', 'utf8');
const server = fs.readFileSync('backend/app.py', 'utf8');
const appJs = fs.readFileSync('apps/web/app.js', 'utf8');
const featureLoader = fs.readFileSync('apps/web/features.js', 'utf8');
const assistantChat = fs.readFileSync('apps/web/assistant-chat.js', 'utf8');
const workspaceJs = fs.readFileSync('apps/web/workspace.js', 'utf8');
const workflow = fs.readFileSync('.github/workflows/ci.yml', 'utf8');

const foundationLink = html.indexOf('/ui-foundation.css');
const polishLink = html.indexOf('/workspace-polish.css?v=20261021-polish-v3-editor-spacing');
assert.match(html, /src="\/app\.js\?v=20261021-nav-v5"/,
  'navigation script cache key changes with shipped navigation behavior');
assert.match(html, /src="\/workspace\.js\?v=20261021-dialog-a11y-v1"/,
  'workspace script cache key changes with dialog accessibility behavior');
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
assert.match(workspaceJs, /setAttribute\('aria-labelledby','workspace-dialog-title'\)|setAttribute\('aria-labelledby',dialogTitle\.id\)/,
  'shared dialogs provide an accessible name from their visible heading');
assert.match(workspaceJs, /setAttribute\('aria-describedby','workspace-dialog-description'\)|setAttribute\('aria-describedby',dialogDescription\.id\)/,
  'shared dialogs expose their supporting description to assistive technology');

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

assert.match(css, /#content \.editor-layout > \.editor-main\s*\{[\s\S]*?display:\s*grid[\s\S]*?gap:\s*14px/,
  'estimate editor groups use deliberate and stable vertical separation');
assert.match(css, /@media \(max-width:\s*700px\)[\s\S]*?body\.workspace-page #content \.editor-layout\s*\{\s*gap:\s*14px !important/,
  'mobile estimate editor preserves the inter-section gap after switching to a vertical layout');

assert.match(html, /src="\/features\.js\?v=20261021-assistant-resize-v1"/,
  'feature loader cache key changes with responsive composer behavior');
assert.match(featureLoader, /\/assistant-chat\.js\?v=20261021-composer-resize-v1/,
  'assistant chat module is cache-busted when composer resize behavior changes');
assert.match(assistantChat, /window\.addEventListener\('resize',resizeActiveAssistantComposer/,
  'assistant composer recalculates after window resizing');
assert.match(assistantChat, /visualViewport\?\.addEventListener\('resize',resizeActiveAssistantComposer/,
  'assistant composer recalculates after mobile visual viewport resizing');

assert.match(css, /#assistant-new-thread::before,[\s\S]*?#assistant-knowledge::before\s*\{[\s\S]*?content:none!important[\s\S]*?mask:none!important[\s\S]*?-webkit-mask:none!important/,
  'legacy assistant pseudo-icons are suppressed so each action has one inline SVG');

assert.match(css, /@media\s*\(prefers-reduced-motion:\s*reduce\)/,
  'animations respect reduced-motion preferences');
assert.match(css, /max-width:\s*800px[\s\S]*?#sidebar\s*\{\s*top:\s*64px/,
  'tablet drawer aligns with the single-row header');
assert.match(css, /max-width:\s*700px[\s\S]*?#sidebar\s*\{\s*top:\s*112px/,
  'phone drawer aligns with the two-row header');
assert.match(workflow, /node tests\/ui_polish\.cjs/,
  'the UI polish contract runs in CI');

console.log('UI polish contract PASS');
