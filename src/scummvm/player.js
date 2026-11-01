/* Point and Click Museum · ScummVM web player.
   Runs inside an <iframe> of the DOSBox/ScummVM room. The parent page sets window.PCM_SVM_JOB:
     { gameId, engine, files: ["sky.dnr", ...], gameBase: "games/<id>/", data: ["modern.zip", "plugins/libsky.so", ...],
       inline: false, args: ["--path=/games/<id>", "--auto-detect"] }
   Files are copied into Emscripten's in-memory file system before ScummVM starts:
     /data/...         themes, engine data and plugins (DATA_PATH, see tools/build_scummvm.sh)
     /games/<id>/...   the game data
   With inline packs (hosts that refuse binary files), each file comes as "<path>.pack.js", a script that calls
   PCM_SVM_FILE(path, base64). */
"use strict";
(function () {
  const statusEl = document.getElementById("status");
  const job = (window.parent && window.parent.PCM_SVM_JOB) || null;
  const say = (text, error) => { statusEl.textContent = text || ""; statusEl.classList.toggle("error", !!error); };
  if (!job) { say("No game selected.", true); return; }

  const packs = {};
  window.PCM_SVM_FILE = (path, b64) => { const r = packs[path]; if (r) r(b64); };
  function viaScript(path) {
    return new Promise((resolve, reject) => {
      packs[path] = b64 => {
        delete packs[path];
        const bin = atob(b64), out = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
        resolve(out);
      };
      const s = document.createElement("script");
      s.src = path + ".pack.js"; s.onerror = () => reject(new Error("missing " + path)); s.onload = () => s.remove();
      document.head.appendChild(s);
    });
  }
  async function viaFetch(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(path + ": HTTP " + r.status);
    return new Uint8Array(await r.arrayBuffer());
  }
  const load = job.inline ? viaScript : viaFetch;

  /* only the plugins this game needs: the shared detection plugin and the engine itself */
  function wanted(path) {
    if (!/^plugins\//.test(path)) return true;
    if (!job.engine) return true;
    const base = path.split("/").pop().replace(/^lib/, "").replace(/\.so$/, "");
    const family = { scumm: ["scumm", "scumm_7_8"], sci: ["sci", "sci32"] }[job.engine] || [job.engine];
    return base === "detection" || family.includes(base);
  }

  async function populate() {
    const data = job.data.filter(wanted);
    const total = data.length + job.files.length;
    let done = 0;
    const put = (dest, bytes) => {
      FS.mkdirTree(dest.slice(0, dest.lastIndexOf("/")) || "/");
      FS.writeFile(dest, bytes);
      say("Loading " + (++done) + "/" + total + "…");
    };
    const mem = job.memFiles || null;   // "bring your own game": files already unzipped by the parent page
    const queue = data.map(p => ["/data/" + p, "data/" + p, false]).concat(job.files.map(p => ["/games/" + job.gameId + "/" + p, job.gameBase + p, !!mem]));
    // a few downloads at a time
    let next = 0;
    async function worker() {
      while (next < queue.length) {
        const [dest, src, inMemory] = queue[next++];
        put(dest, inMemory ? mem[dest.slice(("/games/" + job.gameId + "/").length)] : await load(src));
      }
    }
    await Promise.all([worker(), worker(), worker(), worker()]);
    FS.mkdirTree("/home/web_user/saves");
    FS.writeFile("/home/web_user/scummvm.ini",
      "[scummvm]\nextrapath=/data\nthemepath=/data\npluginspath=/data/plugins\nsavepath=/home/web_user/saves\n" +
      "gui_theme=scummmodern\nfullscreen=false\naspect_ratio=true\nfiltering=false\n");
    say("");
  }

  window.Module = {
    canvas: document.getElementById("canvas"),
    print: t => console.log("[scummvm]", t),
    printErr: t => console.warn("[scummvm]", t),
    setStatus: t => { if (t && !/^Running/.test(t)) say(t); },
    preRun: [() => {
      addRunDependency("pcm-files");
      populate().then(() => removeRunDependency("pcm-files"))
        .catch(e => { say("Could not load the game: " + e.message, true); console.error(e); });
    }],
    onAbort: what => say("ScummVM stopped: " + what, true),
  };
  // custom_shell-pre.js (compiled into scummvm.js) reads the command line from the URL fragment
  if (!location.hash) location.hash = encodeURI(job.args.join(" "));
  const s = document.createElement("script");
  s.src = "scummvm.js";
  s.onerror = () => say("ScummVM is not installed. Run tools/build_scummvm.sh and rebuild the site.", true);
  document.body.appendChild(s);
  window.addEventListener("message", e => { if (e.data === "pcm-focus") Module.canvas.focus(); });
})();
