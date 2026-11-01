// Fake ScummVM used by tests/scummvm.test.js: mimics the globals of the Emscripten build (FS, run dependencies,
// arguments from the URL fragment) and records which files the player copied into the virtual file system.
Module.arguments = decodeURI(location.hash.slice(1)).split(" ");
var FILES = {};
var FS = { mkdirTree() {}, writeFile(p, d) { FILES[p] = d.length; } };
var deps = 0;
function addRunDependency() { deps++; }
function removeRunDependency() { if (--deps === 0) main(); }
function main() {
  window.FAKE_RESULT = { args: Module.arguments, files: Object.keys(FILES).sort() };
  const c = Module.canvas.getContext("2d"); c.fillStyle = "#4fd6c8"; c.fillRect(0, 0, 50, 50);
}
(Module.preRun || []).forEach(f => f());
if (deps === 0) main();
