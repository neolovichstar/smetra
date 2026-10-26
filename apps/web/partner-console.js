"use strict";
/* Smetra partner console. Talks only to /api/partners/v1/console/* with a
   one-hour session token. The long-lived API key is used once at sign-in and
   never stored. Every figure on screen comes from the server; where the server
   has no source yet, the page says so instead of drawing placeholder numbers. */
(() => {
  const API = "/api/partners/v1/console";
  const STORE = "smetra.partner.session";
  const REFERRAL_BASE = "https://smetra.online/api/partners/r/";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);

  /* ---------- formatting ---------- */
  const nf = new Intl.NumberFormat("ru-RU");
  const num = value => nf.format(Number(value) || 0);
  const rub = kopecks => {
    const value = (Number(kopecks) || 0) / 100;
    return new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", minimumFractionDigits: value % 1 ? 2 : 0, maximumFractionDigits: 2 }).format(value);
  };
  const pct = (part, whole) => (whole > 0 ? (Math.round(part / whole * 1000) / 10).toLocaleString("ru-RU") + "%" : "—");
  const bps = value => ((Number(value) || 0) / 100).toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + "%";
  const day = unix => (unix ? new Date(unix * 1000).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" }) : "—");
  const dayTime = unix => (unix ? new Date(unix * 1000).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
  const isoDay = value => new Date(value + "T00:00:00Z").toLocaleDateString("ru-RU", { day: "numeric", month: "short", timeZone: "UTC" });

  /* ---------- icons (24 grid, 1.6 stroke) ---------- */
  const ICONS = {
    overview: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
    analytics: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    links: '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1"/>',
    catalog: '<path d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5z"/><path d="m4 7.5 8 4.5 8-4.5M12 12v9"/>',
    finance: '<rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="M3 10h18M7 15h3"/>',
    payouts: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 19h16"/>',
    domain: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.6 3.5 5.4 3.5 8.5s-1 5.9-3.5 8.5c-2.5-2.6-3.5-5.4-3.5-8.5s1-5.9 3.5-8.5z"/>',
    api: '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14"/>',
    sdk: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 9h17M7 6.8h.01M9.5 6.8h.01"/>',
    activity: '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>',
    book: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/>',
    more: '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
    alert: '<path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4.5M12 17.2h.01"/>',
    check: '<circle cx="12" cy="12" r="8.5"/><path d="m8.5 12.2 2.4 2.4 4.6-4.8"/>',
    info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>',
    copy: '<rect x="8.5" y="8.5" width="12" height="12" rx="2"/><path d="M15.5 8.5V5.5a2 2 0 0 0-2-2h-8a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h3"/>',
    download: '<path d="M12 4v11M7 10.5l5 5 5-5M5 20h14"/>',
    refresh: '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v5h-5"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    lock: '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
    offline: '<path d="M2 8.5a15 15 0 0 1 4.5-2.8M22 8.5A15 15 0 0 0 10 5M5.5 12.5a10 10 0 0 1 3-2M18.5 12.5a10 10 0 0 0-4-2.4M9 16a4.5 4.5 0 0 1 6 0M12 19.5h.01M3 3l18 18"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    upload: '<path d="M12 20V9M7 13.5l5-5 5 5M5 4h14"/>',
    external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    receipt: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
    key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M17 6l2.5 2.5M14.5 8.5 17 11"/>',
  };
  const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
  const ico = name => `<span class="pc-ico">${icon(name)}</span>`;

  /* ---------- toasts ---------- */
  const toast = (text, kind = "") => {
    const host = $("#toasts");
    const el = document.createElement("div");
    el.className = "p-toast" + (kind ? " is-" + kind : "");
    el.setAttribute("role", kind === "error" ? "alert" : "status");
    el.textContent = text;
    host.append(el);
    setTimeout(() => el.remove(), kind === "error" ? 6000 : 3200);
  };
  const copyText = async (text, label = "Скопировано") => {
    try { await navigator.clipboard.writeText(text); toast(label, "ok"); return true; }
    catch { toast("Не удалось скопировать. Выделите текст и скопируйте вручную.", "error"); return false; }
  };

  /* ---------- session ---------- */
  let session = null; // { token, expiresAt }
  const loadSession = () => {
    try {
      const raw = JSON.parse(sessionStorage.getItem(STORE) || "null");
      if (raw && typeof raw.token === "string" && /^smp_session_[A-Za-z0-9_-]{35,100}$/.test(raw.token) && raw.expiresAt > Date.now() + 5000) return raw;
    } catch { /* storage unavailable */ }
    return null;
  };
  // Only the one-hour session token is kept, and only for this tab.
  const saveSession = value => { try { value ? sessionStorage.setItem(STORE, JSON.stringify(value)) : sessionStorage.removeItem(STORE); } catch { /* tab-only memory still works */ } };

  class ApiError extends Error {
    constructor(status, message, kind) { super(message); this.status = status; this.kind = kind; }
  }
  const explain = (status, serverText) => {
    if (status === 401) return new ApiError(401, "Сессия закончилась. Войдите снова.", "auth");
    if (status === 403) return new ApiError(403, serverText || "Нет доступа к этому действию.", "forbidden");
    if (status === 404) return new ApiError(404, "Раздел не найден на сервере.", "missing");
    if (status === 409) return new ApiError(409, serverText || "Действие сейчас невозможно.", "conflict");
    if (status === 413) return new ApiError(413, "Слишком большой запрос. Разделите данные на части.", "validation");
    if (status === 429) return new ApiError(429, "Слишком много запросов. Подождите несколько минут.", "rate");
    if (status === 400) return new ApiError(400, serverText || "Сервер не принял данные.", "validation");
    if (status === 503) return new ApiError(503, serverText || "Сервис проверки временно недоступен. Повторите позже.", "unavailable");
    return new ApiError(status, "Сервер ответил ошибкой. Повторите попытку позже.", "server");
  };
  const api = async (path, { method = "GET", body } = {}) => {
    if (!session) throw new ApiError(401, "Сессия закончилась. Войдите снова.", "auth");
    if (!navigator.onLine) throw new ApiError(0, "Нет подключения к интернету.", "offline");
    let response;
    try {
      response = await fetch(API + path, {
        method, credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer",
        headers: { Authorization: "PartnerSession " + session.token, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new ApiError(0, navigator.onLine ? "Сервер не отвечает. Проверьте соединение и повторите." : "Нет подключения к интернету.", "offline");
    }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = explain(response.status, typeof payload.error === "string" ? payload.error : "");
      if (error.kind === "auth") expire();
      throw error;
    }
    return payload;
  };

  /* ---------- shared data ---------- */
  const cache = {};
  const load = (key, fetcher, fresh = false) => {
    if (!fresh && cache[key]) return cache[key];
    cache[key] = fetcher().catch(error => { delete cache[key]; throw error; });
    return cache[key];
  };
  const profile = fresh => load("profile", () => api("/profile"), fresh);
  const summary = fresh => load("summary", () => api("/summary"), fresh);
  const domain = fresh => load("domain", () => api("/domain"), fresh);
  const analytics = (days, fresh) => load("analytics" + days, () => api("/analytics?days=" + days), fresh);
  const firstProducts = fresh => load("products-first", () => api("/products?limit=1"), fresh);
  const clearCache = () => Object.keys(cache).forEach(key => delete cache[key]);
  let period = 30;

  /* ---------- routes ---------- */
  const ROUTES = [
    { id: "overview", title: "Обзор", icon: "overview", group: "Работа" },
    { id: "analytics", title: "Аналитика", icon: "analytics", group: "Работа" },
    { id: "links", title: "Партнёрские ссылки", short: "Ссылки", icon: "links", group: "Работа" },
    { id: "catalog", title: "Каталог материалов", short: "Каталог", icon: "catalog", group: "Работа" },
    { id: "finance", title: "Финансы и комиссии", short: "Финансы", icon: "finance", group: "Деньги" },
    { id: "payouts", title: "Выплаты", icon: "payouts", group: "Деньги" },
    { id: "domain", title: "Подтверждение домена", short: "Домен", icon: "domain", group: "Интеграция" },
    { id: "api", title: "API и интеграции", short: "API", icon: "api", group: "Интеграция" },
    { id: "sdk", title: "SDK и материалы", short: "SDK", icon: "sdk", group: "Интеграция" },
    { id: "activity", title: "История операций", short: "История", icon: "activity", group: "Аккаунт" },
    { id: "settings", title: "Настройки", icon: "settings", group: "Аккаунт" },
  ];
  const TABBAR = ["overview", "analytics", "catalog", "finance"];
  const routeFromHash = () => {
    const id = (location.hash.match(/^#\/([a-z]+)/) || [])[1];
    return ROUTES.find(route => route.id === id) || ROUTES[0];
  };
  const navLink = (route, attention) => `<a class="pc-nav-link" href="#/${route.id}" data-route="${route.id}" title="${esc(route.title)}">${ico(route.icon)}<span class="pc-nav-text">${esc(route.title)}</span>${attention ? `<span class="pc-badge" aria-label="Требует внимания">!</span>` : ""}</a>`;
  let attention = new Set();
  const drawNav = () => {
    let group = "";
    $("#pc-nav").innerHTML = ROUTES.map(route => {
      const head = route.group !== group ? `<div class="pc-nav-group">${esc((group = route.group))}</div>` : "";
      return head + navLink(route, attention.has(route.id));
    }).join("");
    $("#pc-more-nav").innerHTML = ROUTES.filter(route => !TABBAR.includes(route.id)).map(route => navLink(route, attention.has(route.id))).join("") + `<a class="pc-nav-link" href="/docs" target="_blank" rel="noopener">${ico("book")}<span class="pc-nav-text">Документация</span></a>`;
    $("#pc-tabbar").innerHTML = TABBAR.map(id => ROUTES.find(route => route.id === id)).map(route => `<a href="#/${route.id}" data-route="${route.id}">${icon(route.icon)}<span>${esc(route.short || route.title)}</span></a>`).join("") + `<button type="button" id="pc-more-btn" aria-expanded="false" aria-controls="pc-more">${icon("more")}<span>Ещё</span></button>`;
    $("#pc-more-btn").addEventListener("click", () => openMore(true));
    markCurrent();
  };
  const markCurrent = () => {
    const current = routeFromHash().id;
    $$("[data-route]").forEach(link => (link.dataset.route === current ? link.setAttribute("aria-current", "page") : link.removeAttribute("aria-current")));
    const more = $("#pc-more-btn");
    if (more) more.classList.toggle("is-current", !TABBAR.includes(current));
  };
  const openMore = open => {
    $("#pc-more").hidden = !open;
    $("#pc-more-btn")?.setAttribute("aria-expanded", String(open));
    if (open) $("#pc-more .pc-nav-link")?.focus();
  };
  $("#pc-more").addEventListener("click", event => { if (event.target.closest("[data-close],a")) openMore(false); });

  /* ---------- page scaffolding ---------- */
  const view = () => $("#view");
  let renderToken = 0;
  const pageHead = (title, lead = "", actions = "") => `<header class="pc-head"><div><h1>${esc(title)}</h1>${lead ? `<p>${lead}</p>` : ""}</div>${actions ? `<div class="pc-head-actions">${actions}</div>` : ""}</header>`;
  const skeleton = () => `<div class="pc-head"><div><div class="pc-skel pc-skel-line pc-skel-title"></div></div></div><div class="pc-kpis">${'<div class="pc-kpi"><div class="pc-skel pc-skel-line"></div><div class="pc-skel pc-skel-line"></div></div>'.repeat(4)}</div><div class="pc-block"><div class="pc-skel pc-skel-kpi"></div></div>`;
  const stateBlock = (iconName, title, text, action = "") => `<div class="pc-state">${ico(iconName)}<h2>${esc(title)}</h2><p>${esc(text)}</p>${action}</div>`;
  const errorState = error => {
    if (error.kind === "offline") return stateBlock("offline", "Нет соединения", error.message, `<button class="p-btn" type="button" data-retry>${icon("refresh")}Повторить</button>`);
    if (error.kind === "forbidden") return stateBlock("lock", "Нет доступа", error.message);
    if (error.kind === "rate") return stateBlock("clock", "Слишком много запросов", error.message, `<button class="p-btn" type="button" data-retry>Повторить</button>`);
    if (error.kind === "auth") return stateBlock("lock", "Сессия закончилась", error.message);
    return stateBlock("alert", "Не удалось загрузить раздел", error.message, `<button class="p-btn" type="button" data-retry>${icon("refresh")}Повторить</button>`);
  };
  const seg = (name, value, options) => `<div class="pc-seg" role="group" aria-label="${esc(name)}">${options.map(([v, label]) => `<button type="button" data-value="${v}" aria-pressed="${String(v) === String(value)}">${esc(label)}</button>`).join("")}</div>`;
  const note = (kind, iconName, html) => `<div class="pc-note is-${kind}">${ico(iconName)}<div>${html}</div></div>`;
  const kpi = (label, value, hint = "", muted = false) => `<div class="pc-kpi${muted ? " is-muted" : ""}"><dt>${esc(label)}</dt><dd>${value}</dd>${hint ? `<small>${hint}</small>` : ""}</div>`;
  const codeBlock = (title, code, lang = "") => `<div class="p-code"><div class="p-code-head"><span>${esc(title)}</span><button class="p-copy" type="button" data-copy>${icon("copy")}Копировать</button></div><pre${lang ? ` data-lang="${lang}"` : ""}><code>${esc(code)}</code></pre></div>`;
  const bindCommon = root => {
    $$("[data-copy]", root).forEach(button => button.addEventListener("click", async () => {
      const text = button.dataset.copyText || button.closest(".p-code")?.querySelector("code")?.textContent || "";
      if (await copyText(text)) { button.classList.add("is-done"); setTimeout(() => button.classList.remove("is-done"), 1400); }
    }));
    $$("[data-retry]", root).forEach(button => button.addEventListener("click", () => render(true)));
  };

  const PAGES = {};
  const render = async (fresh = false) => {
    if (!session) return;
    const route = routeFromHash();
    markCurrent();
    document.title = route.title + " · Кабинет партнёра · Сметра";
    const token = ++renderToken;
    const host = view();
    host.innerHTML = skeleton();
    const live = () => token === renderToken;
    try {
      if (fresh) clearCache();
      await PAGES[route.id](host, live);
      if (live()) bindCommon(host);
    } catch (error) {
      if (!live()) return;
      host.innerHTML = errorState(error instanceof ApiError ? error : new ApiError(0, "Что-то пошло не так. Обновите страницу.", "server"));
      bindCommon(host);
    }
  };

  /* ---------- chart ---------- */
  const SERIES = {
    visits: { label: "Переходы", color: "#f3f3f4" },
    registrations: { label: "Регистрации", color: "#8fa7d8" },
    payments: { label: "Оплаты", color: "#62c294" },
    materials_clicks: { label: "Клики по материалам", color: "#d6a24a" },
  };
  const chart = (host, timeline, keys) => {
    let shown = new Set(keys.slice(0, 3));
    const draw = () => {
      const width = host.clientWidth || 600, height = width < 520 ? 200 : 240;
      const pad = { l: 36, r: 8, t: 8, b: 24 };
      const w = width - pad.l - pad.r, h = height - pad.t - pad.b;
      const active = keys.filter(key => shown.has(key));
      const max = Math.max(1, ...timeline.flatMap(row => active.map(key => row[key] || 0)));
      const niceMax = max <= 4 ? 4 : Math.ceil(max / 4) * 4;
      const x = i => pad.l + (timeline.length < 2 ? w / 2 : i / (timeline.length - 1) * w);
      const y = v => pad.t + h - v / niceMax * h;
      const ticks = [0, 1, 2, 3, 4].map(i => niceMax / 4 * i);
      const every = Math.ceil(timeline.length / (width < 520 ? 4 : 7));
      const empty = timeline.every(row => keys.every(key => !row[key]));
      const legend = `<div class="pc-legend">${keys.map(key => `<button type="button" data-series="${key}" aria-pressed="${shown.has(key)}"><i style-c="${key}"></i>${esc(SERIES[key].label)}</button>`).join("")}</div>`;
      if (empty) {
        host.innerHTML = `<div class="pc-empty-chart"><div><strong>За период событий нет</strong><p class="p-hint">График появится после первых переходов по вашей ссылке.</p></div></div>`;
        return;
      }
      host.innerHTML = `${legend}<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="График по дням: ${esc(active.map(k => SERIES[k].label).join(", "))}">
        <g class="grid">${ticks.map(t => `<line x1="${pad.l}" x2="${width - pad.r}" y1="${y(t)}" y2="${y(t)}"/>`).join("")}</g>
        <g class="axis">${ticks.map(t => `<text x="${pad.l - 8}" y="${y(t) + 4}" text-anchor="end">${num(Math.round(t))}</text>`).join("")}
        ${timeline.map((row, i) => (i % every === 0 || i === timeline.length - 1) ? `<text x="${x(i)}" y="${height - 4}" text-anchor="${i === 0 ? "start" : i === timeline.length - 1 ? "end" : "middle"}">${esc(isoDay(row.date))}</text>` : "").join("")}</g>
        ${active.map(key => {
          const points = timeline.map((row, i) => `${x(i).toFixed(1)},${y(row[key] || 0).toFixed(1)}`);
          return `<path class="area" fill="${SERIES[key].color}" d="M${x(0)},${y(0)} L${points.join(" L")} L${x(timeline.length - 1)},${y(0)} Z"/><path class="series" stroke="${SERIES[key].color}" d="M${points.join(" L")}"/>`;
        }).join("")}
        <line class="cursor" x1="0" x2="0" y1="${pad.t}" y2="${pad.t + h}" visibility="hidden"/>
      </svg><div class="pc-tip" hidden></div>
      <table class="visually-hidden"><caption>Данные графика</caption><thead><tr><th>Дата</th>${active.map(k => `<th>${esc(SERIES[k].label)}</th>`).join("")}</tr></thead><tbody>${timeline.map(row => `<tr><td>${esc(row.date)}</td>${active.map(k => `<td>${row[k] || 0}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
      $$("[style-c]", host).forEach(el => { el.style.background = SERIES[el.getAttribute("style-c")].color; });
      $$("[data-series]", host).forEach(button => button.addEventListener("click", () => {
        const key = button.dataset.series;
        if (shown.has(key) && shown.size === 1) return;
        shown.has(key) ? shown.delete(key) : shown.add(key);
        draw();
      }));
      const svg = $("svg", host), cursor = $(".cursor", host), tip = $(".pc-tip", host);
      const move = event => {
        const rect = svg.getBoundingClientRect();
        const px = (event.clientX - rect.left) / rect.width * width;
        const i = Math.max(0, Math.min(timeline.length - 1, Math.round((px - pad.l) / (w || 1) * (timeline.length - 1))));
        const row = timeline[i];
        cursor.setAttribute("x1", x(i)); cursor.setAttribute("x2", x(i)); cursor.setAttribute("visibility", "visible");
        tip.hidden = false;
        tip.innerHTML = `<b>${esc(new Date(row.date + "T00:00:00Z").toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }))}</b>${active.map(key => `<div><span><i style-c="${key}"></i>${esc(SERIES[key].label)}</span><span>${num(row[key])}</span></div>`).join("")}`;
        $$("[style-c]", tip).forEach(el => { el.style.background = SERIES[el.getAttribute("style-c")].color; });
        const left = x(i) / width * rect.width;
        tip.style.left = Math.min(rect.width - tip.offsetWidth, Math.max(0, left + 12)) + "px";
      };
      svg.addEventListener("pointermove", move);
      svg.addEventListener("pointerleave", () => { tip.hidden = true; cursor.setAttribute("visibility", "hidden"); });
    };
    draw();
    const resize = new ResizeObserver(() => draw());
    resize.observe(host);
  };

  /* ---------- 1. Overview ---------- */
  PAGES.overview = async (host, live) => {
    const [me, totals, report, proof, products] = await Promise.all([profile(), summary(), analytics(period), domain(), firstProducts()]);
    if (!live()) return;
    const paid = report.verified_subscription_payments;
    const held = Math.max(0, totals.earned_kopecks - totals.cleared_kopecks);
    const items = [];
    if (proof.status !== "verified") items.push(["domain", "Домен не подтверждён", proof.status === "expired" ? "Подтверждение устарело. Пройдите проверку снова." : "Пока домен не подтверждён, ваши товары не показываются пользователям."]);
    if (!products.items.length) items.push(["catalog", "Каталог пуст", "Загрузите товары, чтобы «Сметра» могла предлагать их в сметах."]);
    if (!report.visits) items.push(["links", "Переходов пока нет", "Разместите партнёрскую ссылку или виджет на сайте магазина."]);
    attention = new Set(items.map(([id]) => id));
    drawNav();
    host.innerHTML = pageHead("Обзор", `Данные за ${period} дн. Время — UTC. Переходы, регистрации и оплаты фиксирует сервер «Сметры».`, seg("Период", period, [[7, "7 дн."], [30, "30 дн."], [90, "90 дн."]])) + `
      <section class="pc-block" aria-labelledby="kpi-funnel"><h2 class="visually-hidden" id="kpi-funnel">Привлечение</h2>
        <dl class="pc-kpis">
          ${kpi("Переходы в «Сметру»", num(report.visits))}
          ${kpi("Регистрации", num(report.registrations), "конверсия " + pct(report.registrations, report.visits))}
          ${kpi("Подтверждённые платежи", num(paid.payments))}
          ${kpi("Платящие аккаунты", num(paid.paying_accounts), "из регистраций " + pct(paid.paying_accounts, report.registrations))}
        </dl>
      </section>
      <section class="pc-block" aria-labelledby="kpi-money">
        <div class="pc-block-head"><h2 id="kpi-money">Комиссии</h2><p>За всё время · учёт без автоматических выплат</p></div>
        <dl class="pc-kpis">
          ${kpi("Начислено", rub(totals.earned_kopecks), num(totals.conversions) + " начисл.")}
          ${kpi("На удержании", rub(held), "30 дней на возврат")}
          ${kpi("Прошло удержание", rub(totals.cleared_kopecks), "ещё не выплачено")}
          ${kpi("Аннулировано", rub(totals.reversed_kopecks), "после возвратов", !totals.reversed_kopecks)}
        </dl>
      </section>
      <section class="pc-block" aria-labelledby="chart-title">
        <div class="pc-block-head"><h2 id="chart-title">Динамика по дням</h2><a class="pc-link" href="#/analytics">Подробная аналитика</a></div>
        <div class="pc-panel pc-chart" id="overview-chart"></div>
      </section>
      <section class="pc-block" aria-labelledby="attn-title">
        <div class="pc-block-head"><h2 id="attn-title">${items.length ? "Требует внимания" : "Настройка завершена"}</h2></div>
        <div class="pc-panel pc-attn">${items.length ? items.map(([route, title, text]) => `<div class="pc-attn-item">${ico("alert")}<div><strong>${esc(title)}</strong><span>${esc(text)}</span></div><a class="p-btn is-small" href="#/${route}">Открыть</a></div>`).join("")
          : `<div class="pc-attn-item is-done">${ico("check")}<div><strong>Домен подтверждён, каталог загружен, переходы идут</strong><span>Следите за динамикой и начислениями.</span></div></div>`}</div>
      </section>`;
    $$(".pc-seg button", host).forEach(button => button.addEventListener("click", () => { period = Number(button.dataset.value); render(); }));
    chart($("#overview-chart", host), report.timeline, ["visits", "registrations", "payments"]);
  };

  /* ---------- 2. Analytics ---------- */
  const csvCell = value => {
    const text = String(value ?? "");
    return /[;"\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const downloadCsv = (name, rows) => {
    // Semicolons and decimal commas: opens correctly in Excel with a Russian locale.
    const body = "﻿" + rows.map(row => row.map(csvCell).join(";")).join("\r\n");
    const url = URL.createObjectURL(new Blob([body], { type: "text/csv;charset=utf-8" }));
    const link = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const rubCsv = kopecks => ((Number(kopecks) || 0) / 100).toFixed(2).replace(".", ",");
  PAGES.analytics = async (host, live) => {
    const report = await analytics(period);
    if (!live()) return;
    const paid = report.verified_subscription_payments;
    const merchant = report.merchant_reported || {};
    const reported = kind => merchant[kind] || { count: 0, amount_kopecks: 0 };
    const repeat = Math.max(0, paid.payments - paid.paying_accounts);
    const steps = [["Переходы", report.visits], ["Регистрации", report.registrations], ["Платящие аккаунты", paid.paying_accounts]];
    host.innerHTML = pageHead("Аналитика", `Период ${period} дн., UTC. Показатели за период, не когортный анализ.`,
      seg("Период", period, [[7, "7 дн."], [30, "30 дн."], [90, "90 дн."]]) + `<button class="p-btn is-small" type="button" id="csv">${icon("download")}CSV</button>`) + `
      <section class="pc-block" aria-labelledby="funnel-title">
        <div class="pc-block-head"><h2 id="funnel-title">Воронка привлечения</h2><p>Повторные оплаты за период: ${num(repeat)}</p></div>
        <div class="pc-panel pc-funnel">${steps.map(([label, value], i) => `<div class="pc-funnel-step"><span>${esc(label)}</span><strong>${num(value)}</strong><div class="pc-funnel-bar"><i data-w="${steps[0][1] ? Math.max(2, value / steps[0][1] * 100) : 0}"></i></div><span class="pc-funnel-rate">${i ? "от предыдущего шага " + pct(value, steps[i - 1][1]) : "100% потока"}</span></div>`).join("")}</div>
      </section>
      <section class="pc-block" aria-labelledby="series-title">
        <div class="pc-block-head"><h2 id="series-title">Временные ряды</h2><p>Нажмите на легенду, чтобы скрыть ряд</p></div>
        <div class="pc-panel pc-chart" id="analytics-chart"></div>
      </section>
      <section class="pc-block" aria-labelledby="money-title">
        <div class="pc-block-head"><h2 id="money-title">Коммерческие показатели</h2><p>Только подтверждённые платёжной системой подписки</p></div>
        <dl class="pc-kpis">
          ${kpi("Оборот подписок", rub(paid.gross_kopecks))}
          ${kpi("Начисленные комиссии", rub(paid.commission_kopecks))}
          ${kpi("Аннулировано после возвратов", rub(paid.reversed_kopecks), "", !paid.reversed_kopecks)}
          ${kpi("Платежей", num(paid.payments))}
        </dl>
      </section>
      <section class="pc-block" aria-labelledby="buy-title">
        <div class="pc-block-head"><h2 id="buy-title">Закупочная аналитика</h2></div>
        <div class="pc-cols">
          <div class="pc-panel pc-panel-pad"><p class="p-label">Фиксирует сервер «Сметры»</p><dl class="pc-kv">
            <dt>Клики по материалам</dt><dd class="num">${num(report.outbound_material_clicks)}</dd></dl></div>
          <div class="pc-panel pc-panel-pad"><p class="p-label">Сообщил магазин <span class="pc-tag-unverified">не проверено</span></p><dl class="pc-kv">
            <dt>Показы виджета</dt><dd class="num">${num(reported("widget_impression").count)}</dd>
            <dt>Клики по виджету</dt><dd class="num">${num(reported("widget_click").count)}</dd>
            <dt>Заказы материалов</dt><dd class="num">${num(reported("material_order_reported").count)} · ${rub(reported("material_order_reported").amount_kopecks)}</dd></dl>
            <p class="p-hint" data-mt>Эти данные отправляет сервер магазина. Они не подтверждают оплату и не влияют на комиссии.</p></div>
        </div>
      </section>`;
    requestAnimationFrame(() => $$(".pc-funnel-bar i", host).forEach(bar => { bar.style.width = bar.dataset.w + "%"; }));
    $$(".pc-seg button", host).forEach(button => button.addEventListener("click", () => { period = Number(button.dataset.value); render(); }));
    chart($("#analytics-chart", host), report.timeline, ["visits", "registrations", "payments", "materials_clicks"]);
    $("#csv", host).addEventListener("click", () => {
      const rows = [["Дата (UTC)", "Переходы", "Регистрации", "Оплаты", "Клики по материалам", "Показы виджета (магазин)", "Заказы (магазин)"]];
      report.timeline.forEach(row => rows.push([row.date, row.visits, row.registrations, row.payments, row.materials_clicks, row.reported_impressions, row.reported_orders]));
      rows.push([], ["Итого за период", report.visits, report.registrations, paid.payments, report.outbound_material_clicks, reported("widget_impression").count, reported("material_order_reported").count],
        ["Оборот подписок, ₽", rubCsv(paid.gross_kopecks)], ["Комиссии, ₽", rubCsv(paid.commission_kopecks)], ["Аннулировано, ₽", rubCsv(paid.reversed_kopecks)]);
      downloadCsv(`smetra-partner-${report.partner}-${period}d.csv`, rows);
    });
  };

  /* ---------- 3. Links ---------- */
  let qrLoader = null;
  const loadQr = () => qrLoader || (qrLoader = new Promise((resolve, reject) => {
    if (window.qrcode) return resolve(window.qrcode);
    const script = Object.assign(document.createElement("script"), { src: "/vendor/qrcode-generator-1.4.4.js", async: true });
    script.onload = () => (window.qrcode ? resolve(window.qrcode) : reject(new Error("qr")));
    script.onerror = () => { qrLoader = null; reject(new Error("qr")); };
    document.head.append(script);
  }));
  const qrSvg = (qrcode, text) => {
    const qr = qrcode(0, "M");
    qr.addData(text);
    qr.make();
    const count = qr.getModuleCount();
    let path = "";
    for (let r = 0; r < count; r++) for (let c = 0; c < count; c++) if (qr.isDark(r, c)) path += `M${c + 2},${r + 2}h1v1h-1z`;
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${count + 4} ${count + 4}" shape-rendering="crispEdges"><rect width="100%" height="100%" fill="#fff"/><path d="${path}" fill="#09090a"/></svg>`;
  };
  PAGES.links = async (host, live) => {
    const [me, totals] = await Promise.all([profile(), summary()]);
    if (!live()) return;
    const link = REFERRAL_BASE + encodeURIComponent(me.code);
    host.innerHTML = pageHead("Партнёрские ссылки", "Новые аккаунты после перехода закрепляются за вами по первому касанию на 7 дней с момента визита.") + `
      <section class="pc-block" aria-labelledby="main-link">
        <div class="pc-block-head"><h2 id="main-link">Основная ссылка</h2><p>Переходов за 30 дней: <b class="num">${num(totals.clicks_30d)}</b></p></div>
        <div class="pc-panel pc-panel-pad">
          <div class="pc-copy-row"><input class="p-input" id="ref-link" readonly value="${esc(link)}" aria-label="Партнёрская ссылка"><button class="p-btn is-primary" type="button" data-copy data-copy-text="${esc(link)}">${icon("copy")}Скопировать</button></div>
          <div class="pc-qr" data-mt>
            <div class="pc-qr-box" id="qr" role="img" aria-label="QR-код партнёрской ссылки"></div>
            <div class="pc-text"><p>QR-код для витрины, ценников и печатных материалов в магазине. Ведёт на ту же ссылку.</p><p data-mt><button class="p-btn is-small" type="button" id="qr-download" disabled>${icon("download")}Скачать SVG</button></p></div>
          </div>
        </div>
      </section>
      <section class="pc-block" aria-labelledby="where">
        <div class="pc-block-head"><h2 id="where">Где разместить</h2></div>
        <div class="pc-cols pc-cols-3">
          <div class="pc-panel pc-panel-pad"><h3 class="p-label">Карточка товара</h3><p class="pc-text">Кнопка «Посчитать смету» рядом с материалами для ремонта.</p></div>
          <div class="pc-panel pc-panel-pad"><h3 class="p-label">Кабинет профессионала</h3><p class="pc-text">Блок для прорабов и бригад: «Считайте объекты в Сметре».</p></div>
          <div class="pc-panel pc-panel-pad"><h3 class="p-label">Рассылки и чеки</h3><p class="pc-text">Ссылка в письме после заказа материалов или QR-код в чеке.</p></div>
        </div>
      </section>
      <section class="pc-block" aria-labelledby="sdk-link">
        <div class="pc-block-head"><h2 id="sdk-link">Ссылка через SDK</h2><a class="pc-link" href="#/sdk">Все варианты виджета</a></div>
        ${codeBlock("HTML", `<script src="https://console.smetra.online/partner-sdk.js" defer></script>\n<a data-smetra-link href="${link}">Посчитать смету</a>\n<script>\n  addEventListener("DOMContentLoaded", () =>\n    SmetraPartner.attach({ code: "${me.code}", selector: "[data-smetra-link]" }));\n</script>`)}
      </section>
      <section class="pc-block" aria-labelledby="campaigns">
        <div class="pc-block-head"><h2 id="campaigns">Кампании и UTM-метки</h2><span class="p-pill is-plain">Планируется</span></div>
        ${note("info", "info", "Отдельные ссылки для каналов, площадок и рекламных размещений с отчётами по каждой появятся, когда сервер начнёт их учитывать. Сейчас все переходы считаются по одной ссылке; дополнительные параметры в ссылку не добавляйте — сервер их не сохраняет.")}
      </section>`;
    loadQr().then(qrcode => {
      if (!live()) return;
      const svg = qrSvg(qrcode, link);
      $("#qr", host).innerHTML = svg;
      const button = $("#qr-download", host);
      button.disabled = false;
      button.addEventListener("click", () => {
        const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
        const a = Object.assign(document.createElement("a"), { href: url, download: `smetra-${me.code}-qr.svg` });
        document.body.append(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      });
    }).catch(() => { $("#qr", host).innerHTML = `<p class="p-hint">QR-код не загрузился</p>`; });
  };

  /* ---------- 4. Catalog ---------- */
  const SKU_RE = /^[A-Za-z0-9_.:-]{1,80}$/;
  const MAX_BATCH = 100, MAX_BYTES = 60000;
  const validateProduct = (item, host, index) => {
    const where = `Товар ${index + 1}${item && typeof item.sku === "string" ? ` (${item.sku})` : ""}: `;
    if (!item || typeof item !== "object" || Array.isArray(item)) return [where + "ожидается объект"];
    const errors = [];
    if (typeof item.sku !== "string" || !SKU_RE.test(item.sku)) errors.push(where + "SKU — 1–80 символов: латиница, цифры, _ . : -");
    if (typeof item.name !== "string" || !item.name.trim() || item.name.trim().length > 200) errors.push(where + "название от 1 до 200 символов");
    if (!Number.isInteger(item.price_kopecks) || item.price_kopecks < 0 || item.price_kopecks > 100000000000) errors.push(where + "price_kopecks — целое число копеек");
    if ("available" in item && typeof item.available !== "boolean") errors.push(where + "available — true или false");
    let url = null;
    try { url = new URL(item.url); } catch { /* reported below */ }
    if (!url || typeof item.url !== "string" || url.protocol !== "https:" || url.username || url.password || (url.port && url.port !== "443") || /[\u0000-\u001f\\]/.test(item.url)) errors.push(where + "url — полная HTTPS-ссылка без логина и порта");
    else if (url.hostname.toLowerCase().replace(/\.$/, "") !== host) errors.push(where + `ссылка должна вести на ${host}`);
    return errors;
  };
  const productPayload = item => ({ sku: item.sku, name: item.name, price_kopecks: item.price_kopecks, url: item.url, available: item.available !== false && item.available !== 0 });
  const sendProducts = async (items, onProgress) => {
    // Split into server-sized batches: at most 100 items and under the 64 KB body limit.
    const batches = [];
    let current = [];
    for (const item of items) {
      const next = [...current, item];
      if (current.length && (next.length > MAX_BATCH || new TextEncoder().encode(JSON.stringify({ products: next })).length > MAX_BYTES)) { batches.push(current); current = [item]; }
      else current = next;
    }
    if (current.length) batches.push(current);
    let accepted = 0;
    for (let i = 0; i < batches.length; i++) {
      onProgress?.(i + 1, batches.length);
      const result = await api("/catalog", { method: "POST", body: { products: batches[i] } });
      accepted += result.accepted;
    }
    return accepted;
  };
  const publication = (item, verified) => (!item.available ? ["is-plain", "Скрыт: нет в наличии"] : verified ? ["is-ok", "Показывается"] : ["is-warn", "Ждёт подтверждения домена"]);
  PAGES.catalog = async (host, live) => {
    const [me, proof] = await Promise.all([profile(), domain()]);
    if (!live()) return;
    const verified = proof.status === "verified";
    const state = { cursors: [""], page: 0, items: [], next: null, selected: new Set(), query: "", filter: "all", tab: "table", limit: innerWidth < 640 ? 25 : 50 };
    host.innerHTML = pageHead("Каталог материалов", `Товары с ценой и ссылкой на ${esc(me.domain)}. Пользователи видят их только после подтверждения домена.`,
      `<button class="p-btn is-primary is-small" type="button" id="open-import">${icon("upload")}Импорт JSON</button>`) +
      (verified ? "" : note("warn", "alert", `<strong>Домен не подтверждён.</strong> Товары можно загружать заранее, показываться они начнут после <a class="pc-link" href="#/domain">подтверждения домена</a>.`)) + `
      <div class="pc-tabs" role="tablist" aria-label="Способ загрузки" data-mt>
        <button type="button" role="tab" aria-selected="true" data-tab="table">Товары</button>
        <button type="button" role="tab" aria-selected="false" data-tab="import">Импорт JSON</button>
        <button type="button" role="tab" aria-selected="false" disabled title="Появится после поддержки на сервере">XML / YML<span class="p-pill is-plain">скоро</span></button>
        <button type="button" role="tab" aria-selected="false" disabled title="Появится после поддержки на сервере">CSV<span class="p-pill is-plain">скоро</span></button>
        <button type="button" role="tab" aria-selected="false" disabled title="Появится после поддержки на сервере">Автосинхронизация<span class="p-pill is-plain">скоро</span></button>
      </div>
      <div id="catalog-body"></div>`;
    const body = $("#catalog-body", host);

    const drawImport = () => {
      body.innerHTML = `<div class="pc-cols">
        <form class="pc-panel pc-panel-pad" id="import-form" novalidate>
          <label class="p-field" for="import-json"><span>JSON с массивом <code>products</code></span>
          <textarea class="p-textarea" id="import-json" spellcheck="false" rows="12" placeholder='{"products":[{"sku":"TILE-30x60","name":"Плитка 30×60","price_kopecks":189000,"url":"https://${esc(me.domain)}/p/tile","available":true}]}'></textarea></label>
          <div class="pc-toolbar" data-mt><label class="p-btn is-small" for="import-file">${icon("upload")}Выбрать файл .json</label><input id="import-file" type="file" accept="application/json,.json" class="visually-hidden">
          <span class="p-hint" id="import-file-name"></span></div>
          <div id="import-errors"></div>
          <div class="pc-toolbar"><button class="p-btn is-primary" type="submit" id="import-send">Проверить и загрузить</button><span class="p-hint" id="import-progress" aria-live="polite"></span></div>
        </form>
        <div class="pc-panel pc-panel-pad"><h3 class="p-label">Правила</h3><ul class="pc-text">
          <li>SKU уникален в пакете; повторная загрузка того же SKU обновляет товар.</li>
          <li>Цена — целое число копеек: 1 890 ₽ → <code>189000</code>.</li>
          <li>Ссылка — только HTTPS на <b>${esc(me.domain)}</b>.</li>
          <li>Больше 100 товаров консоль разделит на несколько запросов.</li>
          <li>Удаление товаров через API пока не поддерживается: снимите товар с продажи (<code>available: false</code>).</li></ul></div>
      </div>`;
      const area = $("#import-json", body), errorsHost = $("#import-errors", body);
      $("#import-file", body).addEventListener("change", async event => {
        const file = event.target.files?.[0];
        if (!file) return;
        if (file.size > 5_000_000) { toast("Файл больше 5 МБ. Разделите каталог.", "error"); return; }
        area.value = await file.text();
        $("#import-file-name", body).textContent = file.name;
      });
      $("#import-form", body).addEventListener("submit", async event => {
        event.preventDefault();
        errorsHost.innerHTML = "";
        area.removeAttribute("aria-invalid");
        let data;
        try { data = JSON.parse(area.value); } catch { data = null; }
        const list = Array.isArray(data) ? data : data?.products;
        const errors = [];
        if (!Array.isArray(list) || !list.length) errors.push("Нужен JSON-объект с непустым массивом products (или сам массив).");
        else {
          const seen = new Set();
          list.forEach((item, index) => {
            errors.push(...validateProduct(item, me.domain, index));
            if (item && typeof item.sku === "string") { if (seen.has(item.sku)) errors.push(`Товар ${index + 1}: SKU ${item.sku} повторяется`); seen.add(item.sku); }
          });
        }
        if (errors.length) {
          area.setAttribute("aria-invalid", "true");
          errorsHost.innerHTML = `<ul class="pc-errors" role="alert">${errors.slice(0, 50).map(e => `<li>${esc(e)}</li>`).join("")}${errors.length > 50 ? `<li>…и ещё ${errors.length - 50}</li>` : ""}</ul>`;
          return;
        }
        const button = $("#import-send", body), progress = $("#import-progress", body);
        button.disabled = true;
        try {
          const accepted = await sendProducts(list.map(productPayload), (i, n) => { progress.textContent = n > 1 ? `Отправка ${i} из ${n}…` : "Отправка…"; });
          progress.textContent = "";
          toast(`Каталог обновлён: ${num(accepted)} товаров`, "ok");
          area.value = "";
          delete cache["products-first"];
          state.cursors = [""]; state.page = 0;
          switchTab("table");
        } catch (error) {
          progress.textContent = "";
          errorsHost.innerHTML = `<ul class="pc-errors" role="alert"><li>${esc(error.message)}</li></ul>`;
        } finally { button.disabled = false; }
      });
    };

    const rows = () => {
      const query = state.query.trim().toLowerCase();
      return state.items.filter(item => (state.filter === "all" || (state.filter === "on" ? item.available : !item.available)) &&
        (!query || item.name.toLowerCase().includes(query) || item.sku.toLowerCase().includes(query)));
    };
    const drawTable = () => {
      const list = rows();
      const selected = list.filter(item => state.selected.has(item.sku));
      body.innerHTML = `<div class="pc-toolbar">
          <div class="pc-search">${icon("search")}<input class="p-input" type="search" id="cat-q" placeholder="Название или SKU на странице" value="${esc(state.query)}" aria-label="Поиск по загруженной странице"></div>
          <select class="p-select" id="cat-filter" aria-label="Доступность"><option value="all">Все товары</option><option value="on">В наличии</option><option value="off">Нет в наличии</option></select>
          <select class="p-select" id="cat-limit" aria-label="Товаров на странице"><option value="25">25 на странице</option><option value="50">50 на странице</option><option value="100">100 на странице</option></select>
        </div>
        ${selected.length ? `<div class="pc-bulk" role="region" aria-label="Действия с выбранными"><strong>Выбрано: ${selected.length}</strong>
          <button class="p-btn is-small" type="button" data-bulk="off">Снять с продажи</button><button class="p-btn is-small" type="button" data-bulk="on">Вернуть в продажу</button><button class="p-btn is-small is-quiet" type="button" data-bulk="clear">Сбросить</button></div>` : ""}
        ${state.items.length ? `<div class="pc-table-wrap"><table class="pc-table"><thead><tr>
          <th class="check"><input class="pc-check" type="checkbox" id="cat-all" aria-label="Выбрать все на странице" ${list.length && selected.length === list.length ? "checked" : ""}></th>
          <th>Название</th><th>SKU</th><th class="r">Цена</th><th>Доступность</th><th>Обновлён</th><th>Ссылка</th><th>Публикация</th><th></th></tr></thead><tbody>
          ${list.map(item => {
            const [kind, text] = publication(item, verified);
            let path = item.url; try { path = new URL(item.url).pathname; } catch { /* keep */ }
            return `<tr class="${state.selected.has(item.sku) ? "is-selected" : ""}">
              <td class="check"><input class="pc-check" type="checkbox" data-sku="${esc(item.sku)}" aria-label="Выбрать ${esc(item.name)}" ${state.selected.has(item.sku) ? "checked" : ""}></td>
              <td class="primary clip" title="${esc(item.name)}">${esc(item.name)}</td>
              <td class="mono" data-label="SKU">${esc(item.sku)}</td>
              <td class="r" data-label="Цена">${rub(item.price_kopecks)}</td>
              <td data-label="Доступность">${item.available ? "В наличии" : '<span class="muted">Нет в наличии</span>'}</td>
              <td class="muted" data-label="Обновлён">${day(item.updated_at)}</td>
              <td class="clip" data-label="Ссылка"><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(path)}</a></td>
              <td data-label="Публикация"><span class="p-pill ${kind}">${esc(text)}</span></td>
              <td class="r"><button class="p-btn is-small is-quiet" type="button" data-edit="${esc(item.sku)}">Изменить</button></td></tr>`;
          }).join("") || `<tr><td colspan="9" class="muted">На этой странице ничего не найдено.</td></tr>`}
          </tbody></table></div>
          <div class="pc-pager"><span>Страница ${state.page + 1} · показано ${list.length} из ${state.items.length}. Поиск — по загруженной странице.</span><div>
            <button class="p-btn is-small" type="button" id="cat-prev" ${state.page ? "" : "disabled"}>Назад</button><button class="p-btn is-small" type="button" id="cat-next" ${state.next ? "" : "disabled"}>Дальше</button></div></div>`
        : `<div class="pc-panel">${`<div class="pc-state is-inline">${ico("catalog")}<h2>Каталог пуст</h2><p>Загрузите первые товары через импорт JSON или Partner API.</p><button class="p-btn is-primary" type="button" data-goto-import>Импорт JSON</button></div>`}</div>`}`;
      $("#cat-filter", body).value = state.filter;
      $("#cat-limit", body).value = String(state.limit);
      $("#cat-q", body)?.addEventListener("input", event => { state.query = event.target.value; const pos = event.target.selectionStart; drawTable(); const input = $("#cat-q", body); input.focus(); input.setSelectionRange(pos, pos); });
      $("#cat-filter", body).addEventListener("change", event => { state.filter = event.target.value; drawTable(); });
      $("#cat-limit", body).addEventListener("change", event => { state.limit = Number(event.target.value); state.cursors = [""]; state.page = 0; fetchPage(); });
      $("#cat-all", body)?.addEventListener("change", event => { list.forEach(item => (event.target.checked ? state.selected.add(item.sku) : state.selected.delete(item.sku))); drawTable(); });
      $$("[data-sku]", body).forEach(box => box.addEventListener("change", () => { box.checked ? state.selected.add(box.dataset.sku) : state.selected.delete(box.dataset.sku); drawTable(); }));
      $$("[data-bulk]", body).forEach(button => button.addEventListener("click", () => bulk(button.dataset.bulk)));
      $$("[data-edit]", body).forEach(button => button.addEventListener("click", () => edit(state.items.find(item => item.sku === button.dataset.edit))));
      $("#cat-prev", body)?.addEventListener("click", () => { state.page--; fetchPage(); });
      $("#cat-next", body)?.addEventListener("click", () => { state.cursors[state.page + 1] = state.next; state.page++; fetchPage(); });
      $("[data-goto-import]", body)?.addEventListener("click", () => switchTab("import"));
    };
    const fetchPage = async () => {
      body.innerHTML = `<div class="pc-panel pc-panel-pad">${'<div class="pc-skel pc-skel-line"></div>'.repeat(6)}</div>`;
      try {
        const page = await api(`/products?limit=${state.limit}&cursor=${encodeURIComponent(state.cursors[state.page] || "")}`);
        if (!live()) return;
        state.items = page.items; state.next = page.next_cursor; state.selected.clear();
        drawTable();
      } catch (error) {
        if (!live()) return;
        body.innerHTML = `<div class="pc-panel">${errorState(error).replace("pc-state", "pc-state is-inline")}</div>`;
        $("[data-retry]", body)?.addEventListener("click", fetchPage);
      }
    };
    const bulk = async action => {
      if (action === "clear") { state.selected.clear(); drawTable(); return; }
      const chosen = state.items.filter(item => state.selected.has(item.sku));
      const changed = chosen.map(item => ({ ...productPayload(item), available: action === "on" }));
      try {
        const accepted = await sendProducts(changed);
        toast(`${action === "on" ? "Возвращено в продажу" : "Снято с продажи"}: ${num(accepted)}`, "ok");
        fetchPage();
      } catch (error) { toast(error.message, "error"); }
    };
    const edit = item => {
      if (!item) return;
      const dialog = document.createElement("dialog");
      dialog.className = "pc-dialog";
      dialog.setAttribute("aria-labelledby", "edit-title");
      dialog.innerHTML = `<form method="dialog" novalidate><h2 id="edit-title">Товар ${esc(item.sku)}</h2>
        <label class="p-field"><span>Название</span><input class="p-input" name="name" maxlength="200" required value="${esc(item.name)}"></label>
        <label class="p-field"><span>Цена, ₽</span><input class="p-input" name="price" inputmode="decimal" required value="${esc(((item.price_kopecks || 0) / 100).toFixed(2).replace(".", ","))}"></label>
        <label class="p-field"><span>Ссылка на товар</span><input class="p-input" name="url" type="url" required value="${esc(item.url)}"></label>
        <label class="pc-switch"><input class="pc-check" type="checkbox" name="available" ${item.available ? "checked" : ""}> В наличии</label>
        <div id="edit-errors"></div>
        <div class="pc-dialog-actions"><button class="p-btn" value="cancel" type="button" data-cancel>Отмена</button><button class="p-btn is-primary" type="submit">Сохранить</button></div></form>`;
      document.body.append(dialog);
      dialog.addEventListener("close", () => dialog.remove());
      $("[data-cancel]", dialog).addEventListener("click", () => dialog.close());
      $("form", dialog).addEventListener("submit", async event => {
        event.preventDefault();
        const form = event.target;
        const price = form.price.value.replace(/\s/g, "").replace(",", ".");
        const candidate = { sku: item.sku, name: form.name.value.trim(), price_kopecks: /^\d+(\.\d{1,2})?$/.test(price) ? Math.round(Number(price) * 100) : NaN, url: form.url.value.trim(), available: form.available.checked };
        const errors = validateProduct(candidate, me.domain, 0).map(e => e.replace(/^Товар 1 \([^)]*\): /, ""));
        if (errors.length) { $("#edit-errors", dialog).innerHTML = `<ul class="pc-errors" role="alert">${errors.map(e => `<li>${esc(e)}</li>`).join("")}</ul>`; return; }
        const submit = $("[type=submit]", dialog);
        submit.disabled = true;
        try { await sendProducts([candidate]); toast("Товар сохранён", "ok"); dialog.close(); fetchPage(); }
        catch (error) { $("#edit-errors", dialog).innerHTML = `<ul class="pc-errors" role="alert"><li>${esc(error.message)}</li></ul>`; }
        finally { submit.disabled = false; }
      });
      dialog.showModal();
    };
    const switchTab = tab => {
      state.tab = tab;
      $$(".pc-tabs [data-tab]", host).forEach(button => button.setAttribute("aria-selected", String(button.dataset.tab === tab)));
      tab === "import" ? drawImport() : fetchPage();
    };
    $$(".pc-tabs [data-tab]", host).forEach(button => button.addEventListener("click", () => switchTab(button.dataset.tab)));
    $("#open-import", host).addEventListener("click", () => switchTab("import"));
    await fetchPage();
  };

  /* ---------- 5. Finance ---------- */
  const STATUS = {
    held: ["is-warn", "На удержании", "Идёт период ожидания возвратов"],
    cleared_unpaid: ["is-info", "Удержание прошло", "Период завершён, деньги ещё не выплачены"],
    reversed: ["is-danger", "Аннулировано", "Платёж возвращён, начисление отменено"],
  };
  PAGES.finance = async (host, live) => {
    const [me, totals] = await Promise.all([profile(), summary()]);
    if (!live()) return;
    const held = Math.max(0, totals.earned_kopecks - totals.cleared_kopecks);
    const state = { cursors: [""], page: 0 };
    host.innerHTML = pageHead("Финансы и комиссии", `Ставка ${bps(me.commission_bps)} с подтверждённых подписок, срок начислений ${num(me.term_days)} дн. с первой оплаты пользователя.`) + `
      <dl class="pc-kpis">
        ${kpi("Начислено", rub(totals.earned_kopecks))}
        ${kpi("На удержании", rub(held))}
        ${kpi("Прошло удержание", rub(totals.cleared_kopecks), "не означает выплату")}
        ${kpi("Аннулировано", rub(totals.reversed_kopecks), "", !totals.reversed_kopecks)}
      </dl>
      <section class="pc-block" aria-labelledby="journal">
        <div class="pc-block-head"><h2 id="journal">Журнал начислений</h2><p>Без данных покупателей: только номер квитанции</p></div>
        <div id="journal-body"></div>
      </section>
      <section class="pc-block">${note("info", "info", "<strong>Как читать статусы.</strong> «На удержании» — 30 дней на возможный возврат. «Удержание прошло» — начисление окончательное, но выплата ещё не произведена. «Аннулировано» — платёж вернули пользователю. Выплаты в пилоте не автоматизированы.")}</section>`;
    const journal = $("#journal-body", host);
    const fetchPage = async () => {
      journal.innerHTML = `<div class="pc-panel pc-panel-pad">${'<div class="pc-skel pc-skel-line"></div>'.repeat(5)}</div>`;
      try {
        const page = await api(`/commissions?limit=30&cursor=${encodeURIComponent(state.cursors[state.page] || "")}`);
        if (!live()) return;
        journal.innerHTML = page.items.length ? `<div class="pc-table-wrap"><table class="pc-table"><thead><tr>
            <th>Квитанция</th><th>Дата начисления</th><th class="r">Сумма платежа</th><th class="r">Ставка</th><th class="r">Комиссия</th><th>Конец удержания</th><th>Статус</th></tr></thead><tbody>
            ${page.items.map(row => { const [kind, text, title] = STATUS[row.status] || ["is-plain", row.status, ""]; return `<tr>
              <td class="mono primary" title="${esc(row.receipt_id)}">${esc(row.receipt_id.slice(0, 8))}…</td>
              <td data-label="Начислено">${day(row.created_at)}</td>
              <td class="r" data-label="Платёж">${rub(row.gross_kopecks)}</td>
              <td class="r" data-label="Ставка">${bps(row.rate_bps)}</td>
              <td class="r" data-label="Комиссия"><b>${rub(row.commission_kopecks)}</b></td>
              <td data-label="Удержание до">${day(row.ready_at)}</td>
              <td data-label="Статус"><span class="p-pill ${kind}" title="${esc(title)}">${esc(text)}</span></td></tr>`; }).join("")}
            </tbody></table></div>
            <div class="pc-pager"><span>Страница ${state.page + 1}</span><div><button class="p-btn is-small" type="button" id="fin-prev" ${state.page ? "" : "disabled"}>Назад</button><button class="p-btn is-small" type="button" id="fin-next" ${page.next_cursor ? "" : "disabled"}>Дальше</button></div></div>`
          : `<div class="pc-panel"><div class="pc-state is-inline">${ico("receipt")}<h2>Начислений пока нет</h2><p>Они появятся после первой подтверждённой оплаты подписки пользователем, пришедшим по вашей ссылке.</p></div></div>`;
        $("#fin-prev", journal)?.addEventListener("click", () => { state.page--; fetchPage(); });
        $("#fin-next", journal)?.addEventListener("click", () => { state.cursors[state.page + 1] = page.next_cursor; state.page++; fetchPage(); });
      } catch (error) {
        if (!live()) return;
        journal.innerHTML = `<div class="pc-panel">${errorState(error).replace("pc-state", "pc-state is-inline")}</div>`;
        $("[data-retry]", journal)?.addEventListener("click", fetchPage);
      }
    };
    await fetchPage();
  };

  /* ---------- 6. Payouts ---------- */
  PAGES.payouts = async (host, live) => {
    const [me, totals] = await Promise.all([profile(), summary()]);
    if (!live()) return;
    host.innerHTML = pageHead("Выплаты", "Раздел готов к подключению финансовой системы. Сейчас программа работает в режиме учёта.") + `
      <div class="pc-cols">
        <div class="pc-panel pc-panel-pad"><dl class="pc-kv">
          <dt>Статус программы</dt><dd><span class="p-pill is-warn">Пилот</span></dd>
          <dt>Автоматические выплаты</dt><dd>${me.payouts_enabled ? "Включены" : "Отключены"}</dd>
          <dt>Прошло удержание</dt><dd class="num">${rub(totals.cleared_kopecks)}</dd>
          <dt>Валюта</dt><dd>${esc(me.currency || "RUB")}</dd></dl></div>
        <div class="pc-panel pc-panel-pad"><h2 class="p-label">Что нужно до первой выплаты</h2><ul class="pc-text">
          <li>Подписанный договор с реквизитами обеих сторон.</li>
          <li>Проверка контрагента и порядок закрывающих документов.</li>
          <li>Акт сверки начислений за период.</li>
          <li>Защищённая система выплат с отдельным аудитом.</li></ul></div>
      </div>
      <section class="pc-block">${note("info", "lock", "Консоль не запрашивает банковские реквизиты и не проводит выплаты. Когда выплаты будут подключены, порядок и сроки появятся здесь и в договоре.")}</section>`;
  };

  /* ---------- 7. Domain ---------- */
  const DOMAIN_STATUS = {
    not_started: ["is-plain", "Не начато"],
    pending: ["is-warn", "Ожидает проверки"],
    verified: ["is-ok", "Подтверждён"],
    expired: ["is-danger", "Подтверждение устарело"],
  };
  PAGES.domain = async (host, live) => {
    const me = await profile();
    let proof = await domain(true);
    if (!live()) return;
    let method = proof.method || "dns";
    let lastError = "";
    const draw = () => {
      const [kind, text] = DOMAIN_STATUS[proof.status] || ["is-plain", proof.status];
      const checkedNotFound = proof.status === "pending" && proof.last_checked_at;
      const recordName = "_smetra-verification." + proof.domain;
      const meta = `<meta name="smetra-domain-verification" content="${proof.token || ""}">`;
      host.innerHTML = pageHead("Подтверждение домена", `Домен ${esc(proof.domain)} указан в договоре. Сам по себе он не считается подтверждённым: нужна проверка записи.`, `<span class="p-pill ${kind}">${esc(text)}</span>`) + `
        <div class="pc-panel pc-panel-pad"><ol class="pc-steps">
          <li class="pc-step ${proof.status !== "not_started" ? "is-done" : ""}"><div><h3>Выберите способ</h3>
            <fieldset class="pc-method" ${proof.status === "verified" ? "disabled" : ""}><legend class="visually-hidden">Способ подтверждения</legend>
              <label><input type="radio" name="method" value="dns" ${method === "dns" ? "checked" : ""}><strong>DNS TXT-запись</strong><span>Надёжно, не зависит от сайта. Обновление DNS занимает до нескольких часов.</span></label>
              <label><input type="radio" name="method" value="meta" ${method === "meta" ? "checked" : ""}><strong>HTML meta-тег</strong><span>Быстро, если вы можете править главную страницу сайта.</span></label>
            </fieldset>
            ${proof.status === "verified" ? "" : `<div><button class="p-btn ${proof.token ? "" : "is-primary"}" type="button" id="dom-begin">${proof.token ? "Создать новый код" : "Получить код проверки"}</button></div>`}
          </div></li>
          <li class="pc-step ${proof.token && proof.status !== "not_started" ? "is-done" : ""}"><div><h3>Добавьте запись</h3>
            ${!proof.token ? `<p class="pc-text">Код появится после первого шага. Он действует 7 дней.</p>` : proof.method === "dns" ? `
              <dl class="pc-record"><dt>Тип</dt><dd>TXT</dd><span></span>
                <dt>Имя</dt><dd>${esc(recordName)}</dd><button class="p-copy" type="button" data-copy data-copy-text="${esc(recordName)}">${icon("copy")}Копировать</button>
                <dt>Значение</dt><dd>${esc(proof.token)}</dd><button class="p-copy" type="button" data-copy data-copy-text="${esc(proof.token)}">${icon("copy")}Копировать</button></dl>
              <p class="p-hint">У некоторых DNS-провайдеров в поле «Имя» указывают только <code>_smetra-verification</code> — домен добавляется сам.</p>`
            : `${codeBlock("Вставьте в <head> главной страницы https://" + proof.domain + "/", meta)}
              ${codeBlock("Пример", `<!doctype html>\n<html>\n<head>\n  <meta charset="utf-8">\n  ${meta}\n  <title>…</title>\n</head>`)}
              <p class="p-hint">Проверяется только главная страница по HTTPS без перенаправлений, первые 64 КБ ответа.</p>`}
          </div></li>
          <li class="pc-step ${proof.status === "verified" ? "is-done" : ""}"><div><h3>Проверьте</h3>
            ${proof.status === "verified" ? `<p class="pc-text">Подтверждён ${dayTime(proof.verified_at)}. Подтверждение действует 90 дней, затем проверку нужно пройти снова.</p>`
              : `<div class="pc-toolbar"><button class="p-btn is-primary" type="button" id="dom-verify" ${proof.token && proof.status !== "not_started" ? "" : "disabled"}>${icon("refresh")}Проверить сейчас</button>
                ${proof.last_checked_at ? `<span class="p-hint">Последняя проверка: ${dayTime(proof.last_checked_at)}</span>` : ""}</div>
                ${checkedNotFound ? note("warn", "alert", "<strong>Запись не найдена.</strong> Проверьте имя и значение. После изменения DNS подождите — обновление может занять несколько часов.") : ""}
                ${lastError ? note("warn", "alert", esc(lastError)) : ""}`}
          </div></li>
        </ol></div>
        <section class="pc-block">${note("info", "info", "Подтверждение действует 90 дней. Товары показываются пользователям только при действующем подтверждении — так «Сметра» гарантирует, что ссылки ведут на ваш сайт.")}</section>`;
      bindCommon(host);
      $$("input[name=method]", host).forEach(radio => radio.addEventListener("change", () => { method = radio.value; }));
      $("#dom-begin", host)?.addEventListener("click", async event => {
        event.currentTarget.disabled = true;
        try { proof = await api("/domain", { method: "POST", body: { method } }); cache.domain = Promise.resolve(proof); lastError = ""; toast("Код проверки создан", "ok"); draw(); }
        catch (error) { lastError = error.message; draw(); }
      });
      $("#dom-verify", host)?.addEventListener("click", async event => {
        const button = event.currentTarget;
        button.disabled = true; button.textContent = "Проверяем…";
        try {
          proof = await api("/domain/verify", { method: "POST", body: {} });
          cache.domain = Promise.resolve(proof);
          lastError = "";
          toast(proof.status === "verified" ? "Домен подтверждён" : "Запись пока не найдена", proof.status === "verified" ? "ok" : "error");
          if (proof.status === "verified") { delete cache.profile; attention.delete("domain"); drawNav(); }
        } catch (error) { lastError = error.message; }
        draw();
      });
    };
    draw();
  };

  /* ---------- 8. API ---------- */
  const SAMPLES = {
    curl: `curl -s https://console.smetra.online/api/partners/v1/console/summary \\\n  -H "Authorization: Partner $SMETRA_PARTNER_API_KEY"`,
    js: `// Только на сервере (Node.js 18+). Ключ — из переменной окружения.\nconst res = await fetch("https://console.smetra.online/api/partners/v1/console/catalog", {\n  method: "POST",\n  headers: {\n    "Authorization": "Partner " + process.env.SMETRA_PARTNER_API_KEY,\n    "Content-Type": "application/json",\n  },\n  body: JSON.stringify({ products: [\n    { sku: "TILE-30x60", name: "Плитка 30×60", price_kopecks: 189000,\n      url: "https://shop.example.ru/p/tile", available: true },\n  ] }),\n});\nif (!res.ok) throw new Error((await res.json()).error);`,
    python: `import os\nfrom smetra_partner import PartnerClient\n\nclient = PartnerClient(os.environ["SMETRA_PARTNER_API_KEY"])\nprint(client.summary())\nclient.update_catalog([\n    {"sku": "TILE-30x60", "name": "Плитка 30×60", "price_kopecks": 189000,\n     "url": "https://shop.example.ru/p/tile", "available": True},\n])`,
    events: `curl -s -X POST https://console.smetra.online/api/partners/v1/console/events \\\n  -H "Authorization: Partner $SMETRA_PARTNER_API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '{"event_key":"order-2026-000123","event_type":"material_order_reported","amount_kopecks":1250000}'`,
    errors: `{\n  "error": "Товар должен вести на подтверждённый HTTPS-домен партнёра"\n}\n\n400  данные не прошли проверку\n401  ключ или сессия недействительны\n403  домен не подтверждён (события)\n409  ключ события уже использован с другими данными\n429  превышен лимит запросов`,
  };
  PAGES.api = async (host, live) => {
    const [me, proof, products] = await Promise.all([profile(), domain(), firstProducts()]);
    if (!live()) return;
    const statusRow = (ok, label, hint) => `<div class="pc-attn-item ${ok ? "is-done" : ""}">${ico(ok ? "check" : "alert")}<div><strong>${esc(label)}</strong><span>${esc(hint)}</span></div></div>`;
    host.innerHTML = pageHead("API и интеграции", "REST API: JSON по HTTPS, авторизация ключом партнёра в заголовке.", `<a class="p-btn is-small" href="/docs" target="_blank" rel="noopener">${icon("book")}Документация</a><a class="p-btn is-small" href="/partner-openapi.json" target="_blank" rel="noopener">OpenAPI 3.1</a>`) + `
      <section class="pc-block" aria-labelledby="int-status"><div class="pc-block-head"><h2 id="int-status">Статус интеграции</h2></div>
        <div class="pc-panel pc-attn">
          ${statusRow(me.active, "Аккаунт партнёра активен", me.active ? "Ключ принимается сервером" : "Аккаунт приостановлен — обратитесь к команде")}
          ${statusRow(proof.status === "verified", "Домен подтверждён", proof.status === "verified" ? "Можно отправлять события магазина" : "События магазина принимаются только после подтверждения")}
          ${statusRow(products.items.length > 0, "Каталог загружен", products.items.length ? "Товары есть в каталоге" : "Загрузите товары через /catalog")}
        </div></section>
      <section class="pc-block" aria-labelledby="examples"><div class="pc-block-head"><h2 id="examples">Примеры</h2>
        <div class="pc-code-tabs" role="tablist" aria-label="Язык">${[["curl", "cURL"], ["js", "JavaScript"], ["python", "Python"]].map(([id, label], i) => `<button type="button" role="tab" data-lang="${id}" aria-selected="${!i}">${label}</button>`).join("")}</div></div>
        <div id="sample">${codeBlock("cURL", SAMPLES.curl)}</div></section>
      <section class="pc-block pc-cols">
        <div><div class="pc-block-head"><h2>События магазина</h2></div>${codeBlock("POST /events", SAMPLES.events)}<p class="p-hint" data-mt>Типы: widget_impression, widget_click, material_order_reported. Сумма — только для заказа. Повтор с тем же event_key не создаёт дубль. Принимаются только при подтверждённом домене.</p></div>
        <div><div class="pc-block-head"><h2>Ошибки</h2></div>${codeBlock("Формат ответа", SAMPLES.errors)}</div>
      </section>
      <section class="pc-block" aria-labelledby="limits"><div class="pc-block-head"><h2 id="limits">Ограничения частоты</h2><p>На партнёра, скользящее окно</p></div>
        <div class="pc-table-wrap"><table class="pc-table"><thead><tr><th>Операция</th><th class="r">Лимит</th></tr></thead><tbody>
          ${[["Сводка (summary)", "100 / час"], ["Страницы каталога и начислений", "120 / час"], ["Загрузка каталога", "20 / час"], ["Домен, проверка, аналитика и события", "120 / час, общий"], ["Проверка домена", "ещё 6 / 15 мин"], ["Вход в консоль (с одного IP)", "8 / 15 мин"]].map(([a, b]) => `<tr><td class="primary">${a}</td><td class="r" data-label="Лимит">${b}</td></tr>`).join("")}
        </tbody></table></div></section>
      <section class="pc-block" aria-labelledby="keys"><div class="pc-block-head"><h2 id="keys">API-ключи</h2></div>
        ${note("info", "key", "Ключ выдаёт и меняет администратор «Сметры». При замене старый ключ и все сессии консоли сразу перестают работать. Храните ключ только на сервере: в браузерном коде, мобильных приложениях и репозиториях его быть не должно. Для замены напишите на <a class=\"pc-link\" href=\"mailto:sales@smetra.online\">sales@smetra.online</a>.")}</section>`;
    $$(".pc-code-tabs button", host).forEach(button => button.addEventListener("click", () => {
      $$(".pc-code-tabs button", host).forEach(b => b.setAttribute("aria-selected", String(b === button)));
      $("#sample", host).innerHTML = codeBlock(button.textContent, SAMPLES[button.dataset.lang]);
      bindCommon($("#sample", host));
    }));
  };

  /* ---------- 9. SDK ---------- */
  PAGES.sdk = async (host, live) => {
    const me = await profile();
    if (!live()) return;
    const link = REFERRAL_BASE + encodeURIComponent(me.code);
    const sdk = `<script src="https://console.smetra.online/partner-sdk.js" defer></script>`;
    const scenarios = [
      { id: "button", title: "Кнопка «Создать смету»", text: "Рядом с товарами для ремонта.", preview: `<div class="pc-preview-shop"><strong>Плитка 30×60 серая</strong><p>1 890 ₽ / м²</p><a class="pc-widget-btn" href="${esc(link)}" target="_blank" rel="noopener">Создать смету</a></div>`,
        code: `${sdk}\n<div id="smetra-button"></div>\n<script>\n  addEventListener("DOMContentLoaded", () =>\n    SmetraPartner.mount({ container: "#smetra-button", code: "${me.code}", label: "Создать смету" }));\n</script>` },
      { id: "ai", title: "Блок с предложением ИИ", text: "В корзине или на странице категории.", preview: `<div class="pc-preview-shop"><div class="pc-widget-card"><div><b>Посчитайте материалы с ИИ</b><small>Опишите ремонт — «Сметра» составит смету и список покупок</small></div><a class="pc-widget-btn" href="${esc(link)}" target="_blank" rel="noopener">Попробовать</a></div></div>`,
        code: `${sdk}\n<div class="smetra-offer">\n  <b>Посчитайте материалы с ИИ</b>\n  <small>Опишите ремонт — «Сметра» составит смету и список покупок</small>\n  <a data-smetra-link href="${link}">Попробовать</a>\n</div>\n<script>\n  addEventListener("DOMContentLoaded", () =>\n    SmetraPartner.attach({ code: "${me.code}", selector: "[data-smetra-link]" }));\n</script>` },
      { id: "pro", title: "Кабинет профессионала", text: "Раздел для прорабов и бригад.", preview: `<div class="pc-preview-shop"><p>Инструменты для профессионалов</p><a class="pc-widget-link" href="${esc(link)}" target="_blank" rel="noopener">Сметы и объекты в «Сметре» →</a></div>`,
        code: `<a href="${link}" rel="noopener">Сметы и объекты в «Сметре»</a>` },
      { id: "order", title: "Ссылка из заказа", text: "В письме или карточке заказа материалов.", preview: `<div class="pc-preview-shop"><p>Заказ № 10423 собран</p><strong>Следующий объект посчитайте заранее</strong><a class="pc-widget-link" href="${esc(link)}" target="_blank" rel="noopener">Открыть «Сметру»</a></div>`,
        code: `<p>Следующий объект посчитайте заранее:\n  <a href="${link}">Открыть «Сметру»</a></p>` },
    ];
    let current = scenarios[0];
    host.innerHTML = pageHead("SDK и материалы", "Готовые варианты размещения. Код безопасен для сайта: в нём нет секретных ключей, только публичный код партнёра.") + `
      <div class="pc-tabs" role="tablist" aria-label="Сценарий">${scenarios.map((s, i) => `<button type="button" role="tab" data-scenario="${s.id}" aria-selected="${!i}">${esc(s.title)}</button>`).join("")}</div>
      <div id="scenario"></div>
      <section class="pc-block">${note("warn", "lock", "<strong>Никогда не вставляйте ключ Partner API в код сайта.</strong> Ключ даёт доступ к каталогу и статистике. Виджету он не нужен.")}</section>`;
    const draw = () => {
      $("#scenario", host).innerHTML = `<div class="pc-cols"><div class="pc-panel pc-panel-pad"><p class="p-label">${esc(current.text)} Предпросмотр:</p><div class="pc-preview" data-mt>${current.preview}</div></div><div>${codeBlock("HTML", current.code)}</div></div>`;
      bindCommon($("#scenario", host));
    };
    $$("[data-scenario]", host).forEach(button => button.addEventListener("click", () => {
      current = scenarios.find(s => s.id === button.dataset.scenario);
      $$("[data-scenario]", host).forEach(b => b.setAttribute("aria-selected", String(b === button)));
      draw();
    }));
    draw();
  };

  /* ---------- 10. Activity ---------- */
  PAGES.activity = async (host, live) => {
    const [proof, commissions, products] = await Promise.all([domain(), api("/commissions?limit=30"), api("/products?limit=100")]);
    if (!live()) return;
    // Real records the server already returns; no invented events.
    const events = [];
    if (proof.verified_at) events.push({ at: proof.verified_at, icon: "domain", kind: "domain", text: `Домен ${proof.domain} подтверждён` });
    if (proof.last_checked_at && proof.last_checked_at !== proof.verified_at) events.push({ at: proof.last_checked_at, icon: "domain", kind: "domain", text: `Проверка домена: ${(DOMAIN_STATUS[proof.status] || [, proof.status])[1].toLowerCase()}` });
    const updates = new Map();
    products.items.forEach(item => updates.set(item.updated_at, (updates.get(item.updated_at) || 0) + 1));
    updates.forEach((count, at) => events.push({ at, icon: "catalog", kind: "catalog", text: `Обновление каталога: ${num(count)} ${count === 1 ? "товар" : "товаров"}` }));
    commissions.items.forEach(row => events.push({ at: row.created_at, icon: "receipt", kind: "money", text: `${row.status === "reversed" ? "Начисление аннулировано" : "Начисление"} ${rub(row.commission_kopecks)}`, meta: row.receipt_id.slice(0, 8) }));
    events.sort((a, b) => b.at - a.at);
    let filter = "all";
    const filters = [["all", "Все"], ["domain", "Домен"], ["catalog", "Каталог"], ["money", "Начисления"]];
    const draw = () => {
      const list = events.filter(e => filter === "all" || e.kind === filter);
      $("#act-list", host).innerHTML = list.length ? `<div class="pc-panel pc-timeline">${list.slice(0, 100).map(e => `<div class="pc-event"><time datetime="${new Date(e.at * 1000).toISOString()}">${dayTime(e.at)}</time>${ico(e.icon)}<span>${esc(e.text)}</span><small>${esc(e.meta || "")}</small></div>`).join("")}</div>`
        : `<div class="pc-panel"><div class="pc-state is-inline">${ico("activity")}<h2>Событий нет</h2><p>Здесь появятся проверки домена, загрузки каталога и начисления.</p></div></div>`;
    };
    host.innerHTML = pageHead("История операций", "Собрано из данных, которые сервер уже отдаёт: проверки домена, даты обновления каталога и начисления.", seg("Категория", "all", filters)) +
      note("info", "info", "Полный журнал аудита (изменения настроек, операции с ключами, кто и когда входил) требует отдельного серверного метода. Он описан в docs/partner-console-contracts.md и будет подключён, когда появится на сервере.") +
      `<div class="pc-block" id="act-list"></div>`;
    $$(".pc-seg button", host).forEach(button => button.addEventListener("click", () => {
      filter = button.dataset.value;
      $$(".pc-seg button", host).forEach(b => b.setAttribute("aria-pressed", String(b === button)));
      draw();
    }));
    draw();
  };

  /* ---------- 11. Settings ---------- */
  PAGES.settings = async (host, live) => {
    const me = await profile(true);
    if (!live()) return;
    const [kind, text] = DOMAIN_STATUS[me.domain_status] || ["is-plain", me.domain_status];
    host.innerHTML = pageHead("Настройки", "Данные аккаунта меняет команда «Сметры» по вашему запросу.") + `
      <div class="pc-cols">
        <section class="pc-panel pc-panel-pad" aria-labelledby="s-general"><h2 class="p-label" id="s-general">Партнёр</h2><dl class="pc-kv">
          <dt>Название</dt><dd>${esc(me.name)}</dd><dt>Код партнёра</dt><dd class="mono">${esc(me.code)}</dd><dt>ID</dt><dd class="mono">${esc(me.id)}</dd>
          <dt>Состояние</dt><dd>${me.active ? '<span class="p-pill is-ok">Активен</span>' : '<span class="p-pill is-danger">Приостановлен</span>'}</dd></dl></section>
        <section class="pc-panel pc-panel-pad" aria-labelledby="s-domain"><h2 class="p-label" id="s-domain">Домен</h2><dl class="pc-kv">
          <dt>Домен</dt><dd>${esc(me.domain)}</dd><dt>Статус</dt><dd><span class="p-pill ${kind}">${esc(text)}</span></dd>
          <dt>Подтверждён</dt><dd>${dayTime(me.domain_verified_at)}</dd></dl><p data-mt><a class="pc-link" href="#/domain">Перейти к подтверждению</a></p></section>
        <section class="pc-panel pc-panel-pad" aria-labelledby="s-terms"><h2 class="p-label" id="s-terms">Условия</h2><dl class="pc-kv">
          <dt>Комиссия</dt><dd>${bps(me.commission_bps)} с подтверждённых подписок</dd><dt>Срок начислений</dt><dd>${num(me.term_days)} дн. с первой оплаты</dd>
          <dt>Валюта</dt><dd>${esc(me.currency)}</dd><dt>Выплаты</dt><dd>${me.payouts_enabled ? "Включены" : "Отключены (пилот)"}</dd></dl></section>
        <section class="pc-panel pc-panel-pad" aria-labelledby="s-api"><h2 class="p-label" id="s-api">API</h2><dl class="pc-kv">
          <dt>Базовый адрес</dt><dd class="mono">https://console.smetra.online/api/partners/v1</dd><dt>Схема</dt><dd><a class="pc-link" href="/partner-openapi.json" target="_blank" rel="noopener">OpenAPI 3.1</a></dd>
          <dt>Документация</dt><dd><a class="pc-link" href="/docs" target="_blank" rel="noopener">console.smetra.online/docs</a></dd></dl></section>
        <section class="pc-panel pc-panel-pad" aria-labelledby="s-sec"><h2 class="p-label" id="s-sec">Безопасность доступа</h2><dl class="pc-kv">
          <dt>Сессия консоли</dt><dd>до ${new Date(session.expiresAt).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</dd>
          <dt>Ключ API</dt><dd>Хранится на сервере только в виде хеша. Замена — через команду «Сметры».</dd></dl>
          <div class="pc-toolbar" data-mt><button class="p-btn is-small is-danger" type="button" id="s-signout">Завершить сессию</button></div></section>
        <section class="pc-panel pc-panel-pad" aria-labelledby="s-help"><h2 class="p-label" id="s-help">Поддержка</h2><dl class="pc-kv">
          <dt>Партнёрство</dt><dd><a class="pc-link" href="mailto:sales@smetra.online">sales@smetra.online</a></dd><dt>Техническая</dt><dd><a class="pc-link" href="mailto:support@smetra.online">support@smetra.online</a></dd></dl></section>
      </div>
      <section class="pc-block">${note("info", "info", "<strong>Планируется:</strong> сотрудники партнёра, роли, приглашения, двухфакторный вход и настройки уведомлений. Они появятся вместе с серверным разграничением доступа.")}</section>`;
    $("#s-signout", host).addEventListener("click", signOut);
  };

  /* ---------- sign in / out ---------- */
  const showApp = () => {
    $("#signin").hidden = true;
    $("#dashboard").hidden = false;
    drawNav();
    tick();
    profile().then(me => { $("#partner-name").textContent = me.name; $("#partner-meta").textContent = me.domain; }).catch(() => {});
  };
  const showSignin = message => {
    $("#dashboard").hidden = true;
    $("#signin").hidden = false;
    const error = $("#key-error");
    error.hidden = !message;
    error.textContent = message || "";
    $("#key").focus();
  };
  let ticker = 0;
  const tick = () => {
    clearInterval(ticker);
    const update = () => {
      if (!session) return;
      const left = Math.max(0, Math.round((session.expiresAt - Date.now()) / 60000));
      const label = $("#session-left");
      label.textContent = `Сессия: ${left} мин`;
      label.classList.toggle("is-low", left <= 5);
      if (session.expiresAt <= Date.now()) expire();
    };
    update();
    ticker = setInterval(update, 30000);
  };
  function expire() {
    if (!session) return;
    session = null;
    saveSession(null);
    clearCache();
    clearInterval(ticker);
    showSignin("Сессия закончилась. Войдите снова — вы вернётесь на ту же страницу.");
  }
  async function signOut() {
    const token = session?.token;
    session = null;
    saveSession(null);
    clearCache();
    clearInterval(ticker);
    if (token) fetch(API + "/logout", { method: "POST", credentials: "omit", headers: { Authorization: "PartnerSession " + token, "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
    showSignin("");
  }
  $("#signout").addEventListener("click", signOut);

  $("#connect").addEventListener("submit", async event => {
    event.preventDefault();
    const input = $("#key");
    const key = input.value.trim();
    const error = $("#key-error");
    const fail = message => { error.hidden = false; error.textContent = message; input.setAttribute("aria-invalid", "true"); input.focus(); };
    input.removeAttribute("aria-invalid");
    error.hidden = true;
    if (!/^smp_live_[A-Za-z0-9_-]{35,100}$/.test(key)) { fail("Ключ начинается с smp_live_ и содержит от 35 символов после префикса."); return; }
    const button = $("#connect button");
    button.disabled = true; button.textContent = "Входим…";
    try {
      const response = await fetch(API + "/session", { method: "POST", credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ api_key: key }) });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        fail(response.status === 401 ? "Ключ не подошёл: он неверный, отозван или аккаунт приостановлен."
          : response.status === 429 ? "Слишком много попыток входа. Подождите 15 минут." : "Не удалось войти. Повторите позже.");
        return;
      }
      session = { token: result.session_token, expiresAt: Date.now() + (Number(result.expires_in) || 3600) * 1000 - 15000 };
      saveSession(session);
      showApp();
      render();
    } catch {
      fail(navigator.onLine ? "Сервер не отвечает. Повторите попытку." : "Нет подключения к интернету.");
    } finally {
      input.value = "";
      button.disabled = false; button.textContent = "Войти";
    }
  });

  /* ---------- shell behaviour ---------- */
  const collapse = $(".pc-collapse");
  const setCollapsed = value => {
    $("#dashboard").classList.toggle("is-collapsed", value);
    collapse.setAttribute("aria-expanded", String(!value));
    collapse.setAttribute("aria-label", value ? "Развернуть меню" : "Свернуть меню");
    try { localStorage.setItem("smetra.partner.side", value ? "mini" : "full"); } catch { /* optional */ }
  };
  collapse.addEventListener("click", () => setCollapsed(!$("#dashboard").classList.contains("is-collapsed")));
  try { if (localStorage.getItem("smetra.partner.side") === "mini") setCollapsed(true); } catch { /* optional */ }
  addEventListener("hashchange", () => { openMore(false); render(); view().focus({ preventScroll: true }); scrollTo(0, 0); });
  addEventListener("keydown", event => { if (event.key === "Escape" && !$("#pc-more").hidden) { openMore(false); $("#pc-more-btn")?.focus(); } });
  addEventListener("online", () => toast("Соединение восстановлено", "ok"));
  addEventListener("offline", () => toast("Нет подключения к интернету", "error"));

  session = loadSession();
  if (session) {
    showApp();
    // Validate the stored session before drawing the page.
    profile().then(() => render()).catch(error => { if (error.kind !== "auth") render(); });
  } else {
    showSignin("");
  }
})();
