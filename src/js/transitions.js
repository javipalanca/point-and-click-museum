/* Point and Click Museum · classic screen transitions between pages.
   Leaving a page closes the screen with an effect (iris on the point you clicked, star wipe, dissolve,
   dithered fade, blinds, diamond, clock); the next page opens with the same effect in reverse.
   Configured in data/site.json → "transitions". Skipped with prefers-reduced-motion. */
"use strict";
(() => {
  const D = PCM.D, C = D.transitions || {};
  const KINDS = ["iris", "star", "dissolve", "fade", "blinds", "diamond", "clock"];
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const BAYER = [[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26], [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25], [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]];
  const store = (k, v) => { try { if (v === undefined) { const x = sessionStorage.getItem(k); sessionStorage.removeItem(k); return x; } sessionStorage.setItem(k, v); } catch (e) { return null; } return null; };

  /* integer hash -> [0,1): a stable random order for the dissolve */
  function noise(x, y, seed) {
    let h = Math.imul(x, 374761393) + Math.imul(y, 668265263) + Math.imul(seed | 0, 2246822519) | 0;
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }

  let cv = null, busy = false;
  function canvas() {
    if (cv) return cv;
    cv = document.createElement("canvas");
    cv.className = "pcm-wipe"; cv.setAttribute("aria-hidden", "true");
    document.body.appendChild(cv);
    return cv;
  }

  /* covered(t): 0 = page fully visible, 1 = screen fully black */
  function paint(kind, t, ox, oy, seed) {
    const px = C.pixel || 6, w = Math.ceil(innerWidth / px), h = Math.ceil(innerHeight / px), c = canvas();
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    const ctx = c.getContext("2d"), img = ctx.createImageData(w, h), a = img.data;
    const cx = ox / px, cy = oy / px;
    const far = Math.max(Math.hypot(cx, cy), Math.hypot(w - cx, cy), Math.hypot(cx, h - cy), Math.hypot(w - cx, h - cy));
    const R = (1 - t) * far;  // visible radius for shape wipes
    const rot = -Math.PI / 2, step = Math.PI * 2 / 5;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const dx = x + 0.5 - cx, dy = y + 0.5 - cy;
      let black;
      switch (kind) {
        case "iris": black = dx * dx + dy * dy > R * R; break;
        case "diamond": black = (Math.abs(dx) + Math.abs(dy)) > R * 1.42; break;
        case "star": {
          const ang = Math.atan2(dy, dx) - rot, local = (((ang % step) + step) % step) / step;
          const edge = R * 2.4 * (0.42 + 0.58 * Math.abs(1 - 2 * local) ** 1.6);  // 5 points, inner radius ≈ 42%
          black = Math.hypot(dx, dy) > edge; break;
        }
        case "blinds": black = (y % 12) < t * 12.5; break;
        case "clock": { const ang = (Math.atan2(dx, -dy) + Math.PI * 2) % (Math.PI * 2); black = ang < t * Math.PI * 2; break; }
        case "dissolve": black = noise(x, y, seed) < t; break;
        default: black = BAYER[y & 7][x & 7] / 64 < t;   // dithered fade to black
      }
      if (black) { const i = (y * w + x) * 4; a[i] = 10; a[i + 1] = 7; a[i + 2] = 22; a[i + 3] = 255; }
    }
    ctx.putImageData(img, 0, 0);
  }

  function animate(kind, from, to, ox, oy, done) {
    const dur = C.duration || 700, start = performance.now(), seed = Math.floor(Math.random() * 1e6);
    const ease = x => x < 0.5 ? 2 * x * x : 1 - (-2 * x + 2) ** 2 / 2;
    (function frame(now) {
      const k = Math.min(1, (now - start) / dur);
      const q = Math.round(ease(k) * 20) / 20;   // 20 steps: chunky, like the old engines
      paint(kind, from + (to - from) * q, ox, oy, seed);
      if (k < 1) requestAnimationFrame(frame); else if (done) done();
    })(start);
  }

  function pick(url) {
    const by = C.byTarget || {};
    for (const [id, kind] of Object.entries(by)) {
      const target = D.pageUrls && D.pageUrls[id];
      if (target && new URL(target, location.href).pathname.replace(/index\.html$/, "") === url.pathname.replace(/index\.html$/, "")) return kind;
    }
    const pool = (C.pool || KINDS).filter(k => KINDS.includes(k));
    return pool[Math.floor(Math.random() * pool.length)] || "fade";
  }

  /* leave the page with a transition, then navigate */
  function go(href, opts = {}) {
    const url = new URL(href, location.href);
    if (reduce || busy) { location.href = url.href; return; }
    busy = true;
    const kind = opts.kind || pick(url);
    const x = opts.x != null ? opts.x : innerWidth / 2, y = opts.y != null ? opts.y : innerHeight / 2;
    if (PCM.soundOn) { PCM.tone(520, 0.12, "triangle", 0.035); PCM.tone(260, 0.2, "triangle", 0.035, 0.12); }
    canvas().classList.add("on");
    animate(kind, 0, 1, x, y, () => {
      store("pcm-wipe", JSON.stringify({ kind }));
      location.href = url.href;
      setTimeout(() => { busy = false; }, 1500);   // if navigation is cancelled
    });
  }
  PCM.go = go;

  /* arriving: open the screen with the same effect */
  const arrive = store("pcm-wipe");
  document.documentElement.classList.remove("pcm-wipe-in");
  if (arrive && !reduce) {
    let kind = "fade";
    try { kind = JSON.parse(arrive).kind; } catch (e) { /* default */ }
    const c = canvas(); c.classList.add("on");
    paint(kind, 1, innerWidth / 2, innerHeight / 2, 0);
    requestAnimationFrame(() => animate(kind, 1, 0, innerWidth / 2, innerHeight / 2, () => c.classList.remove("on")));
  }
  /* back/forward cache: never come back to a closed screen */
  addEventListener("pageshow", e => { if (e.persisted && cv) { cv.classList.remove("on"); busy = false; } });

  /* intercept internal links */
  document.addEventListener("click", e => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest && e.target.closest("a[href]");
    if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
    const url = new URL(a.getAttribute("href"), location.href);
    if (url.origin !== location.origin || !/^https?:$/.test(url.protocol)) return;
    if (url.pathname === location.pathname && url.search === location.search) return;   // same page / #anchor
    e.preventDefault();
    const lang = a.hasAttribute("hreflang");
    go(url.href, { kind: lang ? (C.languageSwitch || "fade") : undefined, x: e.clientX || undefined, y: e.clientY || undefined });
  });
})();
