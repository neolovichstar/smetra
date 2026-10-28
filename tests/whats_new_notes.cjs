'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const data = JSON.parse(fs.readFileSync(path.join(root, 'apps/web/whats-new.json'), 'utf8'));
const renderer = fs.readFileSync(path.join(root, 'apps/web/whats-new.js'), 'utf8');
const icons = new Set([...renderer.matchAll(/^\s*'([a-z-]+)':/gm)].map(match => match[1]));
assert.equal(data.schema_version, 2);
assert(Array.isArray(data.posts));
assert(icons.size >= 8, 'SVG registry must include a useful set of icons');
const ids = new Set();
for (const post of data.posts) {
  assert.match(post.id, /^[a-z0-9-]{1,100}$/);
  assert(!ids.has(post.id), 'A published post ID must not change or repeat');
  ids.add(post.id);
  assert.match(post.date, /^\d{4}-\d{2}-\d{2}$/);
  assert(!Number.isNaN(Date.parse(post.date)), 'Date must be valid');
  assert(['released', 'development'].includes(post.status));
  assert(['major', 'patch', 'preview'].includes(post.type));
  assert.equal(post.status === 'development', post.type === 'preview');
  assert(icons.has(post.icon), 'Unknown SVG post icon: ' + post.icon);
  assert(typeof post.title === 'string' && post.title.length > 5);
  assert(typeof post.summary === 'string' && post.summary.length <= 500);
  assert(Array.isArray(post.changes) && post.changes.length > 0);
  assert(post.changes.length <= (post.type === 'patch' ? 4 : 12));
  for (const change of post.changes) {
    assert(icons.has(change.icon), 'Unknown SVG change icon: ' + change.icon);
    assert(typeof change.text === 'string' && change.text.length <= 450);
    assert(!/\p{Extended_Pictographic}/u.test(change.text), 'Use SVG instead of emoji');
  }
}
assert(renderer.includes('escapeHtml'), 'Post text must be HTML-escaped');
console.log('Whats New: valid releases and SVG icons (' + data.posts.length + ' posts)');
