const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.SMETRA_PLAYWRIGHT_MODULE || 'playwright');

const fixture = JSON.parse(fs.readFileSync(process.env.SMETRA_PROFILE_FIXTURE || 'data/profile-fixture.json', 'utf8'));
const base = fixture.base;
assert(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname), 'Use the isolated local profile fixture');
const output = 'data/qa/account-layout';
fs.mkdirSync(output, { recursive: true });

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.SMETRA_CHROME_PATH ? { executablePath: process.env.SMETRA_CHROME_PATH } : {}),
    args: ['--no-sandbox'],
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 }, reducedMotion: 'reduce' });
  await context.addCookies([{ name: 'session', value: fixture.owner.token, url: base, httpOnly: true, sameSite: 'Lax' }]);
  const page = await context.newPage();
  const errors = [], checks = [], measurements = [];
  page.on('pageerror', error => errors.push(error.message));

  async function verifyLayout(label) {
    const result = await page.evaluate(() => {
      const frames = [...document.querySelectorAll('.sidebar-avatar,.profile-avatar,.profile-hero-avatar')]
        .filter(frame => frame.getClientRects().length && getComputedStyle(frame).visibility !== 'hidden')
        .map(frame => {
          const image = frame.querySelector('img'), box = frame.getBoundingClientRect(), picture = image?.getBoundingClientRect();
          return {
            frame: frame.className, width: box.width, height: box.height,
            loaded: !!image?.complete && image.naturalWidth > 0,
            contained: !!picture && picture.left >= box.left - 1 && picture.top >= box.top - 1 && picture.right <= box.right + 1 && picture.bottom <= box.bottom + 1,
          };
        });
      const section = document.querySelector('#account-content > section').getBoundingClientRect();
      return { viewport: innerWidth, documentWidth: document.documentElement.scrollWidth, left: section.left, width: section.width, frames };
    });
    assert(result.documentWidth <= result.viewport + 1, label + ': no horizontal document overflow');
    if(result.viewport>640||label.startsWith('profile '))assert(result.frames.length > 0, label + ': avatar frames exist');
    for (const frame of result.frames) {
      assert(frame.width > 0 && frame.width <= 96 && frame.height > 0 && frame.height <= 96, label + ': bounded ' + frame.frame);
      assert(frame.loaded && frame.contained, label + ': image stays inside ' + frame.frame);
    }
    assert.equal(await page.locator('#account-content h1').count(), 1, label + ': one page heading');
    return result;
  }

  async function openSection(section) {
    await page.locator('[data-account-section="' + section + '"]').click();
    await page.locator('[data-account-section="' + section + '"][aria-current="page"]').waitFor();
    if (section === 'profile') await page.locator('.profile-hero-avatar img').waitFor();
    if (section === 'usage') await page.locator('#hub-usage-host:not([aria-busy]) .usage-summary-grid').waitFor();
    if (section === 'settings') {
      await page.locator('#hub-tab-account').click();
      await page.locator('#hub-avatar-controls [data-avatar-upload]').waitFor();
    }
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate(() => scrollTo(0, 0));
  }

  async function verifySelectedTab(id, focused = false) {
    await page.locator('#hub-tab-' + id + '[aria-selected="true"]').waitFor();
    assert.equal(await page.locator('[data-hub-tab][aria-selected="true"]').count(), 1);
    assert.equal(await page.locator('.settings-content-panels [role="tabpanel"]:visible').count(), 1);
    assert(await page.locator('#hub-panel-' + id).isVisible(), id + ': corresponding panel is visible');
    await page.waitForFunction(({ id, focused }) => {
      const selected = document.getElementById('hub-tab-' + id), rail = selected.parentElement;
      const button = selected.getBoundingClientRect(), box = rail.getBoundingClientRect();
      return selected.tabIndex === 0 && (!focused || document.activeElement === selected) && button.left >= box.left - 1 && button.right <= box.right + 1;
    }, { id, focused });
  }

  try {
    await page.goto(base + '/app#settings');
    await page.locator('#hub-tab-account').click();
    await page.locator('#hub-avatar-controls input[type=file]').setInputFiles('data/profile-avatar.png');
    await page.getByRole('dialog').waitFor();
    await page.getByRole('button', { name: 'Сохранить фото', exact: true }).click();
    await page.getByRole('dialog').waitFor({ state: 'detached' });
    await page.waitForFunction(() => document.querySelector('#sidebar-avatar img')?.complete && document.querySelector('#sidebar-avatar img').naturalWidth === 384);
    await page.locator('#toast').waitFor({ state: 'hidden' });
    checks.push('real image upload and crop produce the bounded 384px avatar');

    for (const width of [320, 390, 850, 1024, 1280, 1920]) {
      await page.setViewportSize({ width, height: 960 });
      const sections = [];
      for (const section of ['profile', 'usage', 'settings']) {
        await openSection(section);
        await page.screenshot({ path: output + '/' + section + '-' + width + '.png' });
        sections.push({ section, ...await verifyLayout(section + ' ' + width) });
      }
      const reference = sections[0];
      measurements.push(...sections);
      for (const section of sections.slice(1)) {
        assert(Math.abs(section.left - reference.left) <= 1, width + ': account sections share a left edge ' + JSON.stringify(sections.map(({section,left})=>({section,left}))));
        assert(Math.abs(section.width - reference.width) <= 1, width + ': account sections share a content width');
      }

      const tabs = await page.locator('[data-hub-tab]').evaluateAll(buttons => buttons.map(button => button.dataset.hubTab));
      assert.equal(tabs.length, 7, 'all settings sections are present');
      for (const id of tabs) {
        await page.locator('#hub-tab-' + id).click();
        await verifySelectedTab(id);
      }
      const tabSizes = await page.locator('[data-hub-tab]').evaluateAll(buttons => buttons.map(button => {
        const style = getComputedStyle(button), box = button.getBoundingClientRect();
        return { height: box.height, left: parseFloat(style.paddingLeft), right: parseFloat(style.paddingRight) };
      }));
      assert(tabSizes.every(button => button.height >= 44 && button.left >= 10 && button.right >= 10), width + ': tabs have usable targets and space around labels');

      await page.locator('#hub-tab-details').click();
      await page.locator('#hub-tab-details').press('End');
      await verifySelectedTab('danger', true);
      await page.locator('#hub-tab-danger').press('Home');
      await verifySelectedTab('details', true);
      await page.locator('#hub-tab-details').press('ArrowLeft');
      await verifySelectedTab('danger', true);
      for (const id of tabs) {
        await page.locator('[data-hub-tab][aria-selected="true"]').press('ArrowRight');
        await verifySelectedTab(id, true);
      }
      await page.locator('#hub-tab-data').click();
      await page.reload();
      await verifySelectedTab('data');
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), width + ': settings remain within the viewport after keyboard and restored tab navigation');
      checks.push(width + 'px: bounded avatars, aligned pages, seven reachable tabs, keyboard focus and restored selection');
    }

    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 960 });
      await openSection('settings');
      await page.locator('#hub-tab-appearance').click();
      await page.locator('#theme-alt').click();
      await page.waitForFunction(() => document.documentElement.dataset.theme === 'light');
      await openSection('profile');
      await verifyLayout('light profile ' + width);
      await page.screenshot({ path: output + '/profile-light-' + width + '.png' });
      await openSection('settings');
      await page.locator('#hub-tab-appearance').click();
      await page.locator('#theme-alt').click();
    }
    checks.push('light and dark theme switching preserves layout on phone and desktop');
    assert.deepEqual(errors, [], 'no uncaught browser errors');
    console.log(JSON.stringify({ checks, errors }));
  } catch (error) {
    await page.screenshot({ path: output + '/failure.png' }).catch(() => {});
    throw error;
  } finally {
    fs.writeFileSync(output + '/result.json', JSON.stringify({ checks, errors, measurements }, null, 2));
    await browser.close();
  }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
