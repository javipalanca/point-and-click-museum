/* Point and Click Museum · Murray, the talking skull: chat widget on every page (bottom-right button).
   The browser only talks to the museum's own server (/api/murray/chat, see server/murray.py), which calls
   the language model. No API key or model endpoint ever reaches this file. */
"use strict";
(() => {
  const { D, $, esc, sfx, mediaFigure } = PCM;
  const fab = $("#murrayFab"), panel = $("#murrayPanel");
  if (!fab || !panel || !D.murray) return;
  const M = D.murray, U = M.ui, log = $("#murrayLog"), input = $("#murrayIn"), send = $("#murraySend");
  const api = D.root + "api/murray/chat";
  const KEY = "pcm-murray";  // the conversation follows the visitor from room to room (this tab only)
  const load = () => { try { return JSON.parse(sessionStorage.getItem(KEY)) || {}; } catch (_) { return {}; } };
  const save = () => { try { sessionStorage.setItem(KEY, JSON.stringify({ open: !panel.hidden, history, shown, mode: lastMode })); } catch (_) { /* private mode */ } };
  const saved = load();
  let history = Array.isArray(saved.history) ? saved.history : [];  // [{role, content}] sent to the server
  let shown = Array.isArray(saved.shown) ? saved.shown : [];        // what the log displays, with sources
  let lastMode = saved.mode || "", busy = false, talkingUntil = 0, started = false;

  /* --- Murray's face: the real talking frames from the game, animated while he speaks */
  const cv = $("#murrayFace"), x = cv.getContext("2d");
  const frames = (M.frames || []).map(f => { const im = new Image(); im.src = f.src; return im; });
  let frame = 0, last = 0, raf = 0;
  function drawFace(t) {
    raf = 0;
    if (panel.hidden) return;
    const talking = performance.now() < talkingUntil;
    if (t - last > 110) { last = t; frame = talking && frames.length > 1 ? 1 + Math.floor(Math.random() * (frames.length - 1)) : 0; }
    const im = frames[frame];
    x.fillStyle = "#000"; x.fillRect(0, 0, cv.width, cv.height);
    if (im && im.complete && im.naturalWidth) x.drawImage(im, 0, cv.height - im.naturalHeight);
    if (!PCM.reduceMotion || talking) raf = requestAnimationFrame(drawFace);
  }
  const animate = () => { if (!raf) raf = requestAnimationFrame(drawFace); };

  /* --- the log */
  function sourcesHtml(sources) {
    return sources && sources.length ? '<p class="src"><span>' + esc(U.sources) + ":</span> " +
      sources.map(s => s.external
        ? '<a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.title) + " ↗</a>"
        : '<a href="' + esc(D.root + D.lang + "/" + s.url) + '">' + esc(s.title) + "</a>").join(" · ") + "</p>" : "";
  }
  const textHtml = t => esc(t).replace(/\n/g, "<br>");
  function render(item) {
    const li = document.createElement("li");
    li.className = "m-" + item.who + (item.waiting ? " waiting" : "");
    li.innerHTML = item.who === "nav" ? "<p>→ " + textHtml(item.text) + "</p>"
      : '<span class="who">' + esc(item.who === "murray" ? "Murray" : U.you) + "</span><p>" + textHtml(item.text) + "</p>" + sourcesHtml(item.sources);
    log.appendChild(li); log.scrollTop = log.scrollHeight;
    return li;
  }
  function add(who, text, sources) { const it = { who, text, sources }; shown.push(it); render(it); save(); }
  function speak(text, sources) { talkingUntil = performance.now() + Math.min(9000, 600 + text.length * 35); add("murray", text, sources); animate(); }
  function mode(m) { lastMode = m || lastMode; $("#murrayMode").textContent = lastMode === "llm" ? U.llmBadge : lastMode === "offline" ? U.offlineBadge : ""; }

  /* Reads the server's Server-Sent Events (data: {"delta"} … data: {"done", "sources", "mode"}) and calls back as they arrive. */
  async function readStream(r, onDelta) {
    if (!/event-stream/.test(r.headers.get("Content-Type") || "")) {  // an older server answering with plain JSON
      const j = await r.json(); onDelta(j.reply || ""); return j;
    }
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf = "", done = null;
    for (;;) {
      const { value, done: end } = await reader.read();
      if (end) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, i); buf = buf.slice(i + 2);
        const line = block.split("\n").find(l => l.startsWith("data:"));
        if (!line) continue;
        let ev; try { ev = JSON.parse(line.slice(5)); } catch (_) { continue; }
        if (ev.delta) onDelta(ev.delta);
        else if (ev.done) done = ev;
        else if (ev.error) throw new Error(ev.error);
      }
    }
    return done || {};
  }

  /* Murray takes the visitor somewhere: the chat stays open on the next page (state is in sessionStorage) */
  function travel(nav) {
    const base = D.pageUrls && D.pageUrls[nav.page];
    if (base == null) return;
    const title = nav.title || (D.ui && D.ui["page_" + nav.page + "_title"]) || nav.page;
    add("nav", U.goingTo + ": " + title);
    const url = new URL(base + (nav.hash ? "#" + nav.hash : ""), location.href);
    setTimeout(() => {
      save();
      if (url.pathname === location.pathname) {           // same room: just move to the spot
        if (nav.hash) { if (location.hash === "#" + nav.hash) dispatchEvent(new HashChangeEvent("hashchange")); else location.hash = nav.hash; }
        else scrollTo({ top: 0, behavior: PCM.reduceMotion ? "auto" : "smooth" });
      } else if (PCM.go) PCM.go(url.href);
      else location.href = url.href;
    }, PCM.reduceMotion ? 300 : 1400);
  }

  async function ask(q) {
    q = q.trim(); if (!q || busy) return;
    busy = true; send.disabled = true; input.value = "";
    add("you", q); history.push({ role: "user", content: q }); sfx("click");
    const li = render({ who: "murray", text: U.thinking, waiting: true }), p = li.querySelector("p");
    let text = "";
    try {
      const r = await fetch(api, { method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ lang: D.lang, page: D.page, stream: true, messages: history.slice(-12) }) });
      if (r.status === 429) { li.remove(); history.pop(); speak(M.errors.busy); return; }
      if (!r.ok) throw new Error("HTTP " + r.status);
      const end = await readStream(r, d => {
        if (!text) li.classList.remove("waiting");
        text += d; p.innerHTML = textHtml(text);
        talkingUntil = performance.now() + 700; animate();          // Murray's jaw moves while the words arrive
        log.scrollTop = log.scrollHeight;
      });
      text = text.trim() || M.errors.failed;
      li.remove();
      history.push({ role: "assistant", content: text });
      add("murray", text, end.sources); mode(end.mode);
      if (end.navigate) travel(end.navigate);
    } catch (e) {
      li.remove(); history.pop();
      if (text) { add("murray", text.trim() + "\n\n" + M.errors.failed); return; }
      speak(location.protocol === "file:" || /HTTP 40[45]|Failed to fetch|NetworkError|Load failed/.test(String(e)) ? M.errors.offlineSite : M.errors.failed);
    } finally { busy = false; send.disabled = false; input.focus({ preventScroll: true }); }
  }

  /* --- open / close */
  function start() {
    if (started) return; started = true;
    send.textContent = U.send; input.placeholder = U.placeholder; $("#murrayPrivacy").textContent = U.privacy;
    $("#murraySugg").innerHTML = M.suggestions.map(s => '<button class="pbtn small" type="button">' + esc(s) + "</button>").join("");
    if (M.frames && M.frames[0]) $("#murrayPrivacy").insertAdjacentHTML("beforeend", mediaFigure(M.frames[0], "Murray", "murray-fig").replace(/<img[^>]*>/, ""));
    shown.forEach(render); mode();
    if (!shown.length) speak(M.greeting);
  }
  function open(focus) {
    start(); panel.hidden = false; fab.setAttribute("aria-expanded", "true"); fab.classList.add("on");
    log.scrollTop = log.scrollHeight; animate(); save();
    if (focus) input.focus({ preventScroll: true });
  }
  function close() { panel.hidden = true; fab.setAttribute("aria-expanded", "false"); fab.classList.remove("on"); save(); fab.focus({ preventScroll: true }); }
  fab.addEventListener("click", () => { sfx("open"); panel.hidden ? open(true) : close(); });
  $("#murrayClose").addEventListener("click", close);
  $("#murrayReset").addEventListener("click", () => { history = []; shown = []; log.innerHTML = ""; speak(M.greeting); });
  panel.addEventListener("keydown", e => { if (e.key === "Escape") { e.stopPropagation(); close(); } });
  $("#murraySugg").addEventListener("click", e => { const b = e.target.closest("button"); if (b) ask(b.textContent); });
  $("#murrayForm").addEventListener("submit", e => { e.preventDefault(); ask(input.value); });
  if (saved.open) open(false);
})();
