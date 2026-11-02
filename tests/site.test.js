/* Smoke tests for the generated site (dist/).
   Run:  python3 build.py && npm test
   Needs Playwright with Chromium (npm install && npx playwright install chromium). */
"use strict";
const http = require("http");
const fs = require("fs");
const path = require("path");
const { chromium, devices } = require("playwright");

const DIST = path.join(__dirname, "..", "dist");
const LANGS = ["es", "en", "de", "fr"];
const PAGES = ["", "timeline/", "studios/", "engines/", "techniques/", "games/", "games/text-adventure/",
  "games/restoration-room/", "games/pixel-hunt/", "games/chronology/", "arcade/"];
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".json": "application/json",
  ".wasm": "application/wasm", ".jsdos": "application/zip", ".xml": "application/xml", ".txt": "text/plain", ".webmanifest": "application/manifest+json" };
const SOLUTIONS = {
  es: ["e", "coger lampara", "o", "teclear 1976", "o", "encender lampara", "coger palanca", "coger disquete", "e", "abrir trampilla", "norte"],
  en: ["east", "take lamp", "west", "type 1976", "west", "light lamp", "take crowbar", "take floppy", "east", "open hatch", "north"],
  de: ["o", "nimm lampe", "w", "tippe 1976", "w", "zünde die lampe an", "nimm brechstange", "nimm diskette", "osten", "öffne falltür", "norden"],
  fr: ["est", "prendre la lampe", "ouest", "taper 1976", "ouest", "allumer la lampe", "prendre le pied de biche", "prendre disquette", "est", "ouvrir la trappe", "nord"],
};

let failures = 0;
const fail = msg => { failures++; console.log("  ✗ " + msg); };
const ok = msg => console.log("  ✓ " + msg);

function serve() {
  return new Promise(resolve => {
    const srv = http.createServer((req, res) => {
      let p = decodeURIComponent(req.url.split("?")[0]);
      if (p.endsWith("/")) p += "index.html";
      const f = path.join(DIST, p);
      if (!f.startsWith(DIST) || !fs.existsSync(f)) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { "Content-Type": TYPES[path.extname(f)] || "application/octet-stream" });
      fs.createReadStream(f).pipe(res);
    }).listen(0, () => resolve(srv));
  });
}

(async () => {
  if (!fs.existsSync(path.join(DIST, "index.html"))) { console.error("dist/ not found: run python3 build.py first"); process.exit(2); }
  const srv = await serve(), base = `http://localhost:${srv.address().port}`;
  const browser = await chromium.launch();

  console.log("Pages (desktop): errors, overflow, internal links");
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const links = new Set();
  for (const l of LANGS) for (const p of PAGES) {
    const page = await ctx.newPage(), errs = [];
    page.on("pageerror", e => errs.push(e.message));
    page.on("console", m => { if (m.type() === "error" && !/fonts\.g|net::/.test(m.text())) errs.push(m.text()); });
    const r = await page.goto(`${base}/${l}/${p}`);
    await page.waitForTimeout(150);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    if (r.status() !== 200 || errs.length || over > 0) fail(`${l}/${p} status=${r.status()} overflow=${over} ${errs.slice(0, 2).join(" | ")}`);
    (await page.$$eval("a[href]", as => as.map(a => a.href))).filter(h => h.startsWith(base)).forEach(h => links.add(h.split("#")[0]));
    await page.close();
  }
  for (const u of links) { const r = await ctx.request.get(u); if (r.status() !== 200) fail("broken link " + u); }
  ok(`${LANGS.length * PAGES.length} pages, ${links.size} internal links checked`);

  console.log("Mobile and tablet: no horizontal overflow");
  for (const dev of ["iPhone SE", "iPhone 13", "iPad Mini"]) {
    const c = await browser.newContext({ ...devices[dev] });
    for (const l of LANGS) for (const p of PAGES) {
      const page = await c.newPage(); await page.goto(`${base}/${l}/${p}`);
      const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      if (over > 0) fail(`${dev} ${l}/${p} overflows by ${over}px`);
      await page.close();
    }
    await c.close(); ok(dev);
  }

  console.log("Text adventure is solvable in every language");
  for (const l of LANGS) {
    const page = await ctx.newPage(); await page.goto(`${base}/${l}/games/text-adventure/`);
    for (const c of SOLUTIONS[l]) { await page.fill("#termIn", c); await page.press("#termIn", "Enter"); }
    /\*\*\*/.test(await page.textContent("#term")) ? ok(l) : fail(`text adventure not solved in ${l}`);
    await page.close();
  }

  console.log("Restoration room is solvable");
  {
    const page = await ctx.newPage(); await page.goto(`${base}/es/games/restoration-room/`);
    const cv = await page.$("#roomCanvas");
    const verb = i => page.click(`#verbs button >> nth=${i}`), inv = i => page.click(`#inv button >> nth=${i}`);
    const click = async (x, y) => {
      await page.evaluate(() => { document.documentElement.style.scrollBehavior = "auto"; document.querySelector("#roomCanvas").scrollIntoView({ block: "start" }); });
      const bb = await cv.boundingBox(); await page.mouse.click(bb.x + x / 320 * bb.width, bb.y + y / 150 * bb.height); await page.waitForTimeout(2800);
    };
    await verb(3); await click(59, 100);            // open drawer
    await verb(1); await click(220, 93);            // take remote
    await verb(3); await inv(1);                    // open remote
    await verb(2); await inv(1); await inv(0);      // batteries + flashlight
    await verb(2); await inv(0); await click(45, 35); // flashlight on vent
    await verb(1); await click(44, 40);             // take key
    await verb(2); await inv(1); await click(290, 80); // key on door
    const won = await page.evaluate(() => (JSON.parse(localStorage.getItem("pcm-awarded")) || []).includes("room:x"));
    won ? ok("door opened") : fail("restoration room not solved");
    await page.close();
  }

  console.log("DOSBox room boots the demo bundle");
  {
    const page = await ctx.newPage(); await page.goto(`${base}/es/arcade/`);
    await page.click(".dos-play"); await page.waitForTimeout(8000);
    (await page.$("#dosHost canvas")) ? ok("emulator canvas present") : fail("emulator did not start");
    await page.close();
  }

  console.log("Screen transitions between pages");
  {
    const page = await ctx.newPage(); const errs = [];
    page.on("pageerror", e => errs.push(e.message));
    await page.goto(`${base}/es/`);
    await page.click(".room-card >> nth=0");
    await page.waitForTimeout(250);
    (await page.$(".pcm-wipe.on")) ? ok("closing effect shown when leaving") : fail("no transition when leaving the page");
    await page.waitForURL(/\/es\/timeline\//);
    await page.waitForTimeout(1200);
    !(await page.$(".pcm-wipe.on")) && !(await page.evaluate(() => document.documentElement.classList.contains("pcm-wipe-in")))
      ? ok("next page opens and the overlay goes away") : fail("overlay stuck after arriving");
    errs.length ? fail("transition errors: " + errs.join(" | ")) : ok("no errors");
    await page.close();
    const rm = await browser.newPage({ reducedMotion: "reduce" });
    await rm.goto(`${base}/es/`);
    await rm.click(".room-card >> nth=1");
    await rm.waitForURL(/\/es\/studios\//, { timeout: 2000 }).then(() => ok("reduced motion: immediate navigation"), () => fail("reduced motion navigation"));
    await rm.close();
  }

  await browser.close(); srv.close();
  console.log(failures ? `\n${failures} failure(s)` : "\nAll checks passed");
  process.exit(failures ? 1 : 0);
})();
