// Deterministic timeline: every frame is a pure function of (t, format).
// window.seek(t) writes all styles from scratch; no CSS transitions, timers or accumulated state.
'use strict';
const Q = new URLSearchParams(location.search);
const V = Q.get('fmt') === 'v';
const W = V ? 1080 : 1920, H = V ? 1920 : 1080;
const BASE = V ? 1.5 : 1;                 // vertical: 720×1280 world rendered at 1.5×
const T_END = 30.5;
const $ = id => document.getElementById(id);
document.body.classList.toggle('v', V);

// ───────── layout ─────────
const L = V ? {
  ww: 720, wh: 1280, colX: 24, colW: 672, compY: 560, greetY: 468, bubY: 76, bubW: 560, thinkY: 236, draftY: 236, compBottom: 1150,
  edX: 16, edY: 76, edW: 688, asW: 688, pgW: 600, pgH: 848, pgX: 60, pgY: 96, pgPad: 44, pgFs: 13.5,
  logoFs: 118, urlFs: 24, capFs: 44, demoFs: 24, cur: 46, focus: [540, 800]
} : {
  ww: 1920, wh: 1080, colX: 704, colW: 760, compY: 476, greetY: 392, bubY: 92, bubW: 620, thinkY: 236, draftY: 236, compBottom: 952,
  edX: 296, edY: 96, edW: 1110, asX: 1436, asW: 330, pgW: 620, pgH: 877, pgX: 774, pgY: 64, pgPad: 48, pgFs: 14,
  logoFs: 168, urlFs: 30, capFs: 30, demoFs: 16, cur: 30, focus: [960, 540]
};
const root = document.documentElement.style;
const px = v => v + 'px';
Object.entries({
  '--ww': L.ww, '--wh': L.wh, '--col-x': L.colX, '--col-w': L.colW, '--comp-y': L.compY, '--bub-y': L.bubY, '--bub-w': L.bubW,
  '--think-y': L.thinkY, '--draft-y': L.draftY, '--ed-x': L.edX, '--ed-y': L.edY, '--ed-w': L.edW, '--as-w': L.asW,
  '--pg-w': L.pgW, '--pg-h': L.pgH, '--pg-x': L.pgX, '--pg-y': L.pgY, '--pg-pad': L.pgPad, '--pg-fs': L.pgFs,
  '--logo-fs': L.logoFs, '--url-fs': L.urlFs, '--cap-fs': L.capFs, '--demo-fs': L.demoFs
}).forEach(([k, v]) => root.setProperty(k, px(v)));
$('greet').style.top = px(L.greetY);
const screen = $('screen'); screen.style.width = px(W); screen.style.height = px(H);

// ───────── math ─────────
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const lerp = (a, b, p) => a + (b - a) * p;
const env = (t, a, b) => clamp((t - a) / (b - a));
const mj = u => { u = clamp(u); return u * u * u * (10 - 15 * u + 6 * u * u); };      // minimum-jerk
const eOut = u => 1 - Math.pow(1 - clamp(u), 3);
const bump = u => (u <= 0 || u >= 1) ? 0 : Math.sin(Math.PI * u);
// Analytic damped spring step response (0 → 1). f in Hz, z damping ratio.
function spr(t, f = 1.4, z = 0.9) {
  if (t <= 0) return 0;
  const w = 2 * Math.PI * f;
  if (z >= 1) return 1 - (1 + w * t) * Math.exp(-w * t);
  const wd = w * Math.sqrt(1 - z * z);
  return 1 - Math.exp(-z * w * t) * (Math.cos(wd * t) + z * w / wd * Math.sin(wd * t));
}
// Retargeting = sum of step responses, so arbitrary seek order gives identical frames.
function track(keys, t, prop, fdef = 1.4, zdef = 0.9) {
  let v = keys[0][prop];
  for (let i = 1; i < keys.length; i++) {
    const k = keys[i], d = k[prop] - keys[i - 1][prop];
    if (d) v += d * spr(t - k.t, k.f ?? fdef, k.z ?? zdef);
  }
  return v;
}
// in/out presence 0..1 with spring-like ease
function pres(t, tin, tout = 1e9, din = 0.32, dout = 0.22) { return eOut(env(t, tin, tin + din)) * (1 - env(t, tout, tout + dout)); }

// ───────── measurement (world coordinates of the main plane, untransformed) ─────────
const R = {};
function wrect(el) {
  const m = $('main').getBoundingClientRect(), r = el.getBoundingClientRect();
  return { x: r.left - m.left, y: r.top - m.top, w: r.width, h: r.height, cx: r.left - m.left + r.width / 2, cy: r.top - m.top + r.height / 2 };
}
function union(a, b) { const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y), x2 = Math.max(a.x + a.w, b.x + b.w), y2 = Math.max(a.y + a.h, b.y + b.h); return { x, y, w: x2 - x, h: y2 - y, cx: (x + x2) / 2, cy: (y + y2) / 2 }; }

