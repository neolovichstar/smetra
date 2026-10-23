'use strict';

const steps = [...document.querySelectorAll('[data-step]')];
const documentHost = document.querySelector('#preview-document');
const prices = [35000, 48000, 15000];
const names = ['Подготовка и демонтаж', 'Плитка и отделка', 'Монтаж сантехники'];
const formatRubles = value => new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 0}).format(value) + ' ₽';
const total = () => prices.reduce((sum, value) => sum + value, 0);

function renderPreview(step) {
  if (!documentHost || !steps.length || !steps[step]) return;
  steps.forEach((button, index) => {
    const active = index === step;
    button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1;
  });
  documentHost.setAttribute('aria-labelledby', steps[step].id);

  if (step === 0) {
    documentHost.innerHTML = `<div class="document-top"><div><span class="overline">Смета · пример</span><h3>Ремонт ванной комнаты</h3><p>Клиент: Заказчик · объект 001</p></div><span class="pill">Черновик</span></div><table class="preview-table"><thead><tr><th>Работа</th><th>Стоимость, ₽</th></tr></thead><tbody>${names.map((name, index) => `<tr><td>${name}</td><td><input aria-label="Стоимость: ${name}" data-price="${index}" type="number" min="0" max="10000000" inputmode="numeric" value="${prices[index]}"></td></tr>`).join('')}</tbody></table><div class="document-total"><span>Итого</span><strong id="preview-total">${formatRubles(total())}</strong></div><p class="document-note">Измените цену любой позиции — итог пересчитается сразу.</p>`;
    documentHost.querySelectorAll('[data-price]').forEach(input => {
      input.addEventListener('input', () => {
        const value = Number(input.value);
        if (Number.isFinite(value) && value >= 0 && value <= 10000000) {
          prices[Number(input.dataset.price)] = value;
          const totalEl = document.querySelector('#preview-total');
          if (totalEl) totalEl.textContent = formatRubles(total());
        }
      });
    });
  } else if (step === 1) {
    documentHost.innerHTML = `<div class="step-result"><span class="overline">Согласование с заказчиком</span><h3>Один документ вместо переписки.</h3><p>Заказчик открывает смету, проверяет позиции и общую стоимость, затем принимает предложение или просит внести изменения.</p><div class="link-preview">сметра / предложение / ремонт-ванной</div><div class="document-total"><span>К согласованию</span><strong>${formatRubles(total())}</strong></div><div class="hero-cta"><button class="btn primary" id="demo-approve" type="button">Согласовать смету</button></div></div>`;
    document.querySelector('#demo-approve')?.addEventListener('click', () => renderPreview(2));
  } else if (step === 2) {
    documentHost.innerHTML = `<div class="step-result"><span class="status-line">Условия согласованы</span><h3>Из сметы — в заказ.</h3><p>Согласованные позиции становятся рабочим планом: можно отслеживать этапы и держать договорённости в одном месте.</p><table class="preview-table"><tbody><tr><td>Подготовка и демонтаж</td><td>Готово</td></tr><tr><td>Плитка и отделка</td><td>В работе</td></tr><tr><td>Монтаж сантехники</td><td>Следующий этап</td></tr></tbody></table></div>`;
  } else {
    const received = Math.round(total() * .4);
    documentHost.innerHTML = `<div class="step-result"><span class="overline">Поступления и остаток</span><h3>Финансы под контролем.</h3><p>Фиксируйте полученные авансы и расходы, чтобы понимать текущий остаток по объекту.</p><div class="document-total"><span>Получено · 40%</span><strong>${formatRubles(received)}</strong></div><div class="progress-line"><span></span></div><div class="document-total"><span>Осталось</span><strong>${formatRubles(total() - received)}</strong></div></div>`;
  }
  documentHost.classList.remove('demo-enter');
  void documentHost.offsetWidth;
  documentHost.classList.add('demo-enter');
}

steps.forEach((button, index) => {
  button.id = 'preview-tab-' + index;
  button.setAttribute('aria-controls', 'preview-document');
  button.tabIndex = index === 0 ? 0 : -1;
  button.addEventListener('click', () => renderPreview(index));
  button.addEventListener('keydown', event => {
    const next = event.key === 'Home' ? 0 :
      event.key === 'End' ? steps.length - 1 :
      event.key === 'ArrowRight' ? (index + 1) % steps.length :
      event.key === 'ArrowLeft' ? (index + steps.length - 1) % steps.length : -1;
    if (next < 0) return;
    event.preventDefault();
    renderPreview(next);
    steps[next].focus();
  });
});
renderPreview(0);

const previewButton = document.querySelector('#use-preview');
previewButton?.addEventListener('click', () => {
  const draft = {
    title: 'Ремонт ванной комнаты',
    client: 'Заказчик',
    items: names.map((name, index) => ({
      name, quantity: '1', unit: 'компл.', unit_price: Math.round(prices[index] * 100)
    }))
  };
  sessionStorage.setItem('smetra.previewDraft', JSON.stringify(draft));
  location.href = '/app?register=1';
});

const formatPrice = amount => new Intl.NumberFormat('ru-RU', {
  style: 'currency', currency: 'RUB', maximumFractionDigits: 0
}).format(amount / 100);

fetch('/api/billing/pricing', {signal: AbortSignal.timeout(5000)})
  .then(response => { if (!response.ok) throw new Error('Pricing unavailable'); return response.json(); })
  .then(data => {
    document.querySelectorAll('[data-price-code]').forEach(element => {
      const amount = data.plans?.[element.dataset.priceCode];
      if (Number.isSafeInteger(amount) && amount >= 0) element.textContent = formatPrice(amount);
    });
  })
  .catch(() => {
    // The server-confirmed prices are shown in the HTML until pricing API is reachable.
  });

const nav = document.querySelector('.black-landing .nav');
const menuToggle = document.querySelector('.landing-menu-toggle');
const navLinks = [...document.querySelectorAll('#landing-nav a')];
function closeMenu() {
  if (!nav || !menuToggle) return;
  nav.classList.remove('is-menu-open');
  menuToggle.setAttribute('aria-expanded', 'false');
  menuToggle.setAttribute('aria-label', 'Открыть меню');
}
menuToggle?.addEventListener('click', () => {
  const open = menuToggle.getAttribute('aria-expanded') !== 'true';
  menuToggle.setAttribute('aria-expanded', String(open));
  menuToggle.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
  nav?.classList.toggle('is-menu-open', open);
});
navLinks.forEach(link => link.addEventListener('click', closeMenu));
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(); });
document.addEventListener('click', event => {
  if (nav && menuToggle?.getAttribute('aria-expanded') === 'true' && !nav.contains(event.target)) closeMenu();
});

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
if (!reducedMotion && 'IntersectionObserver' in window) {
  const targets = document.querySelectorAll('.landing-section,.feature-list article');
  targets.forEach((element, index) => {
    element.classList.add('scroll-reveal');
    element.style.setProperty('--reveal-delay', `${Math.min(index % 3, 2) * 55}ms`);
  });
  document.body.classList.add('motion-ready');
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('in-view');
        observer.unobserve(entry.target);
      }
    });
  }, {threshold: .08, rootMargin: '0px 0px -24px 0px'});
  targets.forEach(element => observer.observe(element));
}
