// Shared 3D stage for the promo video and stills: a black-titanium iPhone on full black,
// the real Smetra interface on its OLED panel, optional water drops on the cover glass.
import * as THREE from '../../apps/web/vendor/three-0.170.0.module.min.js';
import { RoundedBoxGeometry } from '../../apps/web/vendor/three-rounded-box-0.170.0.js';
import { RoomEnvironment } from '../../apps/web/vendor/three-room-environment-0.170.0.js';

export { THREE };
export function createStage(W, H) {
  const gl = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
  gl.setPixelRatio(1); gl.setSize(W, H);
  gl.outputColorSpace = THREE.SRGBColorSpace;
  gl.toneMapping = THREE.ACESFilmicToneMapping; gl.toneMappingExposure = 1.05;
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
  const pmrem = new THREE.PMREMGenerator(gl);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  const camera = new THREE.PerspectiveCamera(30, W / H, 0.01, 50);

  // ── Phone: iPhone Pro proportions, black titanium, flat sides with a soft edge ──
  const PW = 0.76, PH = 1.56, PD = 0.082, R = 0.125, BEVEL = 0.007;
  const phone = new THREE.Group(); scene.add(phone);
  const roundedRect = (w, h, r) => { const s = new THREE.Shape(); s.moveTo(-w / 2 + r, -h / 2); s.lineTo(w / 2 - r, -h / 2); s.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r); s.lineTo(w / 2, h / 2 - r); s.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2); s.lineTo(-w / 2 + r, h / 2); s.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r); s.lineTo(-w / 2, -h / 2 + r); s.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2); return s; };
  const frameMat = new THREE.MeshStandardMaterial({ color: 0x18191c, metalness: 1, roughness: 0.3, envMapIntensity: 1.35 });
  const frameGeo = new THREE.ExtrudeGeometry(roundedRect(PW - 2 * BEVEL, PH - 2 * BEVEL, R - BEVEL), { depth: PD - 2 * BEVEL, bevelEnabled: true, bevelThickness: BEVEL, bevelSize: BEVEL, bevelSegments: 5, curveSegments: 24 });
  frameGeo.translate(0, 0, -(PD - 2 * BEVEL) / 2);
  phone.add(new THREE.Mesh(frameGeo, frameMat));
  // Front: one sheet of black glass, a thin bezel, the OLED panel.
  const frontGlass = new THREE.Mesh(new THREE.ShapeGeometry(roundedRect(PW - 0.01, PH - 0.01, R - 0.005), 24),
    new THREE.MeshPhysicalMaterial({ color: 0x000000, roughness: 0.04, metalness: 0, clearcoat: 1, clearcoatRoughness: 0.03, envMapIntensity: 0.9 }));
  frontGlass.position.z = PD / 2 + 0.0008; phone.add(frontGlass);
  const SW = PW - 0.036, SH = PH - 0.036;
  const screenGeo = new THREE.ShapeGeometry(roundedRect(SW, SH, R - 0.018), 24);
  { const uv = screenGeo.attributes.uv, pos = screenGeo.attributes.position; for (let i = 0; i < uv.count; i++) uv.setXY(i, pos.getX(i) / SW + 0.5, pos.getY(i) / SH + 0.5); }
  const screenMat = new THREE.MeshBasicMaterial({ toneMapped: false });
  const screen = new THREE.Mesh(screenGeo, screenMat); screen.position.z = PD / 2 + 0.0016; phone.add(screen);
  // A faint sky reflection on the cover glass, no tint over the blacks.
  const gloss = new THREE.Mesh(screenGeo, new THREE.MeshPhysicalMaterial({ color: 0x000000, transparent: true, opacity: 0.22, roughness: 0.02, metalness: 0, clearcoat: 1, envMapIntensity: 1.6, depthWrite: false, blending: THREE.AdditiveBlending }));
  gloss.position.z = PD / 2 + 0.0024; phone.add(gloss);
  const island = new THREE.Mesh(new THREE.ShapeGeometry(roundedRect(0.19, 0.054, 0.027), 12), new THREE.MeshBasicMaterial({ color: 0x000000 }));
  island.position.set(0, SH / 2 - 0.05, PD / 2 + 0.003); phone.add(island);
  // Buttons: action and volume on the left, side button on the right.
  for (const [y, h, side] of [[0.36, 0.17, 1], [0.5, 0.06, -1], [0.36, 0.1, -1], [0.22, 0.1, -1]]) {
    const b = new THREE.Mesh(new RoundedBoxGeometry(0.01, h, 0.03, 3, 0.004), frameMat);
    b.position.set(side * (PW / 2 + 0.002), y, 0); phone.add(b);
  }
  // Back: matte black glass and the square camera plateau with three lenses.
  const back = new THREE.Mesh(new THREE.ShapeGeometry(roundedRect(PW - 0.01, PH - 0.01, R - 0.005), 24),
    new THREE.MeshPhysicalMaterial({ color: 0x0b0b0c, roughness: 0.55, metalness: 0, clearcoat: 0.3, envMapIntensity: 0.6 }));
  back.rotation.y = Math.PI; back.position.z = -PD / 2 - 0.0008; phone.add(back);
  const plateau = new THREE.Mesh(new RoundedBoxGeometry(0.31, 0.31, 0.016, 6, 0.07), new THREE.MeshPhysicalMaterial({ color: 0x0d0d0e, roughness: 0.2, clearcoat: 1, envMapIntensity: 0.9 }));
  const PX = PW / 2 - 0.2, PY = PH / 2 - 0.2; plateau.position.set(PX, PY, -PD / 2 - 0.008); phone.add(plateau);
  const ringMat = new THREE.MeshStandardMaterial({ color: 0x1b1c1f, metalness: 1, roughness: 0.25 });
  const lensMat = new THREE.MeshPhysicalMaterial({ color: 0x02030a, roughness: 0.02, clearcoat: 1, metalness: 0.3, envMapIntensity: 1.4, sheen: 1, sheenColor: new THREE.Color(0x2a3a6a) });
  for (const [x, y] of [[0.062, 0.062], [0.062, -0.062], [-0.062, 0]]) {
    const ring = new THREE.Mesh(new THREE.CylinderGeometry(0.052, 0.052, 0.022, 48), ringMat);
    ring.rotation.x = Math.PI / 2; ring.position.set(PX - x, PY + y, -PD / 2 - 0.024); phone.add(ring);
    const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.038, 0.038, 0.024, 48), lensMat);
    lens.rotation.x = Math.PI / 2; lens.position.set(PX - x, PY + y, -PD / 2 - 0.026); phone.add(lens);
  }
  const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(-2, 3, 2); scene.add(key);
  const rim = new THREE.DirectionalLight(0x9cc4ff, 1.4); rim.position.set(3, -1, -2); scene.add(rim);

  // ── Screens: real interface with a status bar ──
  const loadImage = src => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = src; });
  const textures = {};
  async function screenTexture(name) {
    const img = await loadImage('scr/' + name + '.png');
    const c = document.createElement('canvas'); c.width = 1170; c.height = 2532;
    const x = c.getContext('2d'); x.fillStyle = '#000'; x.fillRect(0, 0, c.width, c.height);
    x.drawImage(img, 0, 132, 1170, 2400);
    x.fillStyle = '#fff'; x.font = '600 46px Onest'; x.textBaseline = 'middle'; x.fillText('9:41', 96, 72);
    for (let i = 0; i < 4; i++) x.fillRect(880 + i * 20, 84 - (i + 1) * 9, 13, (i + 1) * 9);
    x.strokeStyle = '#fff'; x.lineWidth = 4; x.beginPath(); x.roundRect(980, 52, 82, 40, 12); x.stroke(); x.fillRect(987, 59, 60, 26); x.fillRect(1066, 64, 6, 16);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
  }


  // Water on the glass: a transparent layer of drops just above the screen.
  const dropsMat = new THREE.MeshBasicMaterial({ transparent: true, toneMapped: false, depthWrite: false, opacity: 0 });
  const drops = new THREE.Mesh(screenGeo, dropsMat); drops.position.z = PD / 2 + 0.003; phone.add(drops);
  // Real water: refracting caps of water on the cover glass (transmission bends the screen beneath).
  const water = new THREE.Group(); water.position.z = PD / 2 + 0.0026; phone.add(water);
  const waterMat = new THREE.MeshPhysicalMaterial({ color: 0xffffff, metalness: 0, roughness: 0, transmission: 1, ior: 1.33, thickness: 0.006,
    specularIntensity: 0.8, envMapIntensity: 1.1 });
  const cap = new THREE.SphereGeometry(1, 40, 20, 0, Math.PI * 2, 0, Math.PI / 2);
  cap.rotateX(Math.PI / 2);
  function setDrops(count, seed) {
    water.clear();
    let s = seed; const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
    const placed = [];
    for (let n = 0, tries = 0; n < count && tries < count * 80; tries++) {
      const r = 0.004 + 0.024 * Math.pow(rnd(), 2.2), x = (rnd() - 0.5) * (SW - 2 * r), y = (rnd() - 0.5) * (SH - 2 * r);
      if (placed.some(([a, b, q]) => (a - x) ** 2 + (b - y) ** 2 < (r + q + 0.004) ** 2)) continue;
      placed.push([x, y, r]); n++;
      const d = new THREE.Mesh(cap, waterMat);
      // Larger drops sag a little under gravity: taller than wide, flatter on top.
      const sag = r > 0.02 ? 1 + rnd() * 0.25 : 1 + rnd() * 0.08;
      d.scale.set(r, r * sag, r * (0.26 + rnd() * 0.1)); d.position.set(x, y, 0);
      water.add(d);
    }
  }
  return { gl, scene, camera, phone, screenMat, dropsMat, textures, screenTexture, setDrops, SW, SH };
}