// ───────── script data (times from the real voice alignment, snapped to a 120 BPM half-beat grid) ─────────
const TASK = 'Комната 18 м². Покраска стен — 42 м², ламинат — 18 м², плинтус — 17 м. Только работы';
const TYPE0 = 4.08, TYPE1 = 6.86;
const typeTimes = (() => {          // human rhythm: short holds after punctuation and spaces
  const w = [...TASK].map((c, i) => (c === ' ' ? 1.25 : 1) + ('.,—'.includes(TASK[i - 1] || '') ? 1.6 : 0));
  const sum = w.reduce((a, b) => a + b, 0); let acc = 0;
  return w.map(x => { acc += x; return TYPE0 + (acc / sum) * (TYPE1 - TYPE0); });
})();
const T = {
  focus: 3.95, send: 7.2, draft: 8.45, open: 11.2, dbl: 12.2, k1: 12.62, k2: 12.72, k3: 12.82, commit: 13.7,
  line: 13.72, total: 14.45, saved: 15.2, exp: 16.7, pdf: 17.45, logo: 25.95
};
const CLICKS = [
  { t: T.focus, el: 'c-input' }, { t: T.send, el: 'c-send' }, { t: T.open, el: 'dr-open' },
  { t: T.dbl, el: 'price', dbl: true }, { t: T.exp, el: 'exp-btn' }, { t: T.pdf, el: 'mi-pdf' }
];
// Sound cues, read by the audio builder through window.getEvents().
function events() {
  const ev = [];
  CLICKS.forEach(c => { ev.push({ t: c.t, type: 'click' }); if (c.dbl) ev.push({ t: c.t + 0.11, type: 'click' }); });
  typeTimes.forEach((t, i) => { if (TASK[i] !== ' ') ev.push({ t, type: 'key' }); });
  [T.k1, T.k2, T.k3].forEach(t => ev.push({ t, type: 'key' }));
  ev.push({ t: T.commit, type: 'key' });
  ev.push({ t: T.send + 0.06, type: 'whoosh', d: 0.5 });
  ev.push({ t: T.draft, type: 'pop' });
  ev.push({ t: T.open + 0.05, type: 'whoosh', d: 0.6 });
  for (let i = 0; i < 5; i++) ev.push({ t: T.line + i * 0.045, type: 'tick' });
  for (let i = 0; i < 5; i++) ev.push({ t: T.total + i * 0.05, type: 'tick' });
  ev.push({ t: T.total + 0.42, type: 'confirm' });
  ev.push({ t: T.exp + 0.05, type: 'menu' });
  ev.push({ t: T.pdf + 0.1, type: 'whoosh', d: 0.7 });
  ev.push({ t: T.pdf + 0.5, type: 'paper' });
  ev.push({ t: 18.9, type: 'confirm' });
  ev.push({ t: T.logo + 0.05, type: 'whoosh', d: 0.6 });
  ev.push({ t: 26.45, type: 'chime' });
  return ev.sort((a, b) => a.t - b.t);
}

// ───────── init: fill static values and measure anchors ─────────
const LETTERS = [...'сметра'];
const F = {};
function init() {
  $('logo-w').innerHTML = LETTERS.map(c => `<span class="w">${c}</span>`).join('');
  $('price').textContent = '550';
  const fo = el => { const c = getComputedStyle(el); return `${c.fontWeight} ${c.fontSize} Onest`; };
  F.lt = fo($('lt2')); F.tot = fo($('ed-total'));
  $('lt2').innerHTML = roll('9 900 ₽', '11 700 ₽', 0, F.lt);
  $('ed-total').innerHTML = roll('28 850 ₽', '30 650 ₽', 0, F.tot);
  $('c-text').textContent = TASK; $('c-ph').style.display = 'none';
  $('bubble').textContent = TASK;
  if (V) { const e = wrect($('ed')); $('aside').style.top = px(e.y + e.h + 14); $('aside').style.left = px(L.edX); }
  else { $('aside').style.left = px(L.asX); $('aside').style.top = px(L.edY); }
  ['composer', 'c-input', 'c-text', 'bubble', 'think', 'draft', 'dr1', 'dr2', 'dr3', 'ed', 'ei2', 'aside', 'price', 'lt2', 'ed-total', 'exp-btn',
    'page', 'file', 'pg-r2', 'pg-sum', 'logo-b', 'logo-slot'].forEach(id => R[id] = wrect($(id)));
  R.drlist = wrect(document.querySelector('.dr-list'));
  R.pgtitle = wrect(document.querySelector('.pg-title'));
  R.pgtable = wrect(document.querySelector('.pg-t'));
  R.edall = union(R.ed, R.aside);
  R.pagefile = union(R.page, R.file);
  // menu hangs under the export button, right-aligned
  const m = $('menu'); const mw = m.offsetWidth;
  m.style.left = px(R['exp-btn'].x + R['exp-btn'].w - mw); m.style.top = px(R['exp-btn'].y + R['exp-btn'].h + 6);
  R.menu = wrect(m); R['mi-pdf'] = wrect($('mi-pdf'));
  const fs = L.logoFs, s = R['logo-slot'];
  R.dot = { x: s.x + 0.045 * fs, y: s.y + s.h - 0.19 * fs, w: 0.19 * fs, h: 0.19 * fs };
  R.dot.cx = R.dot.x + R.dot.w / 2; R.dot.cy = R.dot.y + R.dot.h / 2;
  // bubble FLIP: start where the typed text sits in the composer
  R.flip = { dx: R['c-text'].x - R['bubble'].x - 14, dy: R['c-text'].y - R['bubble'].y - 10 };
  $('c-text').textContent = ''; $('bubble').textContent = TASK;
  buildCamera();
}

