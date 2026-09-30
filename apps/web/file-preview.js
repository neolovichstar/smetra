/* Authenticated previews for files already attached to a workspace record. */
window.SmetraFilePreview = (() => {
  let dialog;
  let objectUrl;
  let controller;

  function release() {
    controller?.abort();
    controller = undefined;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = undefined;
    dialog?.querySelector('.file-preview-body')?.replaceChildren();
  }

  function close() {
    if (dialog?.open) dialog.close();
    release();
  }

  function ensureDialog() {
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.className = 'file-preview-dialog';
    dialog.innerHTML = '<div class="file-preview-top"><div><span>СМЕТРА / ФАЙЛ</span><strong class="file-preview-name"></strong></div><div class="file-preview-actions"><button class="btn small file-preview-save" type="button">Скачать</button><button class="file-preview-close" type="button" aria-label="Закрыть просмотр">×</button></div></div><div class="file-preview-body" role="status"></div>';
    dialog.querySelector('.file-preview-close').addEventListener('click', close);
    dialog.addEventListener('close', release);
    dialog.addEventListener('click', event => {
      if (event.target === dialog) close();
    });
    document.body.append(dialog);
    return dialog;
  }

  async function open(file, workspaceId) {
    const view = ensureDialog();
    release();
    view.querySelector('.file-preview-name').textContent = file.name;
    const body = view.querySelector('.file-preview-body');
    body.textContent = 'Открываем файл…';
    view.querySelector('.file-preview-save').disabled = true;
    if (!view.open) view.showModal();
    controller = new AbortController();
    const request = controller;
    try {
      const response = await fetch('/api/files/' + encodeURIComponent(file.id), {
        credentials: 'same-origin',
        headers: workspaceId ? {'X-Workspace-Id': workspaceId} : {},
        signal: request.signal
      });
      if (!response.ok) {
        let message = 'Не удалось открыть файл';
        try { message = (await response.json()).error || message; } catch (_) { /* HTTP error */ }
        throw new Error(message);
      }
      const bytes = await response.blob();
      if (request !== controller || !view.open) return;
      if (!['image/png', 'image/jpeg', 'application/pdf', 'text/plain'].includes(file.mime) ||
          bytes.type !== file.mime) throw new Error('Формат файла не поддерживается');
      body.replaceChildren();
      if (file.mime === 'text/plain') {
        const markdown = file.name.toLowerCase().endsWith('.md');
        const content = document.createElement(markdown ? 'div' : 'pre');
        content.className = markdown ? 'assistant-markdown file-preview-markdown' : 'file-preview-text';
        const text = await bytes.text();
        if (markdown && typeof window.assistantMarkdown === 'function' && text.length <= 200000) content.innerHTML = window.assistantMarkdown(text);
        else content.textContent = text;
        if (request !== controller || !view.open) return;
        body.append(content);
      } else {
        objectUrl = URL.createObjectURL(bytes);
        if (file.mime === 'application/pdf') {
          const frame = document.createElement('iframe');
          frame.title = file.name;
          frame.src = objectUrl;
          frame.className = 'file-preview-pdf';
          body.append(frame);
        } else {
          const image = document.createElement('img');
          image.alt = file.name;
          image.src = objectUrl;
          image.className = 'file-preview-image';
          body.append(image);
        }
      }
      const save = view.querySelector('.file-preview-save');
      save.disabled = false;
      save.onclick = () => {
        const url = objectUrl || URL.createObjectURL(bytes);
        const link = document.createElement('a');
        link.href = url;
        link.download = file.name;
        link.click();
        if (!objectUrl) setTimeout(() => URL.revokeObjectURL(url), 30000);
      };
    } catch (error) {
      if (error.name === 'AbortError' || !view.open) return;
      body.textContent = error.message;
    }
  }

  return {open, close};
})();
