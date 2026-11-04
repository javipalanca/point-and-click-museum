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
  /* game volume (0–1), for DOSBox (js-dos setVolume) and ScummVM (a gain node inside its frame); remembered */
  const vol = $("#dosVol"), volOut = $("#dosVolOut");
  let volume = store("dosVolume") == null ? 0.8 : +store("dosVolume");
  const showVolume = () => { vol.value = volume; volOut.textContent = Math.round(volume * 100) + "%"; };
  function applyVolume() {
    if (player) try { player.setVolume(volume); } catch (e) { /* older js-dos */ }
    const f = host.querySelector(".svm-frame");
    if (f) try { f.contentWindow.PCM_SET_VOLUME && f.contentWindow.PCM_SET_VOLUME(volume); } catch (e) { /* frame not ready */ }
  }
  showVolume();

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

  /* the mouse controls only make sense for DOSBox; ScummVM reads the browser mouse directly */
  function mouseMode(engine) {
    const svm = engine === "scummvm";
    mouseBtn.hidden = svm; sens.hidden = svm; $("label[for=dosSens]").hidden = svm;
    if (svm) hint.textContent = t("svmMouseHint"); else renderMouse();
  }

  async function stop() {
    if (document.pointerLockElement) document.exitPointerLock();
    mouseMode("dosbox");
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
      volume,
      onEvent: (ev) => { if (ev === "ci-ready" && player) { try { player.setMouseCapture(capture); player.setMouseSensitivity(sensitivity); player.setVolume(volume); } catch (e) { /* older player */ } } },
    });
    player = window.Dos(el, options);
    stopBtn.disabled = false; fullBtn.disabled = false;
    $("#dosScreen").scrollIntoView({ behavior: PCM.reduceMotion ? "auto" : "smooth", block: "nearest" });
    return true;
  }

  /* ScummVM: player.html in an iframe; it reads window.PCM_SVM_JOB from this page */
  async function runScummVM(title, job) {
    sfx("open");
    if (!D.svm || !D.svm.available) { now.textContent = t("svmMissing"); toast(t("svmMissing")); return false; }
    await stop();
    window.PCM_SVM_JOB = Object.assign({ data: D.svm.data, inline: D.svm.inline, volume }, job);
    idle.hidden = true; now.textContent = "▶ " + title + " · ScummVM";
    const f = document.createElement("iframe");
    f.className = "svm-frame"; f.title = title; f.allow = "autoplay; fullscreen; gamepad";
    f.src = D.svm.base + "player.html#" + encodeURI(job.args.join(" "));
    f.addEventListener("load", () => { try { f.contentWindow.focus(); f.contentWindow.postMessage("pcm-focus", "*"); } catch (e) { /* ignore */ } });
    host.appendChild(f);
    mouseMode("scummvm");
    stopBtn.disabled = false; fullBtn.disabled = false;
    $("#dosScreen").scrollIntoView({ behavior: PCM.reduceMotion ? "auto" : "smooth", block: "nearest" });
    return true;
  }
  const svmArgs = id => ["--path=/games/" + id, "--auto-detect"];

  /* ---------- zip reading in the browser (for "bring your own game") ---------- */
  async function unzip(buf) {
    const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength), out = {};
    let eocd = -1;
    for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65557); i--) if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    if (eocd < 0) throw new Error("not a zip");
    let p = dv.getUint32(eocd + 16, true);
    for (let k = 0, n = dv.getUint16(eocd + 10, true); k < n; k++) {
      const method = dv.getUint16(p + 10, true), size = dv.getUint32(p + 20, true), nl = dv.getUint16(p + 28, true),
        xl = dv.getUint16(p + 30, true), cl = dv.getUint16(p + 32, true), local = dv.getUint32(p + 42, true);
      const name = new TextDecoder().decode(buf.subarray(p + 46, p + 46 + nl)).replace(/\\/g, "/");
      p += 46 + nl + xl + cl;
      if (name.endsWith("/") || name.startsWith("__MACOSX/")) continue;
      const start = local + 30 + dv.getUint16(local + 26, true) + dv.getUint16(local + 28, true), raw = buf.subarray(start, start + size);
      if (method === 0) out[name] = raw.slice();
      else if (method === 8) out[name] = new Uint8Array(await new Response(new Blob([raw]).stream().pipeThrough(new DecompressionStream("deflate-raw"))).arrayBuffer());
      else throw new Error("unsupported zip compression " + method);
    }
    return out;
  }
  /* same rules as tools/add_game.py */
  const SIGNATURES = [
    ["sky", n => n.has("sky.dnr") && n.has("sky.dsk")], ["queen", n => n.has("queen.1") || n.has("queen.1c")],
    ["lure", n => n.has("disk1.vga")], ["drascula", n => n.has("packet.001")],
    ["dreamweb", n => [...n].some(x => /^dreamw\w*\.r00$/.test(x))], ["teenagent", n => n.has("on.res") && n.has("off.res")],
    ["cge", n => n.has("vol.cat") && n.has("vol.dat")], ["sci", n => n.has("resource.map")],
    ["agi", n => (n.has("logdir") && n.has("picdir")) || [...n].some(x => x.endsWith(".wag"))],
    ["scumm", n => [...n].some(x => /^(\d\d\.lfl|.+\.(la0|he0|sou))$/.test(x) || (x.endsWith(".000") && x !== "resource.000"))],
    ["ags", n => n.has("ac2game.dat") || [...n].some(x => x.endsWith(".ags"))],
  ];
  function detectScummVM(files) {
    const dirs = {};
    Object.keys(files).forEach(f => { const i = f.lastIndexOf("/"), d = i < 0 ? "" : f.slice(0, i); (dirs[d] = dirs[d] || new Set()).add(f.slice(i + 1).toLowerCase()); });
    const order = Object.keys(dirs).sort((a, b) => a.split("/").length - b.split("/").length);
    for (const [engine, test] of SIGNATURES) for (const d of order) if (test(dirs[d])) return { engine, folder: d };
    return null;
  }
  const isWindowsExe = b => b[0] === 0x4d && b[1] === 0x5a && b.length > 0x40 &&
    (o => b[o] === 0x50 && b[o + 1] === 0x45 && b[o + 2] === 0 && b[o + 3] === 0)(b[0x3c] | b[0x3d] << 8 | b[0x3e] << 16 | b[0x3f] << 24);
  function guessExe(files) {
    const skip = /^(install|setup|uninst|config|setsound|sound|dos4gw|cwsdpmi|pkunzip|readme|patch|vesa|univbe)\.\w+$/i;
    return Object.keys(files).filter(f => /\.(exe|com|bat)$/i.test(f) && !skip.test(f.split("/").pop()) && !isWindowsExe(files[f]))
      .sort((a, b) => a.split("/").length - b.split("/").length || /\.exe$/i.test(b) - /\.exe$/i.test(a))[0] || "";
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
  vol.addEventListener("input", () => { volume = +vol.value; store("dosVolume", volume); showVolume(); applyVolume(); });
  sens.addEventListener("input", () => {
    sensitivity = +sens.value; store("dosSens", sensitivity);
    if (player) try { player.setMouseSensitivity(sensitivity); } catch (e) { /* ignore */ }
  });

  $$(".dos-play").forEach(b => b.addEventListener("click", () => {
    const g = D.arcade.games.find(x => x.id === b.dataset.id);
    if (!g || !g.bundle) return;
    if (g.engine === "scummvm") {
      runScummVM(g.title, { gameId: g.id, engine: g.svmEngine, files: g.files || [], gameBase: "games/" + g.id + "/", args: svmArgs(g.id) });
      return;
    }
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
      const bytes = new Uint8Array(await file.arrayBuffer()), want = $("#byoEngine").value;
      let files;
      try { files = await unzip(bytes); } catch (x) { err.textContent = x.message; sfx("bad"); return; }
      const svm = want !== "dosbox" ? detectScummVM(files) : null;
      if (svm && (want === "scummvm" || !exe)) {
        const prefix = svm.folder ? svm.folder + "/" : "", mem = {};
        Object.keys(files).forEach(f => { if (f.startsWith(prefix)) mem[f.slice(prefix.length)] = files[f]; });
        runScummVM(file.name, { gameId: "byo", engine: svm.engine, files: Object.keys(mem), memFiles: mem, gameBase: "", args: svmArgs("byo") });
        return;
      }
      if (want === "scummvm") { err.textContent = t("byoNoGame"); sfx("bad"); return; }
      const run_exe = exe || guessExe(files);
      if (!run_exe) { err.textContent = t("byoNoGame"); sfx("bad"); return; }
      run(file.name, { dosboxConf: dosboxConf(run_exe), initFs: bytes });
    } else { err.textContent = t("byoBadType"); sfx("bad"); }
  });
})();

