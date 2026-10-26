"use strict";
/* Partner landing: navigation, reveal on scroll, the pressed-surface tilt of
   cards and the lazy 3D hero scene. Nothing here is needed to read the page. */
(() => {
  const motion = !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const fine = matchMedia("(hover: hover) and (pointer: fine)");

  // Sticky header gets its hairline once the page scrolls.
  const nav = document.querySelector(".pl-nav");
  const onScroll = () => nav.classList.toggle("is-scrolled", scrollY > 8);
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // Phone menu.
  const menu = document.querySelector(".pl-menu");
  const drawer = document.getElementById("pl-drawer");
  const setMenu = open => {
    drawer.hidden = !open;
    menu.setAttribute("aria-expanded", String(open));
    menu.setAttribute("aria-label", open ? "Закрыть меню" : "Открыть меню");
  };
  menu.addEventListener("click", () => setMenu(drawer.hidden));
  drawer.addEventListener("click", event => { if (event.target.closest("a")) setMenu(false); });
  addEventListener("keydown", event => { if (event.key === "Escape" && !drawer.hidden) { setMenu(false); menu.focus(); } });

  // Reveal sections once.
  if (motion && "IntersectionObserver" in window) {
    document.documentElement.classList.add("js-reveal");
    const targets = document.querySelectorAll(".pl-head,.pl-steps,.pl-value,.pl-flows,.pl-terms,.pl-int,.pl-sec,.pl-timeline,.pl-faq,.pl-cta");
    const seen = new IntersectionObserver(entries => entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-in");
      seen.unobserve(entry.target);
    }), { rootMargin: "0px 0px -8% 0px" });
    targets.forEach(el => { el.classList.add("pl-reveal"); seen.observe(el); });
  }

  // Pressed-surface tilt: the side under the cursor sinks away from the viewer.
  // CSS rotateY(+a) moves the right edge back, rotateX(+a) moves the top edge back.
  const MAX = 5;
  const tilt = card => {
    let frame = 0, target = { x: 0, y: 0 }, current = { x: 0, y: 0 }, inside = false;
    const step = () => {
      current.x += (target.x - current.x) * 0.14;
      current.y += (target.y - current.y) * 0.14;
      const done = Math.abs(target.x - current.x) < 0.01 && Math.abs(target.y - current.y) < 0.01;
      if (done) current = { ...target };
      card.style.transform = current.x || current.y
        ? `perspective(900px) rotateX(${(-current.y * MAX).toFixed(3)}deg) rotateY(${(current.x * MAX).toFixed(3)}deg)`
        : "";
      frame = done ? 0 : requestAnimationFrame(step);
    };
    const kick = () => { if (!frame) frame = requestAnimationFrame(step); };
    card.addEventListener("pointermove", event => {
      if (event.pointerType !== "mouse" || !fine.matches) return;
      const rect = card.getBoundingClientRect();
      target = {
        x: Math.max(-1, Math.min(1, (event.clientX - rect.left - rect.width / 2) / (rect.width / 2))),
        y: Math.max(-1, Math.min(1, (event.clientY - rect.top - rect.height / 2) / (rect.height / 2))),
      };
      card.style.setProperty("--lx", ((target.x + 1) * 50).toFixed(1) + "%");
      card.style.setProperty("--ly", ((target.y + 1) * 50).toFixed(1) + "%");
      if (!inside) { inside = true; card.classList.add("is-pressed"); }
      kick();
    });
    card.addEventListener("pointerleave", () => { inside = false; card.classList.remove("is-pressed"); target = { x: 0, y: 0 }; kick(); });
  };
  if (motion) document.querySelectorAll(".pl-value article,.pl-flow").forEach(tilt);

  // Hero scene: steps work without WebGL; the 3D view loads after first paint.
  const scene = document.querySelector("[data-scene]");
  if (!scene) return;
  const tabs = [...scene.querySelectorAll("[data-step]")];
  const text = scene.querySelector(".pl-scene-text");
  const captions = [
    "Специалист размечает помещение: стены, пол, проёмы.",
    "«Сметра» выделяет элементы и считает площади и объёмы.",
    "Элементы превращаются в перечень материалов с количеством.",
    "Перечень уходит в корзину магазина партнёра. Покупка — на вашем сайте.",
  ];
  let current = 0, controller = null, timer = 0, userPicked = false, visible = false;
  const select = (index, fromUser) => {
    current = (index + tabs.length) % tabs.length;
    tabs.forEach((tab, i) => { tab.setAttribute("aria-selected", String(i === current)); tab.tabIndex = i === current ? 0 : -1; });
    text.textContent = captions[current];
    controller?.go(current);
    if (fromUser) { userPicked = true; clearInterval(timer); timer = 0; }
  };
  tabs.forEach((tab, i) => tab.addEventListener("click", () => select(i, true)));
  scene.querySelector("[role=tablist]").addEventListener("keydown", event => {
    const delta = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (!delta) return;
    event.preventDefault();
    select(current + delta, true);
    tabs[current].focus();
  });
  select(0);
  const autoplay = () => {
    if (!motion || userPicked || timer || !visible) return;
    timer = setInterval(() => select(current + 1), 3600);
  };
  const stop = () => { clearInterval(timer); timer = 0; };

  const webgl = (() => {
    try { const c = document.createElement("canvas"); return Boolean(c.getContext("webgl2") || c.getContext("webgl")); }
    catch { return false; }
  })();
  const saveData = navigator.connection?.saveData === true;
  const load = () => {
    if (!webgl || saveData || controller) return;
    import("/partner-scene.js?v=p1").then(module => {
      controller = module.mount(scene, { motion, onReady: () => scene.classList.add("is-ready") });
      controller?.go(current, true);
      controller?.setVisible(visible);
    }).catch(() => { /* the static drawing stays */ });
  };
  new IntersectionObserver(entries => entries.forEach(entry => {
    visible = entry.isIntersecting;
    controller?.setVisible(visible);
    if (visible) autoplay(); else stop();
  }), { threshold: 0.25 }).observe(scene);
  const idle = window.requestIdleCallback || (fn => setTimeout(fn, 600));
  if (document.readyState === "complete") idle(load, { timeout: 2000 });
  else addEventListener("load", () => idle(load, { timeout: 2000 }), { once: true });
})();
