/* Public landing asset reliability: no external CSS fetch is required.
 * The inline rules must match the original CSS files, in their original order.
 * Invoke after: python scripts/build_web.py
 */
'use strict';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'apps/web/index.html'), 'utf8');
const deployed = fs.readFileSync(path.join(root, 'dist/web/index.html'), 'utf8');
const names = ['tokens.css', 'base.css', 'components.css', 'site.css'];
const css = '\n' + names.map(name =>
  fs.readFileSync(path.join(root, 'apps/web/ui', name), 'utf8')
).join('\n') + '\n';
const marker = '<style data-smetra-public-css="inlined">';
const styleBlock = marker + css + '</style>';

assert.equal(deployed.split(marker).length - 1, 1, 'Only one embedded CSS block');
assert.ok(deployed.includes(styleBlock), 'CSS must be byte-for-byte identical to its sources');
assert.equal(deployed.replace(styleBlock, names.map(name => {
  const match = source.match(new RegExp('<link rel="stylesheet" href="/ui/' +
    name.replace('.', '\\.') + '\\?v=[^"]+">'));
  assert.ok(match, 'Source stylesheet missing: ' + name);
  return match[0];
}).join('\n')), source, 'Only stylesheet delivery may change in landing HTML');

const config = JSON.parse(fs.readFileSync(path.join(root, 'vercel.json'), 'utf8'));
const policy = config.headers.flatMap(x => x.headers)
  .find(h => h.key.toLowerCase() === 'content-security-policy').value;
const digest = crypto.createHash('sha256').update(css, 'utf8').digest('base64');
assert.ok(policy.includes("'sha256-" + digest + "'"), 'CSP must allow exactly the CSS in the page');
assert.ok(!policy.includes("'unsafe-inline'"), 'Never weaken the style CSP');
assert.doesNotMatch(deployed, /<link\s+rel="stylesheet"/, 'Landing must not depend on CSS link downloads');

console.log('PASS: public landing HTML contains unchanged CSS, source markup unchanged, restrictive CSP');
