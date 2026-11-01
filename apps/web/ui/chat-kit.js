/* Messenger building blocks shared by support and the communication center:
   day dividers, grouped bubbles with time inside, initials avatars and a
   typing indicator. Everything is escaped text; no inline styles (CSP). */
(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const date = value => new Date(Number(value || 0) * 1000);
  const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  const clock = value => value ? new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' }).format(date(value)) : '';
  const day = value => {
    const d = date(value), today = new Date(), yesterday = new Date(Date.now() - 864e5);
    if (sameDay(d, today)) return 'Сегодня';
    if (sameDay(d, yesterday)) return 'Вчера';
    return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', ...(d.getFullYear() !== today.getFullYear() ? { year: 'numeric' } : {}) }).format(d);
  };
  // Short stamp for chat lists: time today, weekday this week, date otherwise.
  const stamp = value => {
    if (!value) return '';
    const d = date(value), now = new Date();
    if (sameDay(d, now)) return clock(value);
    if (now - d < 6 * 864e5) return new Intl.DateTimeFormat('ru-RU', { weekday: 'short' }).format(d);
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit' }).format(d);
  };
  const initials = name => {
    const words = String(name || '?').trim().split(/\s+/).filter(Boolean);
    return esc(((words[0]?.[0] || '?') + (words[1]?.[0] || '')).toLocaleUpperCase('ru-RU'));
  };
  // Stable tint per name, chosen from a small palette defined in CSS.
  const tint = name => Array.from(String(name || '')).reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % 6;
  const linkify = text => esc(text).replace(/https?:\/\/[^\s<]+/g, url => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`).replace(/\n/g, '<br>');

  /* messages: [{id, body, created_at, mine, author, kind: 'user'|'system'|'assistant'|'admin', pending}] */
  const thread = (messages, { showAuthors = false } = {}) => {
    let html = '', lastDay = null, previous = null;
    for (const m of messages) {
      const d = date(m.created_at || Date.now() / 1000);
      if (!lastDay || !sameDay(d, lastDay)) { html += `<div class="tg-day"><span>${esc(day(m.created_at || Date.now() / 1000))}</span></div>`; previous = null; }
      lastDay = d;
      if (m.kind === 'system') { html += `<div class="tg-service"><span>${esc(m.body)}</span></div>`; previous = null; continue; }
      const grouped = previous && previous.mine === m.mine && previous.author === m.author && (m.created_at - previous.created_at) < 300;
      const author = showAuthors && !m.mine && !grouped && m.author ? `<span class="tg-author tg-tint-${tint(m.author)}">${esc(m.author)}</span>` : '';
      html += `<div class="tg-msg${m.mine ? ' is-mine' : ''}${grouped ? ' is-grouped' : ''}${m.pending ? ' is-pending' : ''}${m.failed ? ' is-failed' : ''}" data-message-id="${esc(m.id || '')}">`
        + `<div class="tg-bubble">${author}<span class="tg-text">${linkify(m.body)}</span><span class="tg-meta">${m.failed ? 'не отправлено' : esc(clock(m.created_at))}${m.mine && !m.failed ? `<span class="tg-tick" aria-hidden="true">${m.pending ? '' : '✓✓'}</span>` : ''}</span></div></div>`;
      previous = m;
    }
    return html;
  };
  const typing = label => `<div class="tg-msg tg-typing" role="status"><div class="tg-bubble"><span class="visually-hidden">${esc(label)}</span><i></i><i></i><i></i></div></div>`;
  // Auto-growing composer textarea, Enter sends and Shift+Enter breaks lines.
  const composer = (textarea, form) => {
    const grow = () => { textarea.style.height = 'auto'; textarea.style.height = Math.min(textarea.scrollHeight, 180) + 'px'; };
    textarea.addEventListener('input', grow);
    textarea.addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && !matchMedia?.('(pointer:coarse)')?.matches) { event.preventDefault(); form.requestSubmit(); }
    });
    return grow;
  };
  window.SmetraChatKit = { esc, clock, day, stamp, initials, tint, thread, typing, composer };
})();