// ───────── number roll with fixed digit slots ─────────
const CTX = document.createElement('canvas').getContext('2d');
const cw = (c, font) => { CTX.font = font; return CTX.measureText(c === ' ' ? ' ' : c).width; };
// Onest has proportional figures, so each changing slot animates its width between the two glyphs.
function roll(a, b, p, font, stagger = 0.06) {
  const n = Math.max(a.length, b.length); a = a.padStart(n, ' '); b = b.padStart(n, ' ');
  const op = c => c === ' ' ? '&nbsp;' : c;
  let h = '<span class="roll">';
  for (let i = 0; i < n; i++) {
    const ca = a[i], cb = b[i];
    if (ca === cb) { h += `<span class="slot"><span>${op(ca)}</span></span>`; continue; }
    const k = (n - 1 - i) * stagger, u = clamp((p - k) / (1 - (n - 1) * stagger));
    const e = spr(u * 0.6, 1.5, 0.88), bl = 3 * bump(clamp(u * 1.25));
    const wa = ca === ' ' && i === 0 ? 0 : cw(ca, font), w = lerp(wa, cw(cb, font), clamp(e));
    h += `<span class="slot" style="width:${w.toFixed(2)}px"><span>&nbsp;</span>` +
      `<span style="transform:translateY(${(-105 * e).toFixed(2)}%);opacity:${(1 - e).toFixed(3)};filter:blur(${bl.toFixed(2)}px)">${op(ca)}</span>` +
      `<span style="transform:translateY(${(105 * (1 - e)).toFixed(2)}%);opacity:${e.toFixed(3)};filter:blur(${bl.toFixed(2)}px)">${op(cb)}</span></span>`;
  }
  return h + '</span>';
}

