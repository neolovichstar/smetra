/* All five phone tabs use the shared router. The header retains the sidebar. */
(() => {
  const bar = document.getElementById('mobile-tabbar');
  if (!bar) return;
  const sync = () => {
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
