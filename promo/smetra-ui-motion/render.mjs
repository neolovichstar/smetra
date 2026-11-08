// Frame-accurate renderer: Playwright drives window.seek(t); FFmpeg averages 4 sub-frames per 60 fps frame.
// usage:
//   node render.mjs stills h 0.5,3.95,8.6        → out/stills/h_8.600.png
//   node render.mjs frames h [workers]           → out/frames_h/000000.png … (240 sub-frames per second)
//   node render.mjs events                       → out/events.json
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const CHROME = process.env.CHROME || path.join(process.env.LOCALAPPDATA || '', 'ms-playwright/chromium-1234/chrome-win64/chrome.exe');
const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, '$1'));
const [mode, fmt = 'h', arg] = process.argv.slice(2);
const size = fmt === 'v' ? { width: 1080, height: 1920 } : { width: 1920, height: 1080 };
const url = pathToFileURL(path.join(here, 'index.html')).href + `?fmt=${fmt}&render=1`;
const FPS = 60, SUB = 4;

async function page(browser) {
  const p = await browser.newPage({ viewport: size, deviceScaleFactor: 1 });
  p.on('pageerror', e => console.error('pageerror', e.message));
  await p.goto(url); await p.evaluate(() => window.seek(0));
  return p;
}
const browser = await chromium.launch({ executablePath: CHROME, args: ['--force-color-profile=srgb', '--disable-lcd-text', '--font-render-hinting=none'] });
fs.mkdirSync(path.join(here, 'out'), { recursive: true });

if (mode === 'events') {
  const p = await page(browser);
  fs.writeFileSync(path.join(here, 'out/events.json'), JSON.stringify(await p.evaluate(() => window.getEvents()), null, 1));
  fs.writeFileSync(path.join(here, 'out/subs.json'), JSON.stringify(await p.evaluate(() => window.getSubs()), null, 1));
} else if (mode === 'stills') {
  const p = await page(browser), dir = path.join(here, 'out/stills'); fs.mkdirSync(dir, { recursive: true });
  for (const t of arg.split(',').map(Number)) {
    await p.evaluate(t => window.seek(t), t);
    await p.screenshot({ path: path.join(dir, `${fmt}_${t.toFixed(3)}.png`) });
  }
} else if (mode === 'frames') {
  const dur = await (await page(browser)).evaluate(() => window.DURATION);
  const total = Math.round(dur * FPS) * SUB, workers = +(arg || 4);
  const dir = path.join(here, `out/frames_${fmt}`); fs.mkdirSync(dir, { recursive: true });
  let next = 0, done = 0; const t0 = Date.now();
  await Promise.all(Array.from({ length: workers }, async () => {
    const own = await chromium.launch({ executablePath: CHROME, args: ['--force-color-profile=srgb', '--disable-lcd-text', '--font-render-hinting=none'] });
    const p = await page(own);
    while (next < total) {
      const i = next++, k = Math.floor(i / SUB), j = i % SUB;
      // sub-frames centred on the output frame time: (k + (j - 1.5)/4) / 60
      const t = Math.max(0, (k + (j - (SUB - 1) / 2) / SUB) / FPS);
      const file = path.join(dir, String(i).padStart(6, '0') + '.png');
      if (!fs.existsSync(file)) { await p.evaluate(t => window.seek(t), t); await p.screenshot({ path: file }); }
      if (++done % 480 === 0) console.log(`${fmt}: ${done}/${total} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
    }
    await own.close();
  }));
}
await browser.close();
