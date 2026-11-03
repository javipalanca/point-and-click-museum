/* Point and Click Museum · technique demos: SCUMM walk boxes with scaling, Sierra priority screens,
   CGA/EGA/VGA palettes applied to a real screenshot. Data: data/techniques.json → demos. */
"use strict";
(() => {
  const { D, $, $$, sfx, mediaFigure } = PCM;
  const reduce = PCM.reduceMotion;

  /* ================= Walk boxes + scaling (SCUMM) ================= */
  if ($("#wbCanvas")) (() => {
    const cv = $("#wbCanvas"), x = cv.getContext("2d"), W = cv.width, H = cv.height;
    // boxes: trapezoids [yTop, yBottom, xL_top, xR_top, xL_bottom, xR_bottom], scale at top/bottom
    const B = [
      { y0: 86, y1: 106, t: [8, 184], b: [0, 192], s0: 0.95, s1: 1.1 },   // 0 foreground
      { y0: 66, y1: 86, t: [40, 150], b: [8, 184], s0: 0.72, s1: 0.95 },  // 1 middle
      { y0: 52, y1: 66, t: [70, 118], b: [40, 150], s0: 0.55, s1: 0.72 }, // 2 back
      { y0: 40, y1: 52, t: [84, 100], b: [70, 118], s0: 0.42, s1: 0.55 }, // 3 corridor
    ];
    const edges = (i, y) => { const b = B[i], k = (y - b.y0) / (b.y1 - b.y0); return [b.t[0] + (b.b[0] - b.t[0]) * k, b.t[1] + (b.b[1] - b.t[1]) * k]; };
    const boxAt = (px, py) => B.findIndex((b, i) => py >= b.y0 && py <= b.y1 && px >= edges(i, py)[0] && px <= edges(i, py)[1]);
    const scaleAt = (i, y) => { const b = B[i], k = (y - b.y0) / (b.y1 - b.y0); return b.s0 + (b.s1 - b.s0) * k; };
    let show = true, pos = { x: 96, y: 100, box: 0 }, path = [], phase = 0, dir = 1;
    const off = document.createElement("canvas"); off.width = 24; off.height = 40; const ox = off.getContext("2d");
    function plan(tx, ty) {
      const tb = boxAt(tx, ty); if (tb < 0) { sfx("bad"); return; }
      path = [];
      let b = pos.box;  // boxes are a chain 0-1-2-3: walk through the middle of each shared edge
      while (b !== tb) { const nb = b + Math.sign(tb - b), ey = nb > b ? B[b].y0 : B[b].y1, [l, r] = edges(b, ey); path.push({ x: Math.max(l + 4, Math.min(r - 4, (tx + pos.x) / 2)), y: ey, box: nb }); b = nb; }
      path.push({ x: tx, y: ty, box: tb }); sfx("click");
    }
    function draw() {
      x.fillStyle = "#2a2046"; x.fillRect(0, 0, W, H);
      x.fillStyle = "#3d3078"; x.fillRect(0, 0, W, 50);
      x.fillStyle = "#55489a"; for (let i = 0; i < W; i += 24) x.fillRect(i, 0, 2, 50);
      x.fillStyle = "#120d24"; x.fillRect(84, 26, 16, 26);                          // far doorway
      // floor in perspective
      x.fillStyle = "#6d4a35"; x.beginPath(); x.moveTo(84, 40); x.lineTo(100, 40); x.lineTo(192, 106); x.lineTo(192, 108); x.lineTo(0, 108); x.lineTo(0, 106); x.closePath(); x.fill();
      x.strokeStyle = "#5d3e2c"; for (let k = 0; k < 8; k++) { const xb = k * 192 / 7; x.beginPath(); x.moveTo(84 + k * 16 / 7, 40); x.lineTo(xb, 108); x.stroke(); }
      if (show) B.forEach((b, i) => {
        x.fillStyle = i === pos.box ? "rgba(255,181,71,.28)" : "rgba(79,214,200,.16)"; x.strokeStyle = "#4fd6c8";
        x.beginPath(); x.moveTo(b.t[0], b.y0); x.lineTo(b.t[1], b.y0); x.lineTo(b.b[1], b.y1); x.lineTo(b.b[0], b.y1); x.closePath(); x.fill(); x.stroke();
        x.fillStyle = "#f3e6c8"; x.font = "7px monospace"; x.fillText("×" + b.s1.toFixed(2), b.b[1] - 26, b.y1 - 2);
      });
      if (show && path.length) { x.strokeStyle = "#ffb547"; x.setLineDash([2, 2]); x.beginPath(); x.moveTo(pos.x, pos.y); path.forEach(p => x.lineTo(p.x, p.y)); x.stroke(); x.setLineDash([]); }
      // character drawn at 1:1 then scaled
      ox.clearRect(0, 0, 24, 40);
      if (PCM.Chars) PCM.Chars.draw(ox, "visitor", 12, 37, { dir, walking: path.length > 0, phase });
      const s = scaleAt(pos.box, pos.y), w = Math.round(24 * s), h = Math.round(40 * s);
      x.imageSmoothingEnabled = false; x.drawImage(off, Math.round(pos.x - w / 2), Math.round(pos.y - h + 3 * s), w, h);
    }
    function step() {
      if (path.length) {
        const p = path[0], dx = p.x - pos.x, dy = p.y - pos.y, d = Math.hypot(dx, dy), v = 0.9 * scaleAt(pos.box, pos.y);
        if (d <= v) { pos.x = p.x; pos.y = p.y; pos.box = p.box; path.shift(); }
        else { pos.x += dx / d * v; pos.y += dy / d * v; dir = dx < 0 ? -1 : 1; phase = (phase + v / 12) % 1; const bb = boxAt(pos.x, pos.y); if (bb >= 0) pos.box = bb; }
      }
      draw(); requestAnimationFrame(step);
    }
    cv.addEventListener("click", e => { const r = cv.getBoundingClientRect(); plan((e.clientX - r.left) / r.width * W, (e.clientY - r.top) / r.height * H); });
    $("#wbBoxes").addEventListener("click", e => { show = !show; e.currentTarget.setAttribute("aria-pressed", String(show)); sfx("click"); });
    if (reduce) { draw(); cv.addEventListener("click", () => { while (path.length) { const p = path.shift(); Object.assign(pos, p); } draw(); }); }
    else requestAnimationFrame(step);
  })();

  /* ================= Priority screen (Sierra AGI/SCI) ================= */
  if ($("#prCanvas")) (() => {
    const cv = $("#prCanvas"), x = cv.getContext("2d"), W = cv.width, H = cv.height;
    // EGA palette, as AGI used it
    const EGA = ["#000000", "#0000aa", "#00aa00", "#00aaaa", "#aa0000", "#aa00aa", "#aa5500", "#aaaaaa", "#555555", "#5555ff", "#55ff55", "#55ffff", "#ff5555", "#ff55ff", "#ffff55", "#ffffff"];
    const HORIZON = 36;
    const band = y => y < HORIZON ? 4 : Math.min(15, 5 + Math.floor((y - HORIZON) / ((H - HORIZON) / 11)));  // 4..15 like AGI
    const objects = [  // things standing in the scene, with their base line (their priority comes from it)
      { kind: "tree", x: 40, base: 70 }, { kind: "tree", x: 120, base: 88 }, { kind: "fence", x: 66, base: 58, w: 46 },
    ];
    const pond = { x: 100, y: 46, w: 44, h: 10 };  // water, with a barrier line around it on the priority screen
    let showPri = false, ego = { x: 30, y: 92, tx: 30, ty: 92, phase: 0, dir: 1 };
    const off = document.createElement("canvas"); off.width = 24; off.height = 40; const ox = off.getContext("2d");
    function drawObj(o, pri) {
      if (o.kind === "tree") {
        if (pri) { x.fillStyle = EGA[band(o.base)]; x.fillRect(o.x - 3, o.base - 30, 6, 30); x.beginPath(); x.arc(o.x, o.base - 34, 12, 0, 7); x.fill(); return; }
        x.fillStyle = "#6b3f22"; x.fillRect(o.x - 3, o.base - 30, 6, 30);
        x.fillStyle = "#1f7a3a"; x.beginPath(); x.arc(o.x, o.base - 34, 12, 0, 7); x.fill();
        x.fillStyle = "#2fa04a"; x.beginPath(); x.arc(o.x - 4, o.base - 38, 6, 0, 7); x.fill();
      } else {
        x.fillStyle = pri ? EGA[band(o.base)] : "#c9b37a";
        for (let i = 0; i < o.w; i += 6) x.fillRect(o.x + i, o.base - 12, 2, 12);
        x.fillRect(o.x, o.base - 10, o.w, 2); x.fillRect(o.x, o.base - 5, o.w, 2);
      }
    }
    const blocked = (px, py) => px >= pond.x - 2 && px <= pond.x + pond.w + 2 && py >= pond.y - 2 && py <= pond.y + pond.h + 2;
    function draw() {
      if (showPri) {
        for (let y = 0; y < H; y++) { x.fillStyle = EGA[band(y)]; x.fillRect(0, y, W, 1); }
        x.fillStyle = EGA[3]; x.fillRect(pond.x, pond.y, pond.w, pond.h);                 // 3 = water
        x.strokeStyle = EGA[0]; x.lineWidth = 1; x.strokeRect(pond.x - 1.5, pond.y - 1.5, pond.w + 3, pond.h + 3);  // 0 = barrier
        objects.forEach(o => drawObj(o, true));
      } else {
        x.fillStyle = "#55ffff"; x.fillRect(0, 0, W, HORIZON);
        x.fillStyle = "#00aa00"; x.fillRect(0, HORIZON, W, H - HORIZON);
        x.fillStyle = "#55ff55"; for (let i = 0; i < 40; i++) x.fillRect((i * 37) % W, HORIZON + ((i * 23) % (H - HORIZON)), 2, 1);
        x.fillStyle = "#0000aa"; x.fillRect(pond.x, pond.y, pond.w, pond.h); x.fillStyle = "#5555ff"; x.fillRect(pond.x + 6, pond.y + 3, 12, 1);
        objects.forEach(o => drawObj(o, false));
      }
      // ego: drawn, then every object with a higher priority band is drawn again on top of it
      ox.clearRect(0, 0, 24, 40);
      if (PCM.Chars) PCM.Chars.draw(ox, "visitor", 12, 37, { dir: ego.dir, walking: ego.x !== ego.tx || ego.y !== ego.ty, phase: ego.phase });
      const s = 0.55 + 0.45 * (ego.y - HORIZON) / (H - HORIZON);
      const w = Math.round(24 * s), h = Math.round(40 * s);
      x.imageSmoothingEnabled = false; x.drawImage(off, Math.round(ego.x - w / 2), Math.round(ego.y - h + 3 * s), w, h);
      objects.filter(o => band(o.base) > band(ego.y)).forEach(o => drawObj(o, showPri));
      if (showPri) { x.fillStyle = "#ffffff"; x.font = "7px monospace"; x.fillText("ego: " + band(ego.y), 3, 9); }
    }
    function step() {
      const dx = ego.tx - ego.x, dy = ego.ty - ego.y, d = Math.hypot(dx, dy);
      if (d > 0.6) {
        const nx = ego.x + dx / d * 0.8, ny = ego.y + dy / d * 0.8;
        if (blocked(nx, ny)) { ego.tx = ego.x; ego.ty = ego.y; } else { ego.x = nx; ego.y = ny; ego.dir = dx < 0 ? -1 : 1; ego.phase = (ego.phase + 0.07) % 1; }
      } else { ego.x = ego.tx; ego.y = ego.ty; }
      draw(); requestAnimationFrame(step);
    }
    cv.addEventListener("click", e => { const r = cv.getBoundingClientRect(); ego.tx = (e.clientX - r.left) / r.width * W; ego.ty = Math.max(HORIZON + 4, (e.clientY - r.top) / r.height * H); cv.focus({ preventScroll: true }); });
    cv.addEventListener("keydown", e => {
      const k = { ArrowLeft: [-8, 0], ArrowRight: [8, 0], ArrowUp: [0, -6], ArrowDown: [0, 6] }[e.key]; if (!k) return;
      e.preventDefault(); ego.tx = Math.max(4, Math.min(W - 4, ego.x + k[0])); ego.ty = Math.max(HORIZON + 4, Math.min(H - 2, ego.y + k[1]));
    });
    $("#prToggle").addEventListener("click", e => { showPri = !showPri; e.currentTarget.setAttribute("aria-pressed", String(showPri)); sfx("click"); if (reduce) draw(); });
    if (reduce) { draw(); cv.addEventListener("click", () => { ego.x = ego.tx; ego.y = ego.ty; draw(); }); } else requestAnimationFrame(step);
  })();

  /* ================= CGA / EGA / VGA on a real screenshot ================= */
  if ($("#palCanvas")) (() => {
    const P = D.techniques.demos.palette, cv = $("#palCanvas"), x = cv.getContext("2d", { willReadFrequently: true });
    if (!P.media) { $("#tech-palette").hidden = true; return; }
    $("#palCredit").innerHTML = mediaFigure(P.media, P.title, "pal-credit").replace(/<img[^>]*>/, "");
    const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
    const PAL = {
      cga: ["#000000", "#55ffff", "#ff55ff", "#ffffff"].map(hex),                 // CGA palette 1, high intensity
      ega: ["#000000", "#0000aa", "#00aa00", "#00aaaa", "#aa0000", "#aa00aa", "#aa5500", "#aaaaaa", "#555555", "#5555ff", "#55ff55", "#55ffff", "#ff5555", "#ff55ff", "#ffff55", "#ffffff"].map(hex),
    };
    const img = new Image(); let orig = null;
    img.onload = () => { cv.width = img.naturalWidth; cv.height = img.naturalHeight; x.drawImage(img, 0, 0); orig = x.getImageData(0, 0, cv.width, cv.height); };
    img.src = P.media.src;
    function render(mode) {
      if (!orig) return;
      if (mode === "vga") { x.putImageData(orig, 0, 0); return; }
      const pal = PAL[mode], out = new ImageData(new Uint8ClampedArray(orig.data), orig.width, orig.height), d = out.data, cache = new Map();
      for (let i = 0; i < d.length; i += 4) {
        const key = (d[i] >> 2) << 12 | (d[i + 1] >> 2) << 6 | d[i + 2] >> 2;
        let c = cache.get(key);
        if (!c) { let best = 1e9; for (const p of pal) { const e = (d[i] - p[0]) ** 2 * 0.3 + (d[i + 1] - p[1]) ** 2 * 0.59 + (d[i + 2] - p[2]) ** 2 * 0.11; if (e < best) { best = e; c = p; } } cache.set(key, c); }
        d[i] = c[0]; d[i + 1] = c[1]; d[i + 2] = c[2];
      }
      x.putImageData(out, 0, 0);
    }
    $$("#palModes button").forEach(b => b.addEventListener("click", () => {
      $$("#palModes button").forEach(o => o.setAttribute("aria-pressed", String(o === b))); render(b.dataset.mode); sfx("click");
    }));
  })();
})();
