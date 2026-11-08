/* First-party aggregate audience measurement. Never sends IP, email, account ID or UA. */
(() => {
  if (navigator.globalPrivacyControl === true || navigator.doNotTrack === '1') return;
  const page = location.pathname === '/' ? 'landing' : location.pathname === '/app' ? 'app' : null;
  if (!page || typeof window.crypto?.randomUUID !== 'function') return;
  try {
    const key = 'smetra.site.traffic.id.v1';
    let id = localStorage.getItem(key);
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id || '')) {
      id = window.crypto.randomUUID();
      localStorage.setItem(key, id);
    }
    void fetch('/api/public/visit', {
      method:'POST',credentials:'omit',keepalive:true,
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({visitor_id:id,page})
    }).catch(() => {});
  } catch (_) {
    // Analytics is nonessential and must never interrupt login or the landing page.
  }
})();
