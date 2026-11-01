// Smetra promo: a 3D phone with the real interface on full black, rendered frame by frame.
import { THREE, createStage } from './phone.js';

const W = 1920, H = 1080, FPS = 30;
const out = document.getElementById('out'), ctx = out.getContext('2d');
const { gl, scene, camera, phone, screenMat, textures, screenTexture, setDrops } = createStage(W, H);

// ── Timeline ──
const ease = t => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
const easeOut = t => 1 - Math.pow(1 - t, 3);
const lerp = (a, b, t) => a + (b - a) * t;
const lerpV = (a, b, t) => a.map((v, i) => lerp(v, b[i], t));
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
// Each shot flies the phone through a fixed camera: from → mid → to (position, rotation).
// Speed ramps fast → nearly still at mid → fast; captions show while it slows down.
const FLY = 2.7;
const SHOTS = [
  { screen: 'quote', from: [[-2.5, -1.1, -0.6], [0.3, 0.9, 0.4]], mid: [[0.3, 0, 0], [0.05, -0.26, 0.03]], to: [[2.7, 1.3, -0.4], [-0.2, -0.95, -0.3]], caption: 'Смета за минуты', side: 'left' },
  { screen: 'assistant', from: [[2.6, 0.7, -0.3], [0, -1.0, -0.4]], mid: [[-0.3, 0, 0], [0.04, 0.28, -0.04]], to: [[-2.7, -0.6, -0.5], [0.1, 1.1, 0.3]], caption: 'ИИ-ассистент считает объёмы', side: 'right' },
  { screen: 'object', from: [[0.3, 2.3, -0.4], [-0.9, 0.2, 0.3]], mid: [[0.3, 0, 0], [-0.08, -0.22, 0.05]], to: [[0.2, -2.4, -0.3], [0.9, -0.1, -0.2]], caption: 'Объекты и замеры', side: 'left' },
  { screen: 'finance', from: [[2.3, -2.0, -0.5], [0.6, -0.6, 0.5]], mid: [[-0.3, 0, 0], [0.06, 0.26, 0]], to: [[-2.4, 2.0, -0.5], [-0.6, 0.7, -0.4]], caption: 'Деньги по каждому заказу', side: 'right' },
  { screen: 'calculators', from: [[0.4, 0.1, -7], [0.2, 3.3, 0.3]], mid: [[0.3, 0, 0], [0, -0.22, 0]], to: [[2.9, -0.2, 0.9], [0.1, -1.2, -0.2]], caption: 'Калькуляторы материалов', side: 'left' },
  { screen: 'quotes', from: [[-2.6, -0.4, -0.4], [0.2, 1.0, 0.3]], mid: [[-0.3, 0, 0], [0.03, 0.3, 0.02]], to: [[2.7, 0.4, -0.4], [-0.1, -1.0, -0.2]], caption: 'Клиент согласует по ссылке', side: 'right' },
  { screen: 'dashboard', settle: true, from: [[2.4, -2.0, -0.5], [0.5, -0.9, 0.4]], mid: [[0.78, -0.02, 0], [0.03, -0.32, 0.01]], title: 'СМЕТЫ · КЛИЕНТЫ · ДЕНЬГИ', dur: 3.4 },
];
let clock = 0;
for (const shot of SHOTS) { shot.t = [clock, clock + (shot.dur || FLY)]; clock = shot.t[1]; }
const LOGO = [clock, clock + 3.2];

