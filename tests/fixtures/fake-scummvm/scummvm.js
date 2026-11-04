// Fake ScummVM used by tests/scummvm.test.js: mimics the globals of the Emscripten build (FS, run dependencies,
// arguments from the URL fragment) and records which files the player copied into the virtual file system.
Module.arguments = decodeURI(location.hash.slice(1)).split(" ");
var FILES = {};
var DATA = {};  // a tiny in-memory file system: enough for the player's saved-games code
var FS = {
  mkdirTree() {},
  writeFile(p, d) { FILES[p] = d.length; DATA[p] = { d: d instanceof Uint8Array ? d : new TextEncoder().encode(String(d)), t: Date.now() }; },
  readFile(p) { return DATA[p].d; },
  stat(p) { return { size: DATA[p].d.length, mtime: DATA[p].t }; },
  readdir(dir) { return [".", ".."].concat(Object.keys(DATA).filter(p => p.startsWith(dir + "/")).map(p => p.slice(dir.length + 1)).filter(n => !n.includes("/"))); },
};
var deps = 0;
function addRunDependency() { deps++; }
function removeRunDependency() { if (--deps === 0) main(); }
function main() {
  window.FAKE_RESULT = { args: Module.arguments, files: Object.keys(FILES).sort() };
  const c = Module.canvas.getContext("2d"); c.fillStyle = "#4fd6c8"; c.fillRect(0, 0, 50, 50);
}
(Module.preRun || []).forEach(f => f());
if (deps === 0) main();
