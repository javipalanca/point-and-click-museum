/* Point and Click Museum · DOSBox room powered by js-dos (https://js-dos.com).
   Games are listed in data/arcade.json. A game with a "bundle" (.jsdos file) gets a PLAY button.
   Visitors can also run their own .jsdos bundle or a .zip with the game files: everything runs
   locally in the browser and nothing is uploaded.

   Mouse: DOS games read a *relative* mouse, so the reliable mode is pointer capture (the same as
   DOSBox's autolock): click the screen to grab the mouse, Esc to release it. If the browser or the
   embedding frame refuses pointer lock, we fall back to direct mode automatically. */
"use strict";
if (document.getElementById("dosHost")) (() => {
  const { D, $, $$, t, esc, sfx, toast, store } = PCM;
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
    catch (e) { now.textContent = t("arcadeEmuError"); toast(t("arcadeEmuError")); PCM.track("arcade_error", { id: title, kind: "emulator" }); return false; }
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

  /* catalogue games: the museum's download proxy (/api/games/<edition>) brings them from ScummVM or Internet Archive;
     the browser keeps them in Cache Storage, so a game is only downloaded once per visitor */
  const CACHE_NAME = "pcm-games-v1";
  async function fetchGame(g) {
    const url = "/api/games/" + g.key;
    let res = null;
    try { res = "caches" in window ? await (await caches.open(CACHE_NAME)).match(url) : null; } catch (e) { /* private mode */ }
    if (!res) {
      if (location.protocol === "file:") throw new Error(t("arcadeNoServer"));
      res = await fetch(url);
      if (res.status === 429) throw new Error(t("arcadeFetchBusy"));
      if (res.status === 404 && !/json/.test(res.headers.get("Content-Type") || "")) throw new Error(t("arcadeNoServer"));
      if (!res.ok) throw new Error(t("arcadeFetchFail"));
      const total = +res.headers.get("Content-Length") || 0, reader = res.body.getReader(), parts = [];
      let got = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        parts.push(value); got += value.length;
        now.textContent = t("arcadeDownloading", { title: g.title, mb: (got / 1048576).toFixed(1) + (total ? " / " + (total / 1048576).toFixed(1) : "") });
      }
      const blob = new Blob(parts, { type: "application/zip" });
      try { if ("caches" in window) await (await caches.open(CACHE_NAME)).put(url, new Response(blob, { headers: { "Content-Type": "application/zip" } })); }
      catch (e) { /* quota or private mode: play without keeping it */ }
      return new Uint8Array(await blob.arrayBuffer());
    }
    return new Uint8Array(await res.arrayBuffer());
  }
  async function playCatalog(g) {
    let bytes;
    try { now.textContent = t("arcadeLoading", { title: g.title }); bytes = await fetchGame(g); }
    catch (e) { now.textContent = t("arcadeNothing"); toast(e.message); sfx("bad"); PCM.track("arcade_error", { id: g.id, kind: "download" }); return; }
    if (g.engine === "scummvm") {
      let files;
      try { files = await unzip(bytes); } catch (e) { toast(t("arcadeFetchFail")); return; }
      runScummVM(g.title, { gameId: g.id, engine: g.svmEngine, files: Object.keys(files), memFiles: files, gameBase: "", args: svmArgs(g.id) });
    } else {
      const u = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
      run(g.title, { url: u }, u);
    }
  }

  /* the chosen game, next to the screen: its box, what it is and where to read more */
  function showInfo(g) {
    const info = $("#dosInfo");
    if (!info) return;
    $$(".dos-game.on").forEach(x => x.classList.remove("on"));
    if (!g) { info.hidden = true; return; }
    const card = $('.dos-game[data-id="' + g.id + '"]');
    if (card) card.classList.add("on");
    const img = card && card.querySelector("img.cover"), credit = card && card.querySelector(".credit"), meta = card && card.querySelector(".meta");
    const links = [];
    if (g.timeline && D.pageUrls.timeline != null) links.push('<a href="' + esc(D.pageUrls.timeline + "#" + g.timeline) + '">' + esc(t("arcadeRecord")) + "</a>");
    if (g.gog) links.push('<a href="' + esc(g.gog) + '" rel="noopener" target="_blank">' + esc(t("buyGog")) + " ↗</a>");
    info.innerHTML = (img ? '<img class="cover" src="' + esc(img.getAttribute("src")) + '" alt="' + esc(t("arcadeCoverAlt", { title: g.title })) + '">' : "") +
      "<h3>" + esc(g.title) + "</h3>" + (meta && meta.textContent.trim() ? '<p class="meta">' + esc(meta.textContent) + "</p>" : "") +
      (g.desc ? '<p class="desc">' + esc(g.desc) + "</p>" : "") + (links.length ? '<p class="links">' + links.join(" · ") + "</p>" : "") +
      (credit ? credit.outerHTML : "");
    info.hidden = false;
  }

  function play(g) {
    showInfo(g);
    PCM.track("arcade_play", { id: g.id, engine: g.engine || "dosbox", src: g.key ? "catalog" : g.local ? "local" : "museum" });
    if (g.key) return playCatalog(g);
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
  }
  $$(".dos-play").forEach(b => b.addEventListener("click", () => {
    const g = D.arcade.games.find(x => x.id === b.dataset.id);
    if (g && (g.bundle || g.key)) play(g);
  }));
  /* arriving from the timeline ("Play in the museum"): #play=<id> */
  const fromHash = () => {
    const m = /^#play=([\w-]+)/.exec(location.hash), g = m && D.arcade.games.find(x => x.id === m[1]);
    if (!g || !(g.bundle || g.key)) return;
    const card = $('.dos-game[data-id="' + g.id + '"]');
    if (card) { card.hidden = false; card.classList.add("flash"); }
    play(g);
  };
  fromHash(); addEventListener("hashchange", fromHash);
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
    showInfo(null);
    const name = file.name.toLowerCase();
    if (name.endsWith(".jsdos")) {
      const u = URL.createObjectURL(file);
      run(file.name, { url: u }, u);
    } else if (name.endsWith(".zip")) {
      const bytes = new Uint8Array(await file.arrayBuffer()), want = $("#byoEngine").value;
      PCM.track("arcade_play", { id: "(own game)", engine: want || "auto", src: "byo" });
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

/* ---------- catalogue: search, company, A–Z index, sort, pages ---------- */
if (document.getElementById("catList")) (() => {
  const { D, $, $$, t, sfx, reduceMotion } = PCM;
  const list = $("#catList"), items = $$(".dos-game", list), count = $("#catCount"), empty = $("#catEmpty");
  const search = $("#catSearch"), studio = $("#catStudio"), sort = $("#catSort"), letters = $$(".letters button");
  if (!search) return; // few games: no filters
  const PER = (D.arcade.catalogue || {}).pageSize || 10;
  const norm = s => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  items.forEach(el => { el._text = norm(el.querySelector("h3").textContent + " " + el.dataset.studio); });
  let letter = "", page = 0, matched = [];
  const pager = document.createElement("nav");
  pager.className = "cat-pages"; pager.setAttribute("aria-label", t("catPages"));
  list.after(pager);

  /* what the search, filters and letter leave, in the list's current order; then only the current page is shown */
  function apply(keepPage) {
    const q = norm(search.value.trim()), st = studio.value;
    matched = $$(".dos-game", list).filter(el => (!q || q.split(/\s+/).every(w => el._text.includes(w))) && (!st || el.dataset.studio === st) &&
      (!letter || el.dataset.letter === letter));
    if (!keepPage) page = 0;
    show();
  }
  function show() {
    const pages = Math.max(1, Math.ceil(matched.length / PER));
    page = Math.min(Math.max(page, 0), pages - 1);
    const visible = new Set(matched.slice(page * PER, page * PER + PER));
    items.forEach(el => { el.hidden = !visible.has(el); });
    count.textContent = t("catCount", { n: matched.length, total: items.length });
    empty.hidden = matched.length > 0;
    pager.hidden = pages < 2;
    if (pages < 2) { pager.innerHTML = ""; return; }
    // first, last and the pages around the current one
    const nums = [...new Set([0, pages - 1, page - 2, page - 1, page, page + 1, page + 2].filter(n => n >= 0 && n < pages))].sort((a, b) => a - b);
    let html = '<button type="button" data-p="' + (page - 1) + '"' + (page === 0 ? " disabled" : "") + ">◀ " + t("catPrev") + "</button>", last = -1;
    nums.forEach(n => {
      if (n - last > 1) html += '<span aria-hidden="true">…</span>';
      html += '<button type="button" data-p="' + n + '"' + (n === page ? ' aria-current="page"' : "") + ' aria-label="' + t("catPage", { n: n + 1, total: pages }) + '">' + (n + 1) + "</button>";
      last = n;
    });
    html += '<button type="button" data-p="' + (page + 1) + '"' + (page === pages - 1 ? " disabled" : "") + ">" + t("catNext") + " ▶</button>";
    pager.innerHTML = html;
  }
  pager.addEventListener("click", e => {
    const b = e.target.closest("button[data-p]");
    if (!b || b.disabled) return;
    page = +b.dataset.p; sfx("click"); show();
    $("#catTitle").scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest" });
  });
  function reorder() {
    const by = sort.value;
    items.slice().sort((a, b) => (by === "year" ? (+a.dataset.year - +b.dataset.year) || a.dataset.key.localeCompare(b.dataset.key) : a.dataset.key.localeCompare(b.dataset.key)))
      .forEach(el => list.appendChild(el));
    apply();
  }
  let searchTimer = null;
  search.addEventListener("input", () => {
    apply();
    clearTimeout(searchTimer);  // only whether a search found something, never what was typed
    if (search.value.trim()) searchTimer = setTimeout(() => PCM.track("catalog_search", { results: matched.length > 0 }), 1500);
  });
  studio.addEventListener("change", () => { sfx("click"); apply(); });
  sort.addEventListener("change", () => { sfx("click"); reorder(); });
  letters.forEach(b => b.addEventListener("click", () => {
    letter = b.dataset.l; letters.forEach(x => x.setAttribute("aria-pressed", String(x === b))); sfx("click"); apply(); list.scrollTop = 0;
  }));
  document.addEventListener("keydown", e => {
    if (e.key === "/" && document.activeElement === document.body) { e.preventDefault(); search.focus(); }
  });
  /* arriving with #play=<id> (from the timeline): open the page where that game is */
  const toHash = () => {
    const m = /^#play=([\w-]+)/.exec(location.hash), el = m && items.find(x => x.dataset.id === m[1]);
    if (!el) return;
    let i = matched.indexOf(el);
    if (i < 0) { search.value = ""; letter = ""; studio.value = "";
      letters.forEach(x => x.setAttribute("aria-pressed", String(x.dataset.l === ""))); apply(); i = matched.indexOf(el); }
    page = Math.floor(i / PER); show();
  };
  apply();
  toHash(); addEventListener("hashchange", toHash);
})();