// ── Compositing: depth-of-field band, vignette, type ──
const blurC = document.createElement('canvas'); blurC.width = W; blurC.height = H; const bctx = blurC.getContext('2d');
function dof(band) {
  if (!band) return;
  const [cy, half, angle] = band;
  bctx.globalCompositeOperation = 'source-over'; bctx.clearRect(0, 0, W, H);
  bctx.filter = 'blur(9px)'; bctx.drawImage(gl.domElement, 0, 0); bctx.filter = 'none';
  // Keep the blur only outside the focus band.
  bctx.globalCompositeOperation = 'destination-in';
  bctx.save(); bctx.translate(W / 2, H * cy); bctx.rotate(angle * Math.PI / 180);
  const g = bctx.createLinearGradient(0, -H * (half + 0.32), 0, H * (half + 0.32));
  const a = 0.32 / (2 * (half + 0.32));
  g.addColorStop(0, 'rgba(0,0,0,1)'); g.addColorStop(a, 'rgba(0,0,0,0.15)'); g.addColorStop(0.5 - half / (2 * (half + 0.32)) + 0.02, 'rgba(0,0,0,0)');
  g.addColorStop(0.5 + half / (2 * (half + 0.32)) - 0.02, 'rgba(0,0,0,0)'); g.addColorStop(1 - a, 'rgba(0,0,0,0.15)'); g.addColorStop(1, 'rgba(0,0,0,1)');
  bctx.fillStyle = g; bctx.fillRect(-W * 1.5, -H * 1.5, W * 3, H * 3); bctx.restore();
  ctx.drawImage(blurC, 0, 0);
}
function vignette() {
  const g = ctx.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 1.05);
  g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,0.85)'); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
}
function caption(text, k, side) {
  if (!text || k <= 0) return;
  ctx.save(); ctx.globalAlpha = k; ctx.fillStyle = '#fff'; ctx.font = '500 30px Onest'; ctx.letterSpacing = '6px';
  ctx.textBaseline = 'alphabetic'; ctx.textAlign = side === 'right' ? 'right' : 'left';
  ctx.fillText(text.toUpperCase(), side === 'right' ? W - 96 : 96, H - 96 + (1 - k) * 14); ctx.restore();
}
function title(text, t) {
  // Letters arrive one by one from a soft blur, like the reference "AI MARKET".
  ctx.save(); ctx.fillStyle = '#fff'; ctx.font = '500 46px Onest'; ctx.letterSpacing = '9px'; ctx.textBaseline = 'middle';
  let x = 150; const y = H / 2;
  [...text].forEach((ch, i) => {
    const k = clamp((t - 0.35 - i * 0.045) / 0.5); const e = easeOut(k);
    ctx.globalAlpha = e; ctx.filter = `blur(${(1 - e) * 10}px)`; ctx.fillText(ch, x, y + (1 - e) * 10);
    x += ctx.measureText(ch).width + 9;
  });
  ctx.restore();
}
function logo(t) {
  // Brand mark: four document lines slide in, then the mark gives way to the wordmark.
  const bars = [[270, 0], [210, 1], [270, 2], [130, 3]];
  const s = 0.62, cx = W / 2, cy = H / 2;
  const markOut = easeOut(clamp((t - 1.35) / 0.45)), word = easeOut(clamp((t - 1.6) / 0.7));
  ctx.save(); ctx.fillStyle = '#fff';
  ctx.globalAlpha = 1 - markOut;
  bars.forEach(([w, i]) => {
    const k = easeOut(clamp((t - 0.1 - i * 0.12) / 0.5));
    const x = cx - 135 * s - (1 - k) * 40, y = cy - 104 * s + i * 66 * s;
    ctx.globalAlpha = (1 - markOut) * k; ctx.beginPath(); ctx.roundRect(x, y, Math.max(30 * s, w * s * k), 30 * s, 15 * s); ctx.fill();
  });
  ctx.globalAlpha = word; ctx.font = '600 120px Onest'; ctx.letterSpacing = '-5px'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.filter = `blur(${(1 - word) * 12}px)`; ctx.fillText('сметра.', cx, cy - 6 + (1 - word) * 12); ctx.filter = 'none';
  const url = easeOut(clamp((t - 2.25) / 0.6)); ctx.globalAlpha = url * 0.6; ctx.font = '400 28px Onest'; ctx.letterSpacing = '4px';
  ctx.fillText('smetra.online', cx, cy + 96);
  ctx.restore();
}

