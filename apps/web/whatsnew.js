/* «Что нового»: product updates in Markdown, views counted once per person, reactions. */
window.SmetraWhatsNew = (() => {
  const REACTIONS = [['up', '👍', 'Полезно'], ['love', '❤️', 'Нравится'], ['fire', '🔥', 'Огонь'], ['down', '👎', 'Не нравится']];
  const e = escapeHtml;
  const longDate = seconds => new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(seconds * 1000));
  const plural = (n, one, few, many) => { const m10 = n % 10, m100 = n % 100; return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many; };
  const eye = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
  let observer;

  const badge = () => window.SmetraRefreshWhatsNew?.();

  const reactionBar = post => `<div class="whatsnew-reactions" role="group" aria-label="Оценка обновления">${REACTIONS.map(([key, glyph, label]) =>
    `<button type="button" class="whatsnew-reaction${post.my_reaction === key ? ' is-active' : ''}" data-reaction="${key}" aria-pressed="${post.my_reaction === key}" aria-label="${label}: ${post.reactions[key]}" title="${label}"><span aria-hidden="true">${glyph}</span><b>${post.reactions[key] || ''}</b></button>`).join('')}</div>`;

  const card = (post, admin) => `<article class="whatsnew-post${post.seen ? '' : ' is-new'}" data-post="${e(post.id)}">
    <header class="whatsnew-head">
      <div class="whatsnew-meta"><time datetime="${new Date(post.published_at * 1000).toISOString()}">${longDate(post.published_at)}</time>${post.tag ? `<span class="whatsnew-tag">${e(post.tag)}</span>` : ''}${post.seen ? '' : '<span class="whatsnew-new" role="img" aria-label="Непрочитано" title="Непрочитано"></span>'}</div>
      <h2>${e(post.title)}</h2>
    </header>
    <div class="whatsnew-body assistant-markdown">${window.SmetraMarkdown.render(post.body)}</div>
    <footer class="whatsnew-foot">${reactionBar(post)}<span class="whatsnew-views" title="Сколько человек прочитали">${eye}<span data-views>${post.views}</span></span>${admin ? `<span class="whatsnew-admin"><button type="button" class="btn small ghost" data-edit>Изменить</button><button type="button" class="btn small ghost danger" data-remove>Удалить</button></span>` : ''}</footer>
  </article>`;

  const editor = (post = {}) => `<form class="whatsnew-editor panel" id="whatsnew-editor" data-id="${e(post.id || '')}">
    <div class="whatsnew-editor-head"><strong>${post.id ? 'Изменить публикацию' : 'Новая публикация'}</strong><div class="whatsnew-editor-tabs" role="tablist"><button type="button" role="tab" aria-selected="true" data-mode="write">Текст</button><button type="button" role="tab" aria-selected="false" data-mode="preview">Просмотр</button></div></div>
    <div class="form-grid"><div class="field"><label for="whatsnew-title">Заголовок</label><input id="whatsnew-title" name="title" required maxlength="140" value="${e(post.title || '')}" placeholder="Хранилище файлов"></div>
    <div class="field"><label for="whatsnew-tag">Метка</label><input id="whatsnew-tag" name="tag" maxlength="40" value="${e(post.tag || '')}" placeholder="Новое, Улучшение, Исправление"></div></div>
    <div class="field"><label for="whatsnew-body">Текст в Markdown</label><textarea id="whatsnew-body" name="body" rows="10" required maxlength="20000" placeholder="## Что изменилось&#10;- Пункт">${e(post.body || '')}</textarea><div class="whatsnew-preview assistant-markdown" hidden></div></div>
    <p class="form-error" role="alert"></p>
    <div class="form-actions"><button class="btn primary" type="submit">${post.id ? 'Сохранить' : 'Опубликовать'}</button><button class="btn" type="button" data-cancel>Отмена</button></div>
  </form>`;

  async function render(active) {
    const data = await api('/changelog');
    if (!active()) return;
    const items = data.items, admin = data.can_publish;
    const unread = items.filter(post => !post.seen).length;
    view(`<section class="workspace-section section-whatsnew">${header('Что нового', unread ? `${unread} ${plural(unread, 'новое обновление', 'новых обновления', 'новых обновлений')}` : 'Обновления Сметры', admin ? '<button class="btn small primary" type="button" id="whatsnew-compose">Новая публикация</button>' : '')}
      <div id="whatsnew-editor-host"></div>
      <div class="whatsnew-feed">${items.length ? items.map(post => card(post, admin)).join('') : '<div class="empty"><h3>Пока тихо</h3><p>Здесь появятся новые возможности и улучшения Сметры.</p></div>'}</div>
    </section>`);
    const feed = document.querySelector('.whatsnew-feed'), host = document.querySelector('#whatsnew-editor-host');

    // A post counts as read once most of it has been on screen for a moment.
    observer?.disconnect();
    const timers = new Map();
    observer = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
      for (const entry of entries) {
        const node = entry.target, id = node.dataset.post;
        if (entry.isIntersecting) {
          if (!timers.has(id)) timers.set(id, setTimeout(() => markSeen(node), 1200));
        } else { clearTimeout(timers.get(id)); timers.delete(id); }
      }
    }, { threshold: 0.5 }) : null;
    async function markSeen(node) {
      observer?.unobserve(node);
      const post = items.find(item => item.id === node.dataset.post);
      if (!post || post.seen || !node.isConnected) return;
      post.seen = true;
      try {
        await api('/changelog/' + encodeURIComponent(post.id) + '/view', { method: 'POST', body: '{}' });
        post.views += 1;
        node.querySelector('[data-views]').textContent = post.views;
        node.classList.remove('is-new');
        node.querySelector('.whatsnew-new')?.classList.add('is-fading');
        badge();
      } catch { post.seen = false; }
    }
    feed.querySelectorAll('.whatsnew-post.is-new').forEach(node => observer ? observer.observe(node) : markSeen(node));

    feed.onclick = async event => {
      const node = event.target.closest('.whatsnew-post');
      if (!node) return;
      const post = items.find(item => item.id === node.dataset.post);
      const reaction = event.target.closest('[data-reaction]');
      if (reaction) {
        const value = post.my_reaction === reaction.dataset.reaction ? null : reaction.dataset.reaction;
        try {
          const result = await api('/changelog/' + encodeURIComponent(post.id) + '/reaction', { method: 'POST', body: JSON.stringify({ reaction: value }) });
          Object.assign(post, result);
          node.querySelector('.whatsnew-reactions').outerHTML = reactionBar(post);
        } catch (error) { notify(error.message); }
        return;
      }
      if (event.target.closest('[data-edit]')) { openEditor(post); return; }
      if (event.target.closest('[data-remove]')) {
        if (!confirm('Удалить публикацию «' + post.title + '»?')) return;
        try { await api('/changelog/' + encodeURIComponent(post.id), { method: 'DELETE' }); notify('Публикация удалена'); await render(active); } catch (error) { notify(error.message); }
      }
    };

    function openEditor(post) {
      host.innerHTML = editor(post);
      const form = host.querySelector('form'), body = form.elements.body, preview = form.querySelector('.whatsnew-preview');
      form.querySelector('.whatsnew-editor-tabs').onclick = event => {
        const tab = event.target.closest('[data-mode]'); if (!tab) return;
        const showPreview = tab.dataset.mode === 'preview';
        form.querySelectorAll('[data-mode]').forEach(button => button.setAttribute('aria-selected', String(button === tab)));
        preview.innerHTML = showPreview ? window.SmetraMarkdown.render(body.value || '*Пусто*') : '';
        preview.hidden = !showPreview; body.hidden = showPreview;
      };
      form.querySelector('[data-cancel]').onclick = () => { host.innerHTML = ''; };
      form.onsubmit = async event => {
        event.preventDefault();
        const button = form.querySelector('[type=submit]'), error = form.querySelector('[role=alert]');
        button.disabled = true; error.textContent = '';
        try {
          const payload = JSON.stringify({ title: form.elements.title.value, tag: form.elements.tag.value, body: body.value });
          if (form.dataset.id) await api('/changelog/' + encodeURIComponent(form.dataset.id), { method: 'PATCH', body: payload });
          else await api('/changelog', { method: 'POST', body: payload });
          notify(form.dataset.id ? 'Публикация обновлена' : 'Обновление опубликовано');
          await render(active);
        } catch (failure) { error.textContent = failure.message; button.disabled = false; }
      };
      form.elements.title.focus();
      host.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    document.querySelector('#whatsnew-compose')?.addEventListener('click', () => openEditor());
  }

  return { render, badge };
})();
