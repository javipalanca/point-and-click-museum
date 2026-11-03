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
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".svg": "image/svg+xml", ".gif": "image/gif", ".jpg": "image/jpeg", ".json": "application/json",
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

  console.log("Timeline and rooms: real images with their sources");
  {
    const page = await ctx.newPage();
    await page.goto(`${base}/es/timeline/`);
    const covers = await page.$$eval(".tl-cover", im => im.map(i => i.getAttribute("src")));
    covers.length >= 20 ? ok(`${covers.length} real covers on the timeline`) : fail(`only ${covers.length} covers`);
    for (const c of covers) { const r = await ctx.request.get(new URL(c, `${base}/es/timeline/`).href); if (r.status() !== 200) fail("missing cover " + c); }
    (await page.$$(".tl-sign")).length === 6 ? ok("one sign per era") : fail("era signs");
    await page.click("#monkey-island .tl-entry");
    const cap = await page.$$eval(".pmodal figcaption a", as => as.map(a => a.href));
    cap.some(h => /github\.com\/libretro-thumbnails\//.test(h)) ? ok("record credits the exact image file") : fail("no image credit in the record: " + cap);
    const loaded = await page.$eval(".pmodal .sheet-cover img", i => i.decode().then(() => i.naturalWidth > 0, () => false));
    loaded ? ok("cover loads in the record") : fail("cover did not load");
    await page.goto(`${base}/en/engines/`);
    const logo = await page.$eval(".cart img.logo", i => i.decode().then(() => i.naturalWidth > 0, () => false)).catch(() => false);
    logo ? ok("engine logo loads") : fail("engine logo");
    await page.goto(`${base}/en/techniques/`);
    await page.click("#uiTabs [role=tab] >> nth=1");  // Maniac Mansion verbs
    const at = async (x, y) => { const r = await (await page.$("#uiCanvas")).boundingBox(); return [r.x + x * r.width / 256, r.y + y * r.height / 128]; };
    await page.evaluate(() => document.getElementById("uiStage").scrollIntoView({ block: "center", behavior: "instant" }));
    await page.click('#uiVerbs [data-verb="Pick up"]'); await page.mouse.click(...await at(178, 106));
    await page.waitForSelector('#uiInv [data-item="key"]', { timeout: 6000 }).then(() => ok("lab: Pick up key"), () => fail("lab: key not picked up"));
    await page.click('#uiVerbs [data-verb="Unlock"]'); await page.mouse.click(...await at(38, 70)); await page.click('#uiInv [data-item="key"]');
    await page.waitForTimeout(4000);
    await page.click('#uiVerbs [data-verb="Open"]'); await page.mouse.click(...await at(38, 70));
    const opened = await page.waitForFunction(() => /creaks open/.test(document.getElementById("uiSay").textContent), null, { timeout: 6000 }).then(() => true, () => false);
    opened ? ok("lab: Unlock door with key, then Open door") : fail("lab: door did not open");
    await page.click("#uiTabs [role=tab] >> nth=5");  // verb coin: hold over the curator, release on the parrot
    await page.evaluate(() => document.getElementById("uiStage").scrollIntoView({ block: "center", behavior: "instant" })); await page.waitForTimeout(100);
    const [cx, cy] = await at(223, 95); await page.mouse.move(cx, cy); await page.mouse.down(); await page.waitForTimeout(450);
    const [px, py] = await at(Math.min(223, 256 - 40) + 16, Math.max(28, Math.min(128 - 28, 95))); await page.mouse.move(px, py); await page.mouse.up();
    const talked = await page.waitForFunction(() => /locked for years/.test(document.getElementById("uiSay").textContent), null, { timeout: 6000 }).then(() => true, () => false);
    talked ? ok("lab: verb coin parrot talks to the curator") : fail("lab: verb coin");
    // Murray: chat widget on every page, talking to /api/murray/chat (mocked here)
    let asked = null;
    await page.route("**/api/murray/chat", async route => {
      asked = JSON.parse(route.request().postData());
      const ev = o => "data: " + JSON.stringify(o) + "\n\n";
      await route.fulfill({ headers: { "Content-Type": "text/event-stream" },
        body: ev({ delta: "¡Tiembla, " }) + ev({ delta: "mortal! SCUMM." }) + ev({ done: true, sources: [{ title: "SCUMM", url: "engines/" }], mode: "llm" }) });
    });
    await page.goto(`${base}/es/engines/`);
    await page.click("#murrayFab");
    (await page.isVisible("#murrayPanel")) ? ok("Murray: the button opens the chat") : fail("Murray panel");
    await page.fill("#murrayIn", "¿Qué es SCUMM?"); await page.press("#murrayIn", "Enter");
    const answered = await page.waitForFunction(() => /Tiembla/.test(document.getElementById("murrayLog").textContent), null, { timeout: 5000 }).then(() => true, () => false);
    const full = await page.$eval("#murrayLog li:last-child", li => li.textContent);
    answered && asked && asked.stream === true && asked.lang === "es" && asked.messages.at(-1).content === "¿Qué es SCUMM?" && /Tiembla, mortal! SCUMM\./.test(full) && /SCUMM/.test(full)
      ? ok("Murray: question sent, streamed answer and sources shown") : fail("Murray chat: " + full);
    await page.goto(`${base}/en/timeline/`);
    const kept = await page.$$eval("#murrayLog li", l => l.length);
    kept >= 3 ? ok("Murray: conversation follows the visitor between rooms") : fail("Murray conversation lost: " + kept);
    await page.keyboard.press("Escape"); await page.focus("#murrayIn").catch(() => {});
    await page.unroute("**/api/murray/chat");
    const js = fs.readdirSync(path.join(DIST, "js")).map(f => fs.readFileSync(path.join(DIST, "js", f), "utf8")).join("\n");
    /MURRAY_LLM|api_key|Authorization|sk-[A-Za-z0-9]/.test(js) ? fail("model configuration found in public JS") : ok("no model URL or key in the public JS");
    await page.goto(`${base}/de/studios/`);
    (await page.$$(".studio .logo, .studio .monogram")).length === 12 ? ok("every studio has a logo or a monogram") : fail("studio marks");
    await page.close();
  }

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

  console.log("Navigation: doors, games submenu, museum map, in-this-room strip");
  {
    const page = await ctx.newPage(); const errs = [];
    page.on("pageerror", e => errs.push(e.message));
    await page.goto(`${base}/es/techniques/`);
    (await page.getAttribute(".door.here .door-link", "aria-current")) === "page" ? ok("current room's door is lit") : fail("no current door");
    await page.click(".sub-toggle");
    (await page.isVisible("#sub-games a")) ? ok("games submenu opens with its button") : fail("games submenu");
    await page.keyboard.press("Escape");
    await page.mouse.move(5, 700);   // on desktop the submenu also opens on hover
    (await page.isHidden("#sub-games")) ? ok("Escape closes the submenu") : fail("submenu stays open");
    await page.click('.subnav a[href="#tech-music"]');
    await page.waitForTimeout(900);
    (await page.getAttribute('.subnav a[href="#tech-music"]', "aria-current")) === "true" ? ok("strip highlights the section in view") : fail("subnav scroll-spy");
    await page.click("#mapBtn");
    (await page.isVisible("#mapPanel")) ? ok("map opens") : fail("map does not open");
    (await page.textContent(".plan-room.here .plan-room-name")).length ? ok("map shows where you are") : fail("no here marker");
    /\d/.test(await page.textContent("#mapVisited")) ? ok("map counts visited rooms") : fail("visited count");
    await page.keyboard.press("Escape");
    (await page.isHidden("#mapPanel")) ? ok("Escape closes the map") : fail("map stays open");
    errs.length ? fail("navigation errors: " + errs.join(" | ")) : ok("no errors");
    await page.close();
    const phone = await (await browser.newContext({ ...devices["iPhone SE"] })).newPage();
    await phone.goto(`${base}/fr/timeline/`);
    (await phone.isHidden(".doors")) && (await phone.isVisible("#mapBtn")) ? ok("phones: doors move into the map") : fail("phone header");
    await phone.click("#mapBtn");
    (await phone.isVisible('.map-settings [data-toggle="sound"]')) ? ok("phones: settings inside the map") : fail("phone map settings");
    await phone.close();
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
