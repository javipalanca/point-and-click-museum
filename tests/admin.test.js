/* End-to-end test of the control panel (server/admin.py): login, catalogue, Internet Archive search, testing a game
   in DOSBox, marking it as available (and withdrawing it), validating it; and that the public proxy only serves it then.
   Also the statistics: the cookie banner of Google Analytics, the museum's own events and the panel's tab.
   Run: npm run test:admin */
"use strict";
const { execFileSync, spawn } = require("child_process");
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = path.join(__dirname, "..");
const shot = (page, name) => process.env.PCM_SHOTS ? page.screenshot({ path: path.join(process.env.PCM_SHOTS, name + ".png") }) : null;
let failures = 0;
const check = (ok, msg) => { console.log((ok ? "  ✓ " : "  ✗ ") + msg); if (!ok) failures++; };
const firstLine = proc => new Promise((resolve, reject) => {
  proc.stdout.once("data", d => resolve(String(d).trim().split("\n")[0]));
  proc.once("exit", c => reject(new Error("exited " + c)));
});

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "pcm-admin-"));
  const sources = spawn("python3", [path.join(__dirname, "fixtures/fake_sources.py")]);
  const src = "http://127.0.0.1:" + await firstLine(sources);
  // a catalogue with a commercial Internet Archive edition (record only) and a game without editions
  const catalog = JSON.parse(fs.readFileSync(path.join(ROOT, "data/catalog.json"), "utf8"));
  catalog.games.push({ id: "quest-for-the-museum", title: "Quest for the Museum", year: 1991, developer: "Some Studio", status: "record",
    sources: ["archive"], editions: [{ key: "quest-for-the-museum-full-msdos-quest-1991", kind: "full", rights: "commercial", emulator: "dosbox",
      run: { exe: "QUEST/QUEST.EXE" }, status: "record", edition: "Internet Archive · msdos_quest_1991", archive: "msdos_quest_1991",
      page: "https://archive.org/details/msdos_quest_1991", download: { provider: "archive", url: src + "/download/msdos_quest_1991/QUEST.ZIP" } }] });
  catalog.games.push({ id: "lonely-game", title: "Lonely Game", year: 1991, status: "record", sources: ["scummvm-catalogue"], editions: [] });
  const catDir = path.join(tmp, "catalog"); fs.mkdirSync(catDir);
  const catFile = path.join(catDir, "catalog.json");
  fs.writeFileSync(catFile, JSON.stringify(catalog));
  const out = path.join(tmp, "site");
  execFileSync("python3", [path.join(ROOT, "build.py"), "--out", out, "--no-local"], { env: { ...process.env, PCM_CATALOG: catFile, PCM_GA_ID: "G-TEST1234", PCM_STATS_URL: "/api/stats" }, stdio: "ignore" });
  const games = spawn("python3", [path.join(ROOT, "server/games.py")], { env: { ...process.env, GAMES_PORT: "0", PCM_CATALOG: catFile,
    GAMES_CACHE: path.join(tmp, "cache"), PCM_GAMES_TEST_HOSTS: "127.0.0.1", PCM_IA_BASE: src, ADMIN_USER: "javi", ADMIN_PASSWORD: "una-clave-larga-de-prueba",
    PCM_STATS_DIR: path.join(tmp, "stats"), MURRAY_URL: "" } });
  let gamesPort = null;
  games.stderr.on("data", d => { const m = /games proxy on :(\d+)/.exec(String(d)); if (m) gamesPort = +m[1]; });
  for (let i = 0; i < 50 && !gamesPort; i++) await new Promise(r => setTimeout(r, 100));
  const front = http.createServer((req, res) => {  // like nginx: the site, and /admin + /api/ to the games container
    if (/^\/(admin|api\/)/.test(req.url)) {
      const p = http.request({ port: gamesPort, path: req.url, method: req.method, headers: req.headers }, r => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
      req.pipe(p); return;
    }
    let p = decodeURIComponent(req.url.split("?")[0].split("#")[0]);
    if (p.endsWith("/")) p += "index.html";
    const f = path.join(out, p);
    if (!f.startsWith(out) || !fs.existsSync(f)) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { "Content-Type": { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".wasm": "application/wasm", ".json": "application/json" }[path.extname(f)] || "application/octet-stream" });
    fs.createReadStream(f).pipe(res);
  }).listen(0);
  const base = "http://localhost:" + front.address().port;
  const browser = await chromium.launch(), page = await browser.newPage({ viewport: { width: 1360, height: 900 } }), errs = [];
  page.on("pageerror", e => errs.push(e.message));
  page.on("dialog", d => d.type() === "confirm" ? d.accept() : d.dismiss());
  const key = "quest-for-the-museum-full-msdos-quest-1991";
  const pub = () => page.evaluate(async u => (await fetch(u)).status, "/api/games/" + key);
  try {
    console.log("Statistics, as a visitor");
    const vctx = await browser.newContext({ viewport: { width: 1280, height: 800 },  // headless browsers count as robots
      userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36" }), v = await vctx.newPage();
    let gaRequests = 0;
    await vctx.route(/googletagmanager\.com/, r => { gaRequests++; r.fulfill({ status: 200, contentType: "text/javascript", body: "/* gtag stub */" }); });
    await vctx.route(/fonts\.(googleapis|gstatic)\.com/, r => r.fulfill({ status: 200, contentType: "text/css", body: "" }));
    v.on("pageerror", e => errs.push(e.message));
    await v.goto(base + "/es/");
    await v.waitForSelector(".pconsent");
    check(gaRequests === 0, "Google Analytics does not load before the visitor answers");
    await v.click('.pconsent [data-c="0"]');
    check(!(await v.$(".pconsent")), "declining closes the banner");
    await v.goto(base + "/es/timeline/");
    await v.waitForTimeout(300);
    check(!(await v.$(".pconsent")) && gaRequests === 0, "the answer is remembered and Google stays out");
    check(!(await vctx.cookies()).some(c => /^_ga/.test(c.name)), "no analytics cookies");
    await v.click("#consentOpen");
    await v.click('.pconsent [data-c="1"]');
    for (let i = 0; i < 20 && !gaRequests; i++) await v.waitForTimeout(100);
    check(gaRequests === 1 && await v.evaluate(() => JSON.stringify(window.dataLayer).includes('"analytics_storage":"granted"')),
      "accepting from the footer loads gtag.js with analytics consent granted (ads stay denied)");
    await v.click(".tl-entry");
    await v.waitForSelector("#modalBg.open");
    await v.waitForTimeout(1200);
    const beacon = v.waitForRequest(r => r.url().endsWith("/api/stats") && r.method() === "POST");
    await v.evaluate(() => { Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true }); document.dispatchEvent(new Event("visibilitychange")); });
    const sent = JSON.parse((await beacon).postData());
    check(sent.e.some(x => x.n === "timeline_open") && sent.e.some(x => x.n === "engage"), "the museum's own events go out in one beacon (record opened, time on the page)");
    check(!JSON.stringify(sent).includes("javi") && !(await vctx.cookies()).some(c => c.name.startsWith("pcm")), "the beacon carries no identifiers and sets no cookies");
    await v.waitForTimeout(300);
    await vctx.close();

    console.log("Access");
    await page.goto(base + "/admin/");
    check(await page.isVisible("#loginForm"), "asks for user and password");
    check(await page.evaluate(async () => (await fetch("/api/admin/catalog")).status) === 401, "the API refuses without a session");
    await page.fill("[name=user]", "javi"); await page.fill("[name=password]", "wrong"); await page.click("#loginForm button");
    await page.waitForSelector("#loginErr:not(:empty)");
    check(!(await page.isVisible("#app")), "a wrong password does not get in");
    await page.fill("[name=password]", "una-clave-larga-de-prueba"); await page.click("#loginForm button");
    await page.waitForSelector("#counts div");
    check((await page.textContent("#who")) === "javi", "logged in");
    check(!(await page.isVisible("#loginForm")) && await page.isVisible("#app"), "the login form goes away once logged in");
    const cookie = (await page.context().cookies()).find(c => c.name === "pcm_admin");
    check(cookie && cookie.httpOnly && cookie.sameSite === "Strict", "session cookie is HttpOnly and SameSite=Strict");
    check(await page.evaluate(async () => (await fetch("/api/admin/sync", { method: "POST", body: "{}" })).status) === 403, "a POST without the panel's header is refused");

    console.log("A commercial game: locate, test, validate, authorise");
    await page.click('[data-tab="games"]');
    await page.fill("#q", "quest for the museum");
    await page.click('#gameList li[data-id="quest-for-the-museum"]');
    check((await page.textContent("#detail .badge")).includes("Solo ficha"), "listed as record only");
    check(await pub() === 404, "the public proxy does not serve it");
    await page.click('#detail [data-act="test"]');
    await page.waitForTimeout(7000);
    await shot(page, "admin-player");
    check(!!(await page.$("#playerHost canvas")), "it runs in the panel's DOSBox before validating it");
    await page.click("#playerClose");
    check(await pub() === 404, "testing it did not publish it");
    await page.click('#detail [data-act="approve"]');
    await page.waitForFunction(() => document.querySelector("#detail h2 .badge").textContent.includes("Jugable"));
    check(true, "marked as available by you: playable, without needing the automatic check");
    for (let i = 0; i < 20 && await pub() !== 200; i++) await page.waitForTimeout(300);
    check(await pub() === 200, "now the public proxy serves it");
    await shot(page, "admin-detail");
    const ov = JSON.parse(fs.readFileSync(path.join(catDir, "catalog.admin.json"), "utf8"));
    const fix = ov["quest-for-the-museum"].editions[key];
    check(fix.approved === true && fix.rightsBy === "javi" && !!fix.rightsAt, "your decision is saved with who and when (catalog.admin.json)");
    await page.click('#detail [data-act="revert"]');
    await page.waitForFunction(() => document.querySelector("#detail h2 .badge").textContent.includes("Solo ficha"));
    for (let i = 0; i < 20 && await pub() !== 404; i++) await page.waitForTimeout(300);
    check(await pub() === 404, "withdrawn from the web: the proxy stops serving it");
    await page.click('#detail [data-act="validate"]');
    await page.waitForSelector("#detail .badge.playable");
    check((await page.textContent("#detail")).includes("DOSBox runs QUEST/QUEST.EXE"), "the automatic check is there to inform you: its steps are shown");
    await page.fill('#detail [data-form="rights"] [name=note]', "Autorizado");
    await page.selectOption('#detail [data-form="rights"] select', "permission");
    await page.click('#detail [data-form="rights"] button');
    await page.waitForFunction(() => document.querySelector("#detail h2 .badge").textContent.includes("Jugable"));
    check(true, "choosing permission in the rights form, without any link, also makes it available");

    console.log("Locate a game in Internet Archive: see what it holds, try it, then add it");
    await page.fill("#q", "lonely game");
    await page.click('#gameList li[data-id="lonely-game"]');
    await page.click("#iaForm button");
    await page.waitForSelector("[data-inspect]");
    check(await page.$('tr[data-ident="msdos_quest_1991"] a[href="https://archive.org/details/msdos_quest_1991"]') !== null, "each result links to its archive.org page");
    await page.click('[data-inspect="win_quest_1998"]');
    await page.waitForSelector('tr.inspect[data-for="win_quest_1998"] .zip');
    const win = await page.textContent('tr.inspect[data-for="win_quest_1998"]');
    check(/solo Windows/.test(win) && !(await page.$('tr.inspect[data-for="win_quest_1998"] [data-add]')), "a Windows-only item is spotted before adding it, and cannot be added");
    await page.click('[data-inspect="msdos_quest_1991"]');
    await page.waitForSelector('tr.inspect[data-for="msdos_quest_1991"] .zip');
    const zipSel = 'tr.inspect[data-for="msdos_quest_1991"] .zip[data-file="QUEST.ZIP"]';
    check(/DOS/.test(await page.textContent(zipSel)) && (await page.$eval(zipSel + " select", s => s.value)) === "QUEST/QUEST.EXE",
      "its zip has a DOS program, and the one that starts the game is suggested");
    check(/sin programa/.test(await page.textContent('tr.inspect[data-for="msdos_quest_1991"] .zip[data-file="QUEST_EXTRAS.ZIP"]')), "a zip with only an installer is flagged");
    await page.$eval('tr.inspect[data-for="msdos_quest_1991"]', el => el.scrollIntoView({ block: "center" }));
    await shot(page, "admin-inspect");
    await page.click(zipSel + " [data-try]");
    await page.waitForTimeout(6000);
    check(!!(await page.$("#playerHost canvas")), "tried in the panel's DOSBox before adding it");
    await page.click("#playerClose");
    check(!JSON.parse(fs.readFileSync(catFile, "utf8")).games.find(g => g.id === "lonely-game").editions.length, "trying it saved nothing");
    await page.click(zipSel + " [data-add]");
    await page.waitForSelector("#detail .edition");
    const added = JSON.parse(fs.readFileSync(catFile, "utf8")).games.find(g => g.id === "lonely-game").editions[0];
    check((await page.textContent("#detail .edition")).includes("msdos_quest_1991") && added.download.file === "QUEST.ZIP" && added.run.exe === "QUEST/QUEST.EXE",
      "added with the zip and the program that were tried");

    console.log("Remove an edition, and restore it");
    await page.click('#detail [data-act="delete"]');
    await page.waitForSelector("#detail [data-restore]");
    check(!(await page.$("#detail .edition")), "the edition is gone from the game");
    const ov2 = JSON.parse(fs.readFileSync(path.join(catDir, "catalog.admin.json"), "utf8"));
    check(Object.keys(ov2["lonely-game"].removedEditions || {}).length === 1, "remembered as removed, so that the daily sync does not bring it back");
    await page.click("#detail [data-restore]");
    await page.waitForSelector("#detail .edition");
    check(!(await page.$("#detail [data-restore]")), "restored");

    console.log("Statistics in the panel");
    await page.click('[data-tab="stats"]');
    await page.waitForSelector("#stats .counts");
    const st = await page.evaluate(async () => (await fetch("/api/admin/stats?days=7")).json());
    // a beacon sent while a page unloads leaves Chromium with its own headless user agent, so it counts as a robot
    const views = st.totals.pageviews + ((st.counters["web.bots"] || {}).page_view || 0);
    check(views === 2 && st.totals.pageviews >= 1 && st.totals.visitors === 1, "page views (" + views + ") and one unique visitor");
    check(st.counters["web.consent"] && st.counters["web.consent"].denied === 1 && st.counters["web.consent"].granted === 1, "the banner answers are counted");
    check(Object.keys(st.counters["web.timeline_open"] || {}).length === 1, "the record opened in the timeline");
    check(Object.keys(st.counters["games.requests"] || {}).includes(key), "the games proxy counts the games it served");
    check((await page.textContent("#stats")).includes("Salas"), "the tab shows the rooms visited");
    const files = fs.readdirSync(path.join(tmp, "stats"));
    check(files.length >= 1 && !files.some(f => fs.readFileSync(path.join(tmp, "stats", f), "utf8").includes("127.0.0.1")), "statistics are kept per day, without IP addresses");
    await shot(page, "admin-stats");

    console.log("Sync, sources, log");
    await page.click('[data-tab="summary"]');
    await page.click("#syncForm button");
    await page.waitForTimeout(500);
    const req = JSON.parse(fs.readFileSync(path.join(catDir, "sync.request.json"), "utf8"));
    check(req.validate === 20 && req.only.length === 3, "the sync request reaches the builder (sync.request.json)");
    await page.waitForTimeout(5500);
    await shot(page, "admin-summary");
    await page.click('[data-tab="downloads"]');
    check((await page.textContent("#downloads")).includes("quest-for-the-museum"), "the downloads are logged");
    await page.click('[data-tab="sources"]');
    check((await page.textContent("#sources")).includes("Internet Archive"), "the sources are listed");
    await page.click("#logout");
    await page.waitForSelector("#loginForm", { state: "visible" });
    check(!(await page.isVisible("#app")), "logging out shows only the login form");
    check(await page.evaluate(async () => (await fetch("/api/admin/catalog")).status) === 401, "logged out");
    check(errs.length === 0, "no JavaScript errors " + errs.join(" | "));
  } finally {
    await browser.close(); front.close(); games.kill(); sources.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  console.log(failures ? `\n${failures} failure(s)` : "\nAll control panel checks passed");
  process.exit(failures ? 1 : 0);
})();
