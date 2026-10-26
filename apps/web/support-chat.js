'use strict';
/* Support as a messenger: threads in a rail on the left, a Telegram-like
   conversation on the right. The AI support agent answers first; the user can
   bring in a person at any time and the history stays in the same thread. */
window.SmetraSupport = (() => {
  const kit = () => window.SmetraChatKit;
  const icon = (name, size = 18) => window.SmetraIcons ? window.SmetraIcons.svg(name, size) : '';
  const topics = ['Вход в аккаунт', 'Оплата и подписка', 'Работа со сметой', 'Ассистент и лимиты', 'Клиентская ссылка'];
  let revision = 0, pollTimer = null;

  const stop = () => { clearInterval(pollTimer); pollTimer = null; };

  const render = async (parentActive = () => true) => {
    stop();
    const mine = ++revision, owner = user;
    const active = () => parentActive() && mine === revision && owner === user && tab === 'support';
    const state = { threads: [], current: null, messages: [], sending: false, topic: '' };

    const railCollapsed = (() => { try { return localStorage.getItem('smetra.support.rail-collapsed') === 'true'; } catch { return false; } })();
    view(`<section class="support-studio tg${railCollapsed ? ' is-rail-collapsed' : ''}" aria-label="Поддержка">
      <aside class="tg-rail" aria-label="Обращения">
        <header class="tg-rail-head">${typeof railToggleMarkup === 'function' ? railToggleMarkup(railCollapsed, 'support-rail-toggle') : ''}<h1>Поддержка</h1><button class="btn small" type="button" id="support-new" aria-label="Новое обращение" title="Новое обращение">${icon('pencil')}<span>Новое</span></button></header>
        <div class="tg-list" id="support-threads" role="list"></div>
        <footer class="tg-rail-foot">${typeof supportContacts === 'string' ? supportContacts : ''}</footer>
      </aside>
      <div class="tg-chat" id="support-chat">
        <header class="tg-head">
          <button class="icon-button tg-back" type="button" id="support-back" aria-label="К списку обращений">${icon('arrow-left')}</button>
          <span class="tg-avatar tg-avatar-brand" aria-hidden="true">${icon('headset', 20)}</span>
          <div class="tg-head-copy"><strong id="support-title">Поддержка Сметры</strong><small id="support-status">ИИ-помощник · отвечает за несколько секунд</small></div>
          <button class="btn small" type="button" id="support-handoff" hidden>${icon('user')}<span>Позвать сотрудника</span></button>
        </header>
        ${typeof emailNotice === 'function' ? emailNotice() : ''}
        <div class="tg-messages" id="support-messages" role="log" aria-live="polite"></div>
        <form id="support-form" class="tg-compose" autocomplete="off">
          <label class="visually-hidden" for="message">Сообщение в поддержку</label>
          <textarea id="message" rows="1" minlength="2" maxlength="4000" placeholder="Сообщение…" required></textarea>
          <button class="tg-send" type="submit" aria-label="Отправить сообщение" title="Отправить">${icon('send-plane', 20)}</button>
        </form>
      </div>
    </section>`);

    const root = document.querySelector('.support-studio');
    const list = root.querySelector('#support-threads');
    const log = root.querySelector('#support-messages');
    const form = root.querySelector('#support-form');
    const input = form.querySelector('#message');
    const send = form.querySelector('.tg-send');
    const title = root.querySelector('#support-title');
    const status = root.querySelector('#support-status');
    const handoff = root.querySelector('#support-handoff');
    const grow = kit().composer(input, form);
    if (typeof bindRailToggle === 'function') bindRailToggle(root.querySelector('#support-rail-toggle'), root, 'smetra.support.rail-collapsed');

    const welcome = () => `<div class="tg-welcome">
        <span class="tg-avatar tg-avatar-brand tg-avatar-lg" aria-hidden="true">${icon('headset', 28)}</span>
        <h2>Чем помочь?</h2>
        <p>Опишите, что не получается. ИИ-помощник ответит сразу, а если вопрос требует проверки — передаст его сотруднику. История сохранится здесь.</p>
        <div class="support-topics tg-chips">${topics.map(topic => `<button type="button" data-support-topic="${kit().esc(topic)}" aria-pressed="false">${kit().esc(topic)}</button>`).join('')}</div>
      </div>`;

    const toMessages = rows => rows.map(m => ({
      id: m.id, body: m.body, created_at: Number(m.created_at || 0),
      mine: m.sender_type === 'user',
      kind: m.sender_type === 'system' ? 'system' : m.sender_type,
      author: m.sender_type === 'admin' ? 'Сотрудник поддержки' : m.sender_type === 'assistant' ? 'ИИ поддержки' : 'Вы',
    }));

    const paintHead = () => {
      const c = state.current;
      title.textContent = c ? (c.subject || 'Обращение') : 'Поддержка Сметры';
      status.textContent = !c ? 'ИИ-помощник · отвечает за несколько секунд'
        : c.status === 'closed' ? 'Обращение закрыто'
        : c.needs_human ? 'Передано сотруднику · ответим здесь'
        : 'ИИ-помощник · можно позвать сотрудника';
      status.classList.toggle('is-waiting', Boolean(c?.needs_human));
      handoff.hidden = !c || c.needs_human || c.status === 'closed';
      const closed = c?.status === 'closed';
      input.disabled = closed;
      input.placeholder = closed ? 'Обращение закрыто — создайте новое' : 'Сообщение…';
      root.classList.toggle('is-chat-open', Boolean(c) || root.classList.contains('is-composing'));
    };

    const paintMessages = (extra = '') => {
      if (!state.current && !state.messages.length) { log.innerHTML = welcome() + extra; bindTopics(); return; }
      log.innerHTML = kit().thread(state.messages, { showAuthors: true }) + extra;
      log.scrollTop = log.scrollHeight;
    };

    const paintList = () => {
      if (!state.threads.length) { list.innerHTML = '<p class="tg-list-empty">Здесь появятся ваши обращения.</p>'; return; }
      list.innerHTML = state.threads.map(t => {
        const preview = t.last_message || (t.needs_human ? 'Ожидает сотрудника' : 'Открыть переписку');
        const on = state.current?.id === t.id;
        return `<button type="button" class="tg-row${on ? ' is-active' : ''}" data-thread="${kit().esc(t.id)}" role="listitem" aria-current="${on}" title="${kit().esc(t.subject || 'Обращение')}">
          <span class="tg-avatar tg-avatar-brand" aria-hidden="true">${icon('headset', 18)}</span>
          <span class="tg-row-copy"><span class="tg-row-top"><strong>${kit().esc(t.subject || 'Обращение')}</strong><time>${kit().esc(kit().stamp(t.last_message_at || t.updated_at || t.created_at))}</time></span>
          <span class="tg-row-bottom"><span class="tg-preview">${kit().esc(preview)}</span>${t.status === 'closed' ? '<span class="tg-badge is-muted">закрыто</span>' : t.needs_human ? '<span class="tg-badge is-waiting">сотрудник</span>' : ''}</span></span>
        </button>`;
      }).join('');
    };

    const bindTopics = () => {
      const buttons = [...log.querySelectorAll('[data-support-topic]')];
      buttons.forEach(button => button.onclick = () => {
        const prefix = state.topic + ': ';
        const text = state.topic && input.value.startsWith(prefix) ? input.value.slice(prefix.length) : input.value;
        state.topic = button.dataset.supportTopic;
        input.value = state.topic + ': ' + text;
        buttons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
        input.focus(); grow();
      });
    };

    const loadThreads = async () => {
      const data = await api('/support/threads');
      if (!active()) return;
      state.threads = Array.isArray(data?.threads) ? data.threads : [];
      if (state.current) state.current = state.threads.find(t => t.id === state.current.id) || state.current;
      paintList(); paintHead();
    };

    const loadMessages = async (quiet = false) => {
      const c = state.current; if (!c) return;
      const data = await api('/support/threads/' + encodeURIComponent(c.id) + '/messages');
      if (!active() || state.current?.id !== c.id) return;
      const next = toMessages(Array.isArray(data?.messages) ? data.messages : []);
      if (quiet && next.length === state.messages.length) return;
      state.messages = next; paintMessages();
    };

    const open = async id => {
      state.current = state.threads.find(t => t.id === id) || null;
      state.messages = []; paintList(); paintHead();
      log.innerHTML = '<div class="tg-loading" role="status">Загружаем переписку…</div>';
      try { await loadMessages(); } catch (error) { if (active()) log.innerHTML = `<p class="tg-error" role="alert">${kit().esc(error.message)}</p>`; }
      if (active() && matchMedia?.('(min-width:801px)')?.matches) input.focus({ preventScroll: true });
    };

    const fresh = () => {
      state.current = null; state.messages = []; state.topic = '';
      root.classList.add('is-composing');
      paintList(); paintHead(); paintMessages();
      input.focus({ preventScroll: true });
    };

    list.addEventListener('click', event => { const row = event.target.closest('[data-thread]'); if (row) { root.classList.remove('is-composing'); open(row.dataset.thread); } });
    root.querySelector('#support-new').onclick = fresh;
    root.querySelector('#support-back').onclick = () => { state.current = null; state.messages = []; root.classList.remove('is-chat-open', 'is-composing'); paintList(); paintHead(); paintMessages(); };

    handoff.onclick = async () => {
      const c = state.current; if (!c || handoff.disabled) return;
      const ok = await window.SmetraDialog.confirm({ title: 'Позвать сотрудника?', message: 'Обращение попадёт в очередь команды поддержки. Ответ придёт в эту переписку.', confirmLabel: 'Позвать' });
      if (!ok || !active()) return;
      handoff.disabled = true;
      try {
        await api('/support/threads/' + encodeURIComponent(c.id) + '/handoff', { method: 'POST', body: JSON.stringify({ reason: 'user_requested_human' }) });
        if (!active()) return;
        c.needs_human = true; paintHead(); await loadMessages(); await loadThreads();
      } catch (error) { notify(error.message); }
      finally { handoff.disabled = false; }
    };

    form.onsubmit = async event => {
      event.preventDefault();
      const message = input.value.trim();
      if (!message || state.sending || send.disabled) return;
      state.sending = true; send.disabled = true;
      const optimistic = { id: 'pending', body: message, created_at: Date.now() / 1000, mine: true, kind: 'user', author: 'Вы', pending: true };
      const before = state.messages;
      state.messages = [...before, optimistic];
      root.classList.add('is-chat-open');
      paintMessages(state.current?.needs_human ? '' : kit().typing('Поддержка печатает'));
      try {
        if (state.current) {
          await api('/support/threads/' + encodeURIComponent(state.current.id) + '/messages', { method: 'POST', body: JSON.stringify({ message }) });
          if (!active()) return;
          if (input.value.trim() === message) { input.value = ''; grow(); }
          await loadMessages(); await loadThreads();
        } else {
          const subject = (state.topic || message.replace(/\s+/g, ' ').slice(0, 60)).trim();
          const data = await api('/support', { method: 'POST', body: JSON.stringify({ message, subject }) });
          if (!active()) return;
          if (input.value.trim() === message) { input.value = ''; grow(); }
          root.classList.remove('is-composing');
          await loadThreads();
          if (data?.ticket_id) await open(data.ticket_id);
        }
      } catch (error) {
        if (!active()) return;
        state.messages = before; paintMessages(); notify(error.message);
      } finally {
        state.sending = false;
        if (send.isConnected) send.disabled = false;
      }
    };

    paintHead(); paintMessages();
    try { await loadThreads(); } catch (error) { if (active()) list.innerHTML = `<p class="tg-error" role="alert">${kit().esc(error.message)}</p>`; }
    if (!active()) return;
    // With no history yet there is nothing to pick: go straight to writing.
    if (!state.threads.length) { root.classList.add('is-composing'); paintHead(); }
    // A person may answer at any moment; keep the open thread fresh.
    pollTimer = setInterval(() => {
      if (!active()) { stop(); return; }
      if (document.hidden || state.sending || !state.current) return;
      loadMessages(true).catch(() => {});
    }, 8000);
  };

  return { render, stop };
})();