// ───────── camera ─────────
// Keys: anchor (rect name) + offsets in world px + relative scale + tilt. Values are retargeted with springs.
let CAM = [];
function buildCamera() {
  const k = (t, a, s, o = {}) => {
    const r = typeof a === 'string' ? R[a] : a;
    return { t, x: r.cx + (o.dx || 0), y: r.cy + (o.dy || 0), s: s * BASE, rx: o.rx || 0, ry: o.ry || 0, f: o.f, z: o.z };
  };
  const c = R.composer;
  const caretLine = { cx: c.x + c.w * (V ? 0.5 : 0.42), cy: c.y + c.h * 0.42 };
  const pc = r => ({ cx: R.page.cx, cy: r.cy });
  CAM = V ? [
    k(0, 'composer', 0.88, { rx: 16, ry: -8 }),
    k(0.05, 'composer', 1.0, { f: 0.5, z: 0.95 }),
    k(3.95, 'composer', 1.07, { dy: -14, f: 0.9 }),
    k(6.7, 'composer', 1.02, { dy: 10, f: 1.0 }),
    k(7.35, { cx: L.ww / 2, cy: 400 }, 0.98, { f: 0.9 }),
    k(8.55, 'draft', 1.04, { f: 0.8 }),
    k(9.6, 'draft', 1.07, { dy: 20, f: 0.6 }),
    k(11.25, 'edall', 0.9, { f: 1.1 }),
    k(11.8, 'ei2', 1.05, { f: 1.0 }),
    k(13.75, union(R.ei2, R.aside), 0.98, { f: 1.0 }),
    k(14.3, union(R.lt2, R['ed-total']), 1.05, { f: 1.0 }),
    k(15.6, 'exp-btn', 1.08, { dx: -250, dy: 150, f: 0.9 }),
    k(17.6, 'pagefile', 0.97, { f: 1.0 }),
    k(19.7, 'pagefile', 0.94, { ry: -9, rx: 4, f: 0.7 }),
    k(21.0, pc(R.pgtitle), 1.15, { ry: -4, rx: 2, f: 0.7 }),
    k(22.4, pc(R.pgtable), 1.12, { f: 0.55 }),
    k(23.6, pc(R['pg-sum']), 1.16, { f: 0.6 }),
    k(24.5, pc(R['pg-r2']), 1.14, { f: 0.7 }),
    k(25.95, { cx: L.ww / 2, cy: R['logo-b'].cy + 40 }, 1.0, { f: 1.0 }),
    k(27.0, { cx: L.ww / 2, cy: R['logo-b'].cy + 40 }, 1.05, { f: 0.22, z: 1 })
  ] : [
    k(0, 'composer', 0.84, { rx: 14, ry: -7 }),
    k(0.05, 'composer', 1.0, { f: 0.5, z: 0.95 }),
    k(3.95, caretLine, 1.42, { f: 0.9 }),
    k(5.5, caretLine, 1.42, { dx: 60, dy: 8, f: 0.6 }),
    k(6.7, 'composer', 1.18, { dx: 120, f: 1.0 }),
    k(7.35, { cx: L.colX + L.colW / 2, cy: 400 }, 1.02, { f: 0.9 }),
    k(8.55, 'draft', 1.24, { f: 0.8 }),
    k(9.6, 'draft', 1.3, { dy: 26, dx: -20, f: 0.6 }),
    k(11.25, 'edall', 0.98, { f: 1.1 }),
    k(11.8, 'ei2', 1.5, { dy: -36, f: 1.15 }),
    k(13.75, union(R.ei2, R.aside), 1.22, { f: 1.0 }),
    k(14.3, 'ed-total', 1.6, { dx: -300, dy: 60, f: 1.0 }),
    k(15.6, 'exp-btn', 1.35, { dx: -220, dy: 110, f: 0.9 }),
    k(17.6, 'pagefile', 0.98, { f: 1.0 }),
    k(19.7, 'pagefile', 0.95, { ry: -10, rx: 4, f: 0.7 }),
    k(21.0, 'pgtitle', 1.75, { dx: 80, ry: -4, rx: 2, f: 0.7 }),
    k(22.4, 'pgtable', 1.55, { f: 0.55 }),
    k(23.6, 'pg-sum', 1.85, { dx: -40, f: 0.6 }),
    k(24.5, 'pg-r2', 1.7, { f: 0.7 }),
    k(25.95, { cx: L.ww / 2, cy: L.wh / 2 }, 1.0, { f: 1.0 }),
    k(27.0, { cx: L.ww / 2, cy: L.wh / 2 }, 1.045, { f: 0.22, z: 1 })
  ];
}
function camera(t) {
  const c = {};
  ['x', 'y', 's', 'rx', 'ry'].forEach(p => c[p] = track(CAM, t, p));
  // continuous, quiet handheld drift while the narration is running
  const a = 1 - env(t, 26.2, 27.5);
  c.x += a * 7 * Math.sin(t * 0.41); c.y += a * 5 * Math.sin(t * 0.33 + 1.1);
  c.rz = a * 0.28 * Math.sin(t * 0.23 + 0.4); c.ry += a * 0.9 * Math.sin(t * 0.27);
  c.rx += a * 0.6 * Math.sin(t * 0.21 + 2);
  return c;
}
function applyCam(c) {
  const [fx, fy] = L.focus;
  const m = `translate(${fx}px,${fy}px) rotateX(${c.rx}deg) rotateY(${c.ry}deg) rotateZ(${c.rz}deg) scale(${c.s}) translate(${-c.x}px,${-c.y}px)`;
  $('main').style.transform = m;
  $('persp').style.perspective = (V ? 2600 : 2200) + 'px';
  $('persp').style.perspectiveOrigin = `${fx}px ${fy}px`;
  // back plane: lower parallax ratio + depth-of-field blur grows with zoom
  const sb = BASE + (c.s - BASE) * 0.72;
  $('shell').style.transform = `translate(${fx}px,${fy}px) rotateX(${c.rx * 0.6}deg) rotateY(${c.ry * 0.6}deg) rotateZ(${c.rz}deg) scale(${sb}) translate(${-c.x}px,${-c.y}px)`;
  const blur = clamp((c.s / BASE - 1) * 5, 0, 3.5) + 0.4;
  $('shell').style.filter = `blur(${blur.toFixed(2)}px)`;
}

// ───────── cursor ─────────
// Moves: target = element (+fraction) or screen point. Position is evaluated against live layout,
// so the hotspot stays glued to the UI while the camera moves.
const MOVES = [
  { t0: 0, t1: 0, sp: [W * 0.9, H * 1.08] },
  { t0: 0.7, t1: 2.75, el: 'c-input', fx: V ? 0.42 : 0.3, fy: 0.5, arc: 0.12 },
  { t0: 4.12, t1: 4.75, el: 'composer', fx: 0.8, fy: 1.55, arc: -0.1 },
  { t0: 6.5, t1: 7.02, el: 'c-send', fx: 0.5, fy: 0.5, arc: 0.1 },
  { t0: 7.42, t1: 8.3, el: 'draft', fx: V ? 0.86 : 1.08, fy: V ? -0.15 : 0.15, arc: 0.08 },
  { t0: 9.22, t1: 9.6, el: 'dr1', fx: 0.66, fy: 0.55, arc: 0.05 },
  { t0: 9.84, t1: 10.18, el: 'dr2', fx: 0.68, fy: 0.55, arc: 0.05 },
  { t0: 10.4, t1: 10.7, el: 'dr3', fx: 0.66, fy: 0.55, arc: 0.05 },
  { t0: 10.76, t1: 11.04, el: 'dr-open', fx: 0.5, fy: 0.55, arc: 0.05 },
  { t0: 11.42, t1: 12.02, el: 'price', fx: 0.62, fy: 0.5, arc: -0.1 },
  { t0: 12.4, t1: 12.66, el: 'price', fx: 0.5, fy: 2.1, arc: 0 },
  { t0: 15.45, t1: 16.48, el: 'exp-btn', fx: 0.5, fy: 0.55, arc: 0.12 },
  { t0: 16.86, t1: 17.26, el: 'mi-pdf', fx: 0.36, fy: 0.55, arc: 0.06 },
  { t0: 17.65, t1: 18.7, el: 'file', fx: 0.86, fy: 1.35, arc: 0.1 }
];
const SHAPES = [[0, 'arrow'], [2.6, 'beam'], [4.2, 'arrow'], [6.92, 'hand'], [7.42, 'arrow'], [10.86, 'hand'], [11.4, 'arrow'],
  [11.88, 'beam'], [12.5, 'arrow'], [16.3, 'hand'], [16.86, 'arrow'], [17.1, 'hand'], [17.6, 'arrow']];
