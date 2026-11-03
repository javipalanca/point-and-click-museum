/* Point and Click Museum · hero, timeline, studios, engines, techniques, navigation. */
"use strict";
(() => {
  const { D, $, $$, t, esc, store, spriteURL, rng, mediaFigure, pixelText, pixelTextWidth, canvasPoint, sfx, tone, ac, typeText, award, openModal, reduceMotion } = PCM;
  const smooth = reduceMotion ? "auto" : "smooth";

  /* ================= Language hint (root page only) ================= */
  (() => {
    if (!D.isRoot || store("lang")) return;
    const pref = (navigator.languages || [navigator.language || ""]).map(l => l.slice(0, 2).toLowerCase()).find(l => D.langHints[l]);
    if (!pref || pref === D.lang) return;
    const h = $("#langHint"), info = D.langHints[pref];
    h.innerHTML = '<span lang="' + pref + '">' + esc(info.text) + '</span> <a href="' + esc(info.url) + '" hreflang="' + pref + '" lang="' + pref + '">' + esc(info.label) + '</a><button type="button" aria-label="' + esc(t("close")) + '">×</button>';
    h.hidden = false;
    h.querySelector("button").onclick = () => { store("lang", D.lang); h.hidden = true; };
  })();
  $$(".langs a, footer a[hreflang]").forEach(a => a.addEventListener("click", () => store("lang", a.getAttribute("hreflang"))));

  const linkHtml = (url, label) => '<a class="ext" href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(label) + ' ↗</a>';
  const linkLabel = url => (/wikipedia\.org/.test(url) ? "Wikipedia" : t("officialSite"));

  /* ================= Hero scene ================= */
  if ($("#heroCanvas")) (() => {
    const cv = $("#heroCanvas"), x = cv.getContext("2d"), W = 320, H = 150;
    const r = rng(3), stars = Array.from({ length: 70 }, () => ({ x: Math.floor(r() * W), y: Math.floor(r() * 46), p: r() * 6 }));
    const spots = D.hero.hotspots;
    const visitor = PCM.Chars.actor("visitor", 52, 138, 1);
    let hover = null, pending = null, tick = 0, running = false, shoot = -1;
    // static background, drawn once
    const bg = document.createElement("canvas"); bg.width = W; bg.height = H;
    (() => {
      const b = bg.getContext("2d"), bands = ["#334f55", "#406066", "#4f7279", "#618086", "#d6789a"];
      for (let y = 0; y < 112; y++) for (let i = 0; i < W; i++) {
        const k = y / 112 * (bands.length - 1), lo = Math.floor(k), f = k - lo;
        const th = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]][y % 4][i % 4] / 16;
        b.fillStyle = bands[Math.min(bands.length - 1, lo + (f > th ? 1 : 0))]; b.fillRect(i, y, 1, 1);
      }
      // far city skyline
      const rr = rng(11);
      for (let i = 0; i < W; i += 6 + Math.floor(rr() * 8)) {
        const w = 6 + Math.floor(rr() * 10), h = 10 + Math.floor(rr() * 26);
        b.fillStyle = "#3d585e"; b.fillRect(i, 104 - h, w, h + 10);
        b.fillStyle = "#ffcf7a"; for (let k = 0; k < 4; k++) if (rr() > 0.5) b.fillRect(i + 1 + Math.floor(rr() * (w - 2)), 104 - h + 2 + Math.floor(rr() * (h - 4)), 1, 1);
      }
      // hills and trees
      b.fillStyle = "#344d52"; for (let i = 0; i < W; i++) { const h = 102 - Math.abs(Math.sin(i / 38)) * 12 - Math.sin(i / 9) * 2; b.fillRect(i, Math.round(h), 1, 140); }
      const tree = (tx, ty, s) => {
        b.fillStyle = "#1f2a3a"; b.fillRect(tx - 1, ty, 2, 10 * s);
        for (let j = 0; j < 14 * s; j++) { const w = Math.round((j / (14 * s)) * 9 * s) + 1; b.fillStyle = j % 3 ? "#1f5a48" : "#18493b"; b.fillRect(tx - Math.floor(w / 2), ty - 14 * s + j, w, 1); }
      };
      [[14, 118, 1.2], [66, 120, 1], [258, 120, 1], [304, 116, 1.3]].forEach(t => tree(...t));
      // museum body
      const bx = 96, bw = 128;
      b.fillStyle = "#3e5054"; b.fillRect(bx, 64, bw, 70);
      b.fillStyle = "#4a5f64"; for (let y = 66; y < 132; y += 4) for (let i = bx + ((y / 4) % 2) * 6; i < bx + bw; i += 12) b.fillRect(i, y, 11, 1);
      // pediment
      for (let j = 0; j < 22; j++) { b.fillStyle = j === 0 ? "#f3e6c8" : (j % 5 === 0 ? "#a6a094" : "#bbb6ad"); b.fillRect(160 - j * 3 - 6, 42 + j, j * 6 + 12, 1); }
      b.fillStyle = "#979083"; for (let j = 8; j < 20; j++) b.fillRect(160 - j * 2 + 4, 44 + j, j * 4 - 8, 1);
      b.fillStyle = "#f3e6c8"; b.fillRect(bx - 6, 63, bw + 12, 3); b.fillStyle = "#c9b98f"; b.fillRect(bx - 6, 65, bw + 12, 1);
      b.fillStyle = "#283b3f"; b.fillRect(bx + 14, 52, bw - 28, 11); b.fillStyle = "#ffb547"; b.fillRect(bx + 14, 52, bw - 28, 1); b.fillRect(bx + 14, 62, bw - 28, 1);
      // steps
      for (let k = 0; k < 4; k++) { b.fillStyle = k % 2 ? "#bbb6ad" : "#e3e0d9"; b.fillRect(bx - 8 - k * 3, 129 + k * 2, bw + 16 + k * 6, 2); }
      // ground and pavement
      b.fillStyle = "#3e565b"; b.fillRect(0, 137, W, 13);
      b.fillStyle = "#4e6b71"; for (let i = 0; i < W; i += 14) b.fillRect(i + ((i / 14) % 2) * 7, 140, 13, 1);
      b.fillStyle = "#31474b"; for (let i = 0; i < W; i += 14) b.fillRect(i, 141, 1, 9);
      b.fillStyle = "#3e5054"; b.fillRect(0, 137, W, 1);
      // bushes
      [[84, 132], [228, 132]].forEach(([px, py]) => { for (let j = 0; j < 7; j++) { b.fillStyle = j < 2 ? "#2f7d46" : "#1f5a33"; b.fillRect(px - 6 + Math.abs(3 - j), py - j, 13 - Math.abs(3 - j) * 2, 1); } });
    })();
    const isHover = id => hover && hover.id === id;
    function disc(cx, cy, rad, col) { x.fillStyle = col; for (let j = -rad; j <= rad; j++) { const w = Math.floor(Math.sqrt(rad * rad - j * j)); x.fillRect(cx - w, cy + j, w * 2 + 1, 1); } }
    function draw() {
      tick++;
      x.drawImage(bg, 0, 0);
      stars.forEach(s => { if (reduceMotion || Math.sin(tick / 22 + s.p * 3) > -0.4) { x.fillStyle = s.p > 5.2 ? "#ffb547" : (s.p > 3 ? "#f3e6c8" : "#aaa292"); x.fillRect(s.x, s.y, 1, 1); } });
      if (!reduceMotion) {
        if (shoot < 0 && Math.random() < 0.003) shoot = 0;
        if (shoot >= 0) { const sx = 40 + shoot * 3, sy = 10 + shoot; for (let k = 0; k < 8; k++) { x.fillStyle = k < 2 ? "#ffffff" : "rgba(243,230,200," + (0.6 - k * 0.07) + ")"; x.fillRect(sx - k * 3, sy - k, 2, 1); } if (++shoot > 30) shoot = -1; }
      }
      // moon with halo and craters
      x.fillStyle = "rgba(243,230,200,.06)"; disc(273, 25, 18, "rgba(243,230,200,.06)"); disc(273, 25, 14, "rgba(243,230,200,.08)");
      disc(273, 25, 10, isHover("moon") ? "#ffffff" : "#f3e6c8"); disc(276, 23, 9, isHover("moon") ? "#ffffff" : "#f8efd8");
      x.fillStyle = "#d9cfa8"; [[269, 21, 2], [277, 29, 2], [275, 19, 1], [268, 28, 1]].forEach(([a, b, rr]) => disc(a, b, rr, "#d9cfa8"));
      // cloud drifting
      const cx = reduceMotion ? 200 : ((tick * 0.08) % (W + 80)) - 40;
      x.fillStyle = "rgba(65,91,96,.85)"; x.fillRect(cx, 30, 34, 4); x.fillRect(cx + 6, 27, 18, 3); x.fillRect(cx + 26, 28, 10, 3);
      x.fillStyle = "rgba(90,117,122,.9)"; x.fillRect(cx + 6, 27, 18, 1);
      // sign
      const label = D.hero.sign; pixelText(x, label, 160 - Math.floor(pixelTextWidth(label) / 2), 55, isHover("sign") ? "#4fd6c8" : "#ffb547");
      // columns and banners
      const bx = 96;
      for (let c = 0; c < 6; c++) {
        const px = bx + 6 + c * 22;
        x.fillStyle = "#eceae3"; x.fillRect(px, 68, 8, 61); x.fillStyle = "#cbc6bd"; x.fillRect(px + 5, 68, 3, 61); x.fillStyle = "#ffffff"; x.fillRect(px + 1, 68, 1, 61);
        x.fillStyle = "#f3e6c8"; x.fillRect(px - 1, 66, 10, 3); x.fillRect(px - 1, 127, 10, 3);
      }
      [[bx + 27, "#ef5d8a"], [bx + 93, "#4fd6c8"]].forEach(([px, col], k) => {
        const sway = reduceMotion ? 0 : Math.round(Math.sin(tick / 40 + k) * 0.6);
        x.fillStyle = col; x.fillRect(px + sway, 70, 8, 22); x.fillRect(px + sway, 92, 3, 3); x.fillRect(px + 5 + sway, 92, 3, 3);
        x.fillStyle = "#131c1e"; x.fillRect(px + 2 + sway, 74, 4, 1); x.fillRect(px + 2 + sway, 78, 4, 1); x.fillRect(px + 2 + sway, 82, 2, 1);
      });
      // windows with silhouettes
      [[bx + 16, 98], [bx + 38, 98], [bx + 82, 98], [bx + 104, 98]].forEach(([wx, wy], k) => {
        const lit = reduceMotion || Math.sin(tick / 47 + k * 2) > -0.8;
        x.fillStyle = "#1d2c2f"; x.fillRect(wx - 1, wy - 1, 10, 18);
        x.fillStyle = lit ? "#ffb547" : "#7a5a2a"; x.fillRect(wx, wy, 8, 16); x.fillStyle = lit ? "#ffd27a" : "#8a6a3a"; x.fillRect(wx, wy, 8, 2);
        if (lit && k % 2 === 0) { x.fillStyle = "#5a3820"; x.fillRect(wx + 2 + (k ? 3 : 0), wy + 8, 3, 8); x.fillRect(wx + 2 + (k ? 3 : 0), wy + 6, 3, 2); }
        x.fillStyle = "#32484c"; x.fillRect(wx + 3, wy, 1, 16); x.fillRect(wx, wy + 7, 8, 1);
      });
      // door
      x.fillStyle = "#8a5a35"; x.fillRect(147, 96, 26, 34);
      x.fillStyle = isHover("door") ? "#ffd27a" : "#131c1e"; x.fillRect(150, 99, 20, 31);
      if (!isHover("door")) { x.fillStyle = "rgba(255,181,71,.18)"; x.fillRect(150, 125, 20, 5); }
      x.fillStyle = "#ffb547"; x.fillRect(150, 98, 20, 1);
      // arcade cabinet
      const ah = isHover("arcade");
      x.fillStyle = "#141a1b"; x.fillRect(232, 106, 22, 31);
      x.fillStyle = ah ? "#4e6a6f" : "#32484c"; x.fillRect(233, 107, 20, 29);
      x.fillStyle = "#ef5d8a"; x.fillRect(233, 107, 20, 4); x.fillStyle = "#ffb547"; x.fillRect(236, 108, 14, 1);
      x.fillStyle = "#071a12"; x.fillRect(235, 112, 16, 9);
      x.fillStyle = (reduceMotion || Math.floor(tick / 24) % 2) ? "#7dffb0" : "#3fbf80"; x.fillRect(237, 114, 8, 1); x.fillRect(237, 116, 11, 1); x.fillRect(237, 118, 5, 1);
      x.fillStyle = "#415b60"; x.fillRect(232, 122, 22, 4);
      x.fillStyle = "#d9455f"; x.fillRect(236, 123, 2, 2); x.fillStyle = "#4fd6c8"; x.fillRect(244, 123, 2, 2); x.fillStyle = "#ffb547"; x.fillRect(248, 123, 2, 2);
      // street lamp with glow
      const glow = reduceMotion ? 1 : 0.85 + Math.sin(tick / 9) * 0.15;
      for (let j = 0; j < 62; j++) { x.fillStyle = "rgba(255,181,71," + (0.12 * glow * (1 - j / 70)) + ")"; x.fillRect(37 - j / 3, 78 + j, (j / 3) * 2 + 2, 1); }
      x.fillStyle = "#141a1b"; x.fillRect(36, 78, 2, 59); x.fillRect(33, 134, 8, 3); x.fillRect(34, 131, 6, 3); x.fillRect(31, 70, 12, 2);
      x.fillStyle = isHover("lamp") ? "#4fd6c8" : "#ffb547"; x.fillRect(33, 72, 8, 6); x.fillStyle = "#ffe0a0"; x.fillRect(35, 73, 4, 3);
      // cat on the steps
      PCM.Chars.cat(x, 276, 128, reduceMotion ? 0 : (Math.floor(tick / 50) % 3 === 2 ? 1 : (Math.floor(tick / 300) % 7 === 0 ? 2 : 0)));
      if (isHover("cat")) { x.fillStyle = "#4fd6c8"; x.fillRect(280, 126, 6, 1); }
      // visitor
      if (!visitor.update() && pending) { const p = pending; pending = null; act(p); }
      visitor.draw(x);
    }
    let visible = true;
    new IntersectionObserver(es => { visible = es[0].isIntersecting; if (visible) kick(); }).observe(cv);
    function loop() { draw(); if (visible && (!reduceMotion || visitor.busy() || pending)) requestAnimationFrame(loop); else running = false; }
    function kick() { if (!running) { running = true; requestAnimationFrame(loop); } }
    function act(s) {
      typeText($("#heroSay"), s.text); sfx("open"); visitor.say(Math.min(4000, s.text.length * 45));
      award("hero", s.id, s.verb + " " + s.name);
      if (s.go && D.pageUrls[s.go]) setTimeout(() => (PCM.go ? PCM.go(D.pageUrls[s.go], { kind: "iris", x: cv.getBoundingClientRect().left + (s.rect[0] + s.rect[2] / 2) / W * cv.clientWidth, y: cv.getBoundingClientRect().top + (s.rect[1] + s.rect[3] / 2) / H * cv.clientHeight }) : (location.href = D.pageUrls[s.go])), 1600);
    }
    const spotAt = (px, py) => spots.find(s => px >= s.rect[0] && px <= s.rect[0] + s.rect[2] && py >= s.rect[1] && py <= s.rect[1] + s.rect[3]);
    cv.addEventListener("pointermove", e => {
      const [px, py] = canvasPoint(cv, e, W, H); hover = spotAt(px, py) || null;
      $("#heroLine").textContent = hover ? hover.verb + " " + hover.name : t("walkTo");
      kick();
    });
    cv.addEventListener("click", e => {
      const [px, py] = canvasPoint(cv, e, W, H), s = spotAt(px, py);
      visitor.walkTo(Math.max(10, Math.min(W - 10, s ? (s.walkTo != null ? s.walkTo : s.rect[0] + s.rect[2] / 2) : px)));
      if (s) $("#heroLine").textContent = s.verb + " " + s.name;
      pending = s || null; if (!s) sfx("click");
      kick();
    });
    kick();
  })();

  /* ================= Timeline ================= */
  if ($("#eraGroups")) (() => {
    const games = D.timeline.games, eras = D.timeline.eras;
    const seen = new Set(store("seen") || []);
    $$(".tl-item").forEach(c => { if (seen.has(games[+c.dataset.i].id)) c.classList.add("seen"); });
    const updCount = () => { $("#tlCount").textContent = t("seenCount", { n: games.filter(g => seen.has(g.id)).length, total: games.length }); };
    updCount();
    function openGame(i) {
      const g = games[i], er = eras.find(e => e.id === g.era), m = g.media || {};
      openModal('<article class="sheet' + (m.cover ? "" : " no-cover") + '" style="--ec:' + er.color + '">' +
        '<header class="sheet-head"><span class="m-year">' + g.year + '</span><span class="sheet-era">' + esc(er.name) + " · " + esc(er.range) + '</span><h3 id="mTitle">' + esc(g.title) + "</h3></header>" +
        '<div class="sheet-body">' + mediaFigure(m.cover, t("coverOf", { title: g.title }), "sheet-cover") +
        '<div class="sheet-info"><dl class="meta"><dt>' + esc(t("studio")) + "</dt><dd>" + esc(g.studio) + "</dd><dt>" + esc(t("engine")) + "</dt><dd>" + esc(g.engine) + "</dd></dl>" +
        "<p>" + esc(g.text.d) + '</p><p class="fact">' + esc(g.text.f) + "</p></div></div>" +
        mediaFigure(m.screenshot, t("screenshotOf", { title: g.title }), "sheet-shot", t("screenshotLabel")) +
        (g.link ? '<p class="m-link"><span class="sheet-src">' + esc(t("sourcesTitle")) + ":</span> " + linkHtml(g.link, linkLabel(g.link) + " · " + g.title) + "</p>" : "") +
        '<div class="nav"><button class="pbtn small" id="mPrev" type="button"' + (i === 0 ? " disabled" : "") + ">◀ " + esc(t("prev")) + '</button><button class="pbtn small" id="mNext" type="button"' + (i === games.length - 1 ? " disabled" : "") + ">" + esc(t("next")) + " ▶</button></div></article>",
        d => { const j = i + d; if (j >= 0 && j < games.length) openGame(j); });
      $("#mPrev").onclick = () => openGame(i - 1); $("#mNext").onclick = () => openGame(i + 1);
      if (!seen.has(g.id)) {
        seen.add(g.id); store("seen", [...seen]); const c = $('.tl-item[data-i="' + i + '"]'); if (c) c.classList.add("seen"); updCount();
        award("timeline", g.id, g.title);
      }
    }
    $$(".tl-entry").forEach(b => b.addEventListener("click", () => openGame(+b.dataset.i)));
    const deep = location.hash.slice(1); if (deep) { const i = games.findIndex(g => g.id === deep); if (i >= 0) openGame(i); }
    /* the stops light up as they scroll into view */
    if ("IntersectionObserver" in window && !reduceMotion) {
      const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { rootMargin: "0px 0px -6% 0px" });
      $$(".tl-item").forEach(el => { el.classList.add("pre"); io.observe(el); });
    }
  })();

  /* ================= Studios ================= */
  if ($("#studiosGrid")) (() => {
    const talked = new Set(store("talked") || []), box = $("#dialog");
    $$(".studio").forEach(el => {
      const s = D.studios[+el.dataset.i];
      if (talked.has(s.id)) $(".talked", el).textContent = t("talkedAlready");
      $(".talk", el).addEventListener("click", () => talk(+el.dataset.i));
    });
    function talk(i) {
      const s = D.studios[i], asked = new Set(), el = $$(".studio")[i];
      box.hidden = false; $("#dlgFace").innerHTML = $(".top", el).firstElementChild.outerHTML; $("#dlgName").textContent = t("guideAbout", { name: s.name });
      $("#dlgLink").innerHTML = s.link ? linkHtml(s.link, t("moreAbout") + " · " + linkLabel(s.link)) : "";
      const render = () => {
        const ul = $("#dlgOpts"); ul.innerHTML = "";
        s.dialog.forEach((q, k) => {
          const li = document.createElement("li"), b = document.createElement("button");
          b.type = "button"; b.textContent = "› " + q[0]; if (asked.has(k)) b.className = "used";
          b.onclick = () => {
            asked.add(k); sfx("click"); typeText($("#dlgText"), q[1]); render();
            if (asked.size === s.dialog.length && !talked.has(s.id)) {
              talked.add(s.id); store("talked", [...talked]); $(".talked", el).textContent = t("talkedAlready");
              award("studios", s.id, s.name);
            }
          };
          li.appendChild(b); ul.appendChild(li);
        });
        const li = document.createElement("li"), b = document.createElement("button");
        b.type = "button"; b.textContent = "› " + t("byeOption");
        b.onclick = () => { sfx("click"); typeText($("#dlgText"), t("byeAnswer"), 18, () => setTimeout(() => { box.hidden = true; $(".talk", el).focus(); }, 900)); };
        li.appendChild(b); ul.appendChild(li);
      };
      typeText($("#dlgText"), t("guideGreeting", { name: s.name }));
      render(); box.scrollIntoView({ behavior: smooth, block: "nearest" }); sfx("open");
      const first = $("#dlgOpts button"); if (first) first.focus({ preventScroll: true });
    }
  })();

  /* ================= Engines ================= */
  if ($("#carts")) (() => {
    const carts = $$(".cart");
    carts.forEach(b => b.addEventListener("click", () => {
      const en = D.engines[+b.dataset.i];
      carts.forEach(c => c.setAttribute("aria-pressed", "false")); b.setAttribute("aria-pressed", "true"); sfx("open");
      $("#led").classList.add("on"); $("#slot").textContent = en.name.toUpperCase();
      const scr = $("#screen");
      $("#engLinks").innerHTML = (en.links || []).map(l => linkHtml(l.url, l.label)).join(" ");
      const mm = en.media || {};
      $("#engMedia").innerHTML = mediaFigure(mm.screenshot, t("engineShot") + ": " + en.name, "eng-shot", t("engineShot")) || mediaFigure(mm.logo, t("logoOf", { name: en.name }), "eng-logo");
      typeText(scr, "> " + t("loading") + " " + en.name.toUpperCase() + "...\n> " + en.year + " · " + en.by + "\n\n" + en.text, 8, () => scr.insertAdjacentHTML("beforeend", '<span class="cur">█</span>'));
      award("engines", en.id, en.name);
    }));
  })();

  /* ================= Techniques: colour cycling ================= */
  if ($("#cycleCanvas")) (() => {
    const cv = $("#cycleCanvas"), x = cv.getContext("2d"), W = 160, H = 96;
    const img = x.createImageData(W, H), idx = new Uint8Array(W * H);
    const fixed = ["#131c1e", "#2c4044", "#415b60", "#5a757a", "#2f7d46", "#5fc46a", "#5a3820", "#8a5a35"];
    const water = ["#2f5057", "#427681", "#65a5b2", "#6fa0f0", "#bfe0ff", "#f3f8ff", "#6fa0f0", "#427681"];
    const toN = h => parseInt(h.slice(1), 16), waterN = water.map(toN), fixedN = fixed.map(toN);
    const r = rng(7);
    for (let y = 0; y < H; y++) for (let i = 0; i < W; i++) {
      let v = y < 40 ? (y < 14 ? 0 : y < 28 ? ((i + y) % 2 ? 0 : 1) : 1) : 2;
      if (y > 30 + Math.sin(i / 9) * 6 + Math.sin(i / 3) * 2) v = 3;
      const fallL = 64 + Math.round(Math.sin(y / 7) * 2), fallR = 96 + Math.round(Math.sin(y / 5));
      if (y > 20 && i > fallL && i < fallR) v = 16 + ((y * 2 + Math.floor(r() * 2) + (i % 3)) % 8);
      if (y > 78) v = 16 + ((y + Math.floor(i / 6) + (i % 2)) % 8);
      if (y > 70 && (i < 40 + Math.sin(y) * 3 || i > 120 - Math.sin(y) * 3) && y < 82) v = (i + y) % 3 ? 6 : 7;
      if ((i < 26 || i > 136) && y > 42 && y < 74 && ((i % 12) - 6) ** 2 * 0.6 + ((y - 50) % 14 - 7) ** 2 * 0.25 < 10) v = (i + y) % 2 ? 4 : 5;
      idx[y * W + i] = v;
    }
    let off = 0, on = true, last = 0, speed = 5;
    function render() {
      for (let p = 0; p < W * H; p++) {
        const v = idx[p], n = v >= 16 ? waterN[(v - 16 + 8 - off) % 8] : fixedN[v];
        img.data[p * 4] = n >> 16; img.data[p * 4 + 1] = (n >> 8) & 255; img.data[p * 4 + 2] = n & 255; img.data[p * 4 + 3] = 255;
      }
      x.putImageData(img, 0, 0);
      water.forEach((c, k) => { x.fillStyle = water[(k + 8 - off) % 8]; x.fillRect(4 + k * 6, 4, 6, 4); });
    }
    let visible = true;
    new IntersectionObserver(es => { visible = es[0].isIntersecting; }).observe(cv);
    function frame(ts) {
      if (visible && on && ts - last > 1000 / speed) { off = (off + 1) % 8; last = ts; render(); }
      requestAnimationFrame(frame);
    }
    render(); if (!reduceMotion) requestAnimationFrame(frame);
    const pbtn = $("#cycleBtn");
    pbtn.onclick = () => { on = !on; pbtn.textContent = t(on ? "cycleOn" : "cycleOff"); pbtn.setAttribute("aria-pressed", on); sfx("click"); if (reduceMotion) { off = (off + 1) % 8; render(); } award("techCycle", "x", D.techniques.demos.cycle.title); };
    $("#cycleSpeed").oninput = e => { speed = +e.target.value; award("techCycle", "x", D.techniques.demos.cycle.title); };
  })();

  /* ================= Techniques: dithering ================= */
  if ($("#ditherCanvas")) (() => {
    const cv = $("#ditherCanvas"), x = cv.getContext("2d"), W = 160, H = 96;
    const B = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]];
    const ramp = [[18, 13, 36], [61, 49, 112], [239, 93, 138], [255, 181, 71], [243, 230, 200]];
    let levels = 3, bayer = true;
    const lerp = (a, b, k) => a.map((v, i) => v + (b[i] - v) * k);
    function colorAt(k) { const s = k * (ramp.length - 1), i = Math.min(ramp.length - 2, Math.floor(s)); return lerp(ramp[i], ramp[i + 1], s - i); }
    function draw() {
      const img = x.createImageData(W, H);
      for (let y = 0; y < H; y++) for (let i = 0; i < W; i++) {
        let k = y / (H - 1);
        const dx = i - 110, dy = y - 60; if (dx * dx + dy * dy < 400) k = 1;
        if (y > 70 + Math.sin(i / 8) * 4) k = 0.05 + (y - 70) / 300;
        const th = bayer ? (B[y % 4][i % 4] + 0.5) / 16 - 0.5 : 0;
        const q = Math.max(0, Math.min(levels - 1, Math.round(k * (levels - 1) + th)));
        const c = colorAt(q / (levels - 1)), p = (y * W + i) * 4;
        img.data[p] = c[0]; img.data[p + 1] = c[1]; img.data[p + 2] = c[2]; img.data[p + 3] = 255;
      }
      x.putImageData(img, 0, 0);
    }
    draw();
    const label = D.techniques.demos.dither.title;
    $("#ditherLevels").oninput = e => { levels = +e.target.value; draw(); award("techDither", "x", label); };
    const pbtn = $("#ditherBtn");
    pbtn.onclick = () => { bayer = !bayer; pbtn.textContent = t(bayer ? "bayerOn" : "bayerOff"); pbtn.setAttribute("aria-pressed", bayer); draw(); sfx("click"); award("techDither", "x", label); };
  })();

  /* ================= Techniques: parallax ================= */
  if ($("#paraCanvas")) (() => {
    const cv = $("#paraCanvas"), x = cv.getContext("2d"), W = 160, H = 96;
    let target = 0, pos = 0, auto = !reduceMotion, visible = true;
    const r = rng(42), stars = Array.from({ length: 40 }, () => [r() * 400, r() * 40]);
    function layer(off, base, amp, freq, col, seed) {
      x.fillStyle = col;
      for (let i = 0; i < W; i++) { const wx = i + off; const h = base - Math.abs(Math.sin(wx / freq + seed)) * amp - Math.sin(wx / (freq / 3)) * amp * 0.2; x.fillRect(i, Math.round(h), 1, H); }
    }
    function draw() {
      pos += (target - pos) * 0.08; if (auto) target += 0.4;
      x.fillStyle = "#1d3134"; x.fillRect(0, 0, W, H); x.fillStyle = "#2d474c"; x.fillRect(0, 30, W, H);
      x.fillStyle = "#f3e6c8"; stars.forEach(s => x.fillRect(Math.round(((s[0] - pos * 0.05) % 400 + 400) % 400) % W, s[1], 1, 1));
      x.fillStyle = "#ffb547"; x.fillRect(Math.round(120 - (pos * 0.05) % 200), 12, 8, 8);
      layer(pos * 0.2, 60, 18, 22, "#415b60", 1); layer(pos * 0.5, 72, 12, 12, "#5a757a", 3); layer(pos, 84, 8, 6, "#2f7d46", 5);
      x.fillStyle = "#8a5a35"; for (let i = -10; i < W + 10; i += 10) x.fillRect(Math.round(i - ((pos * 2) % 10)), 82, 2, 14); x.fillRect(0, 86, W, 2);
    }
    new IntersectionObserver(es => { visible = es[0].isIntersecting; }).observe(cv);
    (function loop() { if (visible) draw(); requestAnimationFrame(loop); })();
    const move = e => { const rc = cv.getBoundingClientRect(); auto = false; target = ((e.clientX - rc.left) / rc.width) * 400; award("techParallax", "x", D.techniques.demos.parallax.title); };
    cv.addEventListener("pointermove", move); cv.addEventListener("pointerdown", move);
    cv.addEventListener("pointerleave", () => { auto = !reduceMotion; });
  })();

  /* ================= Techniques: dynamic music ================= */
  if ($("#musCanvas")) (() => {
    const themes = {
      A: { wave: "triangle", step: 0.18, mel: [60, 64, 67, 72, 67, 64, 62, 65, 69, 72, 69, 65, 64, 67, 71, 74], bass: [48, 48, 53, 52] },
      B: { wave: "square", step: 0.14, mel: [57, 60, 63, 57, 60, 63, 62, 61, 57, 60, 64, 57, 60, 64, 63, 62], bass: [45, 45, 44, 44] },
    };
    let playing = false, cur = "A", queued = null, step = 0, timer = null, nextT = 0;
    const cv = $("#musCanvas"), x = cv.getContext("2d"), info = $("#musInfo");
    const mtof = m => 440 * Math.pow(2, (m - 69) / 12);
    function drawBar(s) {
      x.fillStyle = "#000"; x.fillRect(0, 0, 160, 40);
      for (let i = 0; i < 16; i++) { x.fillStyle = i === s ? (cur === "A" ? "#4fd6c8" : "#ef5d8a") : (i % 4 === 0 ? "#4f6165" : "#32484c"); x.fillRect(4 + i * 9.6, 10, 7, 20); }
      if (queued) { x.fillStyle = "#ffb547"; x.fillRect(4, 34, 152, 2); }
    }
    function tick() {
      const a = ac(); if (!a) return;
      while (nextT < a.currentTime + 0.15) {
        if (step % 16 === 0 && queued) { cur = queued; queued = null; info.textContent = t("musicSwitched", { theme: t(cur === "A" ? "calm" : "danger") }); }
        const th = themes[cur], s = step % 16, when = nextT - a.currentTime;
        if (PCM.soundOn) {
          tone(mtof(th.mel[s]), 0.16, th.wave, 0.045, when);
          if (s % 4 === 0) tone(mtof(th.bass[s / 4]), 0.4, "triangle", 0.07, when);
          if (cur === "B" && s % 2 === 1) tone(90, 0.04, "sawtooth", 0.02, when);
        }
        drawBar(s); step++; nextT += th.step;
      }
    }
    drawBar(-1);
    const play = $("#musPlay");
    play.onclick = () => {
      const a = ac(); if (!a) { info.textContent = t("noAudio"); return; }
      playing = !playing; play.textContent = t(playing ? "stopMusic" : "play");
      if (playing) {
        if (!PCM.soundOn) info.textContent = t("soundOff");
        step = 0; nextT = a.currentTime + 0.05; timer = setInterval(tick, 40); award("techMusic", "x", D.techniques.demos.music.title);
      } else { clearInterval(timer); drawBar(-1); }
    };
    const pick = k => () => {
      $("#musA").setAttribute("aria-pressed", k === "A"); $("#musB").setAttribute("aria-pressed", k === "B");
      if (!playing) { cur = k; return; }
      if (k !== cur) { queued = k; info.textContent = t("musicQueued"); }
    };
    $("#musA").onclick = pick("A"); $("#musB").onclick = pick("B");
  })();

})();
