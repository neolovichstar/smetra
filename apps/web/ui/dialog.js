/* Shared confirmation and input dialogs. Replace the browser's native
   confirm()/prompt() so every decision looks like the rest of the cabinet,
   is keyboard accessible and works in the Android WebView. */
(() => {
  const icon = (name, size = 20) => window.SmetraIcons ? window.SmetraIcons.svg(name, size) : '';
  let open = null;

  const build = ({ title, message, confirmLabel, cancelLabel, danger, input }) => {
    const dialog = document.createElement('dialog');
    dialog.className = 'sm-dialog' + (danger ? ' is-danger' : '');
    dialog.setAttribute('aria-labelledby', 'sm-dialog-title');
    const form = document.createElement('form');
    form.method = 'dialog';
    form.className = 'sm-dialog-body';
    const mark = document.createElement('span');
    mark.className = 'sm-dialog-mark';
    mark.setAttribute('aria-hidden', 'true');
    mark.innerHTML = icon(danger ? 'trash' : input ? 'pencil' : 'check');
    const heading = document.createElement('h2');
    heading.id = 'sm-dialog-title';
    heading.textContent = title;
    form.append(mark, heading);
    if (message) {
      const text = document.createElement('p');
      text.className = 'sm-dialog-text';
      text.textContent = message;
      form.append(text);
    }
    let field = null;
    if (input) {
      const label = document.createElement('label');
      label.className = 'sm-dialog-field';
      const caption = document.createElement('span');
      caption.textContent = input.label || 'Значение';
      field = document.createElement('input');
      field.value = input.value || '';
      field.maxLength = input.maxLength || 200;
      field.placeholder = input.placeholder || '';
      field.required = input.required !== false;
      field.autocomplete = 'off';
      label.append(caption, field);
      form.append(label);
    }
    const actions = document.createElement('div');
    actions.className = 'sm-dialog-actions';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'btn';
    cancel.dataset.dialogCancel = '';
    cancel.textContent = cancelLabel || 'Отмена';
    const confirm = document.createElement('button');
    confirm.type = 'submit';
    confirm.className = 'btn ' + (danger ? 'danger' : 'primary');
    confirm.dataset.dialogConfirm = '';
    confirm.textContent = confirmLabel || 'Подтвердить';
    actions.append(cancel, confirm);
    form.append(actions);
    dialog.append(form);
    return { dialog, form, cancel, confirm, field };
  };

  const show = options => new Promise(resolve => {
    open?.finish(null);
    const parts = build(options);
    const { dialog, form, cancel, field } = parts;
    const returnFocus = document.activeElement;
    let done = false;
    const finish = value => {
      if (done) return;
      done = true;
      if (open?.dialog === dialog) open = null;
      // A closing dialog stays visible for its exit animation; make it inert
      // so neither people nor scripts can act on it twice.
      dialog.inert = true;
      dialog.querySelectorAll('[data-dialog-confirm],[data-dialog-cancel]').forEach(button => { button.removeAttribute('data-dialog-confirm'); button.removeAttribute('data-dialog-cancel'); button.disabled = true; });
      document.body.classList.remove('modal-open');
      const remove = () => { try { dialog.close(); } catch {} dialog.remove(); };
      if (matchMedia?.('(prefers-reduced-motion: reduce)')?.matches || !dialog.isConnected) remove();
      else { dialog.classList.add('is-closing'); setTimeout(remove, 170); }
      if (returnFocus?.isConnected && typeof returnFocus.focus === 'function') returnFocus.focus({ preventScroll: true });
      resolve(value);
    };
    open = { dialog, finish };
    form.addEventListener('submit', event => {
      event.preventDefault();
      if (field) {
        const value = field.value.trim();
        if (field.required && !value) { field.focus(); return; }
        finish(value);
      } else finish(true);
    });
    cancel.addEventListener('click', () => finish(field ? null : false));
    dialog.addEventListener('cancel', event => { event.preventDefault(); finish(field ? null : false); });
    dialog.addEventListener('click', event => { if (event.target === dialog) finish(field ? null : false); });
    document.body.append(dialog);
    document.body.classList.add('modal-open');
    if (typeof dialog.showModal === 'function') { try { dialog.showModal(); } catch { dialog.setAttribute('open', ''); } }
    else dialog.setAttribute('open', '');
    (field || (options.danger ? cancel : parts.confirm)).focus?.();
    if (field) field.select?.();
  });

  window.SmetraDialog = {
    confirm: (options = {}) => show(typeof options === 'string' ? { title: options } : options),
    prompt: (options = {}) => show({ confirmLabel: 'Сохранить', ...options, input: { label: options.label, value: options.value, placeholder: options.placeholder, maxLength: options.maxLength, required: options.required } }),
    close: () => open?.finish(null),
  };
})();
