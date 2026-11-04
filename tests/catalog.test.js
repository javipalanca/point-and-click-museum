/* End-to-end test of the automatic catalogue: timeline "Play in the museum" -> DOSBox room -> the download proxy
   (server/games.py) brings the game from a fake source -> ScummVM (fake build) or DOSBox runs it; the browser keeps
   the download in Cache Storage and ScummVM's saved games in IndexedDB.
   Run: npm run test:catalog */
"use strict";
const { execFileSync, spawn } = require("child_process");
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = path.join(__dirname, "..");
let failures = 0;
const check = (ok, msg) => { console.log((ok ? "  ✓ " : "  ✗ ") + msg); if (!ok) failures++; };
const firstLine = proc => new Promise((resolve, reject) => {
  proc.stdout.once("data", d => resolve(String(d).trim().split("\n")[0]));
  proc.once("exit", c => reject(new Error("exited " + c)));
});

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "pcm-cat-"));
  const sources = spawn("python3", [path.join(__dirname, "fixtures/fake_sources.py")]);
  const src = "http://127.0.0.1:" + await firstLine(sources);
  // a catalogue with two playable games (as tools/sync_catalog.py writes it after validating them)
  const catalog = JSON.parse(fs.readFileSync(path.join(ROOT, "data/catalog.json"), "utf8"));
  const ok = { ok: true, at: "2026-11-05T00:00:00Z", checks: ["test"] };
  const bass = catalog.games.find(g => g.id === "beneath-a-steel-sky");
  bass.status = "playable"; bass.gog = "https://www.gog.com/en/game/beneath_a_steel_sky";
  bass.editions = [{ key: "bass-test", kind: "full", rights: "freeware", emulator: "scummvm", run: { svmEngine: "sky" }, status: "playable",
    edition: "Freeware CD Version", validated: ok, download: { provider: "scummvm", url: src + "/frs/extras/sky.zip" } }];
  catalog.games.push({ id: "pixel-cave", title: "Pixel Cave", year: 2026, developer: "Museum", status: "playable", editions: [
    { key: "pixel-cave-test", kind: "full", rights: "shareware", emulator: "dosbox", run: { exe: "CAVE/CAVE.COM" }, status: "playable",
      edition: "Test", validated: ok, download: { provider: "archive", url: src + "/download/pixelcave/CAVE.ZIP" } }] });
  const catFile = path.join(tmp, "catalog.json");
  fs.writeFileSync(catFile, JSON.stringify(catalog));
  const out = path.join(tmp, "site");
  execFileSync("python3", [path.join(ROOT, "build.py"), "--out", out, "--no-local"],
    { env: { ...process.env, PCM_CATALOG: catFile, PCM_SCUMMVM_VENDOR: path.join(__dirname, "fixtures/fake-scummvm") }, stdio: "ignore" });
  // the download proxy, and a front server like nginx (static files + /api/games/)
  const games = spawn("python3", [path.join(ROOT, "server/games.py")], {
    env: { ...process.env, GAMES_PORT: "0", PCM_CATALOG: catFile, GAMES_CACHE: path.join(tmp, "proxy"), PCM_GAMES_TEST_HOSTS: "127.0.0.1" } });
  let gamesPort = null;
  games.stderr.on("data", d => { const m = /games proxy on :(\d+)/.exec(String(d)); if (m) gamesPort = +m[1]; });
  for (let i = 0; i < 50 && !gamesPort; i++) await new Promise(r => setTimeout(r, 100));
  let proxied = 0;
  const front = http.createServer((req, res) => {
    if (req.url.startsWith("/api/games/")) {
      proxied++;
      http.get({ port: gamesPort, path: req.url, headers: req.headers }, r => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
      return;
    }
    let p = decodeURIComponent(req.url.split("?")[0].split("#")[0]);
    if (p.endsWith("/")) p += "index.html";
    const f = path.join(out, p);
    if (!f.startsWith(out) || !fs.existsSync(f)) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { "Content-Type": { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".wasm": "application/wasm", ".png": "image/png" }[path.extname(f)] || "application/octet-stream" });
    fs.createReadStream(f).pipe(res);
  }).listen(0);
  const base = "http://localhost:" + front.address().port;

  const browser = await chromium.launch(), ctx = await browser.newContext(), page = await ctx.newPage(), errs = [];
  page.on("pageerror", e => errs.push(e.message));
  try {
    console.log("Timeline -> museum");
    await page.goto(base + "/es/timeline/#beneath-a-steel-sky");
    await page.waitForSelector(".m-actions");
    check(await page.locator('.m-actions a[href*="gog.com"]').count() === 1, "the record links to GOG");
    check(await page.locator(".tl-play").count() >= 1, "playable games are marked on the timeline");
    await page.click(".m-actions .pbtn");
    await page.waitForURL(/arcade\/#play=beneath-a-steel-sky/);
    await page.waitForTimeout(2500);
    let frame = page.frames().find(f => f.url().includes("player.html"));
    let r = frame && await frame.evaluate(() => window.FAKE_RESULT);
    check(r && r.files.includes("/games/beneath-a-steel-sky/sky.dnr"), "the proxy brought the game and ScummVM got its files (without their folder)");
    check(proxied === 1, "downloaded once through /api/games/");
    check(await page.evaluate(async () => !!(await (await caches.open("pcm-games-v1")).match("/api/games/bass-test"))), "kept in the browser's cache");

    console.log("Saved games");
    await frame.evaluate(() => FS.writeFile("/home/web_user/saves/sky.001", new Uint8Array([1, 2, 3])));
    await page.waitForTimeout(5800);
    await page.reload(); await page.waitForTimeout(2500);
    frame = page.frames().find(f => f.url().includes("player.html"));
    r = frame && await frame.evaluate(() => window.FAKE_RESULT);
    check(r && r.files.includes("/home/web_user/saves/sky.001"), "a saved game comes back on the next visit (IndexedDB)");
    check(proxied === 1, "the second time it comes from the browser's cache, not the server");

    console.log("DOSBox");
    await page.click('.dos-game[data-id="pixel-cave"] .dos-play');
    await page.waitForTimeout(6000);
    check(!!(await page.$("#dosHost canvas")) && !(await page.$(".svm-frame")), "a DOS game of the catalogue runs in DOSBox");
    for (const bad of ["cave", "../../etc/passwd", "monkey-island-demo-monkey1-dos-ega-demo-en"]) {
      const code = await page.evaluate(async u => (await fetch(u)).status, "/api/games/" + bad);
      check(code === 404, "the proxy refuses what is not playable: " + bad);
    }
    check(errs.length === 0, "no JavaScript errors " + errs.join(" | "));
  } finally {
    await browser.close(); front.close(); games.kill(); sources.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  console.log(failures ? `\n${failures} failure(s)` : "\nAll catalogue checks passed");
  process.exit(failures ? 1 : 0);
})();
