/* Minimal first-party aggregate visit counting. No IPs, email, cookies or external analytics. */
(() => {
  if (!window.crypto?.randomUUID || !window.fetch) return;
  if (navigator.globalPrivacyControl === true || navigator.doNotTrack === '1') return;
  const page = location.pathname === '/app' ? 'app' : location.pathname === '/' ? 'landing' : null;
  if (!page) return;
  let visitorId;
  try {
    const key = 'smetra.traffic.visitor.v1';
    visitorId = localStorage.getItem(key);
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(visitorId || '')) {
      visitorId = crypto.randomUUID();
      localStorage.setItem(key, visitorId);
    }
  } catch {
    // Private browsing / blocked storage: count this pageview without tracking
    // identity across reloads.
    visitorId = crypto.randomUUID();
  }
  try {
    void fetch('/api/public/visit', {
      method: 'POST',
      credentials: 'omit',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({visitor_id: visitorId, page}),
      keepalive: true,
    }).catch(() => {});
  } catch {}
})();
