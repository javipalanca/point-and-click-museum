/* Integration test of the ScummVM room without compiling ScummVM: builds the site with the fake
   ScummVM in tests/fixtures/fake-scummvm and checks what the player loads.
   Run: npm run test:scummvm */
"use strict";
const { execFileSync } = require("child_process");
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = path.join(__dirname, "..");
let failures = 0;
const check = (ok, msg) => { console.log((ok ? "  ✓ " : "  ✗ ") + msg); if (!ok) failures++; };

function serve(dir) {
  return new Promise(resolve => {
    const srv = http.createServer((req, res) => {
      let p = decodeURIComponent(req.url.split("?")[0].split("#")[0]);
      if (p.endsWith("/")) p += "index.html";
      const f = path.join(dir, p);
      if (!f.startsWith(dir) || !fs.existsSync(f)) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { "Content-Type": { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".wasm": "application/wasm" }[path.extname(f)] || "application/octet-stream" });
      fs.createReadStream(f).pipe(res);
    }).listen(0, () => resolve(srv));
  });
}

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "pcm-svm-"));
  // a ScummVM (SCUMM) game and a DOS game, as a visitor would upload them
  execFileSync("python3", ["-c", `
import zipfile, sys
with zipfile.ZipFile(sys.argv[1] + "/monkey.zip", "w") as z:
    z.writestr("MONKEY/MONKEY.000", "a"); z.writestr("MONKEY/MONKEY.001", "b")
paint = open(sys.argv[2], "rb").read()
with zipfile.ZipFile(sys.argv[1] + "/dosgame.zip", "w") as z:
    z.writestr("GAME/GAME.EXE", paint); z.writestr("GAME/INSTALL.EXE", b"x")
`, tmp, path.join(ROOT, "tools/dos/PAINT.COM")]);
  const browser = await chromium.launch();
  for (const inline of [false, true]) {
    console.log(inline ? "Inline packs (--inline-bundles)" : "Plain files");
    const out = path.join(tmp, inline ? "inline" : "plain");
    execFileSync("python3", [path.join(ROOT, "build.py"), "--out", out, "--no-local", ...(inline ? ["--inline-bundles"] : [])],
      { env: { ...process.env, PCM_SCUMMVM_VENDOR: path.join(__dirname, "fixtures/fake-scummvm") }, stdio: "ignore" });
    const srv = await serve(out), base = `http://localhost:${srv.address().port}`;
    const page = await browser.newPage(); const errs = [];
    page.on("pageerror", e => errs.push(e.message));
    await page.goto(base + "/es/arcade/");
    check(!(await page.$('.dos-game[data-id="beneath-a-steel-sky"]')), "a freeware without its files is not on the shelf (only what can be played)");
    await page.click(".byo-wrap summary");
    await page.setInputFiles("#byoFile", path.join(tmp, "monkey.zip"));
    await page.click("#byoForm button[type=submit]");
    await page.waitForTimeout(1500);
    const frame = page.frames().find(f => f.url().includes("player.html"));
    const r = frame && await frame.evaluate(() => window.FAKE_RESULT);
    check(r && r.args.join(" ") === "--path=/games/byo --auto-detect", "ScummVM gets --path and --auto-detect");
    check(r && r.files.includes("/games/byo/MONKEY.000") && !r.files.some(f => f.includes("/MONKEY/")), "game files copied without their folder");
    check(r && r.files.includes("/data/plugins/libscumm.so") && r.files.includes("/data/plugins/libdetection.so") && !r.files.includes("/data/plugins/libsky.so"),
      "only the detection plugin and the game's engine are loaded");
    check(r && r.files.includes("/home/web_user/scummvm.ini"), "scummvm.ini written");
    const gain = () => frame.evaluate(() => { const c = window.PCM_TEST_CTX || (window.PCM_TEST_CTX = new AudioContext());
      if (!c.pcmMaster) c.createOscillator().connect(c.destination); return c.pcmMaster && c.pcmMaster.gain.value; });
    check(frame && Math.abs(await gain() - 0.8) < 0.01, "ScummVM's sound goes through the volume control (80% by default)");
    await page.locator("#dosVol").fill("0.3");
    check(frame && Math.abs(await gain() - 0.3) < 0.01 && (await page.textContent("#dosVolOut")) === "30%", "the volume slider changes ScummVM's volume");
    check(await page.isHidden("#dosMouse"), "DOSBox mouse controls hidden for ScummVM");
    await page.click("#dosStop");   // back to the room, then the next game
    await page.setInputFiles("#byoFile", path.join(tmp, "dosgame.zip"));
    await page.click("#byoForm button[type=submit]");
    await page.waitForTimeout(6000);
    check(!!(await page.$("#dosHost canvas")) && !(await page.$(".svm-frame")), "a DOS zip without executable is detected and runs in DOSBox");
    await page.locator("#dosVol").fill("0.6");
    await page.waitForTimeout(300);
    check(await page.evaluate(() => Object.entries(localStorage).some(([k, v]) => /^jsdos.*volume$/.test(k) && +v === 0.6)),
      "the volume slider sets js-dos's volume");
    check(errs.length === 0, "no JavaScript errors " + errs.join(" | "));
    await page.close(); srv.close();
  }
  await browser.close();
  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(failures ? `\n${failures} failure(s)` : "\nAll ScummVM checks passed");
  process.exit(failures ? 1 : 0);
})();
