"use strict";
/* Developer docs enhancements. The documentation itself is static HTML; this
   only adds copy buttons, highlights the current section and closes the phone
   section list after a jump. */
(() => {
  document.documentElement.classList.add("js");
  document.querySelectorAll("[data-copy]").forEach(button => {
    button.hidden = false;
    button.addEventListener("click", async () => {
      const code = button.closest(".p-code")?.querySelector("code")?.textContent || "";
      try {
        await navigator.clipboard.writeText(code);
        button.textContent = "Скопировано";
        button.classList.add("is-done");
      } catch {
        button.textContent = "Выделите вручную";
      }
      setTimeout(() => { button.textContent = "Копировать"; button.classList.remove("is-done"); }, 1600);
    });
  });

  const mobile = document.querySelector(".pd-nav-mobile");
  mobile?.addEventListener("click", event => { if (event.target.closest("a")) mobile.open = false; });

  const sections = [...document.querySelectorAll(".pd-body h2[id]")];
  const subs = [...document.querySelectorAll(".pd-body h3[id]")];
  const toc = document.getElementById("docs-toc");
  if (toc?.querySelector("[data-toc-for]")) toc.classList.add("has-items");
  let current = "";
  const update = () => {
    const line = 120;
    let active = sections[0];
    for (const heading of sections) if (heading.getBoundingClientRect().top <= line) active = heading;
    let activeSub = null;
    for (const heading of subs) if (heading.id.startsWith(active.id + "-") && heading.getBoundingClientRect().top <= line) activeSub = heading;
    if (active.id + (activeSub?.id || "") === current) return;
    current = active.id + (activeSub?.id || "");
    document.querySelectorAll(".pd-nav a").forEach(link => link.setAttribute("aria-current", String(link.hash === "#" + active.id)));
    document.querySelectorAll("[data-toc-for]").forEach(list => list.classList.toggle("is-active", list.dataset.tocFor === active.id));
    document.querySelectorAll(".pd-toc a").forEach(link => link.setAttribute("aria-current", String(Boolean(activeSub) && link.hash === "#" + activeSub.id)));
  };
  let queued = false;
  addEventListener("scroll", () => { if (queued) return; queued = true; requestAnimationFrame(() => { queued = false; update(); }); }, { passive: true });
  if (sections.length) update();
})();
