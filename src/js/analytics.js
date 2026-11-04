/* Point and Click Museum · usage statistics.
   Two independent parts, both off unless build.py was given them (data → analytics):
   - stats: the museum's own counters (server/stats.py). No cookies, nothing stored in the browser, no identifiers;
     events go in batches with navigator.sendBeacon. Off when the browser asks not to be tracked (GPC / DNT).
   - ga: Google Analytics 4. Loaded only after the visitor accepts it in the banner (it sets cookies); the choice
     is remembered and can be changed from the footer. Consent Mode starts with everything denied.
   Other scripts call PCM.track(name, params); it never throws and does nothing without a destination. */
"use strict";
(() => {
  const { D, $, t, esc, store } = PCM;
  const A = D.analytics || {};
  const web = /^https?:$/.test(location.protocol);
  const optOut = navigator.globalPrivacyControl === true || navigator.doNotTrack === "1" || window.doNotTrack === "1";
  const own = web && A.stats && !optOut;
  let ga = false;
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
  let timer = null;
  function track(n, p = {}) {
    try {
      if (own) {
        queue.push({ n, p: Object.assign({ page: D.page, lang: D.lang }, p) });
        if (queue.length >= 20) flush();
        else if (!timer) timer = setTimeout(() => { timer = null; flush(); }, 8000);
      }
      if (ga && n !== "page_view" && n !== "engage") window.gtag("event", n, Object.assign({ room: D.page }, p));
    } catch (e) { /* ignore */ }
  }
  PCM.track = track;

  /* ---------- page view, time on the page and how far it was read ---------- */
  const navEntry = (performance.getEntriesByType && performance.getEntriesByType("navigation")[0]) || {};
  const w = innerWidth, dev = w < 600 ? "mobile" : w < 1024 ? "tablet" : "desktop";
  track("page_view", { ref: document.referrer, dev, nav: navEntry.type || "navigate", blang: (navigator.language || "").slice(0, 2) });
  let visible = document.visibilityState === "visible" ? performance.now() : null, shown = 0, maxScroll = 0;
  const scrolled = () => {
    const h = document.documentElement.scrollHeight - innerHeight;
    maxScroll = Math.max(maxScroll, h > 0 ? Math.round(100 * scrollY / h) : 100);
  };
  addEventListener("scroll", scrolled, { passive: true }); scrolled();

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
  document.addEventListener("click", e => {
    const a = e.target.closest && e.target.closest("a[href]");
    if (!a) return;
    let u; try { u = new URL(a.href, location.href); } catch (_) { return; }
    if (a.hasAttribute("hreflang") && a.getAttribute("hreflang") !== D.lang) track("lang_switch", { from: D.lang, to: a.getAttribute("hreflang") });
    else if (/^https?:$/.test(u.protocol) && u.host !== location.host) track("outbound", { url: u.origin });
  }, true);

  /* ---------- Google Analytics, only with consent ---------- */
  if (!A.ga || !web) return;
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { window.dataLayer.push(arguments); };
  window.gtag("consent", "default", { analytics_storage: "denied", ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied" });

  function startGA() {
    if (ga) return;
    ga = true;
    window.gtag("consent", "update", { analytics_storage: "granted" });
    window.gtag("js", new Date());
    window.gtag("config", A.ga, { page_title: document.title, content_group: D.page, language: D.lang, allow_google_signals: false, allow_ad_personalization_signals: false });
    const s = document.createElement("script");
    s.async = true; s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(A.ga);
    document.head.appendChild(s);
  }
  function stopGA() {
    if (ga) window.gtag("consent", "update", { analytics_storage: "denied" });
    ga = false;
    const domain = location.hostname.split(".").slice(-2).join(".");
    document.cookie.split(";").map(c => c.trim().split("=")[0]).filter(n => /^_ga/.test(n)).forEach(n => {
      [location.hostname, "." + domain, ""].forEach(d => { document.cookie = n + "=; Max-Age=0; path=/" + (d ? "; domain=" + d : ""); });
    });
  }
  function choose(granted) {
    store("consent", granted ? "granted" : "denied");
    track("consent", { granted });
    granted ? startGA() : stopGA();
    hide();
  }

  let box = null;
  function hide() { if (box) { box.remove(); box = null; } }
  function ask() {
    if (box) return;
    box = document.createElement("div");
    box.className = "pconsent px"; box.setAttribute("role", "region"); box.setAttribute("aria-label", t("consentLink"));
    box.innerHTML = "<p>" + esc(t("consentText")) + '</p><div class="row"><button class="pbtn small" type="button" data-c="1">' + esc(t("consentAccept")) +
      '</button><button class="pbtn small ghost" type="button" data-c="0">' + esc(t("consentReject")) + "</button></div>";
    box.addEventListener("click", e => { const b = e.target.closest("button[data-c]"); if (b) choose(b.dataset.c === "1"); });
    document.body.appendChild(box);
  }
  const btn = $("#consentOpen");
  if (btn) btn.addEventListener("click", ask);
  if (optOut) return;                       // the browser already said no: no banner, no Google
  const choice = store("consent");
  if (choice === "granted") startGA();
  else if (choice !== "denied") ask();
})();
