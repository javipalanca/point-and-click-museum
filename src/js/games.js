/* Point and Click Museum · data-driven minigames (see data/minigames/*.json). */
"use strict";
(() => {
  const { D, $, t, fmt, esc, spriteURL, rng, canvasPoint, sfx, typeText, award, reduceMotion } = PCM;
  const R = PCM.Rules;
  const G = D.games;

  /* ================= 1 · Text adventure ================= */
  if ($("#term")) (() => {
    const A = G.textAdventure, V = A.vocab, M = A.messages;
    const term = $("#term"), input = $("#termIn");
    const norm = s => s.toLowerCase().replace(/ß/g, "ss").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9ñ ]/g, " ").replace(/\s+/g, " ").trim();
    const verbMap = {}, phraseMap = {}, dirMap = {}, nounMap = {};
    Object.entries(V.verbs).forEach(([id, ws]) => ws.forEach(w => { w = norm(w); (w.includes(" ") ? phraseMap : verbMap)[w] = id; }));
    Object.entries(V.dirs).forEach(([id, ws]) => ws.forEach(w => { dirMap[norm(w)] = id; }));
    Object.entries(V.nouns).forEach(([id, ws]) => ws.forEach(w => { nounMap[norm(w)] = id; }));
    const stop = new Set(V.stop.map(norm));

    function parse(raw) {
      let words = norm(raw).split(" ").filter(Boolean);
      if (!words.length) return null;
      let verb = null, noun = null, rest;
      if (words.length > 1 && phraseMap[words[0] + " " + words[1]]) { verb = phraseMap[words[0] + " " + words[1]]; rest = words.slice(2); }
      else if (verbMap[words[0]]) { verb = verbMap[words[0]]; rest = words.slice(1); }
      else if (dirMap[words[0]]) { verb = "go"; noun = dirMap[words[0]]; rest = []; }
      else rest = words.slice(1);
      // separable verbs at the end ("mach die Lampe an")
      if (!verb && words.length > 2 && phraseMap[words[0] + " " + words[words.length - 1]]) { verb = phraseMap[words[0] + " " + words[words.length - 1]]; rest = words.slice(1, -1); }
      rest = rest.filter(w => !stop.has(w));
      if (verb === "go" && !noun) noun = dirMap[rest[0]] || null;
      const nouns = verb === "go" ? [] : rest.map(w => nounMap[w]).filter(Boolean);
      const arg = (raw.match(/\d+/) || [null])[0];
      return { verb, noun: verb === "go" ? noun : (nouns[0] || null), noun2: nouns[1] || null, arg, unknown: !verb };
    }

    let S;
    function reset() {
      S = { room: A.start, flags: {}, counters: {}, inv: [], at: {}, moves: 0, done: false };
      Object.entries(A.items).forEach(([id, it]) => { S.at[id] = it.at; });
    }
    function out(text, cls) { const d = document.createElement("div"); if (cls) d.className = cls; d.textContent = text; term.appendChild(d); term.scrollTop = term.scrollHeight; }
    const room = () => A.rooms[S.room];
    const dark = () => !!room().darkUnless && !R.all(room().darkUnless, S);
    const itemsHere = () => Object.keys(A.items).filter(id => S.at[id] === S.room && !S.inv.includes(id));
    function look() {
      if (dark()) { out(room().dark); return; }
      out(R.fragments(room().desc, S));
      const here = itemsHere(); if (here.length) out(fmt(M.seeHere, { items: here.map(i => A.items[i].name).join(", ") }));
    }
    function move(to) { S.room = to; look(); }
    const hooks = {
      drop: i => { S.at[i] = S.room; },
      give: i => { S.at[i] = null; },
      look,
      win: () => { S.done = true; out(fmt(M.won, { moves: S.moves }), "sys"); sfx("win"); award(A.award, "x", A.title); },
      award: k => award(k, "x"),
      sound: s => sfx(s),
    };
    function builtin(q) {
      const n = q.noun;
      switch (q.verb) {
        case "look":
          if (!n) return look();
          if (dark()) return out(M.darkTake);
          if (A.items[n] && (S.inv.includes(n) || S.at[n] === S.room)) return out(R.fragments(A.items[n].desc, S));
          if (room().scenery && room().scenery[n]) return out(R.fragments(room().scenery[n], S));
          return out(n ? M.notHere : M.nothingSpecial);
        case "take":
          if (!n) return out(M.takeWhat);
          if (S.inv.includes(n)) return out(M.alreadyHave);
          if (dark()) return out(M.darkTake);
          if (A.items[n] && S.at[n] === S.room) { S.inv.push(n); S.at[n] = null; return out(fmt(M.taken, { item: A.items[n].name })); }
          if (room().scenery && room().scenery[n]) return out(M.cantTake);
          return out(M.notHere);
        case "drop":
          if (!n || !S.inv.includes(n)) return out(M.dontHave);
          S.inv = S.inv.filter(i => i !== n); S.at[n] = S.room; return out(M.dropped);
        case "inventory":
          return out(S.inv.length ? fmt(M.invList, { items: S.inv.map(i => A.items[i].name).join(", ") }) : M.invEmpty);
        case "go": {
          if (!n) return out(M.goWhere);
          const ex = room().exits && room().exits[n];
          if (!ex) return out(M.cantGo);
          if (typeof ex === "string") return move(ex);
          if (R.all(ex.if, S)) return move(ex.to);
          return out(ex.else);
        }
        case "help": return out(M.help, "sys");
        default: return out(M.cantDo);
      }
    }
    function cmd(raw) {
      const q = parse(raw); if (!q) return;
      if (q.verb === "restart") { reset(); term.innerHTML = ""; intro(); return; }
      if (S.done) return out(M.gameOver);
      if (q.unknown) return out(fmt(M.dontUnderstand, { input: raw.trim() }));
      S.moves++;
      const rule = R.find(A.rules, q, S);
      if (rule) { const txt = R.text(rule, S); if (txt) out(txt, (rule.do || []).some(e => e.startsWith("award:")) ? "sys" : ""); R.apply(rule.do, S, hooks); return; }
      builtin(q);
    }
    function intro() { M.intro.forEach((l, i) => out(l, i < 2 ? "sys" : "")); look(); }
    reset(); intro();
    $("#termForm").addEventListener("submit", e => {
      e.preventDefault(); const v = input.value; if (!v.trim()) return;
      out("> " + v, "in"); input.value = ""; sfx("click"); cmd(v);
    });
  })();

  /* ================= 2 · Restoration room (verbs + inventory) ================= */
  if ($("#roomCanvas")) (() => {
    const C = G.room, M = C.messages, [W, H] = C.size, ch = C.character;
    const cv = $("#roomCanvas"), x = cv.getContext("2d");
    const verbLabel = id => C.verbs.find(v => v.id === id).label;
    let verb, selItem, S, hover = null, walking = null, running = false;
    const guy = PCM.Chars.actor(ch.name || "curator", ch.start, ch.y, 1.4);
    const spotsActive = () => C.spots.filter(s => R.all(s.if, S));
    const msg = text => { typeText($("#roomMsg"), text, 14); guy.say(Math.min(3500, text.length * 40)); kick(); };
    function sentence(target) {
      let s = verbLabel(verb);
      if (selItem) s += " " + C.items[selItem].name + " " + C.with;
      if (target) s += " " + target;
      $("#roomSentence").textContent = s;
    }
    function renderVerbs() {
      const g = $("#verbs"); g.innerHTML = "";
      C.verbs.forEach(v => {
        const b = document.createElement("button"); b.type = "button"; b.textContent = v.label; b.setAttribute("aria-pressed", v.id === verb);
        b.onclick = () => { verb = v.id; selItem = null; renderVerbs(); renderInv(); sentence(); sfx("click"); };
        g.appendChild(b);
      });
    }
    function renderInv() {
      const g = $("#inv"); g.innerHTML = "";
      for (let i = 0; i < 8; i++) {
        const b = document.createElement("button"), it = S.inv[i]; b.type = "button";
        if (it) {
          b.innerHTML = '<img alt="" width="40" height="40" src="' + spriteURL(C.items[it].icon) + '">';
          b.setAttribute("aria-label", C.items[it].name); b.setAttribute("aria-pressed", selItem === it);
          b.onclick = () => clickItem(it); b.onmouseenter = () => sentence(C.items[it].name);
        } else { b.disabled = true; b.setAttribute("aria-label", M.emptySlot); }
        g.appendChild(b);
      }
    }
    const hooks = {
      give: () => renderInv(), remove: () => { if (!S.inv.includes(selItem)) selItem = null; renderInv(); },
      sound: s => sfx(s), award: k => award(k, "x"),
      win: () => { S.flags.won = true; sfx("win"); award(C.award, "x", C.title); },
    };
    function act(v, noun, item) {
      const q = { verb: v, noun, item: item || null, room: "room" };
      const rule = R.find(C.rules, q, S, true);
      selItem = null;
      if (rule) { const txt = R.text(rule, S); R.apply(rule.do, S, hooks); renderInv(); sentence(); if (txt) msg(txt); kick(); return; }
      renderInv(); sentence();
      const isItem = !!C.items[noun];
      if (item) return msg(isItem ? M.nonsense : M.noWork);
      if (isItem) return msg(v === "look" ? C.items[noun].desc : fmt(M.cantItem, { item: C.items[noun].name }));
      msg({ use: M.chooseItem, take: M.cantTake, talk: M.noTalk, look: M.nothingSpecial }[v] || M.noWork);
    }
    function clickItem(it) {
      sfx("click");
      if (verb === "use" && !selItem) { selItem = it; renderInv(); sentence(); return; }
      if (verb === "use" && selItem && selItem !== it) return act("use", it, selItem);
      act(verb, it, null);
    }
    const props = PCM.Scene;
    function draw() {
      props.render(x, C.scene, S, hover ? hover.id : null);
      if (!guy.update() && walking) { const w = walking; walking = null; act(verb, w.spot.id, w.item); }
      guy.draw(x);
      props.render(x, C.foreground || [], S, hover ? hover.id : null);
    }
    let visible = true;
    new IntersectionObserver(es => { visible = es[0].isIntersecting; if (visible) kick(); }).observe(cv);
    function loop() { draw(); if (visible && (!reduceMotion || guy.busy() || walking)) requestAnimationFrame(loop); else running = false; }
    function kick() { if (!running) { running = true; requestAnimationFrame(loop); } }
    const spotAt = (px, py) => spotsActive().find(s => px >= s.rect[0] && px <= s.rect[0] + s.rect[2] && py >= s.rect[1] && py <= s.rect[1] + s.rect[3]);
    cv.addEventListener("pointermove", e => { const [px, py] = canvasPoint(cv, e, W, H); hover = spotAt(px, py) || null; sentence(hover ? hover.name : ""); kick(); });
    cv.addEventListener("pointerleave", () => { hover = null; sentence(); kick(); });
    cv.addEventListener("click", e => {
      const [px, py] = canvasPoint(cv, e, W, H), s = spotAt(px, py);
      const [minX, maxX] = C.walkBounds;
      guy.walkTo(Math.max(minX, Math.min(maxX, Math.round(s ? (s.walkTo != null ? s.walkTo : s.rect[0] + s.rect[2] / 2) : px))));
      if (s) { sentence(s.name); walking = { spot: s, item: selItem }; } else { walking = null; selItem = null; renderInv(); sentence(); }
      kick();
    });
    function reset() {
      S = { room: "room", flags: {}, counters: {}, inv: [] }; selItem = null; verb = C.verbs[0].id; walking = null;
      guy.x = guy.tx = ch.start; guy.dir = 1; renderVerbs(); renderInv(); sentence(); msg(M.intro); kick();
    }
    $("#roomReset").onclick = () => { reset(); sfx("click"); };
    reset();
  })();

  /* ================= 3 · Pixel hunt ================= */
  if ($("#huntCanvas")) (() => {
    const C = G.hunt, M = C.messages, [W, H] = C.size;
    const cv = $("#huntCanvas"), x = cv.getContext("2d");
    const shade = document.createElement("canvas"); shade.width = W; shade.height = H; const sx = shade.getContext("2d");
    let round = 0, scene = null, timeLeft = 0, timer = null, misses = 0, hinted = false, playing = false, flash = 0, tick = 0;
    let torch = { x: W / 2, y: H / 2 }, running = false, visible = true;
    const motes = Array.from({ length: 26 }, (_, i) => ({ x: Math.random(), y: Math.random(), v: 0.0006 + Math.random() * 0.0012, s: i % 3 }));
    $("#huntRounds").textContent = C.rounds; $("#huntMsg").textContent = M.start;
    const darkness = () => (C.darkness || [0, 0.35, 0.86])[Math.min(round, C.rounds) - 1] || 0;
    function draw() {
      tick++;
      if (!scene) scene = PCM.Scene.attic(W, H, 4242, 1, C);
      x.drawImage(scene.bg, 0, 0);
      const [wx, wy] = scene.window;
      // light shaft from the round window + dust motes
      x.save(); x.globalCompositeOperation = "lighter";
      const g = x.createLinearGradient(wx, wy, wx + 30, H);
      g.addColorStop(0, "rgba(120,150,255,.16)"); g.addColorStop(1, "rgba(120,150,255,0)");
      x.fillStyle = g; x.beginPath(); x.moveTo(wx - 9, wy); x.lineTo(wx + 9, wy); x.lineTo(wx + 70, H); x.lineTo(wx + 10, H); x.closePath(); x.fill();
      motes.forEach(m => {
        if (!reduceMotion) { m.y += m.v; if (m.y > 1) m.y = 0; }
        const my = wy + m.y * (H - wy), spread = (my - wy) / (H - wy), mx = wx - 8 + spread * 20 + m.x * (16 + spread * 44);
        x.fillStyle = "rgba(255,240,200," + (0.25 + 0.2 * Math.sin(tick / 20 + m.x * 9)) + ")"; x.fillRect(Math.round(mx), Math.round(my), 1, 1);
      });
      x.restore();
      // lighting: darker each round, the last one only by torchlight
      const d = playing || round ? darkness() : 0;
      if (d > 0) {
        sx.clearRect(0, 0, W, H); sx.globalCompositeOperation = "source-over"; sx.fillStyle = "rgba(6,4,14," + d + ")"; sx.fillRect(0, 0, W, H);
        sx.globalCompositeOperation = "destination-out";
        const lights = [[wx + 20, H * 0.75, 70, 0.5]];
        if (round >= C.rounds) lights.push([torch.x, torch.y, C.torchRadius || 34, 1]);
        lights.forEach(([lx, ly, lr, a]) => { const rg = sx.createRadialGradient(lx, ly, 0, lx, ly, lr); rg.addColorStop(0, "rgba(0,0,0," + a + ")"); rg.addColorStop(0.7, "rgba(0,0,0," + a * 0.6 + ")"); rg.addColorStop(1, "rgba(0,0,0,0)"); sx.fillStyle = rg; sx.fillRect(lx - lr, ly - lr, lr * 2, lr * 2); });
        x.drawImage(shade, 0, 0);
        if (round >= C.rounds) { x.strokeStyle = "rgba(255,220,150,.25)"; x.beginPath(); x.arc(torch.x, torch.y, (C.torchRadius || 34) * 0.7, 0, Math.PI * 2); x.stroke(); }
      }
      if (flash > 0 && scene) {
        const { x: tx, y: ty } = scene.target, rr = 10 + (flash % 8);
        x.strokeStyle = flash % 2 ? "#4fd6c8" : "#ef5d8a"; x.lineWidth = 1; x.strokeRect(tx - rr + 3.5, ty - rr + 3.5, rr * 2, rr * 2);
        flash--;
      }
    }
    function loop() { draw(); if (visible && (!reduceMotion || flash > 0)) requestAnimationFrame(loop); else running = false; }
    function kick() { if (!running) { running = true; requestAnimationFrame(loop); } }
    new IntersectionObserver(es => { visible = es[0].isIntersecting; if (visible) kick(); }).observe(cv);
    function newRound() {
      round++; scene = PCM.Scene.attic(W, H, Math.floor(Math.random() * 1e9), round, C);
      timeLeft = C.baseTime - (round - 1) * C.timeStepPerRound; hinted = false; flash = 0; $("#huntHint").disabled = false;
      $("#huntRound").textContent = round; $("#huntTime").textContent = timeLeft;
      $("#huntMsg").textContent = fmt(round >= C.rounds && M.torch ? M.torch : M.round, { round }); kick();
    }
    function end() { playing = false; clearInterval(timer); $("#huntHint").disabled = true; flash = 40; kick(); }
    function start() { round = 0; misses = 0; $("#huntMiss").textContent = 0; playing = true; clearInterval(timer); newRound(); timer = setInterval(tickT, 1000); sfx("open"); }
    function tickT() {
      timeLeft--; $("#huntTime").textContent = timeLeft;
      if (timeLeft <= 0) { end(); $("#huntMsg").textContent = M.timeUp; sfx("bad"); }
    }
    cv.addEventListener("pointermove", e => { const [px, py] = canvasPoint(cv, e, W, H); torch = { x: px, y: py }; if (reduceMotion) kick(); });
    cv.addEventListener("click", e => {
      if (!playing) return;
      const [px, py] = canvasPoint(cv, e, W, H), tol = C.hitTolerance, { x: tx, y: ty } = scene.target;
      torch = { x: px, y: py };
      if (px >= tx - tol && px <= tx + 7 + tol && py >= ty - tol && py <= ty + 7 + tol) {
        sfx("points"); flash = 20; kick();
        if (round >= C.rounds) { end(); $("#huntMsg").textContent = fmt(M.won, { misses }); award(C.award, "x", C.title); sfx("win"); }
        else { $("#huntMsg").textContent = M.found; setTimeout(newRound, 900); }
      } else {
        misses++; $("#huntMiss").textContent = misses; sfx("bad");
        $("#huntMsg").textContent = M.quips[misses % M.quips.length];
      }
    });
    $("#huntStart").onclick = start;
    $("#huntHint").onclick = () => {
      if (!playing || hinted) return; hinted = true; timeLeft = Math.max(1, timeLeft - C.hintCost); $("#huntTime").textContent = timeLeft;
      flash = 12; kick(); $("#huntMsg").textContent = M.hint; $("#huntHint").disabled = true;
    };
    kick();
  })();

  /* ================= 4 · Chronology ================= */
  if ($("#orderList")) (() => {
    const C = G.chronology, M = C.messages, games = D.timeline.games;
    let picks = [], set = [], checked = false;
    function newSet() {
      checked = false; picks = []; set = []; const years = new Set();
      for (const g of games.slice().sort(() => Math.random() - 0.5)) { if (!years.has(g.year)) { years.add(g.year); set.push(g); } if (set.length === C.count) break; }
      render(); $("#orderMsg").textContent = "";
    }
    function render() {
      const el = $("#orderList"); el.innerHTML = "";
      const sorted = set.slice().sort((a, c) => a.year - c.year);
      set.forEach(g => {
        const b = document.createElement("button"), k = picks.indexOf(g); b.type = "button";
        b.className = "ord" + (k >= 0 ? " picked" : "") + (checked ? " reveal " + (sorted.indexOf(g) === k ? "ok" : "bad") : "");
        b.innerHTML = '<span class="slot">' + (k + 1) + '</span>' + (g.media && g.media.cover ? '<img class="ord-cover" alt="" width="' + g.media.cover.w + '" height="' + g.media.cover.h + '" src="' + esc(g.media.cover.src) + '">' : "") + '<span><span style="display:block">' + esc(g.title) + '</span><span class="yr3">' + g.year + "</span></span>";
        b.onclick = () => { if (checked) return; sfx("click"); if (k >= 0) picks.splice(k, 1); else picks.push(g); render(); };
        el.appendChild(b);
      });
    }
    $("#orderCheck").onclick = () => {
      if (picks.length < set.length) { $("#orderMsg").textContent = fmt(M.needAll, { count: set.length }); sfx("bad"); return; }
      checked = true; render();
      const ok = picks.every((g, i) => i === 0 || picks[i - 1].year <= g.year);
      if (ok) { $("#orderMsg").textContent = M.ok; award(C.award, "x", C.title); sfx("win"); }
      else { $("#orderMsg").textContent = M.bad; sfx("bad"); }
    };
    $("#orderNew").onclick = () => { newSet(); sfx("click"); };
    newSet();
  })();
})();
