/* Bottom tab bar on phones. The four section buttons are ordinary [data-tab]
   controls, so app.js routes them and marks the active one; this file only
   handles «Ещё» (the full section list) and hides the bar while typing. */
(() => {
  const bar = document.getElementById('mobile-tabbar');
  const more = document.getElementById('tabbar-more');
  const toggle = document.getElementById('nav-toggle');
  if (!bar || !more || !toggle) return;
  const direct = new Set([...bar.querySelectorAll('[data-tab]')].map(button => button.dataset.tab));

  more.addEventListener('click', () => toggle.click());
  const sync = () => {
    const open = document.body.classList.contains('nav-open');
    const route = location.hash.slice(1) || 'dashboard';
    more.setAttribute('aria-expanded', String(open));
    more.classList.toggle('active', open || !direct.has(route.split(/[/?]/)[0]));
    bar.querySelectorAll('[data-tab]').forEach(button => {
      if (button.classList.contains('active')) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
  };
  new MutationObserver(sync).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  bar.querySelectorAll('[data-tab]').forEach(button => new MutationObserver(sync).observe(button, { attributes: true, attributeFilter: ['class'] }));
  addEventListener('hashchange', sync);
  sync();

  // The on-screen keyboard shrinks the visual viewport; the bar would sit on top of it.
  const viewport = window.visualViewport;
  if (viewport) {
    const keyboard = () => {
      const typing = document.activeElement?.matches?.('input:not([type=checkbox]):not([type=radio]):not([type=range]),textarea,select,[contenteditable="true"]');
      document.body.classList.toggle('keyboard-open', Boolean(typing) && viewport.height < window.innerHeight * 0.8);
    };
    viewport.addEventListener('resize', keyboard);
    document.addEventListener('focusin', keyboard);
    document.addEventListener('focusout', () => setTimeout(keyboard, 50));
  }
})();
