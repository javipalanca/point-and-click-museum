/* Point and Click Museum · interface lab (techniques room).
   One small original scene played with the real interfaces of famous adventures: Zork's parser, the SCUMM verb
   bars of Maniac Mansion and Monkey Island 1–2, Full Throttle's emblem menu, The Curse of Monkey Island's verb coin,
   Broken Sword's two-button cursor and Machinarium's single click. Data: data/techniques.json → interfaces, lab. */
"use strict";
(() => {
  const { D, $, $$, t, esc, sfx, award, mediaFigure } = PCM;
  if (!$("#uiTabs") || !D.techniques || !D.techniques.lab) return;
  const UI = D.techniques.interfaces, LAB = D.techniques.lab, G = LAB.generic, OBJ = LAB.objects;
  const W = 256, H = 128, FLOOR = 112;

  /* ---------------------------------------------------------------- scene state */
  const HOT = {  // hotspots in scene pixels; walkX = where the player stands to act
    door: { x: 22, y: 38, w: 34, h: 58, walkX: 62 },
    painting: { x: 106, y: 28, w: 44, h: 34, walkX: 128 },
    key: { x: 172, y: 104, w: 12, h: 8, walkX: 168 },
    curator: { x: 214, y: 78, w: 18, h: 36, walkX: 196 },
  };
  let S;  // state of the current run
  const reset = () => {
    S = { locked: true, open: false, taken: false, inv: [], held: null, verb: null, first: null, say: "", sayUntil: 0,
          hover: null, mouse: null, coin: null, invOpen: false, bubble: null, pending: null };
    if (P) { P.x = 96; P.tx = 96; P.dir = 1; }
  };
  const P = PCM.Chars ? PCM.Chars.actor("visitor", 96, FLOOR, 1.4) : null;
  const visible = id => !(id === "key" && S.taken);
  const name = id => OBJ[id].name;
  function hit(x, y) {
    for (const id of ["key", "curator", "painting", "door"]) {
      const h = HOT[id];
      if (visible(id) && x >= h.x && x < h.x + h.w && y >= h.y && y < h.y + h.h) return id;
    }
    return null;
  }

  /* ---------------------------------------------------------------- rules: what each action does */
  const say = (txt, ms) => { S.say = txt; S.sayUntil = performance.now() + (ms || Math.max(2200, txt.length * 70)); if (P) P.say(Math.min(2400, txt.length * 45)); };
  function act(action, a, b) {
    const o = a && OBJ[a];
    if (action === "walk" || !o) return;
    if (action === "whatis") return say(o.name);
    if (["read", "fix", "turnon", "newkid"].includes(action)) return say(G[action]);
    if (action === "use" && !b && a === "door") action = "open";
    if (action === "use" && !b && OBJ[a].item && !S.taken) action = "pickup";
    if ((action === "use" || action === "unlock") && ((a === "key" && b === "door") || (a === "door" && b === "key"))) {
      if (!S.locked) return say(G.done);
      S.locked = false; sfx("points"); award("techUi", "lab-door", t("labDoorAward")); return say(OBJ.door.unlock);
    }
    if (action === "unlock" && a === "door") return say(OBJ.door.open);
    if (action === "give") return say(a === "key" && b === "curator" ? OBJ.curator.give : G.default);
    if (action === "pickup" && o.item) {
      if (S.taken) return say(G.default);
      S.taken = true; S.inv.push(a); sfx("click"); renderInv(); return say(o.pickup);
    }
    if (action === "open" && a === "door") {
      if (S.open) return say(G.done);
      if (S.locked) return say(o.open);
      S.open = true; sfx("open"); return say(o.openUnlocked);
    }
    if (action === "close" && a === "door") { if (!S.open) return say(o.close); S.open = false; return say(G.done); }
    if (action === "pull") action = "push";
    say(o[action] || G.default);
  }
  /* walk to the object first, then act (like SCUMM) */
  function perform(action, a, b) {
    const target = b || a;
    if (P && target && HOT[target]) { P.walkTo(HOT[target].walkX); S.pending = () => act(action, a, b); }
    else act(action, a, b);
  }

  /* ---------------------------------------------------------------- drawing */
  let ctx, canvas, cur;
  const px = (x, y, w, h, c) => { ctx.fillStyle = c; ctx.fillRect(x, y, w, h); };
  function drawScene() {
    px(0, 0, W, H, "#3b2f5c");
    for (let y = 0; y < 96; y += 8) px(0, y, W, 1, "#43366a");              // wall panels
    for (let x = 0; x < W; x += 32) px(x, 0, 1, 96, "#33284f");
    px(0, 88, W, 8, "#2a2046");                                              // skirting
    px(0, 96, W, 32, "#6d4a35");                                             // wooden floor
    for (let y = 100; y < H; y += 6) px(0, y, W, 1, "#5d3e2c");
    for (let x = 8; x < W; x += 40) px(x + ((x / 40) % 2) * 12, 96, 1, 32, "#5d3e2c");
    // door
    const d = HOT.door;
    px(d.x - 3, d.y - 3, d.w + 6, d.h + 3, "#2a1d14");
    if (S.open) { px(d.x, d.y, d.w, d.h, "#120d24"); px(d.x, d.y + d.h - 10, d.w, 10, "#1f1944"); px(d.x - 2, d.y, 4, d.h, "#8a5a36"); }
    else {
      px(d.x, d.y, d.w, d.h, "#8a5a36");
      px(d.x + 4, d.y + 4, d.w - 8, 22, "#7a4e2e"); px(d.x + 4, d.y + 30, d.w - 8, 24, "#7a4e2e");
      px(d.x + d.w - 8, d.y + 30, 4, 4, "#e6b84a"); px(d.x + d.w - 7, d.y + 35, 2, 3, "#120d24");
    }
    // painting
    const p = HOT.painting;
    px(p.x, p.y, p.w, p.h, "#c99a2e"); px(p.x + 3, p.y + 3, p.w - 6, p.h - 6, "#2e4a3a");
    px(p.x + 16, p.y + 8, 12, 12, "#e2b48c"); px(p.x + 14, p.y + 6, 16, 4, "#5a3a22");
    px(p.x + 18, p.y + 12, 2, 2, "#120d24"); px(p.x + 24, p.y + 12, 2, 2, "#120d24");
    px(p.x + 12, p.y + 20, 20, 8, "#3a2a5a");
    px(p.x + 2, p.y + p.h, p.w - 4, 2, "#2a2046");
    // key
    if (!S.taken) { const k = HOT.key; px(k.x + 2, k.y + 3, 3, 3, "#ffd75a"); px(k.x + 5, k.y + 4, 6, 1, "#ffd75a"); px(k.x + 8, k.y + 5, 1, 2, "#ffd75a"); px(k.x + 10, k.y + 5, 1, 1, "#ffd75a"); px(k.x + 3, k.y + 4, 1, 1, "#6d4a35"); }
    // characters
    if (PCM.Chars) {
      PCM.Chars.draw(ctx, "curator", HOT.curator.x + 9, FLOOR, { dir: -1 });
      if (P) { if (P.update() === false && S.pending && !P.moving()) { const f = S.pending; S.pending = null; f(); } P.draw(ctx); }
    }
  }
  /* small pixel icons: hand, eyes, mouth, boot, skull, parrot, key, cursors */
  const ICON = {
    hand: ["..XX....", ".XXXX.X.", ".XXXXXXX", "XXXXXXXX", "XXXXXXX.", ".XXXXX..", "..XXX...", "..XXX..."],
    eyes: ["........", ".XX..XX.", "XWWXXWWX", "XWKXXWKX", ".XX..XX.", "........", "........", "........"],
    mouth: ["........", "........", ".XXXXXX.", "XRRRRRRX", "XRWWWWRX", ".XRRRRX.", "..XXXX..", "........"],
    boot: ["..XXX...", "..XXX...", "..XXX...", "..XXX...", "..XXXX..", "..XXXXXX", ".XXXXXXX", ".XXXXXXX"],
    skull: ["..XXXX..", ".XXXXXX.", "XKKXXKKX", "XKKXXKKX", "XXXKKXXX", ".XXXXXX.", ".XKXKXK.", "..XXXX.."],
    parrot: ["...GGG..", "..GGKG..", "..GGGYY.", ".RGGGY..", ".RRGG...", ".RRRG...", "..RR.G..", "..R....."],
    key: ["........", ".YYY....", "Y...YYYY", "Y...Y.YY", ".YYY....", "........", "........", "........"],
    look: ["........", "..XXXX..", ".XWWWWX.", "XWWKKWWX", ".XWWWWX.", "..XXXX..", "........", "........"],
    talk: [".XXXXXX.", "XWWWWWWX", "XWKWKWKX", "XWWWWWWX", ".XXXXXX.", "...XX...", "..X.....", "........"],
    question: ["..XXXX..", ".XX..XX.", ".....XX.", "....XX..", "...XX...", "...XX...", "........", "...XX..."],
    door: ["..XXXX..", ".XXXXXX.", ".XXXXXX.", ".XXXXYX.", ".XXXXXX.", ".XXXXXX.", ".XXXXXX.", "XXXXXXXX"],
    arrow: ["X.......", "XX......", "XWX.....", "XWWX....", "XWWWX...", "XWWXX...", "XXWX....", "...X...."],
  };
  const COLORS = { X: null, W: "#f3e6c8", K: "#120d24", R: "#c43a3a", G: "#3fbf4f", Y: "#ffd75a" };
  function icon(name, x, y, color, scale) {
    const rows = ICON[name], s = scale || 1;
    rows.forEach((r, j) => { for (let i = 0; i < r.length; i++) { const c = r[i]; if (c === ".") continue; ctx.fillStyle = c === "X" ? color : COLORS[c]; ctx.fillRect(x + i * s, y + j * s, s, s); } });
  }
  function disc(cx, cy, r, c) { ctx.fillStyle = c; for (let y = -r; y <= r; y++) { const w = Math.floor(Math.sqrt(r * r - y * y)); ctx.fillRect(cx - w, cy + y, w * 2 + 1, 1); } }
  /* Full Throttle: a flaming ring topped by a skull (eyes / mouth), fist on the left, boot on the right */
  const COIN_ZONES = {
    ft: { r: 22, zones: { eyes: [0, -11, 7], mouth: [0, 0, 6], hand: [-27, 4, 10], boot: [27, 4, 10] } },
    cmi: { r: 27, zones: { hand: [-16, 0, 9], skull: [0, 0, 8], parrot: [16, 0, 9] } },
  };
  function drawCoin(style) {
    const c = S.coin, Z = COIN_ZONES[style];
    if (style === "ft") {
      for (let k = 0; k < 28; k++) { const a = k / 28 * Math.PI * 2, f = (k % 2 ? 3 : 6) + (Math.floor(performance.now() / 90 + k) % 3); disc(c.x + Math.round(Math.cos(a) * (Z.r - 2)), c.y + Math.round(Math.sin(a) * (Z.r - 2)), f > 6 ? 3 : 2, k % 3 ? "#ff7a1a" : "#ffcf3a"); }
      disc(c.x, c.y, Z.r - 4, "#2a1a10"); disc(c.x, c.y, Z.r - 6, "#3a2414");
      disc(c.x, c.y - 9, 9, "#efe6cf"); px(c.x - 6, c.y - 3, 13, 6, "#efe6cf");               // skull
      px(c.x - 6, c.y - 14, 4, 4, "#120d24"); px(c.x + 3, c.y - 14, 4, 4, "#120d24");          // eyes
      px(c.x - 4, c.y - 2, 9, 3, "#120d24"); for (let i = -3; i < 5; i += 2) px(c.x + i, c.y - 2, 1, 3, "#efe6cf");  // teeth
      icon("hand", c.x - 35, c.y - 4, "#c08850", 2); icon("boot", c.x + 19, c.y - 4, "#4a4a52", 2);
    } else {
      disc(c.x, c.y, Z.r + 1, "#7a5a10"); disc(c.x, c.y, Z.r, "#e6b84a"); disc(c.x, c.y, Z.r - 3, "#f2cf63");
      icon("hand", c.x - 24, c.y - 8, "#e2b48c", 2); icon("skull", c.x - 8, c.y - 8, "#efe6cf", 2); icon("parrot", c.x + 8, c.y - 8, "#3fbf4f", 2);
    }
    const hz = coinZone(style);
    if (hz) { const z = Z.zones[hz]; ctx.strokeStyle = "#4fd6c8"; ctx.lineWidth = 1; ctx.strokeRect(c.x + z[0] - z[2] + 0.5, c.y + z[1] - z[2] + 0.5, z[2] * 2, z[2] * 2); }
  }
  function coinZone(style) {
    const c = S.coin, m = S.mouse; if (!c || !m) return null;
    let best = null, bd = 1e9;
    for (const [k, z] of Object.entries(COIN_ZONES[style].zones)) { const d = Math.hypot(m.x - (c.x + z[0]), m.y - (c.y + z[1])); if (d <= z[2] + 2 && d < bd) { bd = d; best = k; } }
    return best;
  }
  function drawCursor(u) {
    const m = S.mouse; if (!m || matchMedia("(pointer: coarse)").matches) return;
    if (S.held) { icon("key", m.x - 2, m.y - 3, "#ffd75a"); return; }
    if (u.kind === "twobutton" || u.kind === "oneclick") {
      const o = S.hover && OBJ[S.hover];
      const k = !o ? "arrow" : u.kind === "oneclick" ? "hand" : o.ctx === "talk" ? "talk" : o.ctx === "look" ? "look" : "hand";
      icon(k, m.x, m.y, k === "hand" ? "#e2b48c" : "#120d24");
      return;
    }
    const c = u.style === "mm" ? "#f3e6c8" : u.style === "mi2" ? "#d6cff3" : "#4fd6c8";
    px(m.x - 4, m.y, 3, 1, c); px(m.x + 2, m.y, 3, 1, c); px(m.x, m.y - 4, 1, 3, c); px(m.x, m.y + 2, 1, 3, c);
  }
  function drawBubble() {  // Machinarium: pictures instead of words
    const b = S.bubble; if (!b || performance.now() > b.until || !P) return;
    const x = Math.max(4, Math.min(W - 8 - b.icons.length * 10, Math.round(P.x) - b.icons.length * 5)), y = 34;
    px(x - 3, y - 3, b.icons.length * 10 + 4, 14, "#f3e6c8"); px(x - 2, y - 4, b.icons.length * 10 + 2, 1, "#f3e6c8");
    px(Math.round(P.x) - 1, y + 11, 3, 3, "#f3e6c8");
    b.icons.forEach((n, i) => icon(n, x + i * 10, y, n === "key" ? "#c99a2e" : n === "door" ? "#8a5a36" : "#120d24"));
  }

  /* ---------------------------------------------------------------- the panel under the scene */
  let U, panel, frame = 0, raf = 0;
  const verbAction = { "Push": "push", "Pull": "pull", "Give": "give", "Open": "open", "Close": "close", "Read": "read", "Walk to": "walk",
    "Pick up": "pickup", "What is": "whatis", "Unlock": "unlock", "New kid": "newkid", "Turn on": "turnon", "Turn off": "turnon",
    "Use": "use", "Fix": "fix", "Look at": "look", "Talk to": "talk" };
  const twoObj = { "Use": "with", "Give": "to", "Unlock": "with" };
  const defaultVerb = { door: "Open", painting: "Look at", key: "Pick up", curator: "Talk to" };
  function sentence() {
    const v = S.verb || "Walk to", h = S.hover ? name(S.hover) : "";
    if (S.first) return `${v} ${name(S.first)} ${twoObj[v]} ${h}`.trim();
    return `${v} ${h}`.trim();
  }
  function renderInv() {
    const box = $("#uiInv"); if (!box) return;
    if (U.style === "mi2") {
      box.innerHTML = Array.from({ length: 8 }, (_, i) => S.inv[i]
        ? `<button type="button" class="inv-slot" data-item="${S.inv[i]}" aria-label="${esc(name(S.inv[i]))}"><canvas width="8" height="8"></canvas></button>`
        : '<span class="inv-slot"></span>').join("");
      $$("canvas", box).forEach(cv => { const c2 = cv.getContext("2d"); ICON.key.forEach((r, j) => { for (let i = 0; i < 8; i++) if (r[i] !== ".") { c2.fillStyle = "#ffd75a"; c2.fillRect(i, j, 1, 1); } }); });
    } else box.innerHTML = S.inv.map(it => `<button type="button" data-item="${it}">${esc(name(it))}</button>`).join("");
    $$("[data-item]", box).forEach(b => {
      b.addEventListener("mouseenter", () => { S.hover = b.dataset.item; upd(); });
      b.addEventListener("mouseleave", () => { S.hover = null; upd(); });
      b.addEventListener("click", () => clickObject(b.dataset.item, true));
      b.addEventListener("contextmenu", e => { e.preventDefault(); if (U.style === "mi2") clickObject(b.dataset.item, true, defaultVerb.key); });
    });
  }
  function upd() {
    const st = $("#uiSentence"); if (st) st.textContent = sentence();
    $$("#uiVerbs button").forEach(b => b.classList.toggle("on", b.dataset.verb === S.verb || (U.style === "mi2" && !S.verb && S.hover && defaultVerb[S.hover] === b.dataset.verb)));
  }
  function clickObject(id, fromInv, forceVerb) {
    const v = forceVerb || S.verb || "Walk to";
    if (v === "Walk to" && !fromInv) { if (P) P.walkTo(HOT[id].walkX); return; }
    if (twoObj[v] && !S.first) {
      if (v === "Unlock" || (v === "Use" && OBJ[id].item && S.inv.includes(id)) || (v === "Give" && S.inv.includes(id))) { S.first = id; upd(); return; }
    }
    const a = S.first || id, b = S.first ? id : null;
    S.verb = null; S.first = null; upd(); sfx("click");
    if (fromInv && !b) act(verbAction[v], a); else perform(verbAction[v], a, b);
  }

  function build(i) {
    U = UI[i]; reset(); cancelAnimationFrame(raf);
    $$("#uiTabs button").forEach((b, k) => b.setAttribute("aria-selected", String(k === i)));
    $("#uiReal").innerHTML = U.media ? mediaFigure(U.media, t("screenshotOf", { title: U.game }), "ui-real-fig", G.realLabel + " · " + U.game + " (" + U.year + ")") : "";
    $("#uiDesc").textContent = U.desc;
    const stage = $("#uiStage");
    stage.className = "ui-stage st-" + (U.style || U.kind);
    if (U.kind === "parser") return buildParser(stage);
    stage.innerHTML = '<div class="ui-screen"><canvas id="uiCanvas" width="' + W + '" height="' + H + '" aria-label="' + esc(G.labLabel) + '"></canvas><div class="ui-say" id="uiSay" aria-live="polite"></div>' +
      (U.kind === "coin" ? '<div class="ui-invpop" id="uiInvPop" hidden><span>' + esc(G.inventory) + '</span><div id="uiInv"></div></div>' : "") +
      (U.kind === "twobutton" || U.kind === "oneclick" ? '<div class="ui-invtop" id="uiInvTop"><div id="uiInv"></div></div>' : "") + "</div>" +
      (U.kind === "verbs" ? '<div class="ui-panel"><div class="ui-sentence" id="uiSentence"></div><div class="ui-bottom"><div class="ui-verbs" id="uiVerbs" style="grid-template-columns:repeat(' + U.cols + ',auto)">' +
        U.verbs.map(v => '<button type="button" data-verb="' + esc(v) + '">' + esc(v) + "</button>").join("") + '</div><div class="ui-inv" id="uiInv"></div></div></div>' : "") +
      (U.kind === "coin" ? '<p class="ui-hint">' + esc(G.hold) + "</p>" : "") +
      '<button class="pbtn small ui-reset" type="button" id="uiReset">' + esc(G.reset) + "</button>";
    canvas = $("#uiCanvas"); ctx = canvas.getContext("2d");
    $("#uiReset").onclick = () => { reset(); renderInv(); upd(); sfx("click"); };
    $$("#uiVerbs button").forEach(b => b.addEventListener("click", () => { S.verb = b.dataset.verb === "Walk to" ? null : b.dataset.verb; S.first = null; sfx("click"); upd(); }));
    bindPointer();
    renderInv(); upd(); loop();
  }

  /* ---------------------------------------------------------------- pointer handling per interface */
  function pos(e) { const r = canvas.getBoundingClientRect(); return { x: Math.round((e.clientX - r.left) / r.width * W), y: Math.round((e.clientY - r.top) / r.height * H) }; }
  function bindPointer() {
    let holdTimer = 0, downAt = null;
    canvas.addEventListener("contextmenu", e => e.preventDefault());
    canvas.addEventListener("pointermove", e => {
      S.mouse = pos(e); S.hover = hit(S.mouse.x, S.mouse.y); if (U.kind === "verbs") upd();
      const top = $("#uiInvTop"); if (top) top.classList.toggle("show", S.mouse.y < 14 && S.inv.length > 0);
    });
    canvas.addEventListener("pointerleave", () => { S.mouse = null; S.hover = null; if (U.kind === "verbs") upd(); });
    canvas.addEventListener("pointerdown", e => {
      const m = pos(e); S.mouse = m; S.hover = hit(m.x, m.y); downAt = m;
      if (U.kind === "coin") {
        if (e.button === 2) { toggleInvPop(); return; }
        if (S.held) { const id = hit(m.x, m.y); if (id) perform("use", S.held, id); S.held = null; return; }
        const id = hit(m.x, m.y);
        if (id) holdTimer = setTimeout(() => { S.coin = { x: Math.max(40, Math.min(W - 40, m.x)), y: Math.max(28, Math.min(H - 28, m.y)), id }; sfx("open"); }, 260);
        try { canvas.setPointerCapture(e.pointerId); } catch (_) { /* old browsers */ }
        return;
      }
      if (U.kind === "twobutton" || U.kind === "oneclick") {
        const id = hit(m.x, m.y);
        if (e.button === 2 && U.kind === "twobutton") { if (S.held) { S.held = null; return; } if (id) { perform("look", id); } return; }
        if (S.held) { if (id) perform("use", S.held, id); S.held = null; return; }
        if (!id) { if (P) P.walkTo(Math.max(16, Math.min(232, m.x))); return; }
        const o = OBJ[id];
        if (U.kind === "oneclick") { oneClick(id); return; }
        perform(o.ctx, id);
        return;
      }
      // SCUMM verbs
      if (e.button === 2 && U.style === "mi2" && S.hover) { clickObject(S.hover, false, defaultVerb[S.hover]); return; }
      const id = hit(m.x, m.y);
      if (id) clickObject(id, false); else { if (P) P.walkTo(Math.max(16, Math.min(232, m.x))); if (S.verb !== null && !S.first) { /* clicking empty floor keeps the verb */ } }
    });
    canvas.addEventListener("pointerup", e => {
      clearTimeout(holdTimer);
      if (U.kind !== "coin") return;
      if (S.coin) {
        const z = coinZone(U.style), id = S.coin.id; S.coin = null;
        if (z) { const a = U.actions.find(x => x[0] === z)[1]; perform(a, id); sfx("click"); }
        return;
      }
      if (downAt && P && e.button === 0) { const m = pos(e); const id = hit(m.x, m.y); P.walkTo(id ? HOT[id].walkX : Math.max(16, Math.min(232, m.x))); }
    });
  }
  function toggleInvPop() {
    const pop = $("#uiInvPop"); if (!pop) return;
    pop.hidden = !pop.hidden; sfx("click");
    $$("#uiInv [data-item]").forEach(b => { b.onclick = () => { S.held = b.dataset.item; pop.hidden = true; }; });
  }
  function oneClick(id) {  // Machinarium: only things within reach; pictures instead of words
    const show = icons => { S.bubble = { icons, until: performance.now() + 2600 }; };
    if (P) P.walkTo(HOT[id].walkX);
    S.pending = () => {
      if (id === "key" && !S.taken) { S.taken = true; S.inv.push("key"); renderInv(); sfx("click"); return; }
      if (id === "door") { if (S.open) return; if (S.locked) return show(["door", "question"]); S.open = true; sfx("open"); return; }
      if (id === "curator") return show(["key", "door"]);
      if (id === "painting") return show(["look"]);
    };
    $$("#uiInv [data-item]").forEach(b => { b.onclick = () => { S.held = b.dataset.item; }; });
  }

  function loop() {
    const u = U;
    const step = () => {
      if (u !== U) return;
      frame++;
      drawScene();
      if (S.coin) drawCoin(U.style);
      drawBubble();
      drawCursor(U);
      const sayEl = $("#uiSay");
      if (sayEl) { const on = performance.now() < S.sayUntil && U.kind !== "oneclick"; sayEl.textContent = on ? S.say : ""; sayEl.classList.toggle("on", on); }
      if (U.kind === "twobutton" || U.kind === "oneclick") $$("#uiInv [data-item]").forEach(b => { b.onclick = () => { S.held = b.dataset.item; }; });
      if (U.kind === "verbs" && $("#uiSentence") && !S.hover && !S.first && frame % 20 === 0) upd();
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
  }

  /* ---------------------------------------------------------------- Zork I parser */
  function buildParser(stage) {
    const Z = LAB.zork;
    stage.innerHTML = '<div class="zork" id="zork"><pre id="zorkOut"></pre><form id="zorkForm" autocomplete="off"><label for="zorkIn">&gt;</label><input id="zorkIn" spellcheck="false" autocapitalize="off" maxlength="60"></form></div>';
    const out = $("#zorkOut"), inp = $("#zorkIn");
    out.textContent = U.intro.join("\n") + "\n";
    $("#zorkForm").addEventListener("submit", e => {
      e.preventDefault();
      let cmd = inp.value.trim().toLowerCase().replace(/\s+/g, " "); inp.value = "";
      if (!cmd) return;
      cmd = Z._alias[cmd] || cmd;
      let r = Z[cmd];
      if (!r || cmd.startsWith("_")) {
        const words = cmd.split(" "), known = new Set(Object.keys(Z).filter(k => !k.startsWith("_")).join(" ").split(" ").concat(Object.keys(Z._alias).join(" ").split(" "), ["the", "go", "open", "read", "take", "get"]));
        const unknown = words.find(w => !known.has(w));
        r = unknown ? Z._unknown.replace("{w}", unknown) : Z._syntax;
      }
      out.textContent += "\n> " + cmd.toUpperCase() + "\n" + r + "\n";
      out.scrollTop = out.scrollHeight; sfx("click");
    });
    inp.focus({ preventScroll: true });
  }

  /* ---------------------------------------------------------------- tabs */
  $$("#uiTabs button").forEach((b, i) => b.addEventListener("click", () => { build(i); sfx("click"); award("techUi", UI[i].id, UI[i].label); }));
  reset(); build(0);
})();
