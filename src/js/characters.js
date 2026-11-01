/* Point and Click Museum · pixel characters (data/characters.json).
   Head and torso are hand-drawn rows; legs are drawn procedurally so the walk cycle is smooth.
   PCM.Chars.actor(name) returns a small state machine with walkTo(), update() and draw(). */
"use strict";
PCM.Chars = (() => {
  const C = (PCM.D.characters || {});
  const W = 16;

  function blit(ctx, rows, pal, x0, y0, flip) {
    for (let j = 0; j < rows.length; j++) {
      const row = rows[j];
      for (let i = 0; i < row.length; i++) {
        const ch = row[i]; if (ch === "." || !pal[ch]) continue;
        ctx.fillStyle = pal[ch]; ctx.fillRect(x0 + (flip ? row.length - 1 - i : i), y0 + j, 1, 1);
      }
    }
  }
  function leg(ctx, pal, L, hx, hy, footDx, lift, dir, back) {
    const len = L.length, out = pal[L.outline], col = pal[back ? L.shade : L.leg], sh = pal[L.shade];
    for (let i = 0; i <= len; i++) {
      const x = Math.round(hx + footDx * (i / len)), y = hy + i - (i === len ? lift : 0);
      ctx.fillStyle = out; ctx.fillRect(x - 1, y, 5, 1);
      ctx.fillStyle = col; ctx.fillRect(x, y, 3, 1);
      if (!back) { ctx.fillStyle = sh; ctx.fillRect(dir > 0 ? x : x + 2, y, 1, 1); }
    }
    const fx = Math.round(hx + footDx), fy = hy + len + 1 - lift;
    const sx = dir > 0 ? fx - 1 : fx - 2;
    ctx.fillStyle = out; ctx.fillRect(sx - 1, fy - 1, 7, 3);
    ctx.fillStyle = pal[back ? L.shoeHi : L.shoe]; ctx.fillRect(sx, fy - 1, 5, 2);
    ctx.fillStyle = pal[L.shoeHi]; ctx.fillRect(dir > 0 ? sx + 3 : sx, fy - 1, 2, 1);
  }
  /* draw a character with its feet at (cx, footY) */
  function draw(ctx, name, cx, footY, o = {}) {
    const c = C.characters && C.characters[name]; if (!c) return;
    const dir = o.dir || 1, flip = dir < 0, L = c.legs, pal = c.palette;
    const walking = !!o.walking, ph = (o.phase || 0) * Math.PI * 2, sw = walking ? Math.sin(ph) : 0;
    const bob = walking && Math.abs(Math.cos(ph)) > 0.7 ? -1 : 0;
    const height = L.hipY + L.length + 2;
    const x0 = Math.round(cx - W / 2), y0 = Math.round(footY - height) + bob;
    // shadow
    ctx.fillStyle = "rgba(0,0,0,.28)"; ctx.fillRect(x0 + 2, footY, W - 3, 1); ctx.fillRect(x0 + 4, footY + 1, W - 7, 1);
    const hips = flip ? L.hips.map(h => W - 3 - h) : L.hips;
    const stride = L.stride * dir;
    const fa = walking ? sw * stride : -1 * dir, fb = walking ? -sw * stride : 1 * dir;
    const la = walking && Math.cos(ph) > 0.3 ? 1 : 0, lb = walking && Math.cos(ph) < -0.3 ? 1 : 0;
    leg(ctx, pal, L, x0 + hips[0], y0 + L.hipY - 1, fb, lb, dir, true);
    leg(ctx, pal, L, x0 + hips[1], y0 + L.hipY - 1, fa, la, dir, false);
    let rows = c.art;
    if ((o.talking && c.talk) || (o.blink && c.blink)) {
      rows = rows.slice();
      if (o.blink && c.blink) Object.entries(c.blink).forEach(([k, v]) => { rows[+k] = v; });
      if (o.talking && c.talk) Object.entries(c.talk).forEach(([k, v]) => { rows[+k] = v; });
    }
    blit(ctx, rows, pal, x0, y0, flip);
  }
  /* a walking actor: x in scene units; speed px/frame */
  function actor(name, x, footY, speed = 1.2) {
    const a = { name, x, tx: x, footY, dir: 1, phase: 0, talkUntil: 0, blinkAt: 0, speed };
    a.moving = () => a.x !== a.tx;
    a.walkTo = tx => { a.tx = Math.round(tx); };
    a.say = ms => { a.talkUntil = performance.now() + ms; };
    a.update = () => {
      if (a.x !== a.tx) {
        const d = Math.sign(a.tx - a.x); a.dir = d; a.x += d * a.speed; a.phase = (a.phase + a.speed / 14) % 1;
        if ((d > 0 && a.x >= a.tx) || (d < 0 && a.x <= a.tx)) { a.x = a.tx; a.phase = 0; }
        return true;
      }
      return false;
    };
    a.draw = ctx => {
      const now = performance.now();
      if (now > a.blinkAt + 160 && Math.random() < 0.004) a.blinkAt = now;
      draw(ctx, name, a.x, a.footY, { dir: a.dir, walking: a.moving(), phase: a.phase,
        talking: now < a.talkUntil && Math.floor(now / 140) % 2 === 0, blink: now - a.blinkAt < 140 });
    };
    a.busy = () => a.moving() || performance.now() < a.talkUntil;
    return a;
  }
  function cat(ctx, x, y, frame) {
    const k = C.cat; if (!k) return;
    blit(ctx, k.frames[frame % k.frames.length], k.palette, x, y, false);
  }
  return { draw, actor, cat };
})();
