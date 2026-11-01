/* First-touch campaign memory: the first ad or UTM link, or the referring site, a visitor
   arrived from. Kept for 30 days in this browser and handed to the server once after
   sign-in, so the admin can see which channels bring accounts that start paying. */
(() => {
  'use strict';
  const KEY = 'smetra.attribution', TTL = 30 * 86400 * 1000;
  const read = () => {
    try { const value = JSON.parse(localStorage.getItem(KEY) || 'null'); return value && Date.now() - value.at < TTL ? value : null; }
    catch { return null; }
  };
  const params = new URLSearchParams(location.search), tags = {};
  for (const field of ['source', 'medium', 'campaign', 'content', 'term']) {
    const value = params.get('utm_' + field);
    if (value) tags[field] = value.slice(0, 100);
  }
  // Auto-tagged ad clicks without UTM tags still name their network.
  if (!tags.source && params.has('yclid')) Object.assign(tags, { source: 'yandex', medium: 'cpc' });
  if (!tags.source && params.has('gclid')) Object.assign(tags, { source: 'google', medium: 'cpc' });
  let referrer = '';
  try {
    const from = document.referrer ? new URL(document.referrer).hostname : '';
    if (from && from !== location.hostname && !from.endsWith('smetra.online')) referrer = from;
  } catch { /* no referrer */ }
  if (!read() && (tags.source || referrer)) {
    try { localStorage.setItem(KEY, JSON.stringify({ ...tags, referrer, landing: location.pathname, at: Date.now() })); } catch { /* private mode */ }
  }
  window.SmetraAttribution = {
    async flush(api) {
      const value = read();
      if (!value) return;
      try { await api('/me/attribution', { method: 'POST', body: JSON.stringify({ ...value, first_seen_at: Math.floor(value.at / 1000) }) }); }
      catch { return; }
      try { localStorage.removeItem(KEY); } catch { /* ignore */ }
    },
  };
})();
