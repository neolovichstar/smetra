'use strict';

/* Recover from a transient failed stylesheet request (for example a stale
   browser/network cache). Do not change the design or retry healthy CSS. */
(() => {
  const recoverStyles = () => {
    const links = document.querySelectorAll('link[rel="stylesheet"][href^="/ui/"]');
    for (const link of links) {
      if (link.sheet || link.dataset.cssRetried) continue;
      link.dataset.cssRetried = '1';
      const retry = link.cloneNode(false);
      const url = new URL(link.href);
      url.searchParams.set('_css_retry', Date.now().toString(36));
      retry.href = url.href;
      retry.addEventListener('load', () => link.remove(), { once: true });
      retry.addEventListener('error', () => retry.remove(), { once: true });
      link.insertAdjacentElement('afterend', retry);
    }
  };
  if (document.readyState === 'complete') setTimeout(recoverStyles, 200);
  else window.addEventListener('load', () => setTimeout(recoverStyles, 200), { once: true });
})();
/* Landing page behaviour. Prices come from the server; demo panels are labelled
   as examples. Motion is progressive: without JS or with reduced motion the
   page is complete and static. */
(() => {
  const root = document.documentElement;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const motion = !reduced && 'IntersectionObserver' in window;
  const params = new URLSearchParams(location.search);

  // Client-facing quote and intake pages reuse the workspace renderer.
  const publicToken = params.get('quote') || params.get('intake');
  if (publicToken) {
    // Client documents read like paper: the shared light theme, independent of the landing.
    document.body.classList.add('public-quote-mode');
    root.dataset.theme = 'light';
    document.body.classList.remove('dark');
    const load = src => new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src; script.async = false;
      script.onload = resolve; script.onerror = () => reject(Error('Не удалось загрузить страницу'));
      document.head.append(script);
    });
    Promise.all(['/ui/icons.js?v=20261025-r5', '/app.js?v=20261025-r5', '/workspace.js?v=20261025-r5'].map(load))
      .then(() => { root.dataset.theme = 'light'; document.body.classList.remove('dark'); })
      .then(() => params.get('intake') ? window.Workspace.intakePage(params.get('intake')) : window.Workspace.publicPage(params.get('quote')))
      .catch(error => {
        const host = document.querySelector('#public-quote');
        host.classList.remove('hidden');
        host.textContent = error.message;
      });
    return;
  }

  // Navigation gains a surface once the page scrolls.
  const nav = document.querySelector('#site-nav');
  let navFrame = 0;
  const syncNav = () => { navFrame = 0; nav?.classList.toggle('is-scrolled', scrollY > 8); };
  addEventListener('scroll', () => { if (!navFrame) navFrame = requestAnimationFrame(syncNav); }, { passive: true });
  syncNav();

  const money = value => new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value) + ' ₽';

  // Reveal on scroll.
  const onVisible = (element, callback, threshold = 0.2) => {
    if (!motion) { callback(); return; }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { observer.disconnect(); callback(); }
    }, { threshold, rootMargin: '0px 0px -8% 0px' });
    observer.observe(element);
  };
  if (motion) {
    root.classList.add('motion');
    const groups = new Map();
    document.querySelectorAll('.reveal').forEach(element => {
      const parent = element.parentElement;
      const index = groups.get(parent) || 0; groups.set(parent, index + 1);
      element.style.setProperty('--delay', Math.min(index, 4) * 70 + 'ms');
      onVisible(element, () => element.classList.add('is-visible'), 0.12);
    });
  }

  // Hero: lines arrive in order, then the total settles.
  const hero = document.querySelector('.hero-visual');
  if (hero) {
    hero.querySelectorAll('[data-line]').forEach((line, index) => line.style.setProperty('--delay', 350 + index * 140 + 'ms'));
    const total = hero.querySelector('[data-count-to]');
    onVisible(hero, () => {
      hero.classList.add('is-visible');
      if (!motion || !total) return;
      const target = Number(total.dataset.countTo), started = performance.now() + 700, duration = 900;
      const tick = now => {
        const progress = Math.min(1, Math.max(0, (now - started) / duration));
        total.textContent = money(Math.round(target * (1 - Math.pow(1 - progress, 3))));
        if (progress < 1) requestAnimationFrame(tick); else total.textContent = money(target);
      };
      total.textContent = money(0);
      requestAnimationFrame(tick);
    }, 0.3);
  }

  // Workflow stepper: accessible tabs with optional autoplay.
  const flow = document.querySelector('[data-flow]');
  if (flow) {
    const tabs = [...flow.querySelectorAll('[role=tab]')];
    const panels = [...flow.querySelectorAll('[data-panel]')];
    const stage = flow.querySelector('[role=tabpanel]');
    const duration = 6000;
    flow.style.setProperty('--flow-duration', duration + 'ms');
    let current = 0, timer = null, autoplay = motion;
    const show = (index, focus = false) => {
      current = (index + tabs.length) % tabs.length;
      tabs.forEach((tab, n) => {
        const selected = n === current;
        tab.setAttribute('aria-selected', String(selected));
        tab.tabIndex = selected ? 0 : -1;
        tab.classList.toggle('is-done', n < current);
        tab.classList.toggle('is-static', !autoplay);
      });
      panels.forEach((panel, n) => {
        const active = n === current;
        panel.hidden = !active;
        panel.classList.toggle('is-active', active);
        if (active && motion) { panel.classList.remove('is-entering'); void panel.offsetWidth; panel.classList.add('is-entering'); }
      });
      stage.setAttribute('aria-labelledby', tabs[current].id);
      if (focus) tabs[current].focus();
      schedule();
    };
    const schedule = () => {
      clearTimeout(timer);
      if (autoplay && !flow.hasAttribute('data-paused')) timer = setTimeout(() => show(current + 1), duration);
    };
    const stop = () => { autoplay = false; clearTimeout(timer); tabs.forEach(tab => tab.classList.add('is-static')); };
    tabs.forEach((tab, index) => tab.addEventListener('click', () => { stop(); show(index); }));
    flow.querySelector('[role=tablist]').addEventListener('keydown', event => {
      const keys = { ArrowRight: 1, ArrowLeft: -1, Home: 'first', End: 'last' };
      if (!(event.key in keys)) return;
      event.preventDefault(); stop();
      const step = keys[event.key];
      show(step === 'first' ? 0 : step === 'last' ? tabs.length - 1 : current + step, true);
    });
    const pause = () => { if (!autoplay) return; flow.setAttribute('data-paused', ''); clearTimeout(timer); };
    const resume = () => { if (!autoplay) return; flow.removeAttribute('data-paused'); show(current); };
    flow.addEventListener('pointerenter', pause); flow.addEventListener('pointerleave', resume);
    flow.addEventListener('focusin', pause); flow.addEventListener('focusout', event => { if (!flow.contains(event.relatedTarget)) resume(); });
    // Autoplay starts only while the section is on screen.
    if (autoplay) {
      clearTimeout(timer); tabs.forEach(tab => tab.setAttribute('aria-selected', String(tab === tabs[0])));
      const observer = new IntersectionObserver(entries => {
        const visible = entries.some(entry => entry.isIntersecting);
        if (visible) { flow.removeAttribute('data-paused'); show(current); } else { flow.setAttribute('data-paused', ''); clearTimeout(timer); }
      }, { threshold: 0.35 });
      observer.observe(flow);
    } else show(0);
  }

  // Assistant demo: message, typing, streamed answer, proposal.
  const chat = document.querySelector('[data-chat-demo]');
  if (chat) {
    const steps = [...chat.querySelectorAll('[data-chat-step]')];
    const text = chat.querySelector('[data-stream]');
    const finish = () => { steps.forEach(step => step.classList.add('is-shown')); chat.classList.remove('is-typing'); text.textContent = text.dataset.stream; };
    if (!motion) finish();
    else onVisible(chat, () => {
      const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
      (async () => {
        steps[0].classList.add('is-shown'); await wait(700);
        steps[1].classList.add('is-shown'); chat.classList.add('is-typing'); await wait(1100);
        chat.classList.remove('is-typing');
        const words = text.dataset.stream.split(' ');
        for (let i = 0; i < words.length; i++) { text.textContent = words.slice(0, i + 1).join(' '); await wait(55); }
        await wait(350); steps[2].classList.add('is-shown');
      })();
    }, 0.35);
  }

  // Pricing from the server catalog.
  const plansHost = document.querySelector('#plans');
  if (plansHost) {
    const features = () => window.SmetraPlanFeatures || {};
    const audience = { starter: 'Чтобы попробовать', pro_solo: 'Для мастера', pro_plus: 'Для учёта денег и закупок', team: 'Для команды до 5 человек' };
    let plans = [], period = 'month';
    const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const render = () => {
      plansHost.innerHTML = plans.map(plan => {
        const free = !plan.month;
        const price = free ? 0 : period === 'year' && plan.year ? plan.year : plan.month;
        const unit = free ? '' : period === 'year' && plan.year ? '/ год' : '/ месяц';
        const saving = !free && period === 'year' && plan.year ? plan.month * 12 - plan.year : 0;
        return `<article class="plan${plan.code === 'pro_solo' ? ' is-featured' : ''}">
          <span class="plan-audience">${escape(audience[plan.code] || '')}</span>
          <h3>${escape(plan.name)}</h3>
          <div class="plan-price"><strong>${money(price / 100)}</strong><span>${unit}</span>${saving > 0 ? `<small>Выгода ${money(saving / 100)} в год</small>` : ''}</div>
          <ul>${(features()[plan.code] || []).map(item => `<li>${escape(item)}</li>`).join('')}</ul>
          <a class="btn ${plan.code === 'pro_solo' ? 'primary' : ''}" href="${free ? '/app?register=1' : '/app?register=1#billing'}">${free ? 'Начать бесплатно' : 'Выбрать ' + escape(plan.name)}</a>
        </article>`;
      }).join('');
    };
    document.querySelectorAll('[data-period]').forEach(button => button.addEventListener('click', () => {
      period = button.dataset.period;
      document.querySelectorAll('[data-period]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      if (plans.length) render();
    }));
    fetch('/api/billing/catalog', { credentials: 'same-origin' })
      .then(response => response.ok ? response.json() : Promise.reject())
      .then(data => {
        if (!Array.isArray(data.plans) || !data.plans.length) throw Error();
        plans = data.plans; render();
      })
      .catch(() => { plansHost.innerHTML = '<p class="plans-loading">Не удалось загрузить цены. Актуальная стоимость всегда показана в кабинете перед оплатой.</p>'; });
  }
})();
