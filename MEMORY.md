# MEMORY.md · decisiones y estado del proyecto

Memoria de trabajo compartida entre personas y agentes. Añade entradas al final de cada sección con fecha
(AAAA-MM-DD). No borres decisiones antiguas: márcalas como «sustituida por…».

## Estado actual (2026-11-04)

- 11 páginas × 4 idiomas = 44 páginas: portada, línea temporal (118 juegos, 85 con portada real), estudios (12, 5 con logo), motores (11),
  técnicas (laboratorio de 8 interfaces + 7 demos), minijuegos (índice + 4 juegos) y sala DOSBox.
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
  Sustituida por el eje vertical del 2026-11-03.
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
- **2026-11-02 · Paleta «atardecer» en lugar de noche** (petición del usuario: «menos oscuro, más luminoso»):
  fondo violeta más claro con degradado hacia un horizonte cálido, superficies hundidas en `--well`, CRT más suave y
  cielo de la fachada al anochecer. Las pantallas (DOSBox, terminales, lienzos) siguen oscuras.
- **2026-11-02 · Transiciones clásicas entre páginas** (`src/js/transitions.js`): se dibujan en un canvas de baja
  resolución (pixeladas, 20 pasos). Iris hacia el punto del clic (como LucasArts), estrella, rombo, reloj, persianas,
  disolución aleatoria y fundido a negro tramado (Bayer 8×8). La página de destino abre con el mismo efecto
  (`sessionStorage`), un script en `<head>` tapa la pantalla antes del primer pintado y `pageshow` evita volver a una
  pantalla negra con el botón Atrás. Sin transición con `prefers-reduced-motion`.
- **2026-11-02 · Skills de terceros vendorizadas** desde repositorios de skills.sh (Anthropic, Vercel, Corey Haines),
  fijadas a un commit y revisadas; `web-design-guidelines` usa una copia local de las reglas en vez de descargarlas.
  skills.sh no era accesible desde la sesión en la nube: se clonaron los repositorios de GitHub.
- **2026-11-02 · Navegación rediseñada** (petición del usuario: «tosca, burda y estática»). Sustituye la barra
  de verbos fija abajo y la barra de estado de papel:
  cabecera fija como un pasillo de puertas (icono + «Sala n» + nombre; la puerta de la sala actual está encendida con
  luz ámbar), en dos filas en todos los anchos de escritorio/tableta (seis salas más las herramientas no caben en una
  ni a 1820 px) y compacta al hacer scroll; submenú de minijuegos (hover en escritorio, botón en táctil);
  puntuación con barra de progreso; menú de idioma; «Plano del museo» como plano arquitectónico (rejilla de
  3 columnas con paredes y puertas, 2 columnas en tableta y un pasillo vertical en móvil) con «Estás aquí» y salas
  visitadas; en móvil las puertas, idiomas y ajustes viven en el plano. Franja fija «En esta sala» con scroll-spy en
  la cronología (épocas) y en técnicas (demos). Pie con directorio de salas, minijuegos e idiomas.
- **2026-11-01 · Catálogo de la sala DOSBox** con buscador, filtro por compañía, índice A–Z (sin artículos iniciales)
  y orden por título/año, visible a partir de 8 juegos (`arcade.json → catalogue.filtersFrom`); tarjetas compactas.

- **2026-11-03 · Línea temporal como eje vertical** (petición del usuario: «cajas cuadradas tan grandes, muy fea»).
  Un eje de píxeles discontinuo; cada época es un cartel con rango, nombre y resumen (`eras[].summary`); marcas de
  década; cada juego es una parada (nodo + año + portada pequeña + título y estudio · motor) alternando a izquierda y
  derecha en escritorio, y con el eje a la izquierda en móvil (< 900 px). Se conservan anclas `era-<id>` y `#<juego>`.
  La ficha (modal) muestra portada, captura, créditos y fuente.
- **2026-11-03 · Imágenes reales en lugar de sprites inventados** (petición del usuario: «imágenes reales, rigor»).
  `data/media.json` registra cada imagen con su fuente fijada a un commit o fichero; `tools/fetch_media.py` (stdlib,
  con decodificador/reductor PNG y cuantización a 256 colores) las guarda en `assets/media/` (versionado, ~2 MB).
  Fuente principal: libretro-thumbnails en GitHub (portadas `Named_Boxarts` y capturas `Named_Snaps`); su nombre de
  fichero indica la edición y se muestra en el crédito. Logos de motores desde sus repositorios oficiales (ScummVM GPL,
  AGS, Godot CC BY 4.0). Estudios sin logo: monograma tipográfico, nunca un emblema inventado. Los motores internos
  (SCUMM, AGI, SCI…) no tienen logo: se ilustran con una captura de un juego hecho con ellos (`refs`).
  Se descartó la portada de Colossal Cave de libretro: es un port de C64 de los 80, no el original de 1976.
  Portadas y capturas tienen copyright de sus editores: se muestran a baja resolución, con crédito y enlace al fichero.
