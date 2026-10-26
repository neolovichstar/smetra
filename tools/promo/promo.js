// Smetra promo: a 3D phone with the real interface on full black, rendered frame by frame.
import { THREE, createStage } from './phone.js';

const W = 1920, H = 1080, FPS = 30, DURATION = 20;
const out = document.getElementById('out'), ctx = out.getContext('2d');
const { gl, scene, camera, phone, screenMat, textures, screenTexture } = createStage(W, H);

// ── Timeline ──
const ease = t => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
const easeOut = t => 1 - Math.pow(1 - t, 3);
const lerp = (a, b, t) => a + (b - a) * t;
const lerpV = (a, b, t) => a.map((v, i) => lerp(v, b[i], t));
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
// Each shot: screen, phone rotation/position from→to, camera position and look target from→to,
// fov, focus band (centre y 0..1, half-height, angle deg), caption.
const SHOTS = [
  { t: [0, 3.6], screen: 'quote', rot: [[-0.95, 0.42, 0.62], [-0.9, 0.3, 0.55]], pos: [[0, 0, 0], [0, 0, 0]],
    cam: [[0.25, -0.55, 1.05], [0.05, -0.15, 0.95]], look: [[0.05, -0.32, 0], [-0.02, 0.18, 0]], fov: 26, focus: [0.52, 0.17, -14], caption: 'Смета за минуты' },
  { t: [3.6, 7.2], screen: 'assistant', rot: [[0.12, -0.62, -0.2], [0.05, -0.5, -0.14]], pos: [[0, 0, 0], [0, 0, 0]],
    cam: [[0.55, 0.42, 1.25], [0.45, 0.1, 1.15]], look: [[0.02, 0.36, 0], [0.0, 0.02, 0]], fov: 24, focus: [0.48, 0.2, 10], caption: 'ИИ-ассистент считает объёмы' },
  { t: [7.2, 10.2], screen: 'object', world: true, rot: [[0.18, 1.62, -0.12], [0.06, 0.3, -0.05]], pos: [[0, -0.05, 0], [0, 0, 0]],
    cam: [[0.12, 0.42, 2.25], [0.05, 0.3, 1.95]], look: [[0, 0.18, 0], [0, 0.12, 0]], fov: 30, focus: [0.42, 0.3, -6], caption: 'Объекты и замеры' },
  { t: [10.2, 13.4], screen: 'finance', rot: [[-0.7, -0.35, -0.5], [-0.72, -0.25, -0.42]], pos: [[0, 0, 0], [0, 0, 0]],
    cam: [[-0.35, -0.6, 1.0], [-0.2, -0.38, 0.92]], look: [[-0.02, 0.38, 0], [0.02, 0.2, 0]], fov: 25, focus: [0.5, 0.17, 12], caption: 'Деньги по каждому заказу' },
  { t: [13.4, 16.8], screen: 'dashboard', rot: [[0.04, -0.62, 0.02], [0.02, -0.34, 0.0]], pos: [[1.02, -0.02, 0], [1.02, 0, 0]],
    cam: [[0, 0, 4.6], [0, 0, 4.3]], look: [[0, 0, 0], [0, 0, 0]], fov: 30, focus: null, title: 'СМЕТЫ · КЛИЕНТЫ · ДЕНЬГИ' },
];
const LOGO = [16.8, 20];

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
function caption(text, k) {
  if (!text || k <= 0) return;
  ctx.save(); ctx.globalAlpha = k; ctx.fillStyle = '#fff'; ctx.font = '500 30px Onest'; ctx.letterSpacing = '6px';
  ctx.textBaseline = 'alphabetic'; ctx.fillText(text.toUpperCase(), 96, H - 96 + (1 - k) * 14); ctx.restore();
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

function place(shot, k) {
  const e = ease(k);
  const [rx, ry, rz] = lerpV(shot.rot[0], shot.rot[1], e);
  phone.rotation.set(rx, ry, rz);
  phone.position.set(...lerpV(shot.pos[0], shot.pos[1], e));
  phone.updateMatrixWorld();
  // Camera offset is given in the phone's frame so close-ups stay on the screen.
  const look = new THREE.Vector3(...lerpV(shot.look[0], shot.look[1], e));
  const camLocal = new THREE.Vector3(...lerpV(shot.cam[0], shot.cam[1], e));
  if (shot.focus && !shot.world) { look.applyMatrix4(phone.matrixWorld); camLocal.applyMatrix4(phone.matrixWorld); }
  camera.position.copy(camLocal); camera.up.set(0, 1, 0); camera.lookAt(look);
  camera.fov = shot.fov; camera.updateProjectionMatrix();
}

window.renderFrame = function (frame) {
  const t = frame / FPS;
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  if (t >= LOGO[0]) { logo(t - LOGO[0]); return; }
  const shot = SHOTS.find(s => t >= s.t[0] && t < s.t[1]) || SHOTS[SHOTS.length - 1];
  const k = (t - shot.t[0]) / (shot.t[1] - shot.t[0]);
  screenMat.map = textures[shot.screen]; screenMat.needsUpdate = true;
  place(shot, k);
  gl.render(scene, camera);
  ctx.drawImage(gl.domElement, 0, 0);
  dof(shot.focus);
  vignette();
  // Fade through black between shots; the last shot fades into the logo.
  const fadeIn = clamp((t - shot.t[0]) / 0.35), fadeOut = clamp((shot.t[1] - t) / 0.3);
  ctx.fillStyle = `rgba(0,0,0,${1 - Math.min(fadeIn, fadeOut)})`; ctx.fillRect(0, 0, W, H);
  if (shot.caption) caption(shot.caption, Math.min(clamp((t - shot.t[0] - 0.5) / 0.5), clamp((shot.t[1] - t - 0.2) / 0.4)));
  if (shot.title) { ctx.save(); ctx.globalAlpha = Math.min(1, fadeOut); title(shot.title, t - shot.t[0]); ctx.restore(); }
};
window.FRAMES = DURATION * FPS;

(async () => {
  await document.fonts.load('600 40px Onest'); await document.fonts.load('500 40px Onest'); await document.fonts.load('400 40px Onest');
  for (const name of new Set(SHOTS.map(s => s.screen))) textures[name] = await screenTexture(name);
  window.READY = true;
})();
