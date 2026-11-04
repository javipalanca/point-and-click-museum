/* End-to-end test of the control panel (server/admin.py): login, catalogue, Internet Archive search, testing a game
   in DOSBox, marking it as available (and withdrawing it), validating it; and that the public proxy only serves it then.
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
  execFileSync("python3", [path.join(ROOT, "build.py"), "--out", out, "--no-local"], { env: { ...process.env, PCM_CATALOG: catFile }, stdio: "ignore" });
  const games = spawn("python3", [path.join(ROOT, "server/games.py")], { env: { ...process.env, GAMES_PORT: "0", PCM_CATALOG: catFile,
    GAMES_CACHE: path.join(tmp, "cache"), PCM_GAMES_TEST_HOSTS: "127.0.0.1", PCM_IA_BASE: src, ADMIN_USER: "javi", ADMIN_PASSWORD: "una-clave-larga-de-prueba" } });
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
  page.on("dialog", d => d.dismiss());
  const key = "quest-for-the-museum-full-msdos-quest-1991";
  const pub = () => page.evaluate(async u => (await fetch(u)).status, "/api/games/" + key);
  try {
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

    console.log("Locate a game in Internet Archive");
    await page.fill("#q", "lonely game");
    await page.click('#gameList li[data-id="lonely-game"]');
    await page.click("#iaForm button");
    await page.waitForSelector("[data-attach]");
    await page.click("[data-attach]");
    await page.waitForSelector("#detail .edition");
    check((await page.textContent("#detail .edition")).includes("msdos_quest_1991"), "an Internet Archive item attached to a game");

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