// Drops for the cover glass: dark lower body, bright rim below, a highlight above.
export function dropsTexture(count = 46, seed = 1) {
  let s = seed; const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
  const c = document.createElement('canvas'); c.width = 1170; c.height = 2532;
  const g = c.getContext('2d'), placed = [];
  for (let n = 0, tries = 0; n < count && tries < count * 60; tries++) {
    const r = 6 + 34 * Math.pow(rnd(), 2.2), x = r + rnd() * (c.width - 2 * r), y = r + rnd() * (c.height - 2 * r), k = 0.9 + rnd() * 0.3;
    if (placed.some(([a, b, q]) => (a - x) ** 2 + (b - y) ** 2 < (r + q + 6) ** 2)) continue;
    placed.push([x, y, r]); n++;
    const ry = r * k;
    g.fillStyle = 'rgba(0,0,0,.35)'; g.beginPath(); g.ellipse(x, y + ry * 0.15, r, ry, 0, 0, Math.PI * 2); g.fill();
    const body = g.createRadialGradient(x, y + ry * 0.25, 0, x, y + ry * 0.1, Math.max(r, ry));
    body.addColorStop(0, 'rgba(255,255,255,.06)'); body.addColorStop(0.6, 'rgba(255,255,255,.02)');
    body.addColorStop(0.86, 'rgba(255,255,255,.12)'); body.addColorStop(1, 'rgba(255,255,255,.34)');
    g.fillStyle = body; g.beginPath(); g.ellipse(x, y, r, ry, 0, 0, Math.PI * 2); g.fill();
    const rim = g.createLinearGradient(0, y - ry, 0, y + ry);
    rim.addColorStop(0, 'rgba(255,255,255,.04)'); rim.addColorStop(0.55, 'rgba(255,255,255,.1)'); rim.addColorStop(1, 'rgba(255,255,255,.6)');
    g.strokeStyle = rim; g.lineWidth = Math.max(1.2, r * 0.08); g.beginPath(); g.ellipse(x, y, r - 1, ry - 1, 0, 0, Math.PI * 2); g.stroke();
    const hx = x - r * 0.34, hy = y - ry * 0.42, hg = g.createRadialGradient(hx, hy, 0, hx, hy, r * 0.32);
    hg.addColorStop(0, 'rgba(255,255,255,.9)'); hg.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = hg; g.beginPath(); g.ellipse(hx, hy, r * 0.3, ry * 0.2, -0.5, 0, Math.PI * 2); g.fill();
  }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}