// Fast at both ends, nearly still in the middle.
const ramp = u => { const v = 2 * u - 1, a = 0.12; return 0.5 + 0.5 * (a * v + (1 - a) * v * v * v); };
const speedAt = u => { const v = 2 * u - 1; return 0.12 + 0.88 * 3 * v * v; };
const settle = u => 1 - Math.pow(1 - u, 4);
function place(shot, k) {
  let p, r;
  if (shot.settle) { const e = settle(k); p = lerpV(shot.from[0], shot.mid[0], e); r = lerpV(shot.from[1], shot.mid[1], e); }
  else {
    const s = ramp(k), a = s < 0.5 ? shot.from : shot.mid, b = s < 0.5 ? shot.mid : shot.to, q = s < 0.5 ? s * 2 : (s - 0.5) * 2;
    p = lerpV(a[0], b[0], q); r = lerpV(a[1], b[1], q);
  }
  phone.position.set(...p); phone.rotation.set(...r); phone.updateMatrixWorld();
  camera.position.set(0, 0, 2.15); camera.up.set(0, 1, 0); camera.lookAt(0, 0, 0);
  camera.fov = 30; camera.updateProjectionMatrix();
}

const acc = document.createElement('canvas'); acc.width = W; acc.height = H; const actx = acc.getContext('2d');
window.renderFrame = function (frame) {
  const t = frame / FPS;
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  if (t >= LOGO[0]) { logo(t - LOGO[0]); return; }
  const shot = SHOTS.find(s => t >= s.t[0] && t < s.t[1]) || SHOTS[SHOTS.length - 1];
  const len = shot.t[1] - shot.t[0], k = (t - shot.t[0]) / len;
  if (screenMat.map !== textures[shot.screen]) { screenMat.map = textures[shot.screen]; screenMat.needsUpdate = true; setDrops(26, 11 + SHOTS.indexOf(shot) * 17); }
  // Motion blur on the fast stretches: average a few renders across the shutter.
  const fast = shot.settle ? k < 0.25 : speedAt(k) > 1.2, subs = fast ? 3 : 1;
  actx.clearRect(0, 0, W, H);
  for (let j = 0; j < subs; j++) {
    const kk = Math.min(1, k + (j / subs) * (0.5 / FPS) / len);
    place(shot, kk); gl.render(scene, camera);
    actx.globalAlpha = 1 / (j + 1); actx.drawImage(gl.domElement, 0, 0);
  }
  actx.globalAlpha = 1;
  ctx.drawImage(acc, 0, 0);
  vignette();
  const first = SHOTS.indexOf(shot) === 0, fadeIn = first ? clamp(t / 0.4) : 1;
  const fadeOut = shot.settle ? clamp((shot.t[1] - t) / 0.35) : 1;
  ctx.fillStyle = `rgba(0,0,0,${1 - Math.min(fadeIn, fadeOut)})`; ctx.fillRect(0, 0, W, H);
  // Captions while the phone is nearly still.
  if (shot.caption) caption(shot.caption, clamp(1 - Math.abs(k - 0.5) / 0.22) * 1.6 > 1 ? 1 : clamp(1 - Math.abs(k - 0.5) / 0.22) * 1.6, shot.side);
  if (shot.title) { ctx.save(); ctx.globalAlpha = fadeOut; title(shot.title, t - shot.t[0] - 0.4); ctx.restore(); }
};
const DURATION = LOGO[1];
window.FRAMES = Math.round(DURATION * FPS);

(async () => {
  await document.fonts.load('600 40px Onest'); await document.fonts.load('500 40px Onest'); await document.fonts.load('400 40px Onest');
  for (const name of new Set(SHOTS.map(s => s.screen))) textures[name] = await screenTexture(name);
  window.READY = true;
})();