function tgt(m) {
  if (m.sp) return m.sp;
  const r = $(m.el).getBoundingClientRect();
  return [r.left + r.width * m.fx, r.top + r.height * m.fy];
}
function cursorPos(t) {
  let i = 0; while (i + 1 < MOVES.length && MOVES[i + 1].t0 <= t) i++;
  const m = MOVES[i], q = tgt(m);
  if (i === 0 || t >= m.t1) return q;
  const p = tgt(MOVES[i - 1]), u = mj((t - m.t0) / (m.t1 - m.t0));
  const dx = q[0] - p[0], dy = q[1] - p[1], d = Math.hypot(dx, dy) || 1, a = (m.arc || 0) * d * bump(u);
  return [p[0] + dx * u - dy / d * a, p[1] + dy * u + dx / d * a];
}
function shapeAt(t) { let s = 'arrow'; for (const [a, n] of SHAPES) if (t >= a) s = n; return s; }
const HOT = { arrow: [3.5, 2.2], hand: [10.6, 2.9], beam: [12, 12] };

// ───────── scene ─────────
const MORPH = () => {
  const dl = R.drlist, ed = R.ed, pg = R.page, dot = R.dot;
  const k = (t, r, f) => ({ t, l: r.x, tp: r.y, r: r.x + r.w, b: r.y + r.h, f });
  return [k(0, dl), k(T.open + 0.05, ed), k(T.pdf + 0.1, pg), k(T.logo + 0.02, dot)];
};
let MK = null;
// split edge springs: the leading edge of each morph moves a little ahead of the trailing one
const EDGE = { l: [2.0, 1.5, 1.7], tp: [2.2, 1.45, 1.6], r: [1.6, 1.75, 1.9], b: [1.5, 1.6, 2.05] };
function morphRect(t) {
  const o = {};
  for (const e of ['l', 'tp', 'r', 'b']) {
    let v = MK[0][e];
    for (let i = 1; i < MK.length; i++) v += (MK[i][e] - MK[i - 1][e]) * spr(t - MK[i].t, EDGE[e][i - 1], 0.88);
    o[e] = v;
  }
  return o;
}
function vis(el, o, y = 0, blur = 0, sc = 1, x = 0) {
  const s = el.style;
  s.opacity = o.toFixed(4);
  s.visibility = o <= 0.001 ? 'hidden' : 'visible';
  s.transform = (x || y || sc !== 1) ? `translate(${x.toFixed(2)}px,${y.toFixed(2)}px) scale(${sc.toFixed(4)})` : 'none';
  s.filter = blur > 0.05 ? `blur(${blur.toFixed(2)}px)` : 'none';
}
// enter/exit with blur: content intervals never overlap during morphs
function blurIn(el, t, tin, tout = 1e9, dy = 10, din = 0.36, dout = 0.2) {
  const i = env(t, tin, tin + din), o = env(t, tout, tout + dout);
  const p = eOut(i) * (1 - o);
  vis(el, p, (1 - eOut(i)) * dy - o * dy * 0.5, (1 - eOut(i)) * 8 + o * 8);
}
const mix = (a, b, p) => a.map((v, i) => Math.round(lerp(v, b[i], p)));