/* ---------- catalogue: search, company, A–Z index, sort ---------- */
if (document.getElementById("catList")) (() => {
  const { $, $$, t, sfx } = PCM;
  const list = $("#catList"), items = $$(".dos-game", list), count = $("#catCount"), empty = $("#catEmpty");
  const search = $("#catSearch"), studio = $("#catStudio"), sort = $("#catSort"), letters = $$(".letters button"), engineSel = $("#catEngine");
  if (!search) return; // few games: no filters
  const norm = s => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  items.forEach(el => { el._text = norm(el.querySelector("h3").textContent + " " + el.dataset.studio); });
  let letter = "";
  function apply() {
    const q = norm(search.value.trim()), st = studio.value, en = engineSel ? engineSel.value : "";
    let n = 0;
    items.forEach(el => {
      const show = (!q || q.split(/\s+/).every(w => el._text.includes(w))) && (!st || el.dataset.studio === st) && (!letter || el.dataset.letter === letter) && (!en || el.dataset.engine === en);
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
  if (engineSel) engineSel.addEventListener("change", () => { sfx("click"); apply(); });
  sort.addEventListener("change", () => { sfx("click"); reorder(); });
  letters.forEach(b => b.addEventListener("click", () => {
    letter = b.dataset.l; letters.forEach(x => x.setAttribute("aria-pressed", String(x === b))); sfx("click"); apply(); list.scrollTop = 0;
  }));
  document.addEventListener("keydown", e => {
    if (e.key === "/" && document.activeElement === document.body) { e.preventDefault(); search.focus(); }
  });
  apply();
})();
