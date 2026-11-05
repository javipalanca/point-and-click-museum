/* Control panel of the catalogue (server/admin.py). Everything that comes from the sources (titles of Internet
   Archive items, errors…) is untrusted text: it only reaches the page through esc() or textContent. */
"use strict";
(() => {
  const $ = (s, el = document) => el.querySelector(s), $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const url = u => /^https?:\/\//.test(String(u || "")) ? esc(u) : "#";
  const STATE = { playable: "Jugable", pending: "Pendiente", record: "Solo ficha" };
  let me = null, catalog = { games: [] }, current = null, pollTimer = null;

  async function api(path, opts = {}) {
    const r = await fetch(path, { credentials: "same-origin", ...opts,
      headers: { "Content-Type": "application/json", "X-PCM-Admin": "1", ...(opts.headers || {}) } });
    if (r.status === 401 && !path.endsWith("/login")) { show(false); throw new Error("sesión caducada"); }
    const data = /json/.test(r.headers.get("Content-Type") || "") ? await r.json() : null;
    if (!r.ok) throw new Error((data && data.error) || "HTTP " + r.status);
    return data;
  }
  const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body || {}) });

  function show(logged) {
    $("#login").hidden = logged; $("#app").hidden = !logged;
    if (!logged) clearInterval(pollTimer);
  }

  /* ---------- login */
  $("#loginForm").addEventListener("submit", async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    $("#loginErr").textContent = "";
    try { await post("/api/admin/login", { user: f.get("user"), password: f.get("password") }); start(); }
    catch (x) { $("#loginErr").textContent = x.message; }
  });
  $("#logout").addEventListener("click", async () => { try { await post("/api/admin/logout"); } catch (e) { /* gone */ } show(false); });

  /* ---------- tabs */
  $$(".tabs button").forEach(b => b.addEventListener("click", () => {
    $$(".tabs button").forEach(x => x.setAttribute("aria-selected", String(x === b)));
    $$("[data-panel]").forEach(p => { p.hidden = p.dataset.panel !== b.dataset.tab; });
    if (b.dataset.tab === "sources") renderSources();
    if (b.dataset.tab === "downloads" || b.dataset.tab === "log") refreshStatus();
    if (b.dataset.tab === "stats") loadStats();
  }));

  /* ---------- summary and sync */
  function renderCounts() {
    const c = { playable: 0, pending: 0, record: 0 };
    catalog.games.forEach(g => { c[g.status] = (c[g.status] || 0) + 1; });
    const eds = catalog.games.reduce((n, g) => n + g.editions.length, 0);
    $("#counts").innerHTML = [["Juegos", catalog.games.length], ["Jugables", c.playable], ["Pendientes", c.pending], ["Solo ficha", c.record], ["Ediciones", eds]]
      .map(([k, v]) => "<div><b>" + v + "</b>" + esc(k) + "</div>").join("");
  }
  let lastStatus = null;
  async function refreshStatus() {
    let st;
    try { st = await api("/api/admin/status"); } catch (e) { return; }
    const s = st.sync || {};
    $("#syncStatus").innerHTML =
      "<dt>Estado</dt><dd>" + (s.running ? '<span class="badge pending">en marcha</span>' : st.requested ? '<span class="badge pending">en cola</span>' : s.finished ? (s.ok ? '<span class="ok">terminada</span>' : '<span class="err">con errores</span>') : "nunca") + "</dd>" +
      "<dt>Inicio</dt><dd>" + esc(s.started || "—") + "</dd><dt>Fin</dt><dd>" + esc(s.finished || "—") + "</dd>" +
      "<dt>Resultado</dt><dd>" + esc(s.summary || "—") + "</dd><dt>Catálogo</dt><dd>" + esc(catalog.generated || "—") + "</dd>";
    $("#cacheStatus").innerHTML = "<dt>Juegos en caché</dt><dd>" + st.cache.files + " (" + st.cache.mb + " MB)</dd>" +
      "<dt>Motores de ScummVM</dt><dd>" + esc(me.engines.join(", ") || "ScummVM no compilado") + "</dd>";
    $("#log").textContent = st.log.join("\n") || "Aún no hay registro.";
    renderDownloads(st.downloads);
    if (lastStatus && lastStatus.running && !s.running) loadCatalog();  // a sync just finished: reload
    lastStatus = s;
  }
  $("#syncForm").addEventListener("submit", async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      await post("/api/admin/sync", { only: f.getAll("only"), validate: +f.get("validate"), retryFailed: f.get("retryFailed") === "on" });
      refreshStatus();
    } catch (x) { alert(x.message); }
  });

  /* ---------- games */
  const norm = s => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  function matches(g) {
    const q = norm($("#q").value.trim()), st = $("#fStatus").value, src = $("#fSource").value, fl = $("#fFlag").value;
    if (st && g.status !== st) return false;
    if (src && !(g.sources || []).includes(src) && !(src === "manual" && g.editions.some(e => e.added))) return false;
    if (fl === "download" && !g.editions.some(e => e.download)) return false;
    if (fl === "nodownload" && g.editions.some(e => e.download)) return false;
    if (fl === "failed" && !g.editions.some(e => e.validated && e.validated.ok === false)) return false;
    if (fl === "timeline" && !g.timeline) return false;
    if (fl === "gog" && !g.gog) return false;
    if (!q) return true;
    const hay = norm([g.title, g.developer, g.id, g.scummvm, g.year].concat(g.editions.map(e => e.archive + " " + e.key)).join(" "));
    return q.split(/\s+/).every(w => hay.includes(w));
  }
  let shown = 200;
  function renderList() {
    const list = catalog.games.filter(matches);
    $("#gCount").textContent = list.length + " de " + catalog.games.length;
    $("#gameList").innerHTML = list.slice(0, shown).map(g =>
      '<li data-id="' + esc(g.id) + '"' + (current === g.id ? " aria-current" : "") + "><span>" + esc(g.title) + "</span>" +
      '<span class="badge ' + esc(g.status) + '">' + esc(STATE[g.status]) + "</span><small>" +
      esc([g.year, g.developer].filter(Boolean).join(" · ")) + " · " + g.editions.length + " ed. · " + esc((g.sources || []).join(", ")) + "</small></li>").join("") +
      (list.length > shown ? '<li class="more"><button class="link">Mostrar más</button></li>' : "");
  }
  $("#gameList").addEventListener("click", e => {
    if (e.target.closest(".more")) { shown += 200; renderList(); return; }
    const li = e.target.closest("li[data-id]");
    if (li) { current = li.dataset.id; renderList(); renderDetail(); }
  });
  ["#q", "#fStatus", "#fSource", "#fFlag"].forEach(s => $(s).addEventListener("input", () => { shown = 200; renderList(); }));

  function renderDetail() {
    const g = catalog.games.find(x => x.id === current), d = $("#detail");
    if (!g) { d.innerHTML = '<p class="muted">Elige un juego de la lista.</p>'; return; }
    const removed = (catalog.removed || {})[g.id] || {};
    d.innerHTML =
      "<h2>" + esc(g.title) + ' <span class="badge ' + esc(g.status) + '">' + esc(STATE[g.status]) + "</span></h2>" +
      '<dl class="kv"><dt>Id</dt><dd>' + esc(g.id) + "</dd><dt>Año · estudio</dt><dd>" + esc([g.year, g.developer].filter(Boolean).join(" · ") || "—") + "</dd>" +
      "<dt>Fuentes</dt><dd>" + esc((g.sources || []).join(", ") || "—") + "</dd>" +
      (g.scummvm ? "<dt>ScummVM</dt><dd>" + esc(g.scummvm) + "</dd>" : "") +
      (g.timeline ? '<dt>Museo</dt><dd><a href="/es/timeline/#' + esc(g.timeline) + '" target="_blank" rel="noopener">ficha en la línea temporal</a></dd>' : "") + "</dl>" +
      '<form class="row" id="gogForm"><label>GOG <input type="url" name="gog" placeholder="https://www.gog.com/en/game/…" value="' + esc(g.gog || "") + '"></label><button>Guardar</button></form>' +
      '<label class="row"><input type="checkbox" id="forceRecord"' + (g.forcedRecord ? " checked" : "") + "> Mantener como solo ficha aunque tenga ediciones jugables</label>" +
      "<h2>Ediciones</h2>" + (g.editions.map(editionHtml).join("") || '<p class="muted">Ninguna fuente la ofrece todavía. Búscala en Internet Archive:</p>') +
      (Object.keys(removed).length ? "<h2>Ediciones eliminadas</h2><ul class=\"removed\">" + Object.entries(removed).map(([k, e]) =>
        "<li>" + esc(e.edition || k) + ' <button class="link" data-restore="' + esc(k) + '">Restaurar</button></li>').join("") + "</ul>" : "") +
      '<h2>Buscar en Internet Archive</h2><form class="row" id="iaForm"><input type="text" name="q" value="' + esc(g.title.split(":")[0]) + '">' +
      '<label><input type="checkbox" name="all"> fuera de las colecciones configuradas</label><button>Buscar</button></form><div id="iaResults"></div>';
    $("#gogForm").addEventListener("submit", async e => {
      e.preventDefault();
      try { await post("/api/admin/games/" + g.id, { gog: new FormData(e.target).get("gog") || null }); await loadCatalog(); } catch (x) { alert(x.message); }
    });
    $("#forceRecord").addEventListener("change", async e => {
      try { await post("/api/admin/games/" + g.id, { forceRecord: e.target.checked }); await loadCatalog(); } catch (x) { alert(x.message); }
    });
    $("#iaForm").addEventListener("submit", async e => {
      e.preventDefault();
      const f = new FormData(e.target), box = $("#iaResults");
      box.innerHTML = '<p class="muted">Buscando…</p>';
      try {
        const r = await api("/api/admin/search?q=" + encodeURIComponent(f.get("q")) + (f.get("all") ? "&all=1" : ""));
        box.innerHTML = r.results.length ? '<table class="ia"><tr><th>Elemento</th><th>Año</th><th>Derechos según sus metadatos</th><th></th></tr>' + r.results.map(x =>
          '<tr data-ident="' + esc(x.identifier) + '"><td>' + esc(x.title) + '<br><small>' + esc(x.identifier) + (x.creator ? " · " + esc([].concat(x.creator)[0]) : "") +
          ' · <a href="' + url(x.page) + '" target="_blank" rel="noopener">archive.org ↗</a></small></td><td>' + esc(x.year || "") +
          "</td><td>" + esc(x.rights[0]) + (x.rights[1] ? " (" + esc(x.rights[1]) + ")" : "") + '</td><td><button data-inspect="' + esc(x.identifier) + '">Ver qué contiene</button></td></tr>' +
          '<tr class="inspect" data-for="' + esc(x.identifier) + '" hidden><td colspan="4"></td></tr>').join("") + "</table>"
          : '<p class="muted">Sin resultados.</p>';
      } catch (x) { box.innerHTML = '<p class="err">' + esc(x.message) + "</p>"; }
    });
  }

  const VERDICT = { dosbox: ["playable", "DOS: se puede probar"], scummvm: ["playable", "ScummVM"], windows: ["fail", "solo Windows: DOSBox no lo ejecuta"],
    nested: ["pending", "zip dentro del zip"], none: ["fail", "sin programa que arranque el juego"], "too-big": ["fail", "demasiado grande (GAMES_MAX_MB)"], error: ["fail", "no se pudo leer"] };
  const mb = n => !n ? "" : n < 1048576 ? Math.max(1, Math.round(n / 1024)) + " KB" : (n / 1048576).toFixed(1) + " MB";
  function inspectionHtml(r) {
    const zip = z => {
      const [cls, label] = VERDICT[z.verdict] || ["pending", z.verdict], svm = z.scummvm;
      const progs = (z.programs || []).map(pr => '<option value="' + esc(pr.path) + '"' + (pr.path === z.suggested ? " selected" : "") + (pr.type === "windows" ? " disabled" : "") + ">" +
        esc(pr.path) + " · " + mb(pr.size) + (pr.type === "windows" ? " (Windows)" : "") + (pr.installer ? " (instalador)" : "") + (pr.path === z.suggested ? " · sugerido" : "") + "</option>").join("");
      // add: what will start (DOS program, ScummVM data, a zip inside to open); try: also a zip with only an installer, to look at it
      const add = ["dosbox", "scummvm", "nested"].includes(z.verdict), tryIt = add || (z.programs || []).some(pr => pr.type !== "windows");
      const usable = (z.programs || []).some(pr => pr.type !== "windows");
      return '<div class="zip" data-file="' + esc(z.name) + '"><h4>' + esc(z.name) + ' <span class="muted">' + mb(z.size) + (z.files ? " · " + z.files + " ficheros" : "") + '</span> <span class="badge ' + cls + '">' + esc(label) + "</span></h4>" +
        (svm ? '<p>Datos de ScummVM: motor <b>' + esc(svm.engine) + "</b>" + (svm.folder ? " en " + esc(svm.folder) + "/" : "") + (svm.built ? "" : ' <span class="err">(no está en nuestra compilación)</span>') + "</p>" : "") +
        (z.inner ? "<p>Contiene: " + z.inner.map(esc).join(", ") + ". Se abre al probarlo.</p>" : "") +
        (z.error ? '<p class="err">' + esc(z.error) + "</p>" : "") +
        (progs && usable ? '<label class="row">Programa <select name="exe"' + (svm ? " disabled" : "") + ">" + progs + "</select></label>" : "") +
        (progs && !usable ? '<p class="muted">Programas: ' + z.programs.map(pr => esc(pr.path) + " (Windows)").join(", ") + "</p>" : "") +
        (z.sample && !progs ? '<p class="muted">Ficheros: ' + z.sample.map(esc).join(", ") + "</p>" : "") +
        (tryIt ? '<div class="row"><button data-try>Probar</button>' + (add ? '<button class="primary" data-add>Añadir como edición</button>' : "") + "</div>" : "") + "</div>";
    };
    return '<div class="inspection"><p><a href="' + url(r.page) + '" target="_blank" rel="noopener">Abrir en archive.org ↗</a>' +
      (r.start ? ' · su emulador arranca <code>' + esc(r.start) + "</code>" : "") + "</p>" +
      (r.zips.length ? r.zips.map(zip).join("") : '<p class="err">No tiene ningún zip.</p>') +
      (r.other.length ? '<p class="muted">Otros ficheros (aún no se pueden usar): ' + r.other.map(o => esc(o.name) + " " + mb(o.size)).join(", ") + "</p>" : "") + "</div>";
  }
  const choice = el => {
    const z = el.closest(".zip"), sel = z.querySelector("select[name=exe]"), ident = el.closest("tr.inspect").dataset.for;
    const rep = inspected[ident], info = rep.zips.find(x => x.name === z.dataset.file);
    return { archive: ident, file: z.dataset.file, title: rep.title, engine: info.scummvm ? info.scummvm.engine : null, exe: info.scummvm ? null : (sel ? sel.value : null) };
  };
  const inspected = {};

  function editionHtml(e) {
    const v = e.validated || {}, dl = e.download || {};
    return '<div class="edition" data-key="' + esc(e.key) + '"><h3>' + esc(e.edition || e.key) +
      ' <span class="badge ' + esc(e.status) + '">' + esc(STATE[e.status]) + "</span>" +
      (v.ok === true ? '<span class="badge playable">validada</span>' : v.ok === false ? '<span class="badge fail">falló</span>' : "") + "</h3>" +
      '<dl class="kv"><dt>Clave</dt><dd>' + esc(e.key) + "</dd><dt>Tipo · motor</dt><dd>" + esc(e.kind) + " · " + esc(e.emulator === "scummvm" ? "ScummVM " + ((e.run || {}).svmEngine || "") : "DOSBox") + "</dd>" +
      "<dt>Derechos</dt><dd>" + esc(e.rights) + (e.rightsHint ? " · indicio: " + esc(e.rightsHint) : "") +
      (e.rightsSource ? ' · <a href="' + url(e.rightsSource) + '" target="_blank" rel="noopener">prueba</a>' : "") + (e.rightsBy ? " · " + esc(e.rightsBy + " " + (e.rightsAt || "")) : "") +
      (e.rightsNote ? "<br><small>" + esc(e.rightsNote) + "</small>" : "") + "</dd>" +
      "<dt>Descarga</dt><dd>" + (dl.url ? '<a href="' + url(dl.url) + '" target="_blank" rel="noopener">' + esc(dl.file || dl.url.split("/").pop()) + "</a>" + (dl.size ? " · " + (dl.size / 1048576).toFixed(1) + " MB" : "") : "—") +
      (e.page ? ' · <a href="' + url(e.page) + '" target="_blank" rel="noopener">página</a>' : "") + "</dd>" +
      "<dt>Arranque</dt><dd>" + esc(JSON.stringify(e.run || {})) + "</dd>" +
      (v.at ? "<dt>Validación</dt><dd>" + esc(v.at) + (v.by ? " · " + esc(v.by) : "") + (v.error ? '<br><span class="err">' + esc(v.error) + "</span>" : "") +
        (v.checks ? '<ul class="checks">' + v.checks.map(c => "<li>" + esc(c) + "</li>").join("") + "</ul>" : "") + "</dd>" : "") + "</dl>" +
      '<div class="row">' + (dl.url ? '<button data-act="test">Probar</button><button data-act="validate">Validar</button>' : '<span class="muted">Sin fichero descargable.</span>') +
      '<button data-act="delete" title="La sincronización no la volverá a traer">Eliminar edición</button>' +
      (e.approved ? '<span class="badge playable">disponible · ' + esc((e.rightsBy || "") + " " + (e.rightsAt || "")) + '</span><button data-act="revert">Retirar de la web</button>' : dl.url ? '<button class="primary" data-act="approve">Marcar como disponible</button>' : "") + "</div>" +
      (e.approved && v.ok === false ? '<p class="err">Está disponible, pero la validación automática falló: comprueba que arranca con «Probar».</p>' : "") +
      '<form class="row" data-form="rights"><select name="rights">' + me.rights.map(r => '<option' + (r === e.rights ? " selected" : "") + ">" + esc(r) + "</option>").join("") + "</select>" +
      '<input type="url" name="source" placeholder="Enlace (opcional)" value="' + esc(e.rightsSource || "") + '">' +
      '<input type="text" name="note" placeholder="Nota (opcional)" value="' + esc(e.rightsNote || "") + '">' +
      "<button>Guardar derechos</button>" + (e.rightsBy && !e.approved ? '<button type="button" data-act="revert">Volver a lo que dice la fuente</button>' : "") + "</form>" +
      '<form class="row" data-form="run"><input type="text" name="exe" placeholder="Programa (GAME/START.BAT)" value="' + esc((e.run || {}).exe || "") + '">' +
      '<input type="number" name="cycles" placeholder="cycles" value="' + esc((e.run || {}).cycles || "") + '"><button>Guardar arranque</button></form></div>';
  }

  async function onDetailClick(ev) {
    const restore = ev.target.closest("[data-restore]");
    if (restore) {
      try { await post("/api/admin/games/" + current + "/restore", { key: restore.dataset.restore }); await loadCatalog(); }
      catch (x) { alert(x.message); }
      return;
    }
    const ins = ev.target.closest("[data-inspect]");
    if (ins) {
      const row = $('tr.inspect[data-for="' + CSS.escape(ins.dataset.inspect) + '"]'), cell = row.querySelector("td");
      if (!row.hidden && cell.innerHTML) { row.hidden = true; return; }
      row.hidden = false; cell.innerHTML = '<p class="muted">Leyendo el índice de sus zips en archive.org…</p>';
      try { inspected[ins.dataset.inspect] = await api("/api/admin/inspect?archive=" + encodeURIComponent(ins.dataset.inspect)); cell.innerHTML = inspectionHtml(inspected[ins.dataset.inspect]); }
      catch (x) { cell.innerHTML = '<p class="err">' + esc(x.message) + "</p>"; }
      return;
    }
    if (ev.target.closest("[data-try]")) {
      const c = choice(ev.target);
      const q = "archive=" + encodeURIComponent(c.archive) + "&file=" + encodeURIComponent(c.file) + (c.engine ? "&engine=" + encodeURIComponent(c.engine) : c.exe ? "&exe=" + encodeURIComponent(c.exe) : "");
      return play(c.title + " · " + c.file + (c.exe ? " · " + c.exe : ""), "/api/admin/try?" + q, c.engine ? "scummvm" : "dosbox", c.engine);
    }
    if (ev.target.closest("[data-add]")) {
      const c = choice(ev.target), b = ev.target.closest("[data-add]");
      b.disabled = true; b.textContent = "Añadiendo…";
      try { await post("/api/admin/games/" + current + "/attach", { archive: c.archive, file: c.file, exe: c.exe, engine: c.engine }); await loadCatalog(); }
      catch (x) { alert(x.message); b.disabled = false; b.textContent = "Añadir como edición"; }
      return;
    }
    const btn = ev.target.closest("[data-act]");
    if (!btn) return;
    const key = btn.closest(".edition").dataset.key;
    if (btn.dataset.act === "test") return test(key);
    if (btn.dataset.act === "delete" && !confirm("¿Eliminar esta edición? La sincronización no la volverá a traer; podrás restaurarla desde esta ficha.")) return;
    btn.disabled = true;
    try {
      if (btn.dataset.act === "validate") { btn.textContent = "Descargando y comprobando…"; await post("/api/admin/editions/" + key + "/validate"); }
      if (btn.dataset.act === "revert") await post("/api/admin/editions/" + key + "/rights", { rights: null });
      if (btn.dataset.act === "delete") await post("/api/admin/editions/" + key + "/delete");
      if (btn.dataset.act === "approve") await post("/api/admin/editions/" + key + "/rights", { approved: true });
      await loadCatalog();
    } catch (x) { alert(x.message); await loadCatalog(); }
  }
  $("#detail").addEventListener("click", onDetailClick);
  document.addEventListener("submit", async ev => {
    const f = ev.target.closest("[data-form]");
    if (!f) return;
    ev.preventDefault();
    const key = f.closest(".edition").dataset.key, data = Object.fromEntries(new FormData(f));
    try {
      if (f.dataset.form === "rights") await post("/api/admin/editions/" + key + "/rights", Object.assign(data, { approved: me.playable.includes(data.rights) }));
      else await post("/api/admin/editions/" + key + "/run", { exe: data.exe, cycles: data.cycles ? +data.cycles : undefined });
      await loadCatalog();
    } catch (x) { alert(x.message); }
  });

  /* ---------- test emulator (DOSBox with js-dos, or ScummVM in its player) */
  let dos = null, blobUrl = null;
  async function unzip(buf) {
    const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength), out = {};
    let eocd = -1;
    for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65557); i--) if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    if (eocd < 0) throw new Error("no es un zip");
    let p = dv.getUint32(eocd + 16, true);
    for (let k = 0, n = dv.getUint16(eocd + 10, true); k < n; k++) {
      const method = dv.getUint16(p + 10, true), size = dv.getUint32(p + 20, true), nl = dv.getUint16(p + 28, true),
        xl = dv.getUint16(p + 30, true), cl = dv.getUint16(p + 32, true), local = dv.getUint32(p + 42, true);
      const name = new TextDecoder().decode(buf.subarray(p + 46, p + 46 + nl));
      p += 46 + nl + xl + cl;
      if (name.endsWith("/")) continue;
      const start = local + 30 + dv.getUint16(local + 26, true) + dv.getUint16(local + 28, true), raw = buf.subarray(start, start + size);
      out[name] = method === 0 ? raw.slice() : new Uint8Array(await new Response(new Blob([raw]).stream().pipeThrough(new DecompressionStream("deflate-raw"))).arrayBuffer());
    }
    return out;
  }
  const loadScript = src => new Promise((res, rej) => { const s = document.createElement("script"); s.src = src; s.onload = res; s.onerror = () => rej(new Error("no se pudo cargar " + src)); document.head.appendChild(s); });
  async function stopPlayer() {
    if (dos) { try { await dos.stop(); } catch (e) { /* stopped */ } dos = null; }
    $("#playerHost").innerHTML = "";
    if (blobUrl) { URL.revokeObjectURL(blobUrl); blobUrl = null; }
  }
  $("#playerClose").addEventListener("click", async () => { await stopPlayer(); $("#player").close(); });
  function test(key) {
    const g = catalog.games.find(x => x.id === current), e = g.editions.find(x => x.key === key);
    return play(g.title + " · " + (e.edition || key), "/api/admin/editions/" + key + "/bundle", e.emulator, (e.run || {}).svmEngine, true);
  }
  /* refresh: an edition of the catalogue (its download log and checks change); an item being tried changes nothing,
     and the search results stay where they were */
  async function play(title, src, emulator, engine, refresh) {
    await stopPlayer();
    $("#playerTitle").textContent = title;
    $("#playerState").textContent = "descargando en el servidor y preparando…";
    $("#player").showModal();
    let bytes;
    try {
      const r = await fetch(src, { credentials: "same-origin" });
      if (!r.ok) throw new Error(((await r.json().catch(() => ({}))).error) || "HTTP " + r.status);
      bytes = new Uint8Array(await r.arrayBuffer());
    } catch (x) { $("#playerState").textContent = "Error: " + x.message; if (refresh) loadCatalog(); return; }
    $("#playerState").textContent = (bytes.length / 1048576).toFixed(1) + " MB";
    if (emulator === "scummvm") {
      const m = await (await fetch("/scummvm/manifest.json")).json().catch(() => ({ available: false }));
      if (!m.available) { $("#playerState").textContent = "ScummVM no está compilado en este servidor (tools/build_scummvm.sh)."; return; }
      const files = await unzip(bytes);
      window.PCM_SVM_JOB = { data: m.data, inline: m.inline, gameId: "test", engine, files: Object.keys(files),
        memFiles: files, gameBase: "", args: ["--path=/games/test", "--auto-detect"], volume: 1 };
      const f = document.createElement("iframe");
      f.src = "/scummvm/player.html#" + encodeURI(window.PCM_SVM_JOB.args.join(" ")); f.allow = "autoplay; fullscreen";
      $("#playerHost").appendChild(f);
    } else {
      if (!window.Dos) {
        const css = document.createElement("link"); css.rel = "stylesheet"; css.href = "/vendor/js-dos/js-dos.css"; document.head.appendChild(css);
        await loadScript("/vendor/js-dos/js-dos.js");
      }
      blobUrl = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
      const el = document.createElement("div"); $("#playerHost").appendChild(el);
      dos = window.Dos(el, { url: blobUrl, pathPrefix: "/vendor/js-dos/emulators/", autoStart: true, noCloud: true, noNetworking: true, theme: "dark" });
    }
    if (refresh) loadCatalog();
  }

  /* ---------- sources and downloads */
  function renderSources() {
    const src = catalog.sources || {}, by = {};
    catalog.games.forEach(g => g.editions.forEach(e => { const p = (e.download || {}).provider || (e.archive ? "archive" : "manual"); (by[p] = by[p] || []).push([g, e]); }));
    const catOnly = catalog.games.filter(g => (g.sources || []).includes("scummvm-catalogue")).length;
    const table = rows => "<table><tr><th>Juego</th><th>Edición</th><th>Derechos</th><th>Estado</th></tr>" + rows.slice(0, 400).map(([g, e]) =>
      "<tr><td>" + esc(g.title) + "</td><td>" + (e.page ? '<a href="' + url(e.page) + '" target="_blank" rel="noopener">' + esc(e.edition) + "</a>" : esc(e.edition)) +
      "</td><td>" + esc(e.rights) + (e.rightsHint ? " (" + esc(e.rightsHint) + ")" : "") + '</td><td><span class="badge ' + esc(e.status) + '">' + esc(STATE[e.status]) + "</span></td></tr>").join("") + "</table>" +
      (rows.length > 400 ? '<p class="muted">… y ' + (rows.length - 400) + " más (usa la pestaña Juegos para buscar).</p>" : "");
    $("#sources").innerHTML =
      '<div class="grid2"><div class="card"><h2>ScummVM</h2><dl class="kv"><dt>scummvm-web</dt><dd>' + esc((src.scummvm || {}).commit || "—") + "</dd>" +
      "<dt>Descargas (freeware y demos)</dt><dd>" + (by.scummvm || []).length + "</dd><dt>Juegos de su catálogo</dt><dd>" + catOnly + "</dd></dl></div>" +
      '<div class="card"><h2>Internet Archive</h2><dl class="kv"><dt>Elementos</dt><dd>' + (by.archive || []).length + "</dd><dt>Última búsqueda</dt><dd>" +
      esc((src.archive || {}).at ? new Date(src.archive.at * 1000).toISOString() : "—") + "</dd></dl></div>" +
      '<div class="card"><h2>GOG</h2><dl class="kv"><dt>Enlaces de tienda</dt><dd>' + catalog.games.filter(g => g.gog).length + "</dd><dt>Última consulta</dt><dd>" +
      esc((src.gog || {}).at ? new Date(src.gog.at * 1000).toISOString() : "—") + "</dd></dl></div></div>" +
      "<h2>Ediciones de ScummVM</h2>" + table(by.scummvm || []) + "<h2>Ediciones de Internet Archive</h2>" + table(by.archive || []) +
      (by.manual ? "<h2>Añadidas a mano</h2>" + table(by.manual) : "");
  }
  /* ---------- statistics (server/stats.py): the site, the games proxy and Murray */
  const fmtN = n => (n == null ? "—" : Number(n).toLocaleString("es-ES"));
  const fmtMs = v => v == null ? "—" : v >= 60000 ? (v / 60000).toFixed(1) + " min" : v >= 1000 ? (v / 1000).toFixed(1) + " s" : Math.round(v) + " ms";
  const NAMES = { "web.pages": "Salas", "web.langs": "Idioma de la página", "web.browser_langs": "Idioma del navegador", "web.devices": "Dispositivo",
    "web.referrers": "De dónde llegan", "web.entry_pages": "Sala de entrada", "web.navigation": "Tipo de navegación", "web.timeline_open": "Fichas abiertas (línea temporal)",
    "web.arcade_play": "Juegos arrancados", "web.arcade_engine": "Emulador", "web.arcade_source": "Origen del juego", "web.arcade_error": "Errores en la sala de juegos",
    "web.award": "Puntos conseguidos (por tipo)", "web.score_complete": "Visitas con los 100 puntos", "web.murray_open": "Murray abierto (por sala)", "web.murray_go": "Murray llevó a…",
    "web.lang_switch": "Cambios de idioma", "web.outbound": "Enlaces externos", "web.toggle": "Ajustes", "web.catalog_search": "Búsquedas en el catálogo",
    "web.consent": "Google Analytics (banner)", "web.js_error": "Errores de JavaScript", "web.vitals_rating": "Core Web Vitals (valoración)", "web.scroll_depth": "Hasta dónde leen",
    "web.bots": "Robots descartados",
    "murray.answers": "Murray · respuestas", "murray.langs": "Murray · idioma", "murray.pages": "Murray · desde qué sala", "murray.turns": "Murray · turno de la conversación",
    "murray.errors": "Murray · errores", "murray.navigate": "Murray · visitas guiadas",
    "games.requests": "Proxy · juegos pedidos", "games.cache": "Proxy · caché", "games.served": "Proxy · respuestas", "games.served_kb": "Proxy · KB servidos",
    "games.errors": "Proxy · errores", "games.not_playable": "Proxy · pedidos no jugables" };
  const ORDER = ["web.pages", "web.entry_pages", "web.referrers", "web.langs", "web.browser_langs", "web.devices", "web.timeline_open", "web.arcade_play",
    "web.arcade_engine", "web.arcade_source", "web.award", "web.scroll_depth", "web.murray_open", "murray.answers", "murray.pages", "murray.langs", "murray.turns",
    "murray.navigate", "murray.errors", "games.requests", "games.cache", "games.served", "games.served_kb", "games.errors", "games.not_playable",
    "web.outbound", "web.lang_switch", "web.toggle", "web.catalog_search", "web.consent", "web.vitals_rating", "web.arcade_error", "web.js_error", "web.score_complete", "web.navigation", "web.bots"];
  function bars(title, kv, unit) {
    const rows = Object.entries(kv || {}).sort((a, b) => b[1] - a[1]), top = rows.slice(0, 15), max = top.length ? top[0][1] : 1;
    const total = rows.reduce((n, r) => n + r[1], 0);
    return '<div class="card stat"><h2>' + esc(title) + ' <span class="muted">' + fmtN(total) + (unit || "") + "</span></h2>" +
      (top.length ? '<table class="hbars"><tbody>' + top.map(([k, v]) =>
        "<tr><th>" + esc(k) + '</th><td class="bar"><span style="width:' + (100 * v / max).toFixed(1) + '%"></span></td><td class="num">' + fmtN(v) + "</td></tr>").join("") +
        "</tbody></table>" + (rows.length > 15 ? '<p class="muted">y ' + (rows.length - 15) + " más</p>" : "") : '<p class="muted">Sin datos todavía.</p>') + "</div>";
  }
  function column(title, daily, key) {
    const max = Math.max(1, ...daily.map(d => d[key]));
    return '<div class="card stat"><h2>' + esc(title) + '</h2><div class="cols" role="img" aria-label="' + esc(title + " por día") + '">' +
      daily.map(d => '<span title="' + esc(d.date + ": " + fmtN(d[key])) + '"><i style="height:' + (100 * d[key] / max).toFixed(1) + '%"></i></span>').join("") +
      '</div><p class="muted cols-axis"><span>' + esc((daily[0] || {}).date || "") + "</span><span>máx. " + fmtN(max) + "</span><span>" + esc((daily[daily.length - 1] || {}).date || "") + "</span></p></div>";
  }
  function timings(title, kv, fmt = fmtMs) {
    const list = Object.entries(kv || {}).sort((a, b) => b[1].n - a[1].n).slice(0, 15), f = (v, k) => (v == null ? "—" : fmt(v, k));
    return '<div class="card stat"><h2>' + esc(title) + "</h2>" + (list.length ? "<table><thead><tr><th></th><th>n</th><th>mediana</th><th>p75</th><th>p95</th></tr></thead><tbody>" +
      list.map(([k, h]) => "<tr><th>" + esc(k) + '</th><td class="num">' + fmtN(h.n) + '</td><td class="num">' + f(h.p50, k) + '</td><td class="num">' + f(h.p75, k) + '</td><td class="num">' + f(h.p95, k) + "</td></tr>").join("") +
      "</tbody></table>" : '<p class="muted">Sin datos todavía.</p>') + "</div>";
  }
  async function loadStats() {
    let s;
    try { s = await api("/api/admin/stats?days=" + $("#statDays").value); } catch (e) { $("#stats").innerHTML = '<p class="err">' + esc(e.message) + "</p>"; return; }
    const T = s.totals;
    $("#statNote").textContent = "Sin cookies ni IPs guardadas. Murray: " + (s.murray === "ok" ? "conectado" : s.murray) + ".";
    $("#stats").innerHTML =
      '<div class="counts">' + [["Visitantes únicos (por día)", T.visitors], ["Páginas vistas", T.pageviews], ["Preguntas a Murray", T.murray], ["Partidas", T.plays]]
        .map(([k, v]) => "<div><b>" + fmtN(v) + "</b>" + esc(k) + "</div>").join("") + "</div>" +
      '<div class="grid2">' + column("Visitantes", s.daily, "visitors") + column("Páginas vistas", s.daily, "pageviews") + "</div>" +
      '<div class="grid3">' +
      timings("Core Web Vitals", s.timings["web.vitals"], (v, k) => (k === "CLS" ? (v / 1000).toFixed(3) : fmtMs(v))) +
      timings("Tiempo en cada sala", s.timings["web.time_on_page"]) +
      timings("Murray · tiempo de respuesta", s.timings["murray.latency"]) +
      timings("Proxy · preparar un juego", s.timings["games.prepare"]) +
      ORDER.filter(k => s.counters[k]).map(k => bars(NAMES[k] || k, s.counters[k], k === "games.served_kb" ? " KB" : "")).join("") +
      Object.keys(s.counters).filter(k => !ORDER.includes(k) && !/pageviews|requests$|page_lang/.test(k) && k !== "games.requests").map(k => bars(NAMES[k] || k, s.counters[k])).join("") +
      "</div>" +
      '<details class="card"><summary>Tabla por día</summary><table><thead><tr><th>Día</th><th>Visitantes</th><th>Páginas</th><th>Murray</th><th>Partidas</th></tr></thead><tbody>' +
      s.daily.slice().reverse().map(d => "<tr><td>" + esc(d.date) + '</td><td class="num">' + fmtN(d.visitors) + '</td><td class="num">' + fmtN(d.pageviews) + '</td><td class="num">' + fmtN(d.murray) + '</td><td class="num">' + fmtN(d.plays) + "</td></tr>").join("") +
      "</tbody></table></details>";
  }
  $("#statDays").addEventListener("change", loadStats);
  $("#statReload").addEventListener("click", loadStats);

  function renderDownloads(list) {
    const failed = [];
    catalog.games.forEach(g => g.editions.forEach(e => { if (e.validated && e.validated.ok === false) failed.push([g, e]); }));
    $("#downloads").innerHTML = "<h2>Descargas recientes</h2>" + (list.length ? "<table><tr><th>Fecha</th><th>Edición</th><th>Quién</th><th>Resultado</th></tr>" + list.map(d =>
      "<tr><td>" + esc(d.at) + "</td><td>" + esc(d.title || "") + "<br><small>" + esc(d.key) + "</small></td><td>" + esc(d.by) + "</td><td>" +
      (d.ok ? '<span class="ok">bien</span> · ' + esc(d.seconds) + " s · " + ((d.bytes || 0) / 1048576).toFixed(1) + " MB" : '<span class="err">' + esc(d.error) + "</span>" + (d.network ? " (red: se reintentará)" : "")) + "</td></tr>").join("") + "</table>" : '<p class="muted">Aún no hay descargas.</p>') +
      "<h2>Validaciones fallidas</h2>" + (failed.length ? "<table><tr><th>Juego</th><th>Edición</th><th>Error</th></tr>" + failed.map(([g, e]) =>
        "<tr><td>" + esc(g.title) + "</td><td>" + esc(e.edition) + "</td><td>" + esc(e.validated.error) + "</td></tr>").join("") + "</table>" : '<p class="muted">Ninguna.</p>');
  }

  /* ---------- start */
  async function loadCatalog() {
    catalog = await api("/api/admin/catalog");
    renderCounts(); renderList(); if (current) renderDetail();
    if (!$("[data-panel=sources]").hidden) renderSources();
  }
  async function start() {
    me = await api("/api/admin/me");
    $("#who").textContent = me.user;
    show(true);
    await loadCatalog(); await refreshStatus();
    clearInterval(pollTimer); pollTimer = setInterval(refreshStatus, 5000);
  }
  start().catch(() => show(false));
})();