function scene(t) {
  // fade from black at the very start, to black at the very end
  $('fade').style.opacity = (1 - eOut(env(t, 0, 0.55)) + env(t, T_END - 0.55, T_END)).toFixed(4);
  $('shell').style.opacity = (0.62 * (1 - env(t, T.logo, T.logo + 0.6))).toFixed(3);
  $('nav-as').className = t < T.open + 0.2 ? 'on' : ''; $('nav-q').className = t < T.open + 0.2 ? '' : 'on';

  // greeting + composer
  blurIn($('greet'), t, 0.3, T.focus, 12);
  const compIn = eOut(env(t, 0.2, 0.75));
  const down = spr(t - T.send - 0.04, 1.3, 0.9) * (L.compBottom - R.composer.y);
  const compOut = env(t, T.open, T.open + 0.25);
  vis($('composer'), compIn * (1 - compOut), (1 - compIn) * 16 + down, compOut * 6);
  const typed = t < T.send + 0.05 ? typeTimes.filter(x => x <= t).length : 0;
  $('c-text').textContent = TASK.slice(0, typed);
  $('c-ph').style.display = typed || (t > T.focus && t < T.send + 0.05) ? 'none' : 'inline';
  const focused = t >= T.focus && t < T.send + 0.08;
  const typing = t >= TYPE0 - 0.1 && t <= TYPE1 + 0.25;
  $('c-caret').style.display = focused && (typing || Math.floor((t - T.focus) / 0.53) % 2 === 0) ? 'inline-block' : 'none';
  const hov = env(t, 2.7, 2.85) * (1 - env(t, T.focus, T.focus + 0.1));
  const comp = $('composer').style;
  comp.borderColor = focused ? 'rgba(237,237,239,.38)' : `rgba(255,255,255,${(0.13 + 0.08 * hov).toFixed(3)})`;
  comp.boxShadow = focused ? '0 0 0 3px rgba(237,237,239,.06),0 12px 32px rgba(0,0,0,.18)' : '0 1px 0 rgba(255,255,255,.02),0 12px 32px rgba(0,0,0,.18)';
  const send = $('c-send');
  send.className = 'abtn' + (typed ? ' ready' : '');
  const press = bump(env(t, T.send - 0.02, T.send + 0.14));
  send.style.transform = `scale(${(1 - 0.1 * press).toFixed(3)})`;
  send.style.background = typed ? (t > 6.95 && t < T.send + 0.1 ? '#fff' : '') : '';

  // conversation: bubble flies from the composer text (shared element)
  const bp = spr(t - T.send - 0.06, 1.5, 0.9), bOut = env(t, T.open, T.open + 0.2);
  const bIn = env(t, T.send + 0.04, T.send + 0.18);
  vis($('bubble'), bIn * (1 - bOut), (1 - bp) * R.flip.dy, bOut * 8 + (1 - bIn) * 3, 1, (1 - bp) * R.flip.dx);
  $('bubble').style.background = `rgba(28,28,31,${bp.toFixed(3)})`;
  blurIn($('think'), t, T.send + 0.38, T.draft - 0.12, 8, 0.3, 0.16);
  $('think-t').style.backgroundPosition = `${(100 - ((t - 7.5) / 0.9 * 100) % 300)}% 0`;

  // draft card
  const dOut = T.open;
  blurIn(document.querySelector('.dr-head'), t, T.draft, dOut);
  const list = document.querySelector('.dr-list');
  const li = eOut(env(t, T.draft + 0.04, T.draft + 0.4)), lo = env(t, dOut, dOut + 0.16);
  vis(list, li * (1 - lo), (1 - li) * 14, (1 - li) * 6);
  list.style.background = lo > 0 ? 'transparent' : '';
  list.style.borderColor = lo > 0 ? 'transparent' : '';
  ['dr1', 'dr2', 'dr3'].forEach((id, i) => {
    const t0 = T.draft + 0.12 + i * 0.12;
    const p = eOut(env(t, t0, t0 + 0.34));
    const el = $(id); el.style.opacity = (p * (1 - lo)).toFixed(3); el.style.transform = `translateY(${((1 - p) * 10).toFixed(2)}px)`;
    const h = [[9.5, 9.95], [10.08, 10.5], [10.62, 10.9]][i];
    el.style.background = `rgba(255,255,255,${(0.035 * env(t, h[0], h[0] + 0.1) * (1 - env(t, h[1], h[1] + 0.12))).toFixed(4)})`;
  });
  const tot = document.querySelector('.dr-total');
  tot.style.opacity = (eOut(env(t, T.draft + 0.5, T.draft + 0.8)) * (1 - lo)).toFixed(3);
  blurIn(document.querySelector('.dr-actions'), t, T.draft + 0.6, dOut, 8, 0.36, 0.14);
  const ob = $('dr-open'), oh = env(t, 10.95, 11.05), op = bump(env(t, T.open - 0.02, T.open + 0.14));
  ob.style.background = oh ? '#1c1c1f' : ''; ob.style.transform = `scale(${(1 - 0.04 * op).toFixed(3)})`;

  // morph box: draft list → editor → PDF page → brand dot
  const mr = morphRect(t), mvis = t >= dOut && t < 99;
  const ms = $('morph').style;
  ms.visibility = mvis ? 'visible' : 'hidden';
  ms.left = px(mr.l); ms.top = px(mr.tp); ms.width = px(Math.max(0, mr.r - mr.l)); ms.height = px(Math.max(0, mr.b - mr.tp));
  const paper = spr(t - T.pdf - 0.1, 1.6, 0.95), toDot = spr(t - T.logo - 0.02, 1.8, 0.95);
  let col = mix([17, 17, 19], [244, 244, 241], paper); col = mix(col, [110, 168, 255], clamp((toDot - 0.55) / 0.4));
  ms.background = `rgb(${col})`;
  ms.borderColor = `rgba(255,255,255,${(0.075 * (1 - paper)).toFixed(3)})`;
  ms.borderRadius = toDot > 0.02 ? `${lerp(4, 0.5 * Math.min(mr.r - mr.l, mr.b - mr.tp), toDot).toFixed(2)}px` : `${lerp(12, 4, paper).toFixed(2)}px`;
  ms.boxShadow = `0 ${(30 * paper * (1 - toDot)).toFixed(1)}px ${(80 * paper * (1 - toDot)).toFixed(1)}px rgba(0,0,0,${(0.5 * paper * (1 - toDot)).toFixed(3)})`;
  if (t >= dOut && t < dOut + 0.02) ms.background = 'rgb(17,17,19)';

  // editor content
  const edIn = T.open + 0.42, edOut = T.pdf + 0.08;
  blurIn($('ed'), t, edIn, edOut, 10, 0.4, 0.18);
  $('ed').style.background = 'transparent'; $('ed').style.borderColor = 'transparent';
  const ai = spr(t - T.open - 0.3, 1.5, 0.9), ao = env(t, edOut, edOut + 0.22);
  vis($('aside'), clamp(ai * 1.4) * (1 - ao), V ? (1 - ai) * 40 : 0, (1 - clamp(ai * 1.4)) * 6 + ao * 6, 1, V ? 0 : (1 - ai) * 48 + ao * 30);

  // price field: hover → double-click select → type 650 → commit
  const pr = $('price');
  const pFocus = t >= T.dbl && t < T.commit;
  pr.className = 'inp' + (pFocus ? ' focus' : '');
  pr.style.borderColor = !pFocus && t > 11.95 && t < T.dbl ? 'rgba(255,255,255,.2)' : '';
  let val = t < T.k1 ? '550' : t < T.k2 ? '6' : t < T.k3 ? '65' : '650';
  const sel = t >= T.dbl + 0.11 && t < T.k1;
  const car = pFocus && !sel && (t < T.k3 + 0.3 || Math.floor((t - T.k3) / 0.53) % 2 === 1);
  pr.innerHTML = sel ? `<span class="selx">${val}</span>` : val + (car ? '<span class="caret" style="height:1.05em"></span>' : '');
  const row2 = $('ei2');
  row2.style.background = `rgba(255,255,255,${(0.03 * bump(env(t, T.line - 0.05, T.line + 1.1))).toFixed(4)})`;
  $('lt2').innerHTML = roll('9 900 ₽', '11 700 ₽', env(t, T.line, T.line + 0.55), F.lt);
  $('ed-total').innerHTML = roll('28 850 ₽', '30 650 ₽', env(t, T.total, T.total + 0.6), F.tot);
  const saving = t >= T.commit && t < T.saved, saved = t >= T.saved;
  $('save-t').textContent = saved ? 'Сохранено' : saving ? 'Сохраняю…' : 'Черновик';
  document.querySelector('#save-state i').style.background = saved ? 'var(--success)' : saving ? 'var(--text)' : 'var(--text-3)';
  const eb = $('exp-btn'), eh = env(t, 16.4, 16.5) * (1 - env(t, 17.0, 17.2)), ep = bump(env(t, T.exp - 0.02, T.exp + 0.14));
  eb.style.background = `rgba(28,28,31,${eh.toFixed(3)})`; eb.style.color = eh > 0.5 ? 'var(--text)' : '';
  eb.style.transform = `scale(${(1 - 0.05 * ep).toFixed(3)})`;

  // export menu (the existing select-menu look)
  const mo = spr(t - T.exp - 0.03, 2.4, 0.86), mc = env(t, T.pdf + 0.08, T.pdf + 0.22);
  const menuP = t > T.exp ? clamp(mo * 1.2) * (1 - mc) : 0;
  vis($('menu'), menuP, (1 - mo) * -6, (1 - clamp(mo * 1.2)) * 4, 0.96 + 0.04 * mo);
  const mi = $('mi-pdf'), mh = env(t, 17.18, 17.26), mp = bump(env(t, T.pdf - 0.02, T.pdf + 0.14));
  mi.style.background = mp > 0 ? '#242428' : mh ? '#1c1c1f' : 'transparent';

  // PDF page + file chip
  const pgIn = T.pdf + 0.62;
  blurIn($('page'), t, pgIn, T.logo, 10, 0.45, 0.16);
  const fi = eOut(env(t, 18.85, 19.25));
  vis($('file'), fi * (1 - env(t, 20.9, 21.2)), (1 - fi) * 14, 0);
  const hl = bump(env(t, 24.15, 25.6));
  $('pg-r2').style.background = `rgba(20,20,24,${(0.06 * clamp(hl * 1.6)).toFixed(3)})`;

  // logo: the dot lands, letters unfold out of it
  $('logo').style.visibility = t > T.logo ? 'visible' : 'hidden';
  [...document.querySelectorAll('#logo-w .w')].forEach((s, i, all) => {
    const t0 = 26.28 + (all.length - 1 - i) * 0.05, p = spr(t - t0, 1.5, 0.9);
    s.style.opacity = clamp(p * 1.3).toFixed(3);
    s.style.transform = `translateX(${((1 - p) * 0.28 * L.logoFs).toFixed(2)}px)`;
    s.style.filter = p < 0.98 ? `blur(${((1 - clamp(p)) * 10).toFixed(2)}px)` : 'none';
  });
  const up = eOut(env(t, 27.1, 27.7));
  vis($('logo-url'), up, (1 - up) * 10, (1 - up) * 6);
  $('dot').style.visibility = 'hidden';
}

