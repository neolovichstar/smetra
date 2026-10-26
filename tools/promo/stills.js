// Ten 1080×1350 promo stills: the 3D iPhone with drops on the glass, real screens, a few words.
import { THREE, createStage } from './phone.js';

const W = 1080, H = 1350;
const out = document.getElementById('out'), ctx = out.getContext('2d');
const { gl, camera, phone, screenMat, setDrops, screenTexture } = createStage(W, H);

// cam/look are world coordinates unless `close` is set: then they are in the phone's own frame,
// so the camera hugs the screen. focus: [centre y 0..1, half-height, angle deg] or null.
export const STILLS = [
  { screen: 'dashboard', rot: [0.06, -0.42, 0.04], pos: [0.1, 0.2, 0], cam: [0, 0, 4.0], look: [0, 0.06, 0], fov: 32,
    kicker: 'Сметы · клиенты · деньги', title: 'Вся работа\nв одном телефоне', sub: 'Для мастеров, бригад и строительных компаний' },
  { screen: 'quote', close: true, rot: [-0.95, 0.38, 0.6], pos: [0, 0, 0], cam: [0.16, -0.5, 1.5], look: [0.0, 0.02, 0], fov: 30, focus: [0.42, 0.24, -16],
    kicker: 'Смета', title: 'Смета за минуты', sub: 'Позиции, объёмы и итог в одном экране' },
  { screen: 'assistant', rot: [0.1, 0.55, -0.12], pos: [-0.05, 0.18, 0], cam: [0, 0, 3.2], look: [0, 0.02, 0], fov: 32, focus: [0.42, 0.34, 8],
    kicker: 'ИИ-ассистент', title: 'Опишите работы —\nон посчитает объёмы', sub: 'Итог пересчитывается автоматически' },
  { screen: 'object', rot: [-1.05, 0.0, 0.42], pos: [0, 0.12, 0], cam: [0, 0.25, 2.55], look: [0, 0.05, 0], fov: 34, focus: [0.4, 0.26, -18],
    kicker: 'Объекты', title: 'Замеры по каждому\nпомещению', sub: 'Площади, формулы и план стоимости' },
  { screen: 'finance', close: true, rot: [-0.7, -0.3, -0.45], pos: [0, 0, 0], cam: [-0.2, -0.5, 1.45], look: [0, 0.2, 0], fov: 30, focus: [0.42, 0.24, 14],
    kicker: 'Финансы', title: 'Деньги по заказам', sub: 'Получено, расходы и что ещё к оплате' },
  { screen: 'quotes', rot: [0.04, -0.62, 0.1], pos: [0.14, 0.2, 0], cam: [0, 0, 3.6], look: [0, 0.05, 0], fov: 32,
    kicker: 'Сметы', title: 'Статусы видны сразу', sub: 'Черновик, отправлена, согласована' },
  { screen: 'calculators', rot: [-0.22, 0.32, 0.28], pos: [0, 0.2, 0], cam: [0, 0, 3.4], look: [0, 0.04, 0], fov: 32, focus: [0.4, 0.34, 0],
    kicker: 'Калькуляторы', title: 'Плитка, ламинат,\nкраска, штукатурка', sub: 'С запасом на подрезку и количеством упаковок' },
  { screen: 'projects', rot: [-0.55, 0.62, 0.35], pos: [0, 0.2, 0], cam: [0, 0.1, 3.2], look: [0, 0.08, 0], fov: 32, focus: [0.38, 0.3, 20],
    kicker: 'Заказы', title: 'От согласования\nдо оплаты', sub: 'Этапы, задачи и поступления по заказу' },
  { screen: 'quote', rot: [0.12, 1.12, -0.06], pos: [0, 0.2, 0], cam: [0, 0.05, 3.8], look: [0, 0.06, 0], fov: 32,
    kicker: 'Клиенту', title: 'Согласование\nпо ссылке', sub: 'Без регистрации и пароля' },
  { screen: 'dashboard', rot: [-0.62, -0.3, -0.26], pos: [0, -0.62, 0], cam: [0, 0.1, 3.9], look: [0, -0.1, 0], fov: 32, brand: true },
];

