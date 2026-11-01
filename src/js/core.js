/* Point and Click Museum · core: data, i18n, sprites, sound, score, modal. */
"use strict";
window.PCM = (() => {
  const D = JSON.parse(document.getElementById("pcm-data").textContent);
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const fmt = (s, vars) => (vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m)) : String(s));
  const t = (key, vars) => fmt(D.ui[key] != null ? D.ui[key] : key, vars);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- storage (per-viewer conveniences only) ---------- */
  function store(k, v) {
    try {
      if (v === undefined) return JSON.parse(localStorage.getItem("pcm-" + k));
      localStorage.setItem("pcm-" + k, JSON.stringify(v));
    } catch (e) { return null; }
    return null;
  }

  /* ---------- sprites ---------- */
  const spriteURL = name => D.root + "img/sprites/" + name + ".png";
  function drawSprite(ctx, name, x0, y0, s = 1) {
    const rows = D.sprites.sprites[name], pal = D.sprites.palette;
    if (!rows) return;
    rows.forEach((row, j) => [...row].forEach((ch, i) => {
      if (ch !== "." && pal[ch]) { ctx.fillStyle = pal[ch]; ctx.fillRect(x0 + i * s, y0 + j * s, s, s); }
    }));
  }
  function hash(str) { let h = 2166136261; for (const ch of str) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
  function rng(seed) { let s = seed >>> 0 || 1; return () => (s = (Math.imul(s ^ (s >>> 15), 2246822519) + 0x9e3779b9) >>> 0, s / 4294967296); }
  function badge(canvas, name) {
    const x = canvas.getContext("2d"), r = rng(hash(name)), cols = ["#ffb547", "#ef5d8a", "#4fd6c8", "#8a8cff", "#5fc46a", "#e07a2e"];
    const fg = cols[Math.floor(r() * cols.length)], fg2 = cols[Math.floor(r() * cols.length)];
    canvas.width = 16; canvas.height = 16; x.fillStyle = "#2f2559"; x.fillRect(0, 0, 16, 16);
    x.fillStyle = "#120d24"; x.fillRect(1, 1, 14, 14);
    for (let j = 0; j < 12; j++) for (let i = 0; i < 6; i++) {
      const v = r(); if (v < 0.5) continue; x.fillStyle = v > 0.82 ? fg2 : fg;
      x.fillRect(2 + i, 2 + j, 1, 1); x.fillRect(13 - i, 2 + j, 1, 1);
    }
  }
  function pixelText(ctx, str, x0, y0, col) {
    const G = D.font.glyphs; ctx.fillStyle = col; let cx = x0;
    for (const ch of str) { const g = G[ch] || G[" "]; g.forEach((row, j) => [...row].forEach((v, i) => { if (v === "1") ctx.fillRect(cx + i, y0 + j, 1, 1); })); cx += g[0].length + 1; }
  }
  function pixelTextWidth(str) { const G = D.font.glyphs; let w = 0; for (const ch of str) w += (G[ch] || G[" "])[0].length + 1; return w - 1; }
  /* canvas pointer -> scene coords */
  function canvasPoint(cv, e, W, H) { const rc = cv.getBoundingClientRect(); return [(e.clientX - rc.left) / rc.width * W, (e.clientY - rc.top) / rc.height * H]; }

  /* ---------- sound ---------- */
  let AC = null, soundOn = store("snd") !== false;
  function ac() {
    if (!AC) { try { AC = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { AC = null; } }
    if (AC && AC.state === "suspended") AC.resume().catch(() => {});
    return AC;
  }
  function tone(freq, dur = 0.08, type = "square", vol = 0.05, when = 0) {
    const a = ac(); if (!a) return; const tt = a.currentTime + when;
    const o = a.createOscillator(), g = a.createGain(); o.type = type; o.frequency.setValueAtTime(freq, tt);
    g.gain.setValueAtTime(vol, tt); g.gain.exponentialRampToValueAtTime(0.0001, tt + dur);
    o.connect(g).connect(a.destination); o.start(tt); o.stop(tt + dur + 0.02);
  }
  function sfx(kind) {
    if (!soundOn) return;
    if (kind === "click") tone(660, 0.05);
    else if (kind === "open") { tone(440, 0.06); tone(660, 0.08, "square", 0.05, 0.06); }
    else if (kind === "bad") { tone(180, 0.12, "sawtooth", 0.05); tone(140, 0.16, "sawtooth", 0.05, 0.1); }
    else if (kind === "points") [523, 659, 784, 1047].forEach((f, i) => tone(f, 0.09, "square", 0.05, i * 0.07));
    else if (kind === "win") [392, 523, 659, 784, 659, 1047].forEach((f, i) => tone(f, 0.14, "triangle", 0.08, i * 0.11));
    else if (kind === "type") tone(1200 + Math.random() * 300, 0.015, "square", 0.015);
  }
  const sndBtn = $("#sndBtn"), crtBtn = $("#crtBtn");
  sndBtn.setAttribute("aria-pressed", soundOn);
  sndBtn.addEventListener("click", () => { soundOn = !soundOn; store("snd", soundOn); sndBtn.setAttribute("aria-pressed", soundOn); sfx("click"); });
  let crtOn = store("crt") !== false;
  document.body.classList.toggle("crt", crtOn); crtBtn.setAttribute("aria-pressed", crtOn);
  crtBtn.addEventListener("click", () => { crtOn = !crtOn; store("crt", crtOn); document.body.classList.toggle("crt", crtOn); crtBtn.setAttribute("aria-pressed", crtOn); sfx("click"); });

  /* ---------- typewriter ---------- */
  function typeText(el, text, speed = 18, done) {
    clearInterval(el._tt); el.textContent = ""; let i = 0;
    if (reduceMotion) { el.textContent = text; if (done) done(); return; }
    el._tt = setInterval(() => {
      el.textContent = text.slice(0, ++i); if (i % 3 === 0) sfx("type");
      if (i >= text.length) { clearInterval(el._tt); if (done) done(); }
    }, speed);
  }

  /* ---------- score ---------- */
  const SC = D.site.score;
  const awarded = new Set(store("awarded") || []);
  const scoreOf = () => [...awarded].reduce((sum, id) => { const a = SC.awards[id.split(":")[0]]; return sum + (a ? a.points : 0); }, 0);
  let score = Math.min(SC.total, scoreOf());
  function renderScore() { $("#score").textContent = t("scoreFmt", { score, total: SC.total }); }
  function toast(msg) { const d = document.createElement("div"); d.textContent = msg; $("#toast").appendChild(d); setTimeout(() => d.remove(), 2700); }
  /* award("timeline", "zork", "Zork") — key must exist in site.json score.awards */
  function award(key, uid, label) {
    const cfg = SC.awards[key]; if (!cfg) { console.warn("Unknown award", key); return false; }
    const id = key + ":" + (uid || "x");
    if (awarded.has(id)) return false;
    if (cfg.cap && [...awarded].filter(a => a.startsWith(key + ":")).length >= cfg.cap) return false;
    awarded.add(id); store("awarded", [...awarded]); score = Math.min(SC.total, scoreOf()); renderScore();
    toast("+" + cfg.points + " · " + (label || t("award_" + key))); sfx("points");
    if (score >= SC.total) setTimeout(showCert, 1200);
    return true;
  }
  renderScore();

  /* ---------- modal ---------- */
  const modalBg = $("#modalBg"), modal = $("#modal");
  let modalNav = null, lastFocus = null;
  function openModal(html, nav) {
    if (!modalBg.classList.contains("open")) lastFocus = document.activeElement;
    modal.innerHTML = html + '<button class="pbtn small close" id="mClose" type="button" aria-label="' + esc(t("close")) + '">X</button>';
    modalBg.classList.add("open"); modalNav = nav || null; $("#mClose").onclick = closeModal; $("#mClose").focus(); sfx("open");
  }
  function closeModal() { modalBg.classList.remove("open"); modalNav = null; if (lastFocus) lastFocus.focus(); }
  modalBg.addEventListener("click", e => { if (e.target === modalBg) closeModal(); });
  document.addEventListener("keydown", e => {
    if (!modalBg.classList.contains("open")) return;
    if (e.key === "Escape") closeModal();
    if (modalNav && e.key === "ArrowRight") modalNav(1);
    if (modalNav && e.key === "ArrowLeft") modalNav(-1);
    if (e.key === "Tab") { /* keep focus inside the dialog */
      const f = $$("button, a, input", modal).filter(el => !el.disabled); if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  });
  function showCert() {
    openModal('<div class="cert"><img src="' + spriteURL("star") + '" alt="" width="96" height="96"><h3 id="mTitle">' + esc(t("certTitle")) + "</h3><p style=\"margin:0 auto\">" + esc(t("certBody")) + '</p><p style="margin:16px auto 0"><button class="pbtn" id="resetAll" type="button">' + esc(t("certReset")) + "</button></p></div>");
    sfx("win");
    $("#resetAll").onclick = () => {
      awarded.clear(); score = 0; store("awarded", []); store("seen", []); store("talked", []); renderScore(); closeModal();
      $$(".card.seen").forEach(c => c.classList.remove("seen"));
    };
  }

  return { D, $, $$, t, fmt, esc, store, spriteURL, drawSprite, hash, rng, badge, pixelText, pixelTextWidth, canvasPoint,
    tone, sfx, ac, get soundOn() { return soundOn; }, typeText, award, toast, openModal, closeModal, reduceMotion };
})();
