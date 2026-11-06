/* Point and Click Museum · usage statistics.
   Three parts, all off unless build.py was given them (data → analytics):
   - stats: the museum's own counters (server/stats.py). No cookies, nothing stored in the browser, no identifiers;
     events go in batches with navigator.sendBeacon. Off when the browser asks not to be tracked (GPC / DNT).
   - ga: Google Analytics 4, following the measurement plan in data/analytics.json (events, parameters, user
     properties; tools/ga_setup.py registers them in the property). Loaded only after the visitor accepts the banner
     (it sets cookies); the choice is remembered and can be changed from the footer. Consent Mode starts denied.
   - clarity: Microsoft Clarity (heatmaps and session recordings), loaded with the same consent as GA.
   Other scripts call PCM.track(name, params) (own statistics and GA) or PCM.ga(name, params) (GA and Clarity only);
   neither ever throws, and both do nothing without a destination. Murray's questions are never sent anywhere. */
"use strict";
(() => {
  const { D, $, $$, t, esc, store } = PCM;
  const A = D.analytics || {};
  const web = /^https?:$/.test(location.protocol);
  const optOut = navigator.globalPrivacyControl === true || navigator.doNotTrack === "1" || window.doNotTrack === "1";
  const own = web && A.stats && !optOut;
  const SC = (D.site && D.site.score) || { awards: {}, total: 100 };
  const MINIGAMES = { textAdventure: "text-adventure", room: "restoration-room", hunt: "pixel-hunt", chronology: "chronology" };
  let ga = false, clarity = false;
  const queue = [];

  function flush() {
    if (!own || !queue.length) return;
    const body = JSON.stringify({ e: queue.splice(0, 40) });
    try {
      if (!(navigator.sendBeacon && navigator.sendBeacon(A.stats, new Blob([body], { type: "text/plain" }))))
        fetch(A.stats, { method: "POST", body, keepalive: true, headers: { "Content-Type": "text/plain" } }).catch(() => {});
    } catch (e) { /* statistics never break the page */ }
    if (queue.length) flush();
  }

  /* ---------- Google Analytics (and Clarity): events of the measurement plan ---------- */
  const debug = (() => { try { if (/[?&]ga_debug=1/.test(location.search)) sessionStorage.setItem("pcm-ga-debug", "1"); return sessionStorage.getItem("pcm-ga-debug") === "1"; } catch (e) { return false; } })();
  const CLARITY_EVENTS = new Set(["game_start", "game_end", "game_error", "level_start", "level_end", "post_score", "search", "murray_open",
    "murray_question", "murray_guided", "language_switch", "gog_click", "outbound_click", "exception", "select_content"]);
  function gaEvent(name, params = {}) {
    try {
      if (ga) window.gtag("event", name, Object.assign({ room: D.page, site_language: D.lang }, debug ? { debug_mode: true } : {}, params));
      if (clarity && CLARITY_EVENTS.has(name)) window.clarity("event", name);
    } catch (e) { /* ignore */ }
  }
  PCM.ga = gaEvent;
  const scoreNow = () => [...new Set(store("awarded") || [])].reduce((n, id) => n + ((SC.awards[id.split(":")[0]] || {}).points || 0), 0);
  const band = s => (s >= SC.total ? "100" : s >= 75 ? "75-99" : s >= 50 ? "50-74" : s >= 25 ? "25-49" : s > 0 ? "1-24" : "0");

  /* the museum's own events, translated to GA4's recommended events where one fits */
  function toGA(n, p) {
    if (n === "award") {
      const pts = (SC.awards[p.key] || {}).points || 0;
      gaEvent("unlock_achievement", { achievement_id: p.key });
      gaEvent("earn_virtual_currency", { virtual_currency_name: "points", value: pts });
      if (MINIGAMES[p.key]) gaEvent("level_end", { level_name: MINIGAMES[p.key], success: true });
      if (ga) window.gtag("set", "user_properties", { score_band: band(scoreNow()) });
    } else if (n === "score_complete") gaEvent("post_score", { score: SC.total });
    else if (n === "timeline_open") gaEvent("select_content", { content_type: "game", content_id: p.id });
    else if (n === "arcade_play") gaEvent("game_start", { game_id: p.id, game_name: p.title || p.id, game_engine: p.engine, game_source: p.src });
    else if (n === "arcade_error") gaEvent("game_error", { game_id: p.id, error_kind: p.kind });
    else if (n === "murray_open") gaEvent("murray_open", {});
    else if (n === "murray_ask") gaEvent("murray_question", { murray_turn: p.turn || 1 });
    else if (n === "murray_go") gaEvent("murray_guided", { destination: p.to });
    else if (n === "toggle") {
      gaEvent("setting_change", { setting: p.what, enabled: p.on ? "yes" : "no" });
      if (ga) window.gtag("set", "user_properties", { [p.what]: p.on ? "on" : "off" });
    } else if (n === "js_error") gaEvent("exception", { description: (p.src ? p.src + ":" + p.line + " " : "") + String(p.msg).slice(0, 100), fatal: false });
    else if (n === "vital") {
      const T = { LCP: [2500, 4000], INP: [200, 500], CLS: [0.1, 0.25], FCP: [1800, 3000], TTFB: [800, 1800] }[p.name] || [Infinity, Infinity];
      const v = p.name === "CLS" ? Math.round(p.value * 1000) : Math.round(p.value);
      gaEvent("web_vitals", { metric_name: p.name, metric_value: v, value: v,
        metric_rating: p.value <= T[0] ? "good" : p.value > T[1] ? "poor" : "needs-improvement", non_interaction: true });
    }
  }

  let timer = null;
  function track(n, p = {}) {
    try {
      if (own) {
        queue.push({ n, p: Object.assign({ page: D.page, lang: D.lang }, p) });
        if (queue.length >= 20) flush();
        else if (!timer) timer = setTimeout(() => { timer = null; flush(); }, 8000);
      }
      if (ga || clarity) toGA(n, p);
    } catch (e) { /* ignore */ }
  }
  PCM.track = track;

  /* ---------- page view, time on the page and how far it was read ---------- */
  const navEntry = (performance.getEntriesByType && performance.getEntriesByType("navigation")[0]) || {};
  const viewport = () => (innerWidth < 600 ? "mobile" : innerWidth < 1024 ? "tablet" : "desktop");
  track("page_view", { ref: document.referrer, dev: viewport(), nav: navEntry.type || "navigate", blang: (navigator.language || "").slice(0, 2) });
  let visible = document.visibilityState === "visible" ? performance.now() : null, shown = 0, maxScroll = 0;
  const reached = new Set();
  const scrolled = () => {
    const h = document.documentElement.scrollHeight - innerHeight;
    maxScroll = Math.max(maxScroll, h > 0 ? Math.round(100 * scrollY / h) : 100);
    [25, 50, 75, 100].forEach(q => { if (maxScroll >= q && !reached.has(q) && (ga || clarity)) { reached.add(q); gaEvent("scroll_depth", { percent: q }); } });
  };
  addEventListener("scroll", scrolled, { passive: true });

  /* ---------- Core Web Vitals (LCP, CLS, INP, FCP, TTFB), measured as web-vitals does, without the library ---------- */
  const vitals = {};
  const observe = (type, fn, opts) => {
    try { new PerformanceObserver(l => l.getEntries().forEach(fn)).observe(Object.assign({ type, buffered: true }, opts)); } catch (e) { /* unsupported */ }
  };
  if (navEntry.responseStart > 0) vitals.TTFB = navEntry.responseStart;
  observe("paint", e => { if (e.name === "first-contentful-paint") vitals.FCP = e.startTime; });
  observe("largest-contentful-paint", e => { vitals.LCP = e.startTime; });
  let cls = 0, win = 0, winStart = 0, winLast = 0;
  observe("layout-shift", e => {
    if (e.hadRecentInput) return;
    if (win && e.startTime - winLast < 1000 && e.startTime - winStart < 5000) win += e.value;
    else { win = e.value; winStart = e.startTime; }
    winLast = e.startTime; cls = Math.max(cls, win); vitals.CLS = cls;
  });
  observe("event", e => { if (e.interactionId) vitals.INP = Math.max(vitals.INP || 0, e.duration); }, { durationThreshold: 40 });
  observe("first-input", e => { vitals.INP = Math.max(vitals.INP || 0, e.duration); });

  let sentVitals = false;
  function leave() {
    if (visible != null) { shown += performance.now() - visible; visible = null; }
    if (!sentVitals) {
      sentVitals = true;
      Object.keys(vitals).forEach(name => track("vital", { name, value: Math.round(name === "CLS" ? vitals[name] * 1000 : vitals[name]) / (name === "CLS" ? 1000 : 1) }));
    }
    if (shown > 1000) { track("engage", { sec: Math.round(shown / 1000), scroll: Math.min(100, maxScroll) }); shown = 0; }
    flush();
  }
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") leave();
    else if (visible == null) visible = performance.now();
  });
  addEventListener("pagehide", leave);

  /* ---------- errors, links out of the museum, language changes ---------- */
  let errors = 0;
  addEventListener("error", e => {
    if (errors++ >= 5 || !e.message) return;
    track("js_error", { msg: e.message, src: String(e.filename || "").split("/").pop().split("?")[0], line: e.lineno || 0 });
  });
  addEventListener("unhandledrejection", e => {
    if (errors++ >= 5) return;
    track("js_error", { msg: "promise: " + String((e.reason && e.reason.message) || e.reason).slice(0, 100), src: "", line: 0 });
  });

  /* ---------- where people click (GA: ui_click with position and place; Clarity draws the heatmaps) ---------- */
  const REGIONS = [["#consentBox", "consent"], ["#dosModal", "dosbox"], ["#modalBg", "modal"], ["#mapPanel", "map"], ["#murrayWidget", "murray"],
    ["#siteHeader", "header"], [".subnav", "subnav"], [".site-footer", "footer"], ["main", "main"]];
  const regionOf = el => (REGIONS.find(([sel]) => el.closest(sel)) || [null, "other"])[1];
  const textOf = el => (el.getAttribute("aria-label") || el.textContent || el.getAttribute("title") || el.getAttribute("alt") || "").replace(/\s+/g, " ").trim().slice(0, 40);
  const nameOf = el => el.dataset.ga || (el.id ? "#" + el.id : "") || [el.tagName.toLowerCase(), ...[...el.classList].slice(0, 2)].join(".");
  const sectionOf = el => { const s = el.closest("[id^='era-'],[id^='studio-'],[id^='engine-'],[id^='tech-'],section[id]"); return s ? s.id : ""; };
  let lastClick = 0;
  document.addEventListener("click", e => {
    const a = e.target.closest && e.target.closest("a[href]");
    if (a) {
      let u = null; try { u = new URL(a.href, location.href); } catch (_) { /* not a URL */ }
      if (u && a.hasAttribute("hreflang") && a.getAttribute("hreflang") !== D.lang) {
        track("lang_switch", { from: D.lang, to: a.getAttribute("hreflang") });
        gaEvent("language_switch", { from_language: D.lang, to_language: a.getAttribute("hreflang") });
      } else if (u && /^https?:$/.test(u.protocol) && u.host !== location.host) {
        track("outbound", { url: u.origin });
        gaEvent("outbound_click", { link_domain: u.hostname.replace(/^www\./, ""), link_url: (u.origin + u.pathname).slice(0, 100), link_text: textOf(a), region: regionOf(a) });
        if (/(^|\.)gog\.com$/.test(u.hostname)) {
          const g = a.closest("[data-id]");
          gaEvent("gog_click", { game_id: g ? g.dataset.id : (location.hash.slice(1) || D.page), link_url: (u.origin + u.pathname).slice(0, 100) });
        }
      }
    }
    if (!(ga || clarity) || performance.now() - lastClick < 250) return;
    const el = e.target.closest && e.target.closest("a, button, summary, [role=tab], [role=button], select, input, canvas, label, .dos-play, .tl-entry");
    if (!el) return;
    lastClick = performance.now();
    const doc = document.documentElement.scrollHeight || 1, five = v => Math.max(0, Math.min(100, Math.round(v / 5) * 5));
    gaEvent("ui_click", { element: nameOf(el), link_text: el.tagName === "INPUT" ? "" : textOf(el), region: regionOf(el), section_id: sectionOf(el),
      x_pct: five(100 * e.clientX / innerWidth), y_pct: five(100 * e.clientY / innerHeight), page_y_pct: five(100 * (e.clientY + scrollY) / doc), viewport: viewport() });
  }, true);

  /* ---------- what holds the attention: sections that stay 1.5 s on screen; minigames started ---------- */
  function watchSections() {
    if (!("IntersectionObserver" in window)) return;
    const seen = new Set(), timers = new Map();
    const io = new IntersectionObserver(entries => entries.forEach(en => {
      const id = en.target.id;
      if (seen.has(id)) return;
      if (en.isIntersecting) timers.set(id, setTimeout(() => { seen.add(id); io.unobserve(en.target); gaEvent("section_view", { section_id: id }); }, 1500));
      else { clearTimeout(timers.get(id)); timers.delete(id); }
    }), { threshold: 0.5 });
    $$("[id^='era-'],[id^='studio-'],[id^='engine-'],[id^='tech-'],main section[id]").forEach(el => io.observe(el));
  }
  if (Object.values(MINIGAMES).includes(D.page)) {
    const start = e => {
      if (!(ga || clarity) || !e.target.closest || !e.target.closest("main")) return;
      ["pointerdown", "keydown"].forEach(k => removeEventListener(k, start, true));
      gaEvent("level_start", { level_name: D.page });
    };
    ["pointerdown", "keydown"].forEach(k => addEventListener(k, start, true));
  }

  /* ---------- Google Analytics and Microsoft Clarity, only with consent ---------- */
  if (!(A.ga || A.clarity) || !web) return;
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { window.dataLayer.push(arguments); };
  window.gtag("consent", "default", { analytics_storage: "denied", ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied" });

  function visitorType() {
    try {
      let n = +(localStorage.getItem("pcm-visits") || 0);
      if (!sessionStorage.getItem("pcm-visit")) { sessionStorage.setItem("pcm-visit", "1"); localStorage.setItem("pcm-visits", String(++n)); }
      return n > 1 ? "returning" : "new";
    } catch (e) { return "unknown"; }
  }
  function startGA() {
    if (ga || !A.ga) return;
    ga = true;
    window.gtag("consent", "update", { analytics_storage: "granted" });
    window.gtag("js", new Date());
    const lang = store("lang");
    window.gtag("set", "user_properties", {
      ui_language: D.lang, browser_language: (navigator.language || "").slice(0, 2).toLowerCase(), preferred_language: lang || "auto",
      device_class: viewport(), score_band: band(scoreNow()), sound: store("snd") === false ? "off" : "on", crt: store("crt") === false ? "off" : "on",
      reduced_motion: PCM.reduceMotion ? "yes" : "no" });
    window.gtag("config", A.ga, Object.assign({ page_title: document.title, content_group: D.page, language: D.lang, room: D.page, site_language: D.lang,
      visitor_type: visitorType(), allow_google_signals: false, allow_ad_personalization_signals: false }, debug ? { debug_mode: true } : {}));
    const s = document.createElement("script");
    s.async = true; s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(A.ga);
    document.head.appendChild(s);
  }
  function startClarity() {
    if (clarity || !A.clarity) return;
    clarity = true;
    window.clarity = window.clarity || function () { (window.clarity.q = window.clarity.q || []).push(arguments); };
    const s = document.createElement("script");
    s.async = true; s.src = "https://www.clarity.ms/tag/" + encodeURIComponent(A.clarity);
    document.head.appendChild(s);
    window.clarity("consent");
    window.clarity("set", "room", D.page); window.clarity("set", "site_language", D.lang); window.clarity("set", "viewport", viewport());
  }
  function start() { startGA(); startClarity(); watchSections(); scrolled(); }
  function stop() {
    if (ga) window.gtag("consent", "update", { analytics_storage: "denied" });
    if (clarity) try { window.clarity("consent", false); } catch (e) { /* not loaded */ }
    ga = clarity = false;
    const domain = location.hostname.split(".").slice(-2).join(".");
    document.cookie.split(";").map(c => c.trim().split("=")[0]).filter(n => /^(_ga|_clck|_clsk|CLID|MUID)/.test(n)).forEach(n => {
      [location.hostname, "." + domain, ""].forEach(d => { document.cookie = n + "=; Max-Age=0; path=/" + (d ? "; domain=" + d : ""); });
    });
    try { localStorage.removeItem("pcm-visits"); } catch (e) { /* ignore */ }
  }
  function choose(granted) {
    store("consent", granted ? "granted" : "denied");
    track("consent", { granted });
    granted ? start() : stop();
    hide();
  }

  let box = null;
  function hide() { if (box) { box.remove(); box = null; } }
  function ask() {
    if (box) return;
    box = document.createElement("div");
    box.className = "pconsent px"; box.id = "consentBox"; box.setAttribute("role", "region"); box.setAttribute("aria-label", t("consentLink"));
    box.innerHTML = "<p>" + esc(t(A.clarity ? (A.ga ? "consentTextBoth" : "consentTextClarity") : "consentText")) + '</p><div class="row"><button class="pbtn small" type="button" data-c="1">' +
      esc(t("consentAccept")) + '</button><button class="pbtn small ghost" type="button" data-c="0">' + esc(t("consentReject")) + "</button></div>";
    box.addEventListener("click", e => { const b = e.target.closest("button[data-c]"); if (b) choose(b.dataset.c === "1"); });
    document.body.appendChild(box);
  }
  const btn = $("#consentOpen");
  if (btn) btn.addEventListener("click", ask);
  if (optOut) return;                       // the browser already said no: no banner, no Google, no Clarity
  const choice = store("consent");
  if (choice === "granted") start();
  else if (choice !== "denied") ask();
})();
