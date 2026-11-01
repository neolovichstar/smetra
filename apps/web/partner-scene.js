/* Partner hero scene: a floor plan becomes a materials list and then a store cart.
   Loaded lazily by partner-landing.js only when WebGL is available. Renders on
   demand (step transitions and dragging) and stops while off screen. */
import * as THREE from "./vendor/three-0.170.0.module.min.js";

const PALETTE = {
  floor: 0x1e1e23, slab: 0x131316, wall: 0x3c3c44, cap: 0x4a4a53, edge: 0xffffff,
  laminate: 0xb9b2a5, tile: 0x9aabc9, drywall: 0xe4e4e6, crate: 0xf3f3f4,
  room: 0xf3f3f4, bath: 0x8fa7d8, partition: 0x62c294,
};
const ease = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const fmt = (value, digits = 1) => value.toLocaleString("ru-RU", { minimumFractionDigits: 0, maximumFractionDigits: digits });

// The example flat, in metres. Quantities in the labels are computed from it.
const ROOM = { x0: -3.6, x1: 0.8, z0: -2.7, z1: 2.7 };
const BATH = { x0: 0.8, x1: 3.6, z0: -2.7, z1: 0 };
const HALL = { x0: 0.8, x1: 3.6, z0: 0, z1: 2.7 };
const WALL_H = 1.05, WALL_T = 0.12, CEILING = 2.7;
const area = r => (r.x1 - r.x0) * (r.z1 - r.z0);
const partitionLength = (ROOM.z1 - ROOM.z0) + (BATH.x1 - BATH.x0) - 0.9 - 0.8; // minus two doors
const partitionArea = partitionLength * CEILING;
const QUANTITIES = {
  laminate: { label: "Ламинат", value: area(ROOM), unit: "м²", packs: Math.ceil(area(ROOM) * 1.05 / 2.2), pack: "уп." },
  tile: { label: "Плитка", value: area(BATH), unit: "м²", packs: Math.ceil(area(BATH) * 1.1 / 1.44), pack: "кор." },
  drywall: { label: "Гипсокартон", value: partitionArea, unit: "м²", packs: Math.ceil(partitionArea / 3), pack: "л." },
};
// The list and the cart sit in front of the plan (lower on screen), on axes
// turned 45° so rows read left to right: U points screen-right, W screen-down.
const U = new THREE.Vector3(1, 0, -1).normalize(), W = new THREE.Vector3(1, 0, 1).normalize();
const LIST_ORIGIN = U.clone().multiplyScalar(-2.4).addScaledVector(W, 5.5);
const LIST_ROWS = { laminate: 0, tile: 1.35, drywall: 2.7 };
const at = (u, w, y = 0) => LIST_ORIGIN.clone().addScaledVector(U, u).addScaledVector(W, w).setY(y);
const CART = at(1.4, 1.4);
const TURN = Math.PI / 4;

