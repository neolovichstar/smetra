/* Public calculator pages: live result from the same calculators.js the cabinet uses,
   and a hand-off of the entered values to the cabinet's calculator after sign-in. */
(() => {
  'use strict';
  const page = document.querySelector('.calc-page[data-calc-kind]');
  const tool = window.SmetraCalculators;
  if (!page || !tool) return;
  const kind = page.dataset.calcKind, form = document.getElementById('calc-form');
  const $ = id => document.getElementById(id);
  const format = value => new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 }).format(value);
  const values = () => Object.fromEntries(new FormData(form).entries());
  const update = () => {
    try {
      const result = tool.calculate(kind, values());
      $('calc-error').hidden = true; $('calc-values').hidden = false;
      $('calc-primary-label').textContent = result.primary.label;
      $('calc-primary').textContent = format(result.primary.value);
      $('calc-primary-unit').textContent = result.primary.unit;
      $('calc-secondary-label').textContent = result.secondary.label;
      $('calc-secondary').textContent = format(result.secondary.value);
      $('calc-secondary-unit').textContent = result.secondary.unit;
      $('calc-formula').textContent = result.description;
      $('calc-to-estimate').removeAttribute('aria-disabled');
    } catch (error) {
      $('calc-error').textContent = error.message; $('calc-error').hidden = false;
      $('calc-values').hidden = true; $('calc-formula').textContent = '';
      $('calc-to-estimate').setAttribute('aria-disabled', 'true');
    }
  };
  // A shared link carries the entered sizes: ?length=6&width=2.5 opens the same calculation.
  const params = new URLSearchParams(location.search);
  for (const input of form.querySelectorAll('input[name]')) {
    const value = params.get(input.name);
    if (value !== null && /^[0-9]{1,9}([.,][0-9]{1,4})?$/.test(value)) input.value = value;
  }
  $('calc-share').addEventListener('click', async () => {
    const link = new URL(location.pathname, location.origin);
    for (const [name, value] of Object.entries(values())) link.searchParams.set(name, String(value).trim());
    link.searchParams.set('utm_source', 'share'); link.searchParams.set('utm_medium', 'calculator'); link.searchParams.set('utm_campaign', kind);
    const title = document.querySelector('h1')?.textContent || 'Расчёт материалов';
    const button = $('calc-share'), label = button.textContent;
    try {
      if (navigator.share && matchMedia('(pointer: coarse)').matches) await navigator.share({ title, text: title + ': ' + $('calc-primary').textContent + ' ' + $('calc-primary-unit').textContent, url: link.href });
      else { await navigator.clipboard.writeText(link.href); button.textContent = 'Ссылка скопирована'; setTimeout(() => { button.textContent = label; }, 2000); }
    } catch (error) {
      if (error?.name !== 'AbortError') { button.textContent = 'Не удалось скопировать'; setTimeout(() => { button.textContent = label; }, 2000); }
    }
  });
  form.addEventListener('input', update);
  form.addEventListener('submit', event => event.preventDefault());
  $('calc-to-estimate').addEventListener('click', event => {
    if ($('calc-to-estimate').getAttribute('aria-disabled') === 'true') { event.preventDefault(); return; }
    try { sessionStorage.setItem(tool.handoffKey, JSON.stringify({ kind, values: values() })); } catch { /* the cabinet opens with defaults */ }
  });
  update();
})();
