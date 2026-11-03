/* Point and Click Museum · site navigation: header of doors, games submenu, language menu,
   museum map (floor plan), visited rooms and the "in this room" strip. */
"use strict";
(() => {
  const { D, $, $$, t, store, sfx, reduceMotion } = PCM;
  const root = document.documentElement, header = $("#siteHeader"), subnav = $(".subnav");

  /* sticky offsets: header and strip heights feed scroll-margin and the strip's top */
  function measure() {
    root.style.setProperty("--hd-h", header.offsetHeight + "px");
    root.style.setProperty("--sub-h", (subnav ? subnav.offsetHeight : 0) + "px");
  }
  measure();
  if ("ResizeObserver" in window) new ResizeObserver(measure).observe(header);
  addEventListener("resize", measure);

  /* compact header once the page scrolls. The header is sticky (in the flow), so compacting it shortens the page and
     moves the scroll position: without a margin it would flip back and forth (flicker) near the threshold or on
     short pages. Hysteresis: compact past ON px only if the page still scrolls after losing the header's extra
     height; expand again near the top (OFF px). */
  const ON = 96, OFF = 8;
  let ticking = false, lost = 0;  // height the header loses when compact (measured while it is full)
  function compactHeader() {
    ticking = false;
    const compact = header.classList.contains("compact");
    if (!compact) lost = Math.max(header.offsetHeight - 60, 0);
    const room = document.documentElement.scrollHeight - innerHeight - (compact ? 0 : lost);  // scroll left once compact
    if (!compact && scrollY > ON && room > ON) header.classList.add("compact");
    else if (compact && scrollY < OFF) header.classList.remove("compact");
  }
  addEventListener("scroll", () => {
    if (ticking) return; ticking = true;
    requestAnimationFrame(compactHeader);
  }, { passive: true });

  /* games submenu: hover on desktop (CSS), button for touch and keyboard */
  const closeSubs = except => $$(".door.has-sub.open").forEach(li => { if (li !== except) { li.classList.remove("open"); $(".sub-toggle", li).setAttribute("aria-expanded", "false"); } });
  $$(".sub-toggle").forEach(btn => btn.addEventListener("click", e => {
    e.stopPropagation();
    const li = btn.closest(".door"), open = !li.classList.contains("open");
    closeSubs(li); li.classList.toggle("open", open); btn.setAttribute("aria-expanded", String(open)); sfx("click");
    if (open) { const first = $(".sub a", li); if (first) first.focus({ preventScroll: true }); }
  }));
  const lang = $(".lang-menu");
  document.addEventListener("click", e => {
    if (!e.target.closest(".door.has-sub")) closeSubs();
    if (lang && lang.open && !e.target.closest(".lang-menu")) lang.open = false;
  });
  document.addEventListener("keydown", e => {
    if (e.key !== "Escape") return;
    const sub = $(".door.has-sub.open");
    if (sub) { closeSubs(); $(".sub-toggle", sub).focus(); }
    if (lang && lang.open) { lang.open = false; $("summary", lang).focus(); }
  });

  /* visited rooms (per visitor, this browser only) */
  const rooms = ["home"].concat(D.nav || []);
  const visited = new Set(store("visited") || []);
  visited.add(D.page);
  store("visited", [...visited]);
  const isVisited = id => visited.has(id) || (id === "games" && (D.gamePages || []).some(g => visited.has(g)));

  /* museum map */
  const btn = $("#mapBtn"), panel = $("#mapPanel"), closeBtn = $("#mapClose");
  let lastFocus = null;
  function renderPlan() {
    let n = 0;
    $$(".plan-room", panel).forEach(r => { const v = isVisited(r.dataset.page); r.classList.toggle("visited", v); if (v) n++; });
    $("#mapVisited").textContent = t("visitedFmt", { n, total: rooms.length });
  }
  function openMap() {
    lastFocus = document.activeElement; renderPlan();
    panel.hidden = false; root.classList.add("map-open"); btn.setAttribute("aria-expanded", "true");
    const r = btn.getBoundingClientRect();
    panel.style.setProperty("--ox", (r.left + r.width / 2) + "px"); panel.style.setProperty("--oy", (r.top + r.height / 2) + "px");
    if (!reduceMotion) { panel.classList.remove("opening"); void panel.offsetWidth; panel.classList.add("opening"); }
    sfx("open");
    const here = $(".plan-room.here a", panel) || closeBtn; here.focus({ preventScroll: true });
  }
  function closeMap() {
    panel.hidden = true; root.classList.remove("map-open"); btn.setAttribute("aria-expanded", "false");
    if (lastFocus) lastFocus.focus({ preventScroll: true });
  }
  btn.addEventListener("click", () => (panel.hidden ? openMap() : closeMap()));
  closeBtn.addEventListener("click", closeMap);
  panel.addEventListener("click", e => { if (e.target === panel) closeMap(); });
  panel.addEventListener("keydown", e => {
    if (e.key === "Escape") { e.stopPropagation(); closeMap(); }
    if (e.key === "Tab") {
      const f = $$("a, button", panel).filter(x => x.offsetParent !== null);
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  });
  addEventListener("pageshow", () => { if (!panel.hidden) closeMap(); });

  /* "in this room" strip: highlight the section being read */
  if (subnav && "IntersectionObserver" in window) {
    const links = $$("a", subnav), targets = links.map(a => document.getElementById(a.getAttribute("href").slice(1))).filter(Boolean);
    const strip = $("ul", subnav);
    const setActive = id => links.forEach(a => {
      const on = a.getAttribute("href") === "#" + id;
      if (on && a.getAttribute("aria-current") !== "true") {
        a.setAttribute("aria-current", "true");
        const l = a.offsetLeft - strip.clientWidth / 2 + a.offsetWidth / 2;
        strip.scrollTo({ left: l, behavior: reduceMotion ? "auto" : "smooth" });
      } else if (!on) a.removeAttribute("aria-current");
    });
    const seen = new Map();
    const io = new IntersectionObserver(es => {
      es.forEach(e => seen.set(e.target.id, e.isIntersecting ? e.boundingClientRect.top : null));
      const visible = targets.filter(el => seen.get(el.id) != null);
      if (visible.length) setActive(visible[0].id);
    }, { rootMargin: "-30% 0px -55% 0px" });
    targets.forEach(el => io.observe(el));
    links.forEach(a => a.addEventListener("click", () => sfx("click")));
  }
})();
