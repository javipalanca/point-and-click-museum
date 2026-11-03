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
  function render(item) {
    const li = document.createElement("li");
    li.className = "m-" + item.who + (item.waiting ? " waiting" : "");
    li.innerHTML = '<span class="who">' + esc(item.who === "murray" ? "Murray" : U.you) + "</span><p>" + esc(item.text).replace(/\n/g, "<br>") + "</p>" +
      (item.sources && item.sources.length ? '<p class="src"><span>' + esc(U.sources) + ":</span> " +
        item.sources.map(s => '<a href="' + esc(D.root + D.lang + "/" + s.url) + '">' + esc(s.title) + "</a>").join(" · ") + "</p>" : "");
    log.appendChild(li); log.scrollTop = log.scrollHeight;
    return li;
  }
  function add(who, text, sources) { const it = { who, text, sources }; shown.push(it); render(it); save(); }
  function speak(text, sources) { talkingUntil = performance.now() + Math.min(9000, 600 + text.length * 35); add("murray", text, sources); animate(); }
  function mode(m) { lastMode = m || lastMode; $("#murrayMode").textContent = lastMode === "llm" ? U.llmBadge : lastMode === "offline" ? U.offlineBadge : ""; }

  async function ask(q) {
    q = q.trim(); if (!q || busy) return;
    busy = true; send.disabled = true; input.value = "";
    add("you", q); history.push({ role: "user", content: q }); sfx("click");
    const wait = render({ who: "murray", text: U.thinking, waiting: true });
    try {
      const r = await fetch(api, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lang: D.lang, messages: history.slice(-12) }) });
      wait.remove();
      if (r.status === 429) { history.pop(); speak(M.errors.busy); return; }
      if (!r.ok) throw new Error("HTTP " + r.status);
      const j = await r.json();
      history.push({ role: "assistant", content: j.reply });
      speak(j.reply, j.sources); mode(j.mode); save();
    } catch (e) {
      wait.remove(); history.pop();
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