export function mount(figure, { motion = true, onReady } = {}) {
  const canvas = figure.querySelector(".pl-scene-canvas");
  const stage = figure.querySelector(".pl-scene-stage");
  const labelHost = figure.querySelector(".pl-scene-labels");
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
  } catch {
    return null;
  }
  const small = Math.min(innerWidth, innerHeight) < 600 || (navigator.hardwareConcurrency || 4) <= 4;
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, small ? 1.5 : 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = !small;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 80);
  const target = new THREE.Vector3(1.2, 0.4, 0);
  const BASE_AZ = Math.PI / 4, ELEV = 0.62, DIST = 30;
  let azimuth = BASE_AZ;

  scene.add(new THREE.HemisphereLight(0xf4f4f6, 0x1a1a1e, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6);
  sun.position.set(-6, 12, 7);
  sun.castShadow = renderer.shadowMap.enabled;
  sun.shadow.mapSize.set(1024, 1024);
  Object.assign(sun.shadow.camera, { left: -9, right: 9, top: 9, bottom: -9, near: 1, far: 40 });
  sun.shadow.bias = -0.0006;
  scene.add(sun);

  const disposables = [];
  const track = item => (disposables.push(item), item);
  const mat = (color, extra = {}) => track(new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0, ...extra }));
  const edgeMat = track(new THREE.LineBasicMaterial({ color: PALETTE.edge, transparent: true, opacity: 0.22 }));
  const box = (w, h, d, material, x, y, z, edges = true) => {
    const geometry = track(new THREE.BoxGeometry(w, h, d));
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(x, y, z);
    mesh.castShadow = mesh.receiveShadow = true;
    if (edges) mesh.add(new THREE.LineSegments(track(new THREE.EdgesGeometry(geometry)), edgeMat));
    return mesh;
  };

  // Slab, floor and a faint 0.6 m grid.
  const plan = new THREE.Group();
  scene.add(plan);
  plan.add(box(7.6, 0.16, 5.8, mat(PALETTE.slab), 0, -0.1, 0));
  const floor = box(7.2, 0.02, 5.4, mat(PALETTE.floor), 0, 0, 0, false);
  floor.castShadow = false;
  plan.add(floor);
  const gridPoints = [];
  for (let x = -3.6; x <= 3.61; x += 0.6) gridPoints.push(x, 0.012, -2.7, x, 0.012, 2.7);
  for (let z = -2.7; z <= 2.71; z += 0.6) gridPoints.push(-3.6, 0.012, z, 3.6, 0.012, z);
  const gridGeometry = track(new THREE.BufferGeometry());
  gridGeometry.setAttribute("position", new THREE.Float32BufferAttribute(gridPoints, 3));
  plan.add(new THREE.LineSegments(gridGeometry, track(new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.045 }))));

  // Walls: exterior with window and entrance gaps, partitions with doors.
  const wallMat = mat(PALETTE.wall);
  const partitionMat = mat(PALETTE.wall, { emissive: PALETTE.partition, emissiveIntensity: 0 });
  const glassMat = mat(0x9fb2cf, { transparent: true, opacity: 0.35, roughness: 0.2 });
  const wallX = (z0, z1, x, material = wallMat) => box(WALL_T, WALL_H, z1 - z0, material, x, WALL_H / 2, (z0 + z1) / 2);
  const wallZ = (x0, x1, z, material = wallMat) => box(x1 - x0, WALL_H, WALL_T, material, (x0 + x1) / 2, WALL_H / 2, z);
  const walls = new THREE.Group();
  plan.add(walls);
  walls.add(wallZ(-3.66, -2.4, -2.7), wallZ(-0.6, 3.66, -2.7), wallZ(-3.66, 3.66, 2.7));
  walls.add(wallX(-2.7, -1.0, -3.6), wallX(0.8, 2.7, -3.6), wallX(-2.7, 1.2, 3.6), wallX(2.2, 2.7, 3.6));
  const sill = (w, x, z, along) => box(along ? w : WALL_T * 0.5, 0.5, along ? WALL_T * 0.5 : w, glassMat, x, 0.55, z, false);
  walls.add(sill(1.8, -1.5, -2.7, true), sill(1.8, -3.6, -0.1, false));
  const partitions = [
    wallX(-2.7, 0.75, 0.8, partitionMat), wallX(1.65, 2.7, 0.8, partitionMat),
    wallZ(0.8, 2.0, 0, partitionMat), wallZ(2.8, 3.6, 0, partitionMat),
  ];
  partitions.forEach(p => walls.add(p));

  // Region highlights for step 1.
  const overlay = (r, color) => {
    const material = track(new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0, depthWrite: false }));
    const mesh = new THREE.Mesh(track(new THREE.PlaneGeometry(r.x1 - r.x0 - 0.16, r.z1 - r.z0 - 0.16)), material);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set((r.x0 + r.x1) / 2, 0.02, (r.z0 + r.z1) / 2);
    plan.add(mesh);
    return material;
  };
  const roomGlow = overlay(ROOM, PALETTE.room);
  const bathGlow = overlay(BATH, PALETTE.bath);

  // Material packs: born inside their region, then lined up as a list, then packed into the cart.
  const kinds = {
    laminate: { count: 6, size: [0.95, 0.11, 0.32], color: PALETTE.laminate, from: ROOM },
    tile: { count: 4, size: [0.42, 0.16, 0.42], color: PALETTE.tile, from: BATH },
    drywall: { count: 4, size: [0.9, 0.04, 0.62], color: PALETTE.drywall, from: { x0: 0.6, x1: 1.0, z0: -2.4, z1: 0.4 } },
  };
  const packs = [];
  Object.entries(kinds).forEach(([kind, spec], k) => {
    const material = mat(spec.color, { roughness: 0.7 });
    for (let i = 0; i < spec.count; i++) {
      const mesh = box(...spec.size, material, 0, 0, 0);
      mesh.visible = false;
      scene.add(mesh);
      const cx = (spec.from.x0 + spec.from.x1) / 2, cz = (spec.from.z0 + spec.from.z1) / 2;
      const h = spec.size[1];
      const born = new THREE.Vector3(cx + (i % 2 ? 0.25 : -0.25), 0.05, cz + (i - spec.count / 2) * 0.18);
      const row = at((i % 3) * (spec.size[0] + 0.06), LIST_ROWS[kind], h / 2 + Math.floor(i / 3) * (h + 0.02) + 0.02);
      const layer = packs.length;
      const cart = CART.clone().addScaledVector(U, -0.5 + (layer % 2) * 0.5).addScaledVector(W, -0.4 + k * 0.4).setY(0.12 + Math.floor(layer / 2) * 0.13);
      packs.push({ mesh, kind, born, row, cart, delay: (k * spec.count + i) * 0.018 });
    }
  });

  // The cart: a light open crate.
  const crate = new THREE.Group();
  crate.position.copy(CART);
  crate.rotation.y = TURN;
  const crateMat = mat(PALETTE.crate, { transparent: true, opacity: 0.9, roughness: 0.5 });
  crate.add(box(2.0, 0.06, 1.6, crateMat, 0, 0.03, 0));
  // Low front wall so the packed materials stay visible.
  crate.add(box(2.0, 0.9, 0.05, crateMat, 0, 0.45, -0.8), box(2.0, 0.36, 0.05, crateMat, 0, 0.18, 0.8));
  crate.add(box(0.05, 0.9, 1.6, crateMat, -1.0, 0.45, 0), box(0.05, 0.9, 1.6, crateMat, 1.0, 0.45, 0));
  crate.scale.setScalar(0.001);
  crate.visible = false;
  scene.add(crate);

  // Labels.
  const tag = (html, extra = "") => {
    const el = document.createElement("div");
    el.className = "pl-tag " + extra;
    el.innerHTML = html;
    labelHost.append(el);
    return el;
  };
  const q = QUANTITIES;
  const labels = [
    { step: 0, at: new THREE.Vector3(-1.4, 0.1, 0.2), el: tag("Комната") },
    { step: 0, at: new THREE.Vector3(2.2, 0.1, -1.35), el: tag("Санузел") },
    { step: 0, at: new THREE.Vector3(2.2, 0.1, 1.35), el: tag("Коридор") },
    { step: 1, at: new THREE.Vector3(-1.4, 0.1, 0.2), el: tag(`<i></i>Пол · <b>${fmt(q.laminate.value)} м²</b>`) },
    { step: 1, at: new THREE.Vector3(2.2, 0.1, -1.35), el: tag(`<i></i>Пол санузла · <b>${fmt(q.tile.value)} м²</b>`) },
    { step: 1, at: new THREE.Vector3(0.8, WALL_H, -1.2), el: tag(`<i></i>Перегородки · <b>${fmt(q.drywall.value)} м²</b>`) },
    ...["laminate", "tile", "drywall"].map(kind => ({
      step: 2, at: at(3.1, LIST_ROWS[kind], 0.1),
      el: tag(`${q[kind].label} <b>${fmt(q[kind].value)} ${q[kind].unit}</b> · ${q[kind].packs} ${q[kind].pack}`, "is-list"),
    })),
    { step: 3, at: CART.clone().addScaledVector(U, 1.25).setY(0.5), el: tag(`Корзина магазина <small>3 позиции · переход к вам</small>`, "is-cart") },
  ];
  const dots = [PALETTE.room, PALETTE.bath, PALETTE.partition];
  labels.filter(l => l.step === 1).forEach((l, i) => { l.el.querySelector("i").style.background = "#" + dots[i].toString(16).padStart(6, "0"); });

  // Camera framing: fit every object that can appear, across the drag range.
  const bounds = [];
  for (const x of [-3.8, 3.8]) for (const z of [-3.0, 3.0]) for (const y of [-0.2, WALL_H + 0.3]) bounds.push(new THREE.Vector3(x, y, z));
  for (const u of [-0.4, 6.6]) for (const w of [-0.5, 3.1]) for (const y of [0, 1.2]) bounds.push(at(u, w, y));
  const place = () => {
    camera.position.set(target.x + DIST * Math.cos(ELEV) * Math.sin(azimuth), target.y + DIST * Math.sin(ELEV), target.z + DIST * Math.cos(ELEV) * Math.cos(azimuth));
    camera.lookAt(target);
    camera.updateMatrixWorld();
  };
  const fit = () => {
    const rect = stage.getBoundingClientRect();
    const width = Math.max(1, rect.width), height = Math.max(1, rect.height);
    renderer.setSize(width, height, false);
    // Frame the union of everything that can appear, over the whole drag range,
    // centred on that union rather than on the camera target.
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const az of [BASE_AZ - 0.32, BASE_AZ + 0.32]) {
      azimuth = az; place();
      for (const p of bounds) {
        const v = p.clone().applyMatrix4(camera.matrixWorldInverse);
        minX = Math.min(minX, v.x); maxX = Math.max(maxX, v.x);
        minY = Math.min(minY, v.y); maxY = Math.max(maxY, v.y);
      }
    }
    azimuth = BASE_AZ + drag; place();
    const aspect = width / height, pad = 1.04;
    let halfW = (maxX - minX) / 2 * pad, halfH = (maxY - minY) / 2 * pad;
    if (halfW / halfH > aspect) halfH = halfW / aspect; else halfW = halfH * aspect;
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    Object.assign(camera, { left: cx - halfW, right: cx + halfW, top: cy + halfH, bottom: cy - halfH });
    camera.updateProjectionMatrix();
    request();
  };

  // State per step, tweened.
  let step = 0, from = 0, progress = 1, startedAt = 0, running = false, visible = true;
  const DURATION = motion ? 1300 : 1;
  const lerp = (a, b, t) => a + (b - a) * t;
  const packState = (p, s) => (s <= 1 ? { pos: p.born, scale: 0.001, visible: false, turn: 0 } : s === 2 ? { pos: p.row, scale: 1, visible: true, turn: TURN } : { pos: p.cart, scale: 1, visible: true, turn: TURN });
  const apply = t => {
    const e = ease(t);
    roomGlow.opacity = lerp(from === 1 ? 0.07 : 0, step === 1 ? 0.07 : 0, e);
    bathGlow.opacity = lerp(from === 1 ? 0.28 : 0, step === 1 ? 0.28 : 0, e);
    partitionMat.emissiveIntensity = lerp(from === 1 ? 0.35 : 0, step === 1 ? 0.35 : 0, e);
    for (const p of packs) {
      const a = packState(p, from), b = packState(p, step);
      const local = Math.min(1, Math.max(0, (t - p.delay) / (1 - 0.3)));
      const k = ease(local);
      p.mesh.visible = a.visible || b.visible;
      p.mesh.position.lerpVectors(a.pos, b.pos, k);
      if (a.pos !== b.pos) p.mesh.position.y += Math.sin(Math.PI * k) * 1.1; // a short arc
      p.mesh.scale.setScalar(Math.max(0.001, lerp(a.scale, b.scale, k)));
      p.mesh.rotation.y = lerp(a.turn, b.turn, k);
    }
    const crateIn = step === 3 ? 1 : 0, crateWas = from === 3 ? 1 : 0;
    const c = lerp(crateWas, crateIn, e);
    crate.visible = c > 0.01;
    crate.scale.setScalar(Math.max(0.001, c));
  };
  const placeLabels = () => {
    const width = stage.clientWidth, height = stage.clientHeight;
    const settled = progress >= 0.75;
    for (const label of labels) {
      const on = label.step === step && settled;
      label.el.classList.toggle("is-on", on);
      if (!on) continue;
      const v = label.at.clone().project(camera);
      label.el.style.transform = `translate(${((v.x + 1) / 2 * width).toFixed(1)}px,${((1 - v.y) / 2 * height).toFixed(1)}px) ${label.el.classList.contains("is-list") ? "translate(0,-50%)" : label.el.classList.contains("is-cart") ? "translate(0,-50%)" : "translate(-50%,-50%)"}`;
    }
  };
  let raf = 0;
  const frame = now => {
    raf = 0;
    if (running) {
      progress = Math.min(1, (now - startedAt) / DURATION);
      apply(progress);
      if (progress >= 1) running = false;
    }
    renderer.render(scene, camera);
    placeLabels();
    if (running && visible) raf = requestAnimationFrame(frame);
  };
  function request() { if (!raf && visible) raf = requestAnimationFrame(frame); }

  // Drag to turn the plan a little; nothing moves on its own.
  let drag = 0, dragStart = null;
  canvas.addEventListener("pointerdown", event => {
    dragStart = { x: event.clientX, value: drag };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", event => {
    if (!dragStart) return;
    drag = Math.max(-0.32, Math.min(0.32, dragStart.value - (event.clientX - dragStart.x) / 320));
    azimuth = BASE_AZ + drag;
    place();
    request();
  });
  const end = () => { dragStart = null; };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);

  const resize = new ResizeObserver(fit);
  resize.observe(stage);
  fit();
  apply(1);
  renderer.render(scene, camera);
  onReady?.();

  const dispose = () => {
    cancelAnimationFrame(raf);
    resize.disconnect();
    disposables.forEach(item => item.dispose?.());
    renderer.dispose();
    labelHost.replaceChildren();
  };
  addEventListener("pagehide", dispose, { once: true });

  return {
    go(next, instant = false) {
      if (next === step && !instant) return;
      from = instant ? next : step;
      step = next;
      startedAt = performance.now();
      progress = instant ? 1 : 0;
      running = !instant;
      if (instant) apply(1);
      request();
    },
    setVisible(value) {
      visible = value;
      if (visible) request(); else { cancelAnimationFrame(raf); raf = 0; }
    },
    dispose,
  };
}