// ───────── HUD: captions, demo note, subtitles, cursor, click rings ─────────
const CAPS = [['cap1', 8.45, 11.05], ['cap2', 12.95, 15.55], ['cap3', 21.0, 25.6]];
const SUBS = [
  [0.0, 1.62, 'Смотри. Допустим,'], [1.62, 3.7, 'нужно посчитать ремонт комнаты.'],
  [3.85, 5.48, 'Пишешь, какие работы нужны'], [5.48, 7.2, 'и какие там объёмы.'],
  [7.35, 9.1, 'Сметра собирает черновик,'], [9.1, 11.45, 'а дальше ты его спокойно проверяешь.'],
  [11.55, 13.75, 'Вот здесь ставишь свою расценку…'], [13.8, 16.2, 'и общая сумма сразу меняется.'],
  [16.4, 17.72, 'Потом выгружаешь PDF'], [17.72, 19.6, 'и отправляешь заказчику,'], [19.6, 20.85, 'как тебе привычно.'],
  [21.0, 22.74, 'Удобно, когда нужно собрать всё'], [22.74, 23.76, 'в одном документе'], [23.76, 25.8, 'и по ходу что-то поправить.'],
  [25.9, 27.4, 'Вот так это выглядит.']
];
function hud(t) {
  const capPos = V ? [60, 132] : [96, 82];
  CAPS.forEach(([id, a, b]) => {
    const el = $(id), p = spr(t - a, 1.6, 0.9), o = env(t, b, b + 0.25);
    el.style.left = px(capPos[0]); el.style.top = px(capPos[1]);
    vis(el, clamp(p * 1.25) * (1 - o), (1 - p) * 18 - o * 8, (1 - clamp(p)) * 10 + o * 8);
    el.style.clipPath = `inset(-20% ${((1 - clamp(p * 1.1)) * 100).toFixed(2)}% -20% 0)`;
  });
  const d = $('demo'), dv = pres(t, 11.75, 17.5, 0.4, 0.2) + pres(t, 18.5, 25.7, 0.4, 0.25);
  if (V) { d.style.left = px(60); d.style.top = px(H - 70); } else { d.style.left = px(96); d.style.top = px(H - 74); }
  d.style.opacity = clamp(dv).toFixed(3);
  // subtitles: vertical edition only
  const sb = $('subs');
  if (V) {
    sb.style.top = px(1600); const s = SUBS.find(x => t >= x[0] && t < x[1]);
    $('subs-t').textContent = s ? s[2] : '';
    const p = s ? env(t, s[0], s[0] + 0.12) * (1 - env(t, s[1] - 0.1, s[1])) : 0;
    sb.style.opacity = p.toFixed(3); sb.style.visibility = s ? 'visible' : 'hidden';
  } else sb.style.visibility = 'hidden';

  // cursor
  const [x, y] = cursorPos(t), shape = shapeAt(t), sz = L.cur;
  const c = $('cursor');
  let squeeze = 0; CLICKS.forEach(k => { squeeze = Math.max(squeeze, bump(env(t, k.t - 0.03, k.t + 0.13)), k.dbl ? bump(env(t, k.t + 0.08, k.t + 0.24)) : 0); });
  const cv = env(t, 0.6, 0.9) * (1 - env(t, 20.0, 20.7));
  c.style.opacity = cv.toFixed(3); c.style.visibility = cv > 0 ? 'visible' : 'hidden';
  c.style.transform = `translate(${x.toFixed(2)}px,${y.toFixed(2)}px) scale(${(1 - 0.14 * squeeze).toFixed(3)})`;
  ['arrow', 'hand', 'beam'].forEach(n => {
    const s = $('cur-' + n).style, k = sz / 24 * (n === 'beam' ? 1.05 : 1);
    s.display = n === shape ? 'block' : 'none';
    s.width = s.height = px(24 * k); s.left = px(-HOT[n][0] * k); s.top = px(-HOT[n][1] * k);
    s.filter = 'drop-shadow(0 2px 4px rgba(0,0,0,.45))';
  });
  // click rings (180–260 ms)
  let html = '';
  CLICKS.forEach(k => [k.t].concat(k.dbl ? [k.t + 0.11] : []).forEach(tc => {
    const u = (t - tc) / 0.24; if (u < 0 || u > 1) return;
    const r = (6 + 22 * eOut(u)) * (sz / 30), a = 0.55 * Math.pow(1 - u, 1.5);
    html += `<div class="ring" style="left:${(x - r).toFixed(2)}px;top:${(y - r).toFixed(2)}px;width:${(2 * r).toFixed(2)}px;height:${(2 * r).toFixed(2)}px;opacity:${a.toFixed(3)};border-width:${(1.5 * sz / 30).toFixed(2)}px"></div>`;
  }));
  $('rings').innerHTML = html;
}

// ───────── public API ─────────
let ready = null;
window.seek = async t => {
  await ready;
  t = clamp(t, 0, T_END);
  scene(t);
  applyCam(camera(t));
  hud(t);
  return t;
};
window.getEvents = async () => { await ready; return events(); };
window.DURATION = T_END;
window.getSubs = () => SUBS;
ready = (async () => {
  await document.fonts.load('600 16px Onest'); await document.fonts.ready;
  init(); MK = MORPH();
})();
if (!Q.has('render')) {               // interactive preview (not used by the renderer)
  const sp = Q.get('t');
  if (sp) window.seek(+sp);
  else { const t0 = performance.now(); const loop = () => { window.seek(((performance.now() - t0) / 1000) % T_END).then(() => requestAnimationFrame(loop)); }; loop(); }
}
