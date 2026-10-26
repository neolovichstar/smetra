'use strict';
(() => {
  const status = document.getElementById('npd-status');
  const rows = document.getElementById('npd-rows');
  const form = document.getElementById('npd-form');
  const submit = document.getElementById('npd-submit');
  const refreshBtn = document.getElementById('npd-refresh');
  const labels = {
    awaiting_tax: 'Нужен чек из ФНС',
    queued: 'Ожидает отправки',
    sending: 'Отправляется',
    sent: 'Отправлен',
    needs_review: 'Требует проверки',
    refunded: 'Возврат: нужна корректировка ФНС'
  };
  const message = (value, error=false) => {
    status.textContent = value;
    status.dataset.error = error ? '1' : '0';
  };
  async function request(url, options) {
    const response = await fetch(url, {...options, credentials:'same-origin', cache:'no-store'});
    let payload = {};
    try { payload = await response.json(); } catch (_) {}
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) throw new Error('Нет доступа. Войдите в административный аккаунт Сметры.');
      throw new Error(payload.error || payload.message || 'Не удалось выполнить запрос');
    }
    return payload;
  }
  const cell = (row, value) => {
    const td = document.createElement('td');
    td.textContent = String(value ?? '—');
    row.appendChild(td);
  };
  async function refresh() {
    refreshBtn.disabled = true;
    try {
      const data = await request('/api/admin/npd/receipts');
      rows.replaceChildren();
      if (!data.items || data.items.length === 0) {
        const tr = document.createElement('tr');
        const td = document.createElement('td'); td.colSpan = 5;
        td.textContent = 'Подтверждённых покупок, ожидающих обработки, пока нет.';
        tr.appendChild(td); rows.appendChild(tr);
      }
      for (const item of data.items || []) {
        const tr = document.createElement('tr');
        const id = document.createElement('td');
        const btn = document.createElement('button');
        btn.type = 'button'; btn.className = 'npd-copy'; btn.textContent = item.payment_id;
        btn.title = 'Нажмите, чтобы заполнить ID платежа';
        btn.addEventListener('click', () => { document.getElementById('npd-payment').value = item.payment_id; document.getElementById('npd-url').focus(); });
        id.appendChild(btn); tr.appendChild(id);
        cell(tr, item.email); cell(tr, (Number(item.amount_kopecks)/100).toFixed(2)+' ₽');
        cell(tr, labels[item.status] || item.status);
        cell(tr, item.sent_at ? new Date(item.sent_at*1000).toLocaleString('ru-RU') : '—');
        rows.appendChild(tr);
      }
      message('Записи загружены. Отправка доступна только для настоящих чеков ФНС.');
    } catch (err) {
      rows.replaceChildren();
      message(err.message || 'Ошибка загрузки', true);
    } finally { refreshBtn.disabled = false; }
  }
  form.addEventListener('submit', async event => {
    event.preventDefault(); submit.disabled = true;
    try {
      const payload = {
        payment_id: document.getElementById('npd-payment').value.trim(),
        receipt_url: document.getElementById('npd-url').value.trim()
      };
      const data = await request('/api/admin/npd/receipts', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      const sent = data.email_delivery?.sent === 1;
      if (sent) document.getElementById('npd-url').value='';
      await refresh();
      message(sent ? 'Чек сохранён, письмо передано почтовому серверу.' :
        'Чек сохранён; проверьте доставку в истории. Если требуется повторная отправка, сначала выясните состояние предыдущей.');
    } catch(err) { message(err.message || 'Не удалось сохранить чек', true); }
    finally { submit.disabled = false; }
  });
  refreshBtn.addEventListener('click', refresh);
  refresh();
})();