- **2026-11-04 · Laboratorio de interfaces** (petición del usuario: «el menú radial y el de un clic no son nada
  precisos»). Sustituye a las maquetas de texto: cada pestaña muestra una captura real del juego y una escena original
  jugable con su interfaz exacta: parser de Zork I (respuestas originales en inglés), 15 verbos de Maniac Mansion
  (DOS 1987), 12 de Monkey Island (EGA 1990), 9 de Monkey Island 2 (clic derecho = verbo resaltado), menú del emblema
  de Full Throttle (mantener pulsado; ojos, boca, puño, bota; inventario con el botón derecho), moneda de CMI (mano,
  calavera, loro), dos botones de Broken Sword (izquierdo actúa, derecho mira; inventario arriba, verificado en el
  código de ScummVM `engines/sword1/menu.cpp`) y clic único de Machinarium (bocadillos con dibujos). Verbos en inglés,
  como en la versión original; las respuestas, en los cuatro idiomas. `src/js/interfaces.js`.
- **2026-11-04 · Técnicas nuevas** (`src/js/techlab.js`): cajas de paseo con escalado (SCUMM), pantalla de prioridad
  de Sierra (bandas 4–15 y colores de control 0–3 de AGI) y paletas CGA/EGA/VGA aplicadas a una captura real de
  King's Quest V.
- **2026-11-04 · 76 aventuras nuevas** (de Adventureland, 1978, a The Rise of the Golden Idol, 2024). Solo datos de
  los que había certeza; se quitaron curiosidades dudosas (controles de Rise of the Dragon, año de Mortevielle…).
- **2026-11-04 · Más fuentes de imágenes accesibles desde la nube (solo GitHub):** libretro-thumbnails de Amiga,
  Atari ST, Spectrum, C64, Wii…; capturas oficiales de `scummvm/scummvm-web`; logos de editoras de
  `HVR88/Monochrome-Gaming-Logos` (recreaciones vectoriales, marcadas como tales y sobre placa oscura).
  `tools/find_media.py` las indexa y la skill `find-media` explica el proceso y la verificación.
  Las capturas de pixel art se reducen por un factor entero.
- **2026-11-03 · Cada estudio lista sus juegos** (`studios.json → games`) y muestra sus portadas enlazadas a la línea temporal.

## Datos técnicos útiles

- js-dos 8.3.20: `Dos(elemento, opciones)` devuelve un objeto con `stop()`, `setMouseCapture(bool)`,
  `setMouseSensitivity(n)`… Opciones usadas: `url` o `dosboxConf` + `initFs` (Uint8Array de un zip), `pathPrefix`,
  `mouseCapture`, `onEvent`. Lee `autolock=true` del `dosbox.conf` para activar la captura.
- Un `.jsdos` es un zip con `.jsdos/dosbox.conf` y `.jsdos/jsdos.json` (`{"version":"js-dos-v8"}`).
- Artifact de claude.ai: no sirve directorios (usar `--link-style file`), envuelve el `index.html` raíz en su propio
  esqueleto, admite `.wasm`, `.js`, `.png`, `.xml`, `.txt`, `.webmanifest` pero no `.zip`.

## Pendiente / ideas

- **Imágenes pendientes:** logos de 7 estudios (Revolution, Cyan, Pendulo, Wadjet Eye, Daedalic, Amanita,
  Terrible Toybox), logo de Visionaire y portadas de 15 juegos (Runaway, Hollywood Monsters, Sam & Max Save the World,
  Blackwell, Machinarium, Deponia, The Walking Dead, Kentucky Route Zero, Broken Age, Return to Monkey Island, Golden
  Idol, Hob's Barrow, Old Skies, Kathy Rain 2, Edna & Harvey) y de las aventuras nuevas sin fuente en GitHub (Samorost,
  Dreamfall, Black Mirror, Sleeping Dragon, Still Life, Fahrenheit, Whispered World, Botanicula, The Next BIG Thing,
  Oxenfree, Lamplight City, Beyond a Steel Sky, Broken Sword Reforged, Rise of the Golden Idol, Gabriel Knight 3,
  Monkey Island SE, Grim Fandango Remastered). Todas tienen ya su fuente `wikipedia:` en `data/media.json`
  (sacada de su enlace): basta con `python3 tools/fetch_media.py` con acceso a Wikipedia y revisar cada imagen.
  Samorost, Botanicula, Broken Sword Reforged, Grim Fandango Remastered y Monkey Island SE no la tienen (su artículo
  muestra otra edición o enlazan a webs oficiales): su portada se añade a mano con la skill `find-media`. Están declaradas
  en `data/media.json` como `wikipedia:` pero Wikipedia/Wikimedia/Wikidata estaban bloqueados en la sesión en la nube.
  Ejecuta `python3 tools/fetch_media.py` en local (o permite esos dominios en el entorno) y revisa cada imagen; la
  parte de Wikimedia de la herramienta no se ha podido probar contra la API real. `--check` lista lo que falta.
- Verificar fechas, estudios y motores contra Wikidata (P577, P178, P408) cuando haya acceso: la portada de Myst es
  la Masterpiece Edition y la de Mystery House una reedición SierraVenture (así lo dice su crédito).

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
- 2026-11-02 · v7: paleta más luminosa, transiciones clásicas entre páginas y skills de terceros.
- 2026-11-02 · v8: navegación nueva (pasillo de puertas, plano del museo, franja «En esta sala», pie con directorio).
- 2026-11-04 · v10: 118 aventuras, laboratorio de interfaces, tres técnicas nuevas, logos de estudios y `find_media`.
- 2026-11-03 · v9: línea temporal como eje con carteles de época, imágenes reales con créditos (portadas, capturas, logos).
