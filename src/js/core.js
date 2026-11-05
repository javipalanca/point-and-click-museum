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
  /* Real image with its credit line (data from data/media.json, prepared by build.py). */
  function mediaFigure(m, alt, cls, caption) {
    if (!m) return "";
    const rights = m.licenseUrl ? '<a href="' + esc(m.licenseUrl) + '" target="_blank" rel="noopener">' + esc(m.rights) + "</a>" : esc(m.rights);
    return '<figure class="media ' + (cls || "") + " media-" + m.role + '"><img src="' + esc(m.src) + '" width="' + m.w + '" height="' + m.h + '" alt="' + esc(alt) + '" loading="lazy" decoding="async">' +
      "<figcaption>" + (caption ? '<span class="media-cap">' + esc(caption) + "</span> " : "") + (m.label ? "<cite>" + esc(m.label) + "</cite> · " : "") + rights + " · " + esc(t("via")) +
      ' <a href="' + esc(m.url) + '" target="_blank" rel="noopener">' + esc(m.via) + " ↗</a></figcaption></figure>";
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
  /* sound and CRT switches: every [data-toggle] button on the page (header and map panel) */
  let crtOn = store("crt") !== false;
  function renderToggles() {
    $$('[data-toggle="sound"]').forEach(b => b.setAttribute("aria-pressed", soundOn));
    $$('[data-toggle="crt"]').forEach(b => b.setAttribute("aria-pressed", crtOn));
    document.body.classList.toggle("crt", crtOn);
  }
  $$("[data-toggle]").forEach(b => b.addEventListener("click", () => {
    if (b.dataset.toggle === "sound") { soundOn = !soundOn; store("snd", soundOn); }
    else { crtOn = !crtOn; store("crt", crtOn); }
    renderToggles(); sfx("click");
    window.PCM.track("toggle", { what: b.dataset.toggle, on: b.dataset.toggle === "sound" ? soundOn : crtOn });
  }));
  renderToggles();

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
  function renderScore() {
    $("#score").textContent = t("scoreShort", { score, total: SC.total });
    const bar = $("#scoreBar"); if (bar) bar.style.width = (100 * score / SC.total) + "%";
    const chip = $(".score-chip"); if (chip) chip.title = t("scoreFmt", { score, total: SC.total });
  }
  function toast(msg) { const d = document.createElement("div"); d.textContent = msg; $("#toast").appendChild(d); setTimeout(() => d.remove(), 2700); }
  /* award("timeline", "zork", "Zork") — key must exist in site.json score.awards */
  function award(key, uid, label) {
    const cfg = SC.awards[key]; if (!cfg) { console.warn("Unknown award", key); return false; }
    const id = key + ":" + (uid || "x");
    if (awarded.has(id)) return false;
    if (cfg.cap && [...awarded].filter(a => a.startsWith(key + ":")).length >= cfg.cap) return false;
    awarded.add(id); store("awarded", [...awarded]); score = Math.min(SC.total, scoreOf()); renderScore();
    toast("+" + cfg.points + " · " + (label || t("award_" + key))); sfx("points");
    window.PCM.track("award", { key });
    if (score >= SC.total) { window.PCM.track("score_complete"); setTimeout(showCert, 1200); }
    return true;
  }
  renderScore();
  /* a language chosen on the site wins over the browser's (the root page reads it, see build.py lang_redirect) */
  document.addEventListener("click", e => { const a = e.target.closest && e.target.closest("a[hreflang]"); if (a) store("lang", a.getAttribute("hreflang")); }, true);

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
      $$(".tl-item.seen").forEach(c => c.classList.remove("seen"));
    };
  }

  return { D, $, $$, t, fmt, esc, store, spriteURL, drawSprite, hash, rng, mediaFigure, pixelText, pixelTextWidth, canvasPoint,
    tone, sfx, ac, get soundOn() { return soundOn; }, typeText, award, toast, openModal, closeModal, reduceMotion,
    track() { /* replaced by analytics.js */ } };
})();
