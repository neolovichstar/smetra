// Determinism check: the same t rendered after different seek orders must give identical pixels.
import { chromium } from 'playwright'; import path from 'node:path'; import { pathToFileURL } from 'node:url'; import fs from 'node:fs';
const b = await chromium.launch({ executablePath: process.env.LOCALAPPDATA + '/ms-playwright/chromium-1234/chrome-win64/chrome.exe', args: ['--disable-lcd-text', '--font-render-hinting=none'] });
const fmt = process.argv[2] || 'h';
const p = await b.newPage({ viewport: fmt === 'v' ? { width: 1080, height: 1920 } : { width: 1920, height: 1080 } });
await p.goto(pathToFileURL(path.resolve('index.html')).href + `?fmt=${fmt}&render=1`);
let bad = 0;
for (const t of [3.2, 9.7, 14.6, 17.2, 22.0, 26.5]) {
  await p.evaluate(t => window.seek(t), t); const a = await p.screenshot();
  await p.evaluate(() => window.seek(29.9)); await p.evaluate(() => window.seek(0.4));
  await p.evaluate(t => window.seek(t), t); const c = await p.screenshot();
  const same = Buffer.compare(a, c) === 0; if (!same) { bad++; fs.writeFileSync(`out/seek_${fmt}_${t}_a.png`, a); fs.writeFileSync(`out/seek_${fmt}_${t}_b.png`, c); } console.log(fmt, t, same ? 'identical' : 'DIFFERENT');
}
await b.close(); process.exit(bad ? 1 : 0);
