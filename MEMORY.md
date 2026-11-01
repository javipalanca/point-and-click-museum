# MEMORY.md · decisiones y estado del proyecto

Memoria de trabajo compartida entre personas y agentes. Añade entradas al final de cada sección con fecha
(AAAA-MM-DD). No borres decisiones antiguas: márcalas como «sustituida por…».

## Estado actual (2026-11-01)

- 11 páginas × 4 idiomas = 44 páginas: portada, línea temporal (41 juegos), estudios (12), motores (11),
  técnicas, minijuegos (índice + 4 juegos) y sala DOSBox.
- Publicado como Artifact privado de claude.ai: https://claude.ai/artifact/RSUfNBGmo8D3XLvqDvXbjY
  (se regenera con `tools/export_artifact.py`).
- `baseUrl` en `data/site.json` es un valor provisional (`https://pointandclick.museum`): cámbialo al dominio real
  antes de publicar en producción (afecta a canonical, hreflang, Open Graph y sitemap).

## Decisiones

- **2026-11-01 · Generador propio en Python sin dependencias.** El usuario programa en Python; evitamos Node como
  requisito para construir. Node solo se usa para las pruebas (Playwright).
- **2026-11-01 · Datos incrustados en cada página** (`<script id="pcm-data">`) en vez de `fetch`: funciona desde
  `file://`, en el Artifact (CSP estricta) y sin servidor. Cada página incluye solo los datos que declara en `site.json → pages[].data`.
- **2026-11-01 · Multipágina en lugar de una sola página larga** (petición del usuario: «hazla navegable»).
  Rutas neutras en inglés (`/es/timeline/`) para todos los idiomas.
- **2026-11-01 · Línea temporal agrupada por épocas en cuadrícula**, sustituyendo al pasillo con scroll horizontal.
- **2026-11-01 · Personajes híbridos:** cabeza y torso dibujados a mano (16 px de ancho) + piernas procedurales para
  un ciclo de paso fluido. Sustituye a los personajes hechos con rectángulos.
- **2026-11-01 · Caza del píxel procedural:** desván distinto en cada ronda, oscuridad creciente y linterna en la última.
- **2026-11-01 · Ratón de DOSBox capturado por defecto** (pointer lock, como `autolock=true`): los juegos DOS leen
  movimiento relativo y el modo directo de js-dos no es fiable. Si el navegador rechaza el pointer lock
  (iframes), se cambia solo a modo directo (`pointerlockerror`). El usuario puede alternar con un botón.
- **2026-11-01 · Prefijos `.pbtn/.pmodal/.ptoast`** porque la CSS de js-dos (daisyUI) pisaba `.btn`, `.modal`, `.toast`.
- **2026-11-01 · Sin juegos comerciales.** La sala DOSBox incluye solo `MUSEUM.COM` y `PAINT.COM` (propios, CC0).
  Los freeware listados (Beneath a Steel Sky, Flight of the Amazon Queen, Drascula, Lure of the Temptress) se
  distribuyen oficialmente para ScummVM; para DOSBox hace falta la versión DOS original con su ejecutable.
- **2026-11-01 · `--inline-bundles`** porque el host de Artifacts no sirve `.zip`/`.jsdos`.
- **2026-11-01 · Colección local de juegos fuera de git.** `tools/add_game.py` convierte zips descargados en bundles
  (`assets/games/`) y los registra en `data/arcade.local.json`; ambos ignorados. `build.py` los mezcla salvo con
  `--no-local` (usado por `export_artifact.py`) y no copia a `dist/` bundles que no estén en el catálogo.
- **2026-11-01 · ScummVM web para los juegos sin ejecutable DOS.** Se usa el port oficial de Emscripten de
  ScummVM 2.9.1 (`dists/emscripten`), compilado con `tools/build_scummvm.sh` (`--datadir=/data`, plugins dinámicos,
  motores scumm, agi, sci, sky, queen, lure, drascula, dreamweb, teenagent, cge y ags). Reproductor propio
  (`src/scummvm/player.js`) en un iframe en lugar del shell oficial: copia a MEMFS `/data` y `/games/<id>` antes de
  arrancar y lanza con `--path=/games/<id> --auto-detect` vía el fragmento de la URL (lo lee `custom_shell-pre.js`).
  Solo carga `libdetection.so` y el plugin del motor del juego. `vendor/scummvm/` no se versiona.
- **2026-11-01 · `add_game.py` elige motor:** ScummVM si reconoce los datos (firmas de ficheros por motor, juegos AGS
  dentro de un `.exe` de Windows), DOSBox si hay programa DOS (descarta ejecutables PE de Windows). Si ScummVM no está
  compilado y hay `.exe` DOS, usa DOSBox. Los zips oficiales de los freeware rellenan su ficha de `arcade.json`.
- **2026-11-01 · Catálogo de la sala DOSBox** con buscador, filtro por compañía, índice A–Z (sin artículos iniciales)
  y orden por título/año, visible a partir de 8 juegos (`arcade.json → catalogue.filtersFrom`); tarjetas compactas.

## Datos técnicos útiles

- js-dos 8.3.20: `Dos(elemento, opciones)` devuelve un objeto con `stop()`, `setMouseCapture(bool)`,
  `setMouseSensitivity(n)`… Opciones usadas: `url` o `dosboxConf` + `initFs` (Uint8Array de un zip), `pathPrefix`,
  `mouseCapture`, `onEvent`. Lee `autolock=true` del `dosbox.conf` para activar la captura.
- Un `.jsdos` es un zip con `.jsdos/dosbox.conf` y `.jsdos/jsdos.json` (`{"version":"js-dos-v8"}`).
- Artifact de claude.ai: no sirve directorios (usar `--link-style file`), envuelve el `index.html` raíz en su propio
  esqueleto, admite `.wasm`, `.js`, `.png`, `.xml`, `.txt`, `.webmanifest` pero no `.zip`.

## Pendiente / ideas

- Verificar los enlaces externos (Wikipedia y webs oficiales): no se pudieron comprobar desde el entorno en la nube.
- Probar la captura del ratón con un juego DOS real en un navegador de escritorio.
- **Compilar ScummVM de verdad** (`tools/build_scummvm.sh`) y probar los freeware: en la sesión en la nube se bloqueó la
  ejecución del script oficial (descarga y ejecuta Emscripten). La integración está probada con un ScummVM simulado;
  pueden hacer falta ajustes (nombres de plugins, rutas) con el build real.
- Guardar partidas de ScummVM entre visitas (hoy van a MEMFS y se pierden al cerrar; habría que enlazar IDBFS).
- Los freeware de ScummVM se pueden redistribuir: valorar versionarlos (excepción en `.gitignore`) una vez probados.
- Posibles mejoras: slugs localizados en las URLs, más estudios (Microïds, Cryo, Coktel Vision),
  modo de alto contraste.

## Historial

- 2026-11-01 · v1: página única con línea temporal, estudios, motores, técnicas y 4 minijuegos.
- 2026-11-01 · v2: datos en JSON, 4 idiomas, SEO, generador Python, sala DOSBox.
- 2026-11-01 · v3: multipágina, personajes y escenas de más calidad, enlaces externos, ratón de DOSBox revisado.
- 2026-11-01 · v4: repositorio git, AGENTS.md, MEMORY.md, skills y pruebas automatizadas (`npm test`).
- 2026-11-01 · v5: `tools/add_game.py` para añadir juegos desde zips, colección local ignorada por git y catálogo con filtros.
- 2026-11-01 · v6: soporte de ScummVM web (script de compilación, reproductor, detección de motor, freeware en el catálogo).
