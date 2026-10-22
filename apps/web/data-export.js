(() => {
  const PAGE = 25;
  const encoder = new TextEncoder();
  let activeController = null;

  const crcTable = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let value = n;
    for (let bit = 0; bit < 8; bit++) value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    crcTable[n] = value >>> 0;
  }

  class ZipWriter {
    constructor(writable = null, signal = null) { this.writable = writable; this.signal = signal; this.parts = []; this.offset = 0; this.entries = []; }
    async write(bytes) {
      if (!bytes?.byteLength) return;
      if (this.writable) await this.writable.write(bytes);
      else this.parts.push(bytes);
      this.offset += bytes.byteLength;
    }
    async entry(path, produce) {
      if (this.entries.length >= 65535) throw Error('В архиве слишком много файлов.');
      const name = encoder.encode(path);
      if (name.length > 65535) throw Error('Слишком длинное имя файла в архиве.');
      const start = this.offset;
      const header = new Uint8Array(30 + name.length), view = new DataView(header.buffer);
      view.setUint32(0, 0x04034b50, true); view.setUint16(4, 20, true); view.setUint16(6, 0x0808, true);
      view.setUint16(8, 0, true); view.setUint16(10, 0, true); view.setUint16(12, 33, true);
      view.setUint16(26, name.length, true); header.set(name, 30);
      await this.write(header);
      let crc = 0xffffffff, size = 0;
      const sink = async chunk => {
        if (!(chunk instanceof Uint8Array)) chunk = new Uint8Array(chunk);
        if (size + chunk.byteLength > 0xffffffff) throw Error('Размер ZIP превышает допустимый предел.');
        for (let offset = 0; offset < chunk.byteLength; offset += 65536) {
          checkAbort(this.signal || { aborted: false });
          const part = chunk.subarray(offset, Math.min(offset + 65536, chunk.byteLength));
          for (const byte of part) crc = crcTable[(crc ^ byte) & 255] ^ (crc >>> 8);
          size += part.byteLength;
          await this.write(part);
          if (size % 1_048_576 < 65536) await new Promise(resolve => setTimeout(resolve, 0));
        }
      };
      await produce(sink);
      crc = (crc ^ 0xffffffff) >>> 0;
      const descriptor = new Uint8Array(16), d = new DataView(descriptor.buffer);
      d.setUint32(0, 0x08074b50, true); d.setUint32(4, crc, true); d.setUint32(8, size, true); d.setUint32(12, size, true);
      await this.write(descriptor);
      this.entries.push({ name, crc, size, start });
    }
    async finish() {
      const centralStart = this.offset;
      for (const entry of this.entries) {
        const header = new Uint8Array(46 + entry.name.length), v = new DataView(header.buffer);
        v.setUint32(0, 0x02014b50, true); v.setUint16(4, 20, true); v.setUint16(6, 20, true);
        v.setUint16(8, 0x0808, true); v.setUint16(10, 0, true); v.setUint16(12, 0, true); v.setUint16(14, 33, true);
        v.setUint32(16, entry.crc, true); v.setUint32(20, entry.size, true); v.setUint32(24, entry.size, true);
        v.setUint16(28, entry.name.length, true); v.setUint32(42, entry.start, true); header.set(entry.name, 46);
        await this.write(header);
      }
      const centralSize = this.offset - centralStart;
      if (this.entries.length > 65535 || centralStart > 0xffffffff || centralSize > 0xffffffff) throw Error('ZIP слишком велик для этого браузера.');
      const end = new Uint8Array(22), v = new DataView(end.buffer);
      v.setUint32(0, 0x06054b50, true); v.setUint16(8, this.entries.length, true); v.setUint16(10, this.entries.length, true);
      v.setUint32(12, centralSize, true); v.setUint32(16, centralStart, true);
      await this.write(end);
      if (this.writable) await this.writable.close();
      return this.writable ? null : new Blob(this.parts, { type: 'application/zip' });
    }
    async abort(error) {
      if (this.writable) { try { await this.writable.abort(error); } catch {} }
      this.parts.length = 0;
    }
  }

  function safeName(value) {
    return String(value || 'Файл').replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_').replace(/\.+$/g, '').trim().slice(0, 160) || 'Файл';
  }
  function checkAbort(signal) { if (signal.aborted) throw new DOMException('Экспорт остановлен.', 'AbortError'); }
  function wait(ms, signal) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(resolve, ms);
      signal.addEventListener('abort', () => { clearTimeout(timer); reject(new DOMException('Экспорт остановлен.', 'AbortError')); }, { once: true });
    });
  }
  async function request(path, workspaceId, signal) {
    for (let attempt = 0; ; attempt++) {
      checkAbort(signal);
      const response = await fetch('/api/export' + path, { credentials: 'same-origin', signal, headers: { 'X-Workspace-Id': workspaceId } });
      if (response.status === 429 && attempt < 5) {
        const body = await response.json().catch(() => ({}));
        await wait(Math.max(1, Number(body.retryAfter) || 5) * 1000, signal);
        continue;
      }
      if (!response.ok) {
        let body = {};
        if ((response.headers.get('content-type') || '').includes('json')) body = await response.json().catch(() => ({}));
        throw Error(body.error || 'Не удалось подготовить экспорт. Повторите попытку.');
      }
      return response;
    }
  }
  async function json(path, workspaceId, signal) {
    const response = await request(path, workspaceId, signal);
    return response.json();
  }
  async function addJsonTable(zip, table, workspaceId, signal, onRows) {
    let offset = 0, first = true;
    await zip.entry(`Данные/${table.name}.json`, async push => {
      await push(encoder.encode('['));
      while (true) {
        checkAbort(signal);
        const result = await json(`/data/${encodeURIComponent(table.name)}?offset=${offset}&limit=${PAGE}`, workspaceId, signal);
        const items = result.items || [];
        for (const item of items) {
          if (!first) await push(encoder.encode(','));
          await push(encoder.encode(JSON.stringify(item)));
          first = false;
        }
        onRows(items.length);
        offset += items.length;
        if (items.length < PAGE) break;
      }
      await push(encoder.encode(']'));
    });
  }
  async function fetchBytes(path, workspaceId, signal, expectedHash, expectedSize) {
    const response = await request(path, workspaceId, signal);
    const reader = response.body?.getReader();
    const chunks = [];
    let size = 0;
    if (reader) {
      while (true) {
        checkAbort(signal);
        const { value, done } = await reader.read();
        if (done) break;
        size += value.byteLength;
        chunks.push(value);
      }
    } else {
      const bytes = new Uint8Array(await response.arrayBuffer()); chunks.push(bytes); size = bytes.length;
    }
    if (size !== expectedSize) throw Error('Один из файлов изменился во время экспорта. Обновите страницу и повторите.');
    const content = new Uint8Array(size);
    let cursor = 0;
    for (const chunk of chunks) { content.set(chunk, cursor); cursor += chunk.byteLength; }
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', content));
    const hash = [...digest].map(value => value.toString(16).padStart(2, '0')).join('');
    if (hash !== expectedHash) throw Error('Проверка целостности одного из файлов не пройдена. Экспорт остановлен.');
    return [content];
  }
  function filePath(file) { return `Файлы/${safeName(file.id)}-${safeName(file.name)}`; }

  async function start(button, status) {
    if (activeController) return;
    const workspaceId = sessionStorage.getItem('workspace_id') || '';
    if (!workspaceId) { status.textContent = 'Не удалось определить рабочее пространство. Обновите страницу.'; return; }
    const controller = new AbortController(); activeController = controller;
    let zip, saveHandle;
    button.disabled = true;
    const cancel = document.querySelector('#export-cancel'); if (cancel) cancel.hidden = false;
    try {
      if (typeof window.showSaveFilePicker === 'function') {
        try { saveHandle = await window.showSaveFilePicker({ suggestedName: `smetra-export-${new Date().toISOString().slice(0, 10)}.zip`, types: [{ description: 'ZIP-архив', accept: { 'application/zip': ['.zip'] } }] }); }
        catch (error) { if (error.name === 'AbortError') throw error; }
      }
      zip = new ZipWriter(saveHandle ? await saveHandle.createWritable() : null, controller.signal);
      status.textContent = 'Читаю состав рабочего пространства…';
      const manifest = await json('', workspaceId, controller.signal);
      if (!manifest || manifest.format !== 'smetra-workspace-export') throw Error('Сервер вернул некорректный состав архива.');
      const summary = { ...manifest, files: manifest.files.map(({ id, name, mime, size, sha256, quote_id, project_id, client_id, public, created_at }) => ({ id, name, mime, size, sha256, quote_id, project_id, client_id, public, created_at })) };
      await zip.entry('README.txt', push => push(encoder.encode(
        'Экспорт рабочего пространства «сметра.»\n\n' +
        'Данные разделены на JSON-файлы в каталоге «Данные». Вложения и версии файлов находятся в каталоге «Файлы».\n' +
        'Служебные учётные данные, пароли и токены публичных ссылок в архив не включаются.\n' +
        'Для восстановления импортируйте JSON-разделы в совместимую версию «сметра.» с сохранением связей по id.\n' +
        'Архив создан по текущим данным; на время выгрузки не редактируйте рабочее пространство.\n'
      )));
      await zip.entry('manifest.json', push => push(encoder.encode(JSON.stringify(summary, null, 2))));
      const totalRows = manifest.tables.reduce((total, table) => total + table.count, 0);
      let completedRows = 0;
      for (let index = 0; index < manifest.tables.length; index++) {
        checkAbort(controller.signal);
        const table = manifest.tables[index];
        status.textContent = `Данные: ${table.name} · ${index + 1} из ${manifest.tables.length} разделов · ${completedRows.toLocaleString('ru-RU')} из ${totalRows.toLocaleString('ru-RU')} записей`;
        await addJsonTable(zip, table, workspaceId, controller.signal, count => { completedRows += count; });
      }
      for (let index = 0; index < manifest.files.length; index++) {
        checkAbort(controller.signal);
        const file = manifest.files[index];
        status.textContent = `Проверяю вложения · ${index + 1} из ${manifest.files.length}`;
        const chunks = await fetchBytes(`/files/${encodeURIComponent(file.id)}`, workspaceId, controller.signal, file.sha256, file.size);
        await zip.entry(filePath(file), async push => { for (const chunk of chunks) await push(chunk); });
      }
      const byFile = new Map(manifest.files.map(file => [file.id, file]));
      for (let index = 0; index < manifest.file_versions.length; index++) {
        checkAbort(controller.signal);
        const version = manifest.file_versions[index], file = byFile.get(version.file_id);
        status.textContent = `Добавляю историю файлов · ${index + 1} из ${manifest.file_versions.length}`;
        const chunks = await fetchBytes(`/versions/${encodeURIComponent(version.id)}`, workspaceId, controller.signal, version.sha256, version.size);
        const name = safeName(file?.name || version.file_id);
        await zip.entry(`Файлы/История/${safeName(version.file_id)}/r${version.revision}-${name}`, async push => { for (const chunk of chunks) await push(chunk); });
      }
      const blob = await zip.finish();
      if (blob) {
        const url = URL.createObjectURL(blob), link = document.createElement('a');
        link.href = url; link.download = `smetra-export-${new Date().toISOString().slice(0, 10)}.zip`;
        document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 60_000);
      }
      status.textContent = 'Архив создан. Сохраните его в надёжном месте: внутри могут быть клиентские данные.';
    } catch (error) {
      if (zip) await zip.abort(error);
      status.textContent = error.name === 'AbortError' ? 'Создание архива остановлено.' : error.message || 'Не удалось создать архив. Повторите попытку.';
    } finally {
      if (activeController === controller) activeController = null;
      if (button.isConnected) button.disabled = false;
      if (cancel?.isConnected) cancel.hidden = true;
    }
  }

  function render() {
    const root = document.querySelector('#settings-export');
    if (!root) return;
    if (!root.isConnected || !root.closest('.settings-page')) return;
    root.innerHTML = `<section class="panel data-export-panel"><div class="data-export-copy"><span class="data-export-kicker">ДАННЫЕ РАБОЧЕГО ПРОСТРАНСТВА</span><h2>Экспорт данных</h2><p class="muted">Один ZIP-архив со сметами, клиентами, проектами, стройкой, знаниями и файлами. Архив собирается в этом браузере; токены и пароли исключены.</p><p class="data-export-note">Включены вложения и история их версий. Доступно владельцу пространства.</p></div><div class="data-export-actions"><button class="btn primary" id="export-start" type="button">Скачать архив</button><button class="btn" id="export-cancel" type="button" hidden>Остановить</button></div><p id="export-status" class="data-export-status" role="status" aria-live="polite"></p></section>`;
    const button = document.querySelector('#export-start'), status = document.querySelector('#export-status');
    const cancelButton=document.querySelector('#export-cancel');
    if(button&&status)button.addEventListener('click', () => start(button, status));
    cancelButton?.addEventListener('click', () => activeController?.abort());
  }
  function cancel() { activeController?.abort(); }
  window.SmetraDataExport = { render, cancel };
})();