const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
function place(s) {
  phone.rotation.set(...s.rot); phone.position.set(...s.pos); phone.updateMatrixWorld();
  const cam = new THREE.Vector3(...s.cam), look = new THREE.Vector3(...s.look);
  if (s.close) { cam.applyMatrix4(phone.matrixWorld); look.applyMatrix4(phone.matrixWorld); }
  camera.aspect = W / H; camera.fov = s.fov; camera.position.copy(cam); camera.lookAt(look); camera.updateProjectionMatrix();
}
const blurC = document.createElement('canvas'); blurC.width = W; blurC.height = H; const bctx = blurC.getContext('2d');
function dof(band) {
  if (!band) return;
  const [cy, half, angle] = band, span = half + 0.3;
  bctx.globalCompositeOperation = 'source-over'; bctx.clearRect(0, 0, W, H);
  bctx.filter = 'blur(7px)'; bctx.drawImage(gl.domElement, 0, 0); bctx.filter = 'none';
  bctx.globalCompositeOperation = 'destination-in';
  bctx.save(); bctx.translate(W / 2, H * cy); bctx.rotate(angle * Math.PI / 180);
  const g = bctx.createLinearGradient(0, -H * span, 0, H * span), edge = 0.3 / (2 * span), mid = half / (2 * span);
  g.addColorStop(0, '#000'); g.addColorStop(edge, 'rgba(0,0,0,.2)'); g.addColorStop(clamp(0.5 - mid), 'rgba(0,0,0,0)');
  g.addColorStop(clamp(0.5 + mid), 'rgba(0,0,0,0)'); g.addColorStop(1 - edge, 'rgba(0,0,0,.2)'); g.addColorStop(1, '#000');
  bctx.fillStyle = g; bctx.fillRect(-W * 2, -H * 2, W * 4, H * 4); bctx.restore();
  ctx.drawImage(blurC, 0, 0);
}
function shade() {
  // Soft vignette and a dark floor for the type.
  const v = ctx.createRadialGradient(W / 2, H * 0.42, H * 0.3, W / 2, H * 0.45, H * 0.85);
  v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,.8)'); ctx.fillStyle = v; ctx.fillRect(0, 0, W, H);
  const f = ctx.createLinearGradient(0, H * 0.62, 0, H); f.addColorStop(0, 'rgba(0,0,0,0)'); f.addColorStop(0.55, 'rgba(0,0,0,.92)'); f.addColorStop(1, '#000');
  ctx.fillStyle = f; ctx.fillRect(0, H * 0.62, W, H * 0.38);
}
function type(s) {
  const L = 84;
  ctx.fillStyle = '#fff'; ctx.textBaseline = 'alphabetic';
  if (s.brand) {
    ctx.textAlign = 'center'; ctx.font = '600 112px Onest'; ctx.letterSpacing = '-5px'; ctx.fillText('сметра.', W / 2, 330);
    ctx.globalAlpha = 0.6; ctx.font = '400 24px Onest'; ctx.letterSpacing = '5px'; ctx.fillText('SMETRA.ONLINE', W / 2, 392);
    ctx.globalAlpha = 1; ctx.textAlign = 'left'; return;
  }
  ctx.globalAlpha = 0.55; ctx.font = '500 18px Onest'; ctx.letterSpacing = '4px';
  const lines = s.title.split('\n'), base = H - 132 - (lines.length - 1) * 52;
  ctx.fillText(s.kicker.toUpperCase(), L, base - 62);
  ctx.globalAlpha = 1; ctx.font = '600 46px Onest'; ctx.letterSpacing = '-1.4px';
  lines.forEach((line, i) => ctx.fillText(line, L, base + i * 52));
  ctx.globalAlpha = 0.6; ctx.font = '400 21px Onest'; ctx.letterSpacing = '0px'; ctx.fillText(s.sub, L, H - 84);
  ctx.globalAlpha = 1;
}

window.renderStill = async (i) => {
  const s = STILLS[i];
  screenMat.map = await screenTexture(s.screen); screenMat.needsUpdate = true;
  setDrops(42, 7 + i * 13);
  place(s); gl.render(phone.parent, camera);
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  ctx.drawImage(gl.domElement, 0, 0);
  dof(s.focus); shade(); type(s);
};
window.STILL_COUNT = STILLS.length;
(async () => { await document.fonts.load('600 40px Onest'); await document.fonts.load('500 20px Onest'); await document.fonts.load('400 20px Onest'); window.READY = true; })();
