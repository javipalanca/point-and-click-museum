/* Point and Click Museum · DOSBox room powered by js-dos (https://js-dos.com).
   Games are listed in data/arcade.json. A game with a "bundle" (.jsdos file) gets a PLAY button.
   Visitors can also run their own .jsdos bundle or a .zip with the game files: everything runs
   locally in the browser and nothing is uploaded.

   Mouse: DOS games read a *relative* mouse, so the reliable mode is pointer capture (the same as
   DOSBox's autolock): click the screen to grab the mouse, Esc to release it. If the browser or the
   embedding frame refuses pointer lock, we fall back to direct mode automatically. */
"use strict";
if (document.getElementById("dosHost")) (() => {
  const { D, $, $$, t, sfx, toast, store } = PCM;
  const E = D.arcade.emulator;
  const base = D.arcadeVendored ? D.root + E.local : E.cdn;
  const host = $("#dosHost"), idle = $("#dosIdle"), now = $("#dosNow"), stopBtn = $("#dosStop"), fullBtn = $("#dosFull");
  const mouseBtn = $("#dosMouse"), sens = $("#dosSens"), hint = $("#dosMouseHint");
  let loader = null, player = null, blobUrl = null;
  const lockAllowed = "exitPointerLock" in document && !(window.matchMedia && matchMedia("(pointer: coarse)").matches);
  let capture = lockAllowed && store("dosCapture") !== false;
  let sensitivity = +(store("dosSens") || 0.5);
  sens.value = sensitivity;

  function renderMouse() {
    mouseBtn.setAttribute("aria-pressed", String(capture));
    mouseBtn.textContent = t(capture ? "mouseLock" : "mouseDirect");
    hint.textContent = t(capture ? "mouseHintLock" : "mouseHintDirect");
    mouseBtn.disabled = !lockAllowed;
  }
  renderMouse();

  function loadJsDos() {
    if (window.Dos) return Promise.resolve();
    if (loader) return loader;
    loader = new Promise((resolve, reject) => {
      const css = document.createElement("link"); css.rel = "stylesheet"; css.href = base + "js-dos.css"; document.head.appendChild(css);
      const s = document.createElement("script"); s.src = base + "js-dos.js"; s.async = true;
      s.onload = () => (window.Dos ? resolve() : reject(new Error("js-dos")));
      s.onerror = () => { loader = null; reject(new Error("js-dos")); };
      document.head.appendChild(s);
    });
    return loader;
  }

  function dosboxConf(exe) {
    const clean = String(exe || "").trim().replace(/\//g, "\\");
    const parts = clean.split("\\").filter(Boolean), file = parts.pop() || "", dir = parts.join("\\");
    return ["[sdl]", "autolock=" + capture, "sensitivity=100", "", "[dosbox]", "machine=svga_s3", "memsize=16", "", "[cpu]", "core=auto", "cputype=auto", "cycles=auto", "",
      "[mixer]", "rate=44100", "", "[sblaster]", "sbtype=sb16", "", "[autoexec]", "@echo off", "mount c .", "c:",
      ...(dir ? ["cd \\" + dir] : []), ...(file ? [file] : [])].join("\n") + "\n";
  }

  async function stop() {
    if (document.pointerLockElement) document.exitPointerLock();
    if (player) { try { await player.stop(); } catch (e) { /* already stopped */ } }
    player = null; host.innerHTML = ""; idle.hidden = false; now.textContent = t("arcadeNothing");
    stopBtn.disabled = true; fullBtn.disabled = true;
    if (blobUrl) { URL.revokeObjectURL(blobUrl); blobUrl = null; }
  }

  async function run(title, opts, blob) {
    sfx("open");
    now.textContent = t("arcadeLoading", { title });
    try { await loadJsDos(); }
    catch (e) { now.textContent = t("arcadeEmuError"); toast(t("arcadeEmuError")); return false; }
    await stop();
    if (blob) blobUrl = blob;
    idle.hidden = true; now.textContent = "▶ " + title;
    const el = document.createElement("div"); el.className = "dos-player"; host.appendChild(el);
    const options = Object.assign({ pathPrefix: base + "emulators/" }, E.options, opts, {
      mouseCapture: capture, mouseSensitivity: sensitivity,
      onEvent: (ev) => { if (ev === "ci-ready" && player) { try { player.setMouseCapture(capture); player.setMouseSensitivity(sensitivity); } catch (e) { /* older player */ } } },
    });
    player = window.Dos(el, options);
    stopBtn.disabled = false; fullBtn.disabled = false;
    $("#dosScreen").scrollIntoView({ behavior: PCM.reduceMotion ? "auto" : "smooth", block: "nearest" });
    return true;
  }

  /* pointer lock refused (sandboxed frame, some browsers): switch to direct mode */
  document.addEventListener("pointerlockerror", () => {
    if (!capture) return;
    capture = false; store("dosCapture", false); renderMouse();
    if (player) try { player.setMouseCapture(false); } catch (e) { /* ignore */ }
    toast(t("pointerLockFail"));
  });
  document.addEventListener("pointerlockchange", () => {
    $("#dosScreen").classList.toggle("locked", !!document.pointerLockElement);
  });
  mouseBtn.addEventListener("click", () => {
    capture = !capture; store("dosCapture", capture); renderMouse(); sfx("click");
    if (!capture && document.pointerLockElement) document.exitPointerLock();
    if (player) try { player.setMouseCapture(capture); } catch (e) { /* ignore */ }
  });
  sens.addEventListener("input", () => {
    sensitivity = +sens.value; store("dosSens", sensitivity);
    if (player) try { player.setMouseSensitivity(sensitivity); } catch (e) { /* ignore */ }
  });

  $$(".dos-play").forEach(b => b.addEventListener("click", () => {
    const g = D.arcade.games.find(x => x.id === b.dataset.id);
    if (!g || !g.bundle) return;
    const packed = window.PCM_BUNDLES && window.PCM_BUNDLES[g.bundle];
    if (packed) { /* bundle shipped as base64 (build.py --inline-bundles) */
      const bin = atob(packed), bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const u = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
      run(g.title, { url: u }, u);
    } else run(g.title, { url: /^https?:/.test(g.bundle) ? g.bundle : D.root + g.bundle });
  }));
  stopBtn.addEventListener("click", () => { sfx("click"); stop(); });
  fullBtn.addEventListener("click", () => {
    const el = $("#dosScreen");
    try { (el.requestFullscreen || el.webkitRequestFullscreen).call(el); } catch (e) { toast(t("fullscreenFail")); }
  });

  $("#byoForm").addEventListener("submit", async e => {
    e.preventDefault();
    const err = $("#byoErr"), file = $("#byoFile").files[0], exe = $("#byoExe").value.trim();
    err.textContent = "";
    if (!file) { err.textContent = t("byoNoFile"); sfx("bad"); return; }
    const name = file.name.toLowerCase();
    if (name.endsWith(".jsdos")) {
      const u = URL.createObjectURL(file);
      run(file.name, { url: u }, u);
    } else if (name.endsWith(".zip")) {
      if (!exe) { err.textContent = t("byoNoExe"); sfx("bad"); return; }
      const bytes = new Uint8Array(await file.arrayBuffer());
      run(file.name, { dosboxConf: dosboxConf(exe), initFs: bytes });
    } else { err.textContent = t("byoBadType"); sfx("bad"); }
  });
})();

/* ---------- catalogue: search, company, A–Z index, sort ---------- */
if (document.getElementById("catList")) (() => {
  const { $, $$, t, sfx } = PCM;
  const list = $("#catList"), items = $$(".dos-game", list), count = $("#catCount"), empty = $("#catEmpty");
  const search = $("#catSearch"), studio = $("#catStudio"), sort = $("#catSort"), letters = $$(".letters button");
  if (!search) return; // few games: no filters
  const norm = s => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  items.forEach(el => { el._text = norm(el.querySelector("h3").textContent + " " + el.dataset.studio); });
  let letter = "";
  function apply() {
    const q = norm(search.value.trim()), st = studio.value;
    let n = 0;
    items.forEach(el => {
      const show = (!q || q.split(/\s+/).every(w => el._text.includes(w))) && (!st || el.dataset.studio === st) && (!letter || el.dataset.letter === letter);
      el.hidden = !show; if (show) n++;
    });
    count.textContent = t("catCount", { n, total: items.length });
    empty.hidden = n > 0;
  }
  function reorder() {
    const by = sort.value;
    items.slice().sort((a, b) => by === "year" ? (+a.dataset.year - +b.dataset.year) || a.dataset.key.localeCompare(b.dataset.key) : a.dataset.key.localeCompare(b.dataset.key))
      .forEach(el => list.appendChild(el));
  }
  search.addEventListener("input", apply);
  studio.addEventListener("change", () => { sfx("click"); apply(); });
  sort.addEventListener("change", () => { sfx("click"); reorder(); });
  letters.forEach(b => b.addEventListener("click", () => {
    letter = b.dataset.l; letters.forEach(x => x.setAttribute("aria-pressed", String(x === b))); sfx("click"); apply(); list.scrollTop = 0;
  }));
  document.addEventListener("keydown", e => {
    if (e.key === "/" && document.activeElement === document.body) { e.preventDefault(); search.focus(); }
  });
  apply();
})();
