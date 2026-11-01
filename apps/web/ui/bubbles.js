// Startup screen: water drops drift up behind the wordmark; tap one to pop it.
(() => {
  const startup = document.getElementById('app-startup');
  if (!startup) return;
  const canvas = document.createElement('canvas');
  canvas.className = 'app-startup-bubbles';
  canvas.setAttribute('aria-hidden', 'true');
  startup.prepend(canvas);
  const ctx = canvas.getContext('2d');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let w = 0, h = 0, dpr = 1, bubbles = [], bursts = [], raf = 0, last = 0;

  // One pre-drawn sprite per radius keeps hundreds of gradients off the frame loop.
  const sprites = new Map();
  const sprite = r => {
    const key = Math.round(r);
    if (sprites.has(key)) return sprites.get(key);
    const s = Math.ceil((key * 2 + 6) * dpr), c = document.createElement('canvas');
    c.width = c.height = s;
    const g = c.getContext('2d'), m = s / 2, R = key * dpr;
    g.fillStyle = 'rgba(0,0,0,.55)';
    g.beginPath(); g.ellipse(m, m + R * 0.16, R, R, 0, 0, Math.PI * 2); g.fill();
    const body = g.createRadialGradient(m, m + R * 0.25, 0, m, m + R * 0.1, R);
    body.addColorStop(0, 'rgba(255,255,255,.10)'); body.addColorStop(0.6, 'rgba(255,255,255,.03)');
    body.addColorStop(0.86, 'rgba(255,255,255,.15)'); body.addColorStop(1, 'rgba(255,255,255,.42)');
    g.fillStyle = body; g.beginPath(); g.arc(m, m, R, 0, Math.PI * 2); g.fill();
    const rim = g.createLinearGradient(0, m - R, 0, m + R);
    rim.addColorStop(0, 'rgba(255,255,255,.06)'); rim.addColorStop(0.55, 'rgba(255,255,255,.12)'); rim.addColorStop(1, 'rgba(255,255,255,.75)');
    g.strokeStyle = rim; g.lineWidth = Math.max(0.8 * dpr, R * 0.09); g.beginPath(); g.arc(m, m, R - g.lineWidth / 2, 0, Math.PI * 2); g.stroke();
    const shine = (x, y, rx, ry, a) => {
      const sg = g.createRadialGradient(x, y, 0, x, y, Math.max(rx, ry));
      sg.addColorStop(0, `rgba(255,255,255,${a})`); sg.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = sg; g.beginPath(); g.ellipse(x, y, rx, ry, -0.5, 0, Math.PI * 2); g.fill();
    };
    shine(m - R * 0.34, m - R * 0.42, R * 0.3, R * 0.2, 0.95);
    if (key > 3) shine(m + R * 0.2, m + R * 0.62, R * 0.46, R * 0.14, 0.35);
    sprites.set(key, c);
    return c;
  };

  const random = (a, b) => a + Math.random() * (b - a);
  const make = (initial) => {
    const r = 3 + 30 * Math.pow(Math.random(), 2.4);
    return { r, x: random(r, w - r), y: initial ? random(-r, h + r) : h + r + random(0, 80),
      speed: random(14, 30) + (34 - r) * 0.6, phase: random(0, Math.PI * 2), sway: random(4, 14), born: performance.now() };
  };
  const resize = () => {
    dpr = Math.min(2, devicePixelRatio || 1);
    w = startup.clientWidth; h = startup.clientHeight;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    sprites.clear();
    const target = Math.min(70, Math.round(w * h / 11000));
    while (bubbles.length < target) bubbles.push(make(true));
    bubbles.length = target;
  };

  const pop = (b) => {
    bubbles.splice(bubbles.indexOf(b), 1);
    const x = b.x + Math.sin(b.phase) * b.sway, now = performance.now();
    const count = 6 + Math.round(b.r / 3);
    const drops = Array.from({ length: count }, (_, i) => {
      const a = (i / count) * Math.PI * 2 + random(-0.3, 0.3), v = random(60, 140) + b.r * 3;
      return { x, y: b.y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, r: random(0.8, 1.8) + b.r * 0.05 };
    });
    bursts.push({ x, y: b.y, r: b.r, t0: now, drops });
    navigator.vibrate?.(8);
    setTimeout(() => bubbles.push(make(false)), 900);
    if (reduced) draw(now);
  };
  canvas.addEventListener('pointerdown', (e) => {
    const rect = canvas.getBoundingClientRect(), px = e.clientX - rect.left, py = e.clientY - rect.top;
    let hit = null, best = Infinity;
    for (const b of bubbles) {
      const d = Math.hypot(px - (b.x + Math.sin(b.phase) * b.sway), py - b.y);
      if (d < b.r + 10 && d < best) { best = d; hit = b; }
    }
    if (hit) pop(hit);
  });

  const draw = (now) => {
    const dt = Math.min(0.05, (now - (last || now)) / 1000); last = now;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    for (const b of bubbles) {
      if (!reduced) { b.y -= b.speed * dt; b.phase += dt * (0.6 + 6 / b.r); if (b.y < -b.r - 10) Object.assign(b, make(false)); }
      const grow = Math.min(1, (now - b.born) / 500), s = sprite(b.r), size = s.width / dpr;
      ctx.globalAlpha = grow;
      ctx.drawImage(s, b.x + Math.sin(b.phase) * b.sway - size / 2, b.y - size / 2, size, size);
    }
    ctx.globalAlpha = 1;
    bursts = bursts.filter(p => {
      const t = (now - p.t0) / 1000;
      if (t > 0.6) return false;
      const k = t / 0.6;
      ctx.strokeStyle = `rgba(255,255,255,${0.55 * (1 - k)})`; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r * (1 + k * 0.9), 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = `rgba(255,255,255,${0.8 * (1 - k)})`;
      for (const d of p.drops) {
        ctx.beginPath(); ctx.arc(p.x + d.vx * t, p.y + d.vy * t + 220 * t * t, d.r * (1 - k * 0.5), 0, Math.PI * 2); ctx.fill();
      }
      return true;
    });
  };

  const visible = () => getComputedStyle(startup).display !== 'none';
  const loop = (now) => {
    if (!visible()) { raf = 0; last = 0; return; }
    draw(now);
    raf = (reduced && !bursts.length) ? 0 : requestAnimationFrame(loop);
  };
  const start = () => {
    if (raf || !visible()) return;
    resize();
    raf = requestAnimationFrame(loop);
  };
  new MutationObserver(start).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  addEventListener('resize', () => { if (visible()) { resize(); if (!raf) raf = requestAnimationFrame(loop); } });
  canvas.addEventListener('pointerdown', () => { if (!raf) raf = requestAnimationFrame(loop); });
  start();
})();
