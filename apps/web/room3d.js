/* Landing hero: a furnished room in real 3D (three.js, vendored), orthographic
   camera from above and slightly to the side. A pre-rendered poster of the same
   scene shows first; WebGL loads after the page and fades in over it. The room
   renders only when the user turns it: no animation loop at rest. */
const root = document.querySelector('[data-room3d]');
const posterMode = new URLSearchParams(location.search).has('room-poster');

const start = () => import('./vendor/three-0.170.0.module.min.js').then(THREE => Promise.all([
  import('./vendor/three-rounded-box-0.170.0.js'),
  import('./vendor/three-room-environment-0.170.0.js'),
]).then(([{ RoundedBoxGeometry }, { RoomEnvironment }]) => build(THREE, RoundedBoxGeometry, RoomEnvironment)));

function build(THREE, RoundedBoxGeometry, RoomEnvironment) {
  const canvas = root.querySelector('canvas');
  const small = matchMedia('(max-width: 700px)').matches;
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance', preserveDrawingBuffer: posterMode });
  } catch {
    return; // No WebGL: the poster stays.
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, small ? 1.5 : 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.VSMShadowMap;
  renderer.shadowMap.autoUpdate = false;

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.55;

  // ── Materials ──
  const std = (color, roughness = 0.8, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness, metalness: 0, ...extra });
  const wallMat = std(0xf3f1ec, 0.92);
  const trimMat = std(0xfafaf8, 0.6);
  const cutMat = std(0xd9d6cf, 0.95);
  const fabric = std(0x9a9a97, 0.95);
  const fabricLight = std(0xcfc6b8, 0.95);
  const walnut = std(0x6b4a33, 0.55);
  const oak = std(0xb88e63, 0.6);
  const blackMetal = std(0x222222, 0.4, { metalness: 0.7 });
  const brass = std(0xc9a35a, 0.35, { metalness: 0.9 });
  const leaf = std(0x4f7a46, 0.7);
  const leafDark = std(0x3d6438, 0.75);
  const ceramic = std(0xf2efe9, 0.35);
  const terracotta = std(0xb8673f, 0.85);
  const mustard = std(0xc99a3c, 0.9);
  const rugMat = std(0xe3ddd2, 1);

  // Oak plank floor, drawn once into a canvas texture.
  const planks = (() => {
    const c = document.createElement('canvas'); c.width = 1024; c.height = 1024;
    const g = c.getContext('2d');
    const rows = 8, rowH = c.height / rows;
    for (let r = 0; r < rows; r++) {
      let x = -((r * 397) % 600);
      while (x < c.width) {
        const len = 520 + ((r * 131 + Math.abs(x) * 7) % 260);
        const tone = 168 + ((r * 53 + Math.abs(x) * 3) % 22) - 11;
        g.fillStyle = `rgb(${tone + 22},${tone - 6},${tone - 46})`;
        g.fillRect(x, r * rowH, len, rowH);
        for (let i = 0; i < 9; i++) { // grain
          g.strokeStyle = `rgba(90,60,30,${0.05 + (i % 3) * 0.02})`;
          g.lineWidth = 1 + (i % 2);
          const y = r * rowH + 10 + i * (rowH - 20) / 9 + Math.sin(x + i) * 3;
          g.beginPath(); g.moveTo(x, y); g.bezierCurveTo(x + len * 0.3, y + 4, x + len * 0.7, y - 4, x + len, y + 2); g.stroke();
        }
        g.fillStyle = 'rgba(60,40,20,.45)'; g.fillRect(x, r * rowH, 2, rowH);
        x += len;
      }
      g.fillStyle = 'rgba(60,40,20,.5)'; g.fillRect(0, r * rowH, c.width, 2);
    }
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(2.2, 2.2); t.anisotropy = renderer.capabilities.getMaxAnisotropy();
    return t;
  })();
  const floorMat = std(0xffffff, 0.55, { map: planks });

  const room = new THREE.Group();
  scene.add(room);
  const add = (geometry, material, x, y, z, { cast = true, receive = true, parent = room, ry = 0, rx = 0, rz = 0 } = {}) => {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(x, y, z); mesh.rotation.set(rx, ry, rz);
    mesh.castShadow = cast; mesh.receiveShadow = receive;
    parent.add(mesh);
    return mesh;
  };
  const box = (w, h, d) => new THREE.BoxGeometry(w, h, d);
  const rbox = (w, h, d, r = 0.04) => new RoundedBoxGeometry(w, h, d, 2, r);
  const cyl = (rt, rb, h, seg = 24, open = false) => new THREE.CylinderGeometry(rt, rb, h, seg, 1, open);

  // ── Shell: slab, two walls with thickness, window, doorway ──
  const W = 5.4, D = 4.4, H = 2.7, T = 0.16, slab = 0.14;
  const x0 = -W / 2, z0 = -D / 2;
  add(box(W + T, slab, D + T), cutMat, -T / 2, -slab / 2, -T / 2, { cast: false });
  add(box(W, 0.012, D), floorMat, 0, 0.006, 0, { cast: false });
  const wall = (w, h, d, x, y, z) => add(box(w, h, d), wallMat, x, y, z);

  // Back wall (along x) with a window opening.
  const win = { cx: 0.55, w: 1.9, sill: 0.8, top: 2.25 };
  const bz = z0 - T / 2;
  wall(win.cx - win.w / 2 - (x0 - T), H, T, (x0 - T + win.cx - win.w / 2) / 2, H / 2, bz);
  wall(W / 2 - (win.cx + win.w / 2), H, T, (win.cx + win.w / 2 + W / 2) / 2, H / 2, bz);
  wall(win.w, win.sill, T, win.cx, win.sill / 2, bz);
  wall(win.w, H - win.top, T, win.cx, (H + win.top) / 2, bz);
  // Window frame, mullion, sill and glass.
  const fw = 0.06, fh = win.top - win.sill;
  add(box(win.w, fw, T * 0.6), trimMat, win.cx, win.sill + fw / 2, bz);
  add(box(win.w, fw, T * 0.6), trimMat, win.cx, win.top - fw / 2, bz);
  add(box(fw, fh, T * 0.6), trimMat, win.cx - win.w / 2 + fw / 2, win.sill + fh / 2, bz);
  add(box(fw, fh, T * 0.6), trimMat, win.cx + win.w / 2 - fw / 2, win.sill + fh / 2, bz);
  add(box(0.045, fh, T * 0.5), trimMat, win.cx, win.sill + fh / 2, bz);
  add(box(win.w + 0.12, 0.04, 0.26), trimMat, win.cx, win.sill - 0.02, bz + 0.08);
  add(box(win.w - 0.1, fh - 0.1, 0.01), new THREE.MeshStandardMaterial({ color: 0xdfeefa, emissive: 0xcfe6fb, emissiveIntensity: 0.55, roughness: 0.08, metalness: 0, transparent: true, opacity: 0.92 }), win.cx, win.sill + fh / 2, bz, { cast: false, receive: false });

  // Left wall (along z) with a doorway near the front.
  const door = { cz: 1.35, w: 0.9, h: 2.1 };
  const lx = x0 - T / 2;
  wall(T, H, door.cz - door.w / 2 - z0, lx, H / 2, (z0 + door.cz - door.w / 2) / 2);
  wall(T, H, D / 2 - (door.cz + door.w / 2), lx, H / 2, (door.cz + door.w / 2 + D / 2) / 2);
  wall(T, H - door.h, door.w, lx, (H + door.h) / 2, door.cz);
  // Door casing.
  add(box(0.03, door.h, 0.07), trimMat, lx + T / 2 + 0.015, door.h / 2, door.cz - door.w / 2 - 0.035);
  add(box(0.03, door.h, 0.07), trimMat, lx + T / 2 + 0.015, door.h / 2, door.cz + door.w / 2 + 0.035);
  add(box(0.03, 0.07, door.w + 0.14), trimMat, lx + T / 2 + 0.015, door.h + 0.035, door.cz);
  // Door leaf with a handle, closed.
  add(box(0.04, door.h, door.w), std(0xf7f6f3, 0.5), lx, door.h / 2, door.cz);
  add(box(0.06, 0.02, 0.12), brass, lx + 0.05, 1.02, door.cz - door.w / 2 + 0.1);
  // Baseboards.
  add(box(W, 0.08, 0.02), trimMat, 0, 0.04, z0 + 0.01);
  add(box(0.02, 0.08, door.cz - door.w / 2 - z0), trimMat, x0 + 0.01, 0.04, (z0 + door.cz - door.w / 2) / 2);

  // ── Furniture ──
  add(rbox(2.6, 0.02, 1.8, 0.01), rugMat, 0.45, 0.022, 0.05, { cast: false });

  // Sofa under the window.
  const sofa = new THREE.Group(); sofa.position.set(0.5, 0, -1.62); room.add(sofa);
  add(rbox(2.3, 0.3, 0.92, 0.05), fabric, 0, 0.23, 0, { parent: sofa });
  add(rbox(2.3, 0.5, 0.24, 0.07), fabric, 0, 0.55, -0.34, { parent: sofa });
  add(rbox(0.2, 0.36, 0.92, 0.07), fabric, -1.05, 0.5, 0, { parent: sofa });
  add(rbox(0.2, 0.36, 0.92, 0.07), fabric, 1.05, 0.5, 0, { parent: sofa });
  add(rbox(0.95, 0.14, 0.66, 0.06), fabric, -0.47, 0.45, 0.08, { parent: sofa });
  add(rbox(0.95, 0.14, 0.66, 0.06), fabric, 0.47, 0.45, 0.08, { parent: sofa });
  add(rbox(0.42, 0.38, 0.14, 0.06), mustard, -0.66, 0.66, -0.16, { parent: sofa, rx: -0.25, rz: 0.08 });
  add(rbox(0.38, 0.34, 0.13, 0.06), terracotta, 0.7, 0.64, -0.17, { parent: sofa, rx: -0.25, rz: -0.1 });
  [[-1.05, -0.36], [1.05, -0.36], [-1.05, 0.36], [1.05, 0.36]].forEach(([x, z]) => add(cyl(0.025, 0.02, 0.08, 12), walnut, x, 0.04, z, { parent: sofa }));

  // Round coffee table with books and a vase.
  const table = new THREE.Group(); table.position.set(0.5, 0, -0.25); room.add(table);
  add(cyl(0.48, 0.48, 0.04, 48), walnut, 0, 0.42, 0, { parent: table });
  [0, 2.09, 4.19].forEach(a => add(cyl(0.015, 0.015, 0.4, 10), blackMetal, Math.cos(a) * 0.32, 0.2, Math.sin(a) * 0.32, { parent: table }));
  add(rbox(0.3, 0.04, 0.22, 0.01), std(0x2f4858, 0.8), -0.15, 0.46, 0.05, { parent: table, ry: 0.3 });
  add(rbox(0.26, 0.035, 0.2, 0.01), std(0xe8e1d3, 0.8), -0.15, 0.497, 0.05, { parent: table, ry: 0.15 });
  add(cyl(0.05, 0.07, 0.2, 24), ceramic, 0.2, 0.54, -0.05, { parent: table });

  // Armchair at an angle, facing the sofa.
  const chair = new THREE.Group(); chair.position.set(-1.45, 0, 0.35); chair.rotation.y = 0.9; room.add(chair);
  add(rbox(0.8, 0.22, 0.78, 0.06), fabricLight, 0, 0.32, 0, { parent: chair });
  add(rbox(0.8, 0.46, 0.18, 0.07), fabricLight, 0, 0.6, -0.31, { parent: chair, rx: -0.12 });
  add(rbox(0.14, 0.24, 0.72, 0.06), fabricLight, -0.36, 0.52, 0, { parent: chair });
  add(rbox(0.14, 0.24, 0.72, 0.06), fabricLight, 0.36, 0.52, 0, { parent: chair });
  [[-0.32, -0.3], [0.32, -0.3], [-0.32, 0.3], [0.32, 0.3]].forEach(([x, z]) => add(cyl(0.02, 0.015, 0.22, 10), oak, x, 0.11, z, { parent: chair, rx: z > 0 ? 0.12 : -0.12 }));

  // Sideboard along the left wall with a lamp, books and a picture above.
  const side = new THREE.Group(); side.position.set(x0 + 0.26, 0, -0.75); room.add(side);
  add(rbox(0.46, 0.56, 1.7, 0.02), oak, 0, 0.36, 0, { parent: side });
  [-0.42, 0.42].forEach(z => add(box(0.006, 0.44, 0.78), std(0x9c7650, 0.6), 0.236, 0.36, z, { parent: side, cast: false }));
  [[-0.17, -0.75], [0.17, -0.75], [-0.17, 0.75], [0.17, 0.75]].forEach(([x, z]) => add(cyl(0.015, 0.015, 0.08, 10), blackMetal, x, 0.04, z, { parent: side }));
  add(cyl(0.07, 0.09, 0.05, 24), ceramic, 0, 0.665, 0.55, { parent: side });
  add(cyl(0.008, 0.008, 0.32, 8), brass, 0, 0.84, 0.55, { parent: side });
  add(cyl(0.1, 0.16, 0.18, 32), std(0xf6efe2, 0.9, { emissive: 0xffd9a0, emissiveIntensity: 0.35, side: THREE.DoubleSide }), 0, 1.02, 0.55, { parent: side, cast: false });
  [0.07, 0.05, 0.06].forEach((h, i) => add(box(0.2, h, 0.04 + i * 0.005), [std(0x7d3c2c), std(0x264653), std(0xd9c7a3)][i], 0, 0.64 + h / 2, -0.35 + i * 0.05, { parent: side }));
  const art = new THREE.Group(); art.position.set(x0 + 0.02, 1.55, -0.75); room.add(art);
  add(box(0.03, 0.82, 1.12), std(0x1d1d1d, 0.5), 0, 0, 0, { parent: art });
  add(box(0.005, 0.7, 1.0), std(0xd8cdb8, 0.95), 0.016, 0, 0, { parent: art, cast: false });
  add(new THREE.CircleGeometry(0.2, 40), std(0xb8673f, 0.9), 0.026, 0.05, 0.15, { parent: art, ry: Math.PI / 2, cast: false });
  add(box(0.004, 0.06, 0.6), std(0x2f4858, 0.9), 0.026, -0.18, -0.12, { parent: art, cast: false });

  // Floor lamp beside the sofa.
  const lamp = new THREE.Group(); lamp.position.set(-1.0, 0, -1.7); room.add(lamp);
  add(cyl(0.16, 0.18, 0.025, 32), blackMetal, 0, 0.0125, 0, { parent: lamp });
  add(cyl(0.012, 0.012, 1.5, 10), blackMetal, 0, 0.76, 0, { parent: lamp });
  add(cyl(0.16, 0.22, 0.28, 32), std(0xf6efe2, 0.9, { emissive: 0xffd9a0, emissiveIntensity: 0.45, side: THREE.DoubleSide }), 0, 1.55, 0, { parent: lamp, cast: false });
  const warm = new THREE.PointLight(0xffc98a, 2.2, 3.2, 1.6); warm.position.set(-1.0, 1.4, -1.6); room.add(warm);

  // Plant in the corner.
  const plant = new THREE.Group(); plant.position.set(x0 + 0.38, 0, z0 + 0.4); room.add(plant);
  add(cyl(0.2, 0.15, 0.42, 32, true), std(0xf2efe9, 0.35, { side: THREE.DoubleSide }), 0, 0.21, 0, { parent: plant });
  add(new THREE.CircleGeometry(0.15, 24), ceramic, 0, 0.002, 0, { parent: plant, rx: -Math.PI / 2, cast: false });
  add(new THREE.CircleGeometry(0.185, 24), std(0x3b2a1e, 1), 0, 0.37, 0, { parent: plant, rx: -Math.PI / 2, cast: false });
  const leafGeo = new THREE.SphereGeometry(0.14, 12, 8);
  for (let i = 0; i < 16; i++) {
    const a = i * 2.4, r = 0.08 + (i % 4) * 0.06, h = 0.6 + (i % 5) * 0.16;
    const l = add(leafGeo, i % 3 ? leaf : leafDark, Math.cos(a) * r, h, Math.sin(a) * r, { parent: plant, rx: Math.cos(a) * 0.6, rz: Math.sin(a) * 0.6 });
    l.scale.set(0.55, 1.6, 0.18);
    l.rotation.y = a;
  }
  add(cyl(0.012, 0.016, 0.7, 8), std(0x5b4636, 0.9), 0, 0.75, 0, { parent: plant });

  // Small side table with a mug by the armchair.
  add(cyl(0.2, 0.2, 0.03, 32), oak, -0.75, 0.52, 1.0);
  add(cyl(0.016, 0.016, 0.5, 10), blackMetal, -0.75, 0.25, 1.0);
  add(cyl(0.14, 0.16, 0.02, 32), blackMetal, -0.75, 0.01, 1.0);
  add(cyl(0.04, 0.035, 0.09, 20), terracotta, -0.7, 0.58, 0.98);

  // ── Light: sun through the window, soft sky, warm lamps ──
  const sun = new THREE.DirectionalLight(0xfff0dc, 3.2);
  sun.position.set(2.2, 5.2, -7.5);
  sun.target.position.set(0.2, 0, 0.6);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  Object.assign(sun.shadow.camera, { left: -5, right: 5, top: 5, bottom: -5, near: 1, far: 20 });
  sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.02; sun.shadow.radius = 6; sun.shadow.blurSamples = 16;
  scene.add(sun, sun.target);
  const fill = new THREE.DirectionalLight(0xe4ecff, 0.7);
  fill.position.set(6, 7, 6);
  scene.add(fill);
  scene.add(new THREE.HemisphereLight(0xf4f1ea, 0x8a7a66, 0.6));

  // ── Camera: orthographic, from above and to the side ──
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 8, 30);
  const target = new THREE.Vector3(-0.15, 0.95, -0.1);
  const view = { azimuth: 0.72, elevation: 0.68 };
  const AZ_MIN = 0.32, AZ_MAX = 1.18;
  const place = () => {
    const r = 18;
    camera.position.set(
      target.x + r * Math.cos(view.elevation) * Math.sin(view.azimuth),
      target.y + r * Math.sin(view.elevation),
      target.z + r * Math.cos(view.elevation) * Math.cos(view.azimuth),
    );
    camera.lookAt(target);
  };
  const render = () => { place(); renderer.render(scene, camera); };
  // Fit the frame to the room's real bounds, checked at every angle the user
  // can turn to, so nothing is cut at any size or rotation.
  const bounds = new THREE.Box3().setFromObject(room);
  const corners = [];
  for (const x of [bounds.min.x, bounds.max.x]) for (const y of [bounds.min.y, bounds.max.y]) for (const z of [bounds.min.z, bounds.max.z]) corners.push(new THREE.Vector3(x, y, z));
  const extent = { left: Infinity, right: -Infinity, bottom: Infinity, top: -Infinity };
  const resting = view.azimuth;
  for (let i = 0; i <= 8; i++) {
    view.azimuth = AZ_MIN + (AZ_MAX - AZ_MIN) * i / 8;
    place(); camera.updateMatrixWorld();
    for (const corner of corners) {
      const p = corner.clone().applyMatrix4(camera.matrixWorldInverse);
      extent.left = Math.min(extent.left, p.x); extent.right = Math.max(extent.right, p.x);
      extent.bottom = Math.min(extent.bottom, p.y); extent.top = Math.max(extent.top, p.y);
    }
  }
  view.azimuth = resting;
  const resize = () => {
    const { width, height } = canvas.getBoundingClientRect();
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    const margin = 1.04;
    const cx = (extent.left + extent.right) / 2, cy = (extent.bottom + extent.top) / 2;
    let halfW = (extent.right - extent.left) / 2 * margin, halfH = (extent.top - extent.bottom) / 2 * margin;
    const aspect = width / height;
    if (halfW / halfH > aspect) halfH = halfW / aspect; else halfW = halfH * aspect;
    Object.assign(camera, { left: cx - halfW, right: cx + halfW, bottom: cy - halfH, top: cy + halfH });
    camera.updateProjectionMatrix();
    render();
  };
  let pending = 0;
  const request = () => { if (!pending) pending = requestAnimationFrame(() => { pending = 0; render(); }); };

  // ── Interaction: horizontal drag turns the room (vertical swipes still scroll) ──
  let drag = null;
  canvas.addEventListener('pointerdown', event => {
    drag = { x: event.clientX }; root.classList.add('is-turning');
    canvas.setPointerCapture?.(event.pointerId);
  });
  canvas.addEventListener('pointermove', event => {
    if (!drag) return;
    view.azimuth = Math.min(AZ_MAX, Math.max(AZ_MIN, view.azimuth - (event.clientX - drag.x) * 0.006));
    drag.x = event.clientX;
    request();
  });
  const release = () => { if (!drag) return; drag = null; root.classList.remove('is-turning'); };
  canvas.addEventListener('pointerup', release);
  canvas.addEventListener('pointercancel', release);
  canvas.addEventListener('keydown', event => {
    const step = { ArrowLeft: 0.08, ArrowRight: -0.08 }[event.key];
    if (!step) return;
    event.preventDefault();
    view.azimuth = Math.min(AZ_MAX, Math.max(AZ_MIN, view.azimuth + step));
    request();
  });

  new ResizeObserver(resize).observe(canvas);

  renderer.shadowMap.needsUpdate = true;
  resize();
  render();
  root.classList.add('is-ready');
  if (posterMode) window.roomPoster = () => { render(); return canvas.toDataURL('image/png'); };
}

if (root) {
  // Load WebGL after the page is interactive, so the hero text and poster paint first.
  const later = window.requestIdleCallback || (fn => setTimeout(fn, 200));
  const go = () => later(() => start().catch(() => {}), { timeout: 1500 });
  if (document.readyState === 'complete') go(); else addEventListener('load', go, { once: true });
}
