// Renders og.html to apps/web/assets/og/smetra-og.jpg (1200×630) for link previews.
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await page.goto('file://' + path.join(__dirname, 'og.html'));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  const out = path.join(__dirname, '../../apps/web/assets/og/smetra-og.jpg');
  await page.screenshot({ path: out, type: 'jpeg', quality: 88 });
  await browser.close();
  console.log(out);
})();
