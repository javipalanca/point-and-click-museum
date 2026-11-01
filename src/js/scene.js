/* Point and Click Museum · scene renderer for data-driven rooms + the procedural attic of the pixel hunt.
   Scene primitives (data/minigames/restoration-room.json → "scene"):
     { "r": [x,y,w,h], "c": "#hex" }                      filled rect
     { "stripes": [x,y,w,h], "step": 20, "size": 10 }     vertical stripes
     { "grad": [x,y,w,h], "from": "#hex", "to": "#hex" }  vertical dithered gradient
     { "books": [x,y,w,h], "seed": 3, "colors": [...] }   a row of book spines
     { "sprite": "name", "at": [x,y], "scale": 1 }        sprite from data/sprites.json
     { "glow": [cx,cy,radius], "rgb": "255,181,71", "a": 0.3 } soft light
     { "px": [[x,y],...], "c": "#hex" }                   loose pixels
   Any primitive accepts "if" (conditions), "hot" (spot id or list) and "hc" (hover colour). */
"use strict";
PCM.Scene = (() => {
  const { rng, drawSprite } = PCM;
  const R = PCM.Rules;
  const BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]];
  const hex = h => { const n = parseInt(h.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; };
  const mix = (a, b, t) => "rgb(" + a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(",") + ")";

  function grad(x, rect, from, to, steps = 6) {
    const [gx, gy, gw, gh] = rect, a = hex(from), b = hex(to);
    for (let j = 0; j < gh; j++) {
      const t = j / Math.max(1, gh - 1) * (steps - 1), lo = Math.floor(t), f = t - lo;
      for (let i = 0; i < gw; i += 1) {
        const k = Math.min(steps - 1, lo + (f > BAYER[j % 4][i % 4] / 16 ? 1 : 0));
        x.fillStyle = mix(a, b, k / (steps - 1)); x.fillRect(gx + i, gy + j, 1, 1);
      }
    }
  }
  function books(x, rect, seed, colors) {
    const [bx, by, bw, bh] = rect, r = rng(seed || 1); let i = bx;
    while (i < bx + bw - 2) {
      const w = 2 + Math.floor(r() * 3), h = bh - Math.floor(r() * (bh / 3));
      if (i + w > bx + bw) break;
      const c = colors[Math.floor(r() * colors.length)];
      if (r() < 0.12 && i + h < bx + bw) { // a book lying flat
        x.fillStyle = "#14101f"; x.fillRect(i, by + bh - 3, h, 3); x.fillStyle = c; x.fillRect(i, by + bh - 3, h - 1, 2); i += h + 1; continue;
      }
      x.fillStyle = "#14101f"; x.fillRect(i, by + bh - h, w + 1, h);
      x.fillStyle = c; x.fillRect(i, by + bh - h, w, h);
      x.fillStyle = "rgba(255,255,255,.18)"; x.fillRect(i, by + bh - h, 1, h);
      x.fillStyle = "rgba(0,0,0,.25)"; x.fillRect(i, by + bh - h + 2, w, 1); x.fillRect(i, by + bh - 3, w, 1);
      i += w + 1;
    }
  }
  function glow(x, cx, cy, rad, rgb, a) {
    const g = x.createRadialGradient(cx, cy, 0, cx, cy, rad);
    g.addColorStop(0, "rgba(" + rgb + "," + a + ")"); g.addColorStop(1, "rgba(" + rgb + ",0)");
    x.fillStyle = g; x.fillRect(cx - rad, cy - rad, rad * 2, rad * 2);
  }
  const cache = new WeakMap();
  function render(x, list, S, hoverId) {
    list.forEach(s => {
      if (s.if && !R.all(s.if, S)) return;
      const hot = s.hot && hoverId && [].concat(s.hot).includes(hoverId);
      const col = hot && s.hc ? s.hc : s.c;
      if (s.r) { x.fillStyle = col; x.fillRect(s.r[0], s.r[1], s.r[2], s.r[3]); }
      else if (s.stripes) { const [sx, sy, sw, sh] = s.stripes; x.fillStyle = col; for (let i = sx; i < sx + sw; i += s.step) x.fillRect(i, sy, Math.min(s.size, sx + sw - i), sh); }
      else if (s.grad || s.books) { // static: cache to an offscreen canvas
        let c = cache.get(s);
        if (!c) {
          const [gx, gy, gw, gh] = s.grad || s.books; c = document.createElement("canvas"); c.width = gx + gw; c.height = gy + gh;
          const cx = c.getContext("2d");
          if (s.grad) grad(cx, s.grad, s.from, s.to, s.steps); else books(cx, s.books, s.seed, s.colors);
          cache.set(s, c);
        }
        x.drawImage(c, 0, 0);
      }
      else if (s.sprite) drawSprite(x, s.sprite, s.at[0], s.at[1], s.scale || 1);
      else if (s.glow) glow(x, s.glow[0], s.glow[1], s.glow[2], s.rgb || "255,181,71", s.a || 0.25);
      else if (s.px) { x.fillStyle = col; s.px.forEach(([px, py]) => x.fillRect(px, py, 1, 1)); }
    });
  }

  /* ---------------- procedural attic for the pixel hunt ---------------- */
  function crate(x, px, py, w, h, r) {
    const wood = ["#8a5a35", "#7a4e2c", "#946640"][Math.floor(r() * 3)];
    x.fillStyle = "#1a1022"; x.fillRect(px - 1, py - 1, w + 2, h + 2);
    x.fillStyle = wood; x.fillRect(px, py, w, h);
    x.fillStyle = "rgba(0,0,0,.22)"; for (let j = py + 3; j < py + h; j += 4) x.fillRect(px, j, w, 1);
    x.fillStyle = "#5a3820"; x.fillRect(px, py, 2, h); x.fillRect(px + w - 2, py, 2, h); x.fillRect(px, py, w, 2);
    x.fillStyle = "rgba(255,255,255,.14)"; x.fillRect(px + 2, py + 2, w - 4, 1);
    if (w > 14 && r() > 0.4) { x.fillStyle = "rgba(20,16,31,.55)"; x.fillRect(px + Math.floor(w / 2) - 3, py + Math.floor(h / 2) - 1, 6, 1); x.fillRect(px + Math.floor(w / 2) - 2, py + Math.floor(h / 2) + 1, 4, 1); }
    if (r() > 0.6) { x.fillStyle = "#c9b98f"; x.fillRect(px + Math.floor(w / 2) - 1, py, 3, h); }
  }
  function trunk(x, px, py) {
    x.fillStyle = "#1a1022"; x.fillRect(px - 1, py - 1, 30, 18);
    x.fillStyle = "#5e1f34"; x.fillRect(px, py, 28, 16); x.fillStyle = "#8a2f4a"; x.fillRect(px, py, 28, 6);
    x.fillStyle = "#c47a1e"; x.fillRect(px, py + 6, 28, 1); x.fillRect(px + 5, py, 2, 16); x.fillRect(px + 21, py, 2, 16);
    x.fillStyle = "#ffb547"; x.fillRect(px + 13, py + 5, 3, 3);
  }
  function monitor(x, px, py, tick) {
    x.fillStyle = "#1a1022"; x.fillRect(px - 1, py - 1, 20, 17);
    x.fillStyle = "#c9c4b0"; x.fillRect(px, py, 18, 15); x.fillStyle = "#a29d88"; x.fillRect(px, py + 12, 18, 3);
    x.fillStyle = "#0b2a1c"; x.fillRect(px + 2, py + 2, 14, 9);
    x.fillStyle = "#3fbf80"; x.fillRect(px + 3, py + 3, 6, 1); x.fillRect(px + 3, py + 5, 9, 1); x.fillRect(px + 3, py + 7, 4, 1);
    x.fillStyle = "#d9455f"; x.fillRect(px + 14, py + 13, 1, 1);
  }
  function bottle(x, px, py, c) {
    x.fillStyle = "#1a1022"; x.fillRect(px - 1, py + 2, 6, 9); x.fillRect(px, py - 1, 4, 4);
    x.fillStyle = c; x.fillRect(px, py + 3, 4, 7); x.fillRect(px + 1, py, 2, 3);
    x.fillStyle = "rgba(255,255,255,.4)"; x.fillRect(px + 1, py + 4, 1, 4);
  }
  function frame(x, px, py, w, h, r) {
    x.fillStyle = "#1a1022"; x.fillRect(px - 1, py - 1, w + 2, h + 2);
    x.fillStyle = "#c47a1e"; x.fillRect(px, py, w, h);
    x.fillStyle = ["#2a1d5c", "#2f7d46", "#3f6fd8"][Math.floor(r() * 3)]; x.fillRect(px + 2, py + 2, w - 4, h - 4);
    x.fillStyle = "#f3e6c8"; x.fillRect(px + w - 6, py + 4, 2, 2);
  }
  function lampProp(x, px, py) {
    x.fillStyle = "#1a1022"; x.fillRect(px + 3, py + 8, 2, 14); x.fillRect(px, py + 22, 8, 2);
    x.fillStyle = "#1a1022"; x.fillRect(px - 2, py - 1, 12, 10);
    x.fillStyle = "#e07a2e"; x.fillRect(px - 1, py, 10, 8); x.fillStyle = "#ffb547"; x.fillRect(px, py + 6, 8, 2);
  }
  function floppy(x, px, py) { /* the 7×7 golden floppy */
    x.fillStyle = "#6e4a10"; x.fillRect(px - 1, py - 1, 9, 9);
    x.fillStyle = "#ffb547"; x.fillRect(px, py, 7, 7);
    x.fillStyle = "#ffd27a"; x.fillRect(px, py, 7, 1);
    x.fillStyle = "#a8a4c4"; x.fillRect(px + 2, py, 3, 2); x.fillStyle = "#14101f"; x.fillRect(px + 3, py, 1, 1);
    x.fillStyle = "#f3e6c8"; x.fillRect(px + 1, py + 4, 5, 2);
  }
  function decoy(x, px, py, r) {
    const k = Math.floor(r() * 4);
    if (k === 0) { x.fillStyle = "#6e4a10"; x.fillRect(px - 1, py - 1, 5, 5); x.fillStyle = "#ffb547"; x.fillRect(px, py, 3, 3); }          // coin
    else if (k === 1) { x.fillStyle = "#ffb547"; x.fillRect(px, py, 3, 2); x.fillRect(px + 3, py + 1, 3, 1); }                                // key
    else if (k === 2) { x.fillStyle = "#6e4a10"; x.fillRect(px - 1, py - 1, 8, 6); x.fillStyle = "#e0b040"; x.fillRect(px, py, 6, 4); }   // brass plate
    else { x.fillStyle = "#3f6fd8"; x.fillRect(px - 1, py - 1, 8, 8); x.fillStyle = "#1b2a6b"; x.fillRect(px, py, 6, 6); x.fillStyle = "#a8a4c4"; x.fillRect(px + 2, py, 2, 2); } // blue floppy
  }
  /* returns { bg: canvas, target: {x,y}, shaft: [...] } */
  function attic(W, H, seed, round, cfg) {
    const c = document.createElement("canvas"); c.width = W; c.height = H; const x = c.getContext("2d"); const r = rng(seed);
    const floorY = Math.round(H * 0.66);
    grad(x, [0, 0, W, floorY], "#231a40", "#3a2a52", 5);
    // plank wall
    x.fillStyle = "rgba(0,0,0,.18)"; for (let i = 0; i < W; i += 18) x.fillRect(i, 0, 1, floorY);
    x.fillStyle = "rgba(255,255,255,.05)"; for (let i = 9; i < W; i += 18) for (let j = 6 + (i % 7); j < floorY; j += 23) x.fillRect(i, j, 1, 1);
    // sloped roof beams
    x.fillStyle = "#3a2414";
    for (let j = 0; j < 40; j++) { x.fillRect(0, j, Math.max(0, 70 - j * 1.8), 1); x.fillRect(W - Math.max(0, 70 - j * 1.8), j, Math.max(0, 70 - j * 1.8), 1); }
    x.fillStyle = "#5a3820"; x.fillRect(0, 10, W, 5); x.fillStyle = "#6e4428"; x.fillRect(0, 10, W, 1); x.fillStyle = "#2a1a10"; x.fillRect(0, 15, W, 1);
    [60, 160, 260].forEach(bx => { x.fillStyle = "#4a2e18"; x.fillRect(bx - 3, 16, 6, floorY - 16); x.fillStyle = "#5a3820"; x.fillRect(bx - 3, 16, 1, floorY - 16); });
    // round window
    const wx = 160, wy = 34;
    for (let j = -12; j <= 12; j++) { const w = Math.floor(Math.sqrt(144 - j * j)); x.fillStyle = "#1a1022"; x.fillRect(wx - w - 2, wy + j, w * 2 + 5, 1); }
    for (let j = -10; j <= 10; j++) { const w = Math.floor(Math.sqrt(100 - j * j)); x.fillStyle = j < 0 ? "#1b2a6b" : "#2343a0"; x.fillRect(wx - w, wy + j, w * 2 + 1, 1); }
    x.fillStyle = "#f3e6c8"; x.fillRect(wx + 3, wy - 6, 3, 3); x.fillStyle = "#5a3820"; x.fillRect(wx, wy - 10, 1, 21); x.fillRect(wx - 10, wy, 21, 1);
    // floor
    grad(x, [0, floorY, W, H - floorY], "#4a2e18", "#2a1a10", 4);
    x.fillStyle = "rgba(0,0,0,.25)"; for (let j = floorY + 4; j < H; j += 6) x.fillRect(0, j, W, 1);
    x.fillStyle = "rgba(255,255,255,.06)"; for (let j = floorY + 4; j < H; j += 6) for (let i = (j * 7) % 40; i < W; i += 40) x.fillRect(i, j - 5, 1, 5);
    x.fillStyle = "#1a1022"; x.fillRect(0, floorY, W, 1);
    // shelves
    const shelves = [[6, 44, 52], [6, 76, 52], [262, 52, 52]];
    const slots = [];
    shelves.forEach(([sx, sy, sw], k) => {
      books(x, [sx, sy - 14, sw, 14], seed + k * 7, ["#d9455f", "#3f6fd8", "#2f7d46", "#8a4fd8", "#c47a1e", "#a8a4c4", "#5e1f34"]);
      x.fillStyle = "#1a1022"; x.fillRect(sx - 1, sy, sw + 2, 4); x.fillStyle = "#8a5a35"; x.fillRect(sx, sy, sw, 2); x.fillStyle = "#5a3820"; x.fillRect(sx, sy + 2, sw, 1);
      slots.push([sx + 6 + Math.floor(r() * (sw - 14)), sy - 8]);
    });
    // cobwebs
    const web = (cx, cy, dx) => { x.fillStyle = "rgba(220,215,240,.35)"; for (let k = 0; k < 14; k++) { x.fillRect(cx + dx * k, cy + k, 1, 1); x.fillRect(cx + dx * k, cy, 1, 1); x.fillRect(cx, cy + k, 1, 1); } for (let k = 4; k < 14; k += 4) for (let q = 0; q <= k; q++) x.fillRect(cx + dx * q, cy + k - Math.round(q * 0.9), 1, 1); };
    web(70, 16, 1); web(W - 71, 16, -1);
    // props on the floor, back to front
    const n = cfg.clutter.base + round * cfg.clutter.perRound;
    const items = [];
    for (let k = 0; k < n; k++) items.push({ y: floorY - 6 + Math.floor(r() * (H - floorY - 6)), x: Math.floor(r() * (W - 30)), k: r() });
    items.sort((a, b) => a.y - b.y);
    const sprites = ["book", "gear", "cd", "skull", "crown", "note", "eye", "robot", "heart", "house", "terminal", "sword"];
    items.forEach(it => {
      const h0 = it.y;
      if (it.k < 0.34) { const w = 14 + Math.floor(r() * 16), h = 10 + Math.floor(r() * 14); crate(x, it.x, h0 - h, w, h, r); slots.push([it.x + 3 + Math.floor(r() * (w - 10)), h0 - h - 8]); }
      else if (it.k < 0.42) { trunk(x, it.x, h0 - 16); slots.push([it.x + 10, h0 - 24]); }
      else if (it.k < 0.48) monitor(x, it.x, h0 - 15, 0);
      else if (it.k < 0.58) { const s = sprites[Math.floor(r() * sprites.length)]; drawSprite(x, s, it.x, h0 - 12, 1); }
      else if (it.k < 0.68) bottle(x, it.x, h0 - 11, ["#2f7d46", "#3f6fd8", "#8a4fd8", "#d9455f"][Math.floor(r() * 4)]);
      else if (it.k < 0.76) frame(x, it.x, h0 - 18, 14 + Math.floor(r() * 8), 16, r);
      else if (it.k < 0.8) lampProp(x, it.x, h0 - 24);
      else { books(x, [it.x, h0 - 10, 18, 10], Math.floor(r() * 1e6), ["#d9455f", "#3f6fd8", "#2f7d46", "#c47a1e", "#a8a4c4"]); slots.push([it.x + 4, h0 - 18]); }
      slots.push([it.x + Math.floor(r() * 20), h0 + 1]);
    });
    for (let k = 0; k < cfg.clutter.decoys + round * cfg.clutter.decoysPerRound; k++) {
      const s = slots[Math.floor(r() * slots.length)]; decoy(x, s[0] + Math.floor(r() * 8) - 4, s[1] + Math.floor(r() * 4), r);
    }
    const valid = slots.filter(([sx, sy]) => sx > 4 && sx < W - 12 && sy > 20 && sy < H - 10);
    const [tx, ty] = valid[Math.floor(r() * valid.length)];
    floppy(x, tx, ty);
    // dust and dirt on top
    x.fillStyle = "rgba(255,240,200,.05)"; for (let k = 0; k < 400; k++) x.fillRect(Math.floor(r() * W), Math.floor(r() * H), 1, 1);
    return { bg: c, target: { x: tx, y: ty }, window: [wx, wy] };
  }
  return { render, attic, glow, grad, floppy };
})();
