/* Production visibility: uncaught errors from our own scripts are sent to the server log
   (no third parties, no storage). At most five distinct errors per page load; addresses keep
   only the path, never query strings or tokens. */
(() => {
  'use strict';
  let sent = 0;
  const seen = new Set();
  const report = (message, source, line, column) => {
    if (sent >= 5 || !message) return;
    let file = '';
    try {
      const url = new URL(source || location.href, location.href);
      if (url.origin !== location.origin) return; // extensions and third-party scripts are not ours to fix
      file = url.pathname;
    } catch { return; }
    const key = message + '|' + file + '|' + line;
    if (seen.has(key)) return;
    seen.add(key); sent++;
    const hash = location.hash && !location.hash.includes('=') ? location.hash.slice(0, 32) : '';
    const body = JSON.stringify({ message: String(message).slice(0, 300), source: file, line: line | 0, column: column | 0, page: location.pathname + hash });
    try {
      const queued = navigator.sendBeacon && navigator.sendBeacon('/api/client-errors', new Blob([body], { type: 'application/json' }));
      if (!queued) fetch('/api/client-errors', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true, credentials: 'same-origin' }).catch(() => {});
    } catch { /* reporting must never break the page */ }
  };
  addEventListener('error', event => {
    if (event.target && event.target !== window) return; // failed images and scripts are network noise
    report(event.message, event.filename, event.lineno, event.colno);
  });
  addEventListener('unhandledrejection', event => {
    const reason = event.reason, stack = String(reason?.stack || '');
    const at = stack.match(/(https?:\/\/[^\s)]+?):(\d+):(\d+)/);
    report('Unhandled rejection: ' + String(reason?.message || reason).slice(0, 270), at?.[1], at ? Number(at[2]) : 0, at ? Number(at[3]) : 0);
  });
})();
