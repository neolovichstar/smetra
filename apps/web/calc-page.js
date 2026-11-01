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
  form.addEventListener('input', update);
  form.addEventListener('submit', event => event.preventDefault());
  $('calc-to-estimate').addEventListener('click', event => {
    if ($('calc-to-estimate').getAttribute('aria-disabled') === 'true') { event.preventDefault(); return; }
    try { sessionStorage.setItem(tool.handoffKey, JSON.stringify({ kind, values: values() })); } catch { /* the cabinet opens with defaults */ }
  });
  update();
})();
