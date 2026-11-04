# MEMORY.md · decisiones y estado del proyecto

Memoria de trabajo compartida entre personas y agentes. Añade entradas al final de cada sección con fecha
(AAAA-MM-DD). No borres decisiones antiguas: márcalas como «sustituida por…».

## Estado actual (2026-11-04)

- 11 páginas × 4 idiomas = 44 páginas (más el chat de Murray en todas): portada, línea temporal (118 juegos, 85 con portada real), estudios (12, 5 con logo), motores (11),
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
- **2026-11-02 · Paleta «atardecer» en lugar de noche** (sustituida por la paleta «museo de época» del 2026-11-05) (petición del usuario: «menos oscuro, más luminoso»):
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

- **2026-11-05 · Paleta «museo de época», sin morados** (petición del usuario: «el morado típico de las webs hechas con
  IA»). Paredes verde botella (`--ink #14211c`), vitrinas de nogal (`--panel`), latón (`--amber`), rojo sangre de buey
  (`--rose`), verdín (`--teal`) y pergamino: los colores de cajas y manuales de los 80–90. Los morados de lienzos y
  sprites se pasaron a azul noche o gris pergamino; se conservan los colores exactos de las interfaces reproducidas
  (EGA/CGA, verbos de Monkey Island 2). Épocas: verdín, musgo, latón, bermellón, azul acero y pergamino.

- **2026-11-05 · EGA con tramado en damero.** La demo de paletas reproduce cómo los juegos EGA simulaban colores
  intermedios: pares de los 16 colores alternados en damero (136 combinaciones) a 320 px de ancho, distancia redmean.
- **2026-11-05 · Docker Compose para desplegar** (petición del usuario). `web`: build público con `build.py` + nginx
  (gzip, caché, cabeceras, `/healthz`, proxy y límite de `/api/murray/`). `murray`: servicio Python sin dependencias,
  sin puertos publicados, solo lectura, sin capacidades. Probado con Docker en la sesión (nginx → Murray → modelo
  falso compatible con OpenAI), incluido que la clave no aparece en `dist/` ni en los logs.
- **2026-11-05 · Murray, la calavera parlante, como chat flotante** (petición del usuario: «un icono abajo a la
  derecha, no una sala»). Botón en todas las páginas con un sprite real de Murray (fotogramas de la animación de hablar
  de *The Curse of Monkey Island*, de `JeanxPereira/CMI-Sprites`, con crédito); la conversación sigue al visitante entre
  salas (`sessionStorage`). Servidor con RAG (BM25 sobre `data/` en cuatro idiomas) y herramientas de solo lectura
  (`search_museum`, `get_record`, `list_games`) para modelos libres vía **API compatible con OpenAI** (petición del
  usuario: él pone el modelo, Qwen 3.8): `MURRAY_LLM_BASE_URL`, `MURRAY_LLM_API_KEY`, `MURRAY_LLM_MODEL` en `.env`.
  Sin modelo, «modo vitrina». Se descartó usar la API de Anthropic y el SDK (`pip` no hace falta).

- **2026-11-05 · Murray mira a la izquierda y sin píxeles rojos** (petición del usuario). Los fotogramas se guardan
  reflejados y con el color #bb3b0b del contorno (resto del extractor de sprites) cambiado por negro, mediante las
  opciones `mirror` y `replace` de `data/media.json` que aplica `tools/fetch_media.py`.
- **2026-11-05 · Murray habla de historia de las aventuras, no de otros museos** (el modelo del usuario respondía sobre
  el Museo de Informática de la UPV, otro proyecto). El prompt y una ficha «sobre el museo» (`murray.json → about`)
  dicen que este es un museo virtual sin relación con ninguna institución ni con ese museo.
- **2026-11-05 · Base de conocimiento de internet para Murray** (petición del usuario). Desde la nube solo eran
  accesibles GitHub y la búsqueda web: `data/murray_kb/history.json` (16 artículos redactados con la búsqueda web, con
  fuentes y discrepancias señaladas) y `scummvm-games.jsonl` (catálogo de scummvm-web fijado a un commit, sin demos ni
  duplicados). `tools/build_murray_kb.py wikipedia` añade Wikipedia en cuatro idiomas (probado con una API falsa;
  pendiente de ejecutar donde Wikipedia sea accesible). Ponderación: ficha del museo > historia > Wikipedia > catálogo.
  2026-11-05: la primera ejecución del usuario abortó con `KeyError: 'query'` (la API de MediaWiki devuelve los errores
  con HTTP 200 y un objeto `error`). Ahora se reintenta con `maxlag`/`ratelimited`, se salta y se informa el artículo
  que falle, y hay una pausa entre peticiones (`PCM_WIKI_PAUSE`).

- **2026-11-05 · Murray en streaming** (petición del usuario). `server/murray.py` llama al modelo con `stream: true`,
  acumula las `tool_calls` por índice, filtra `<think>…</think>` aunque llegue partido (`ThinkFilter`) y reenvía cada
  fragmento por SSE cuando el cliente manda `stream: true` o `Accept: text/event-stream`; sin eso sigue respondiendo un
  JSON. nginx con `proxy_buffering off` y el servidor con `X-Accel-Buffering: no`. Si el modelo falla a mitad, se
  conserva lo escrito y se añade un aviso; si falla antes, responde en modo vitrina. Probado en Docker: los fragmentos
  llegan al navegador al ritmo del modelo.

- **2026-11-05 · Murray guía la visita** (petición del usuario: «que me lleve a la sala sin pinchar»). Herramienta
  `go_to` (y marca `[[go:…]]` para modelos sin herramientas) que el servidor valida con `Museum.resolve_target`:
  salas de `site.json` y fichas (`game:`→`timeline/#id`, `era:`→`#era-id`, `studio:`→`studios/#studio-id`,
  `engine:`→`engines/#engine-id`, `technique:`/`interface:`→`techniques/#tech-…`). El evento `done` lleva `navigate`;
  el widget anuncia «Rumbo a…», guarda la conversación abierta y usa `PCM.go` (transición). Al llegar: la línea temporal
  abre la ficha, los motores insertan el cartucho y los estudios resaltan su vitrina (también con `hashchange`).
  El navegador manda `page` para que Murray sepa dónde está el visitante.

- **2026-11-05 · Guardarraíles de tema para Murray** (petición del usuario: «que NO hable de nada que no sea
  aventuras gráficas»). Tres capas: reglas sin modelo (`server/guard.py`: nombres de la base de conocimiento, sagas,
  vocabulario del género en 4 idiomas, saludos → sí; manipulación y otros museos → negativa fija); clasificador con el
  propio modelo solo para lo dudoso, viendo la respuesta anterior; prompt endurecido y recordatorio en cada mensaje.
  La puntuación BM25 se descartó como señal: «receta de paella» o «capital de Francia» puntuaban alto por el catálogo.
  Calibrado: ningún mensaje fuera de tema de la batería pasa las reglas. `MURRAY_GUARD=strict|rules|off`.

- **2026-11-05 · Guardarraíles menos estrictos** (petición del usuario: «¿qué es un pollo de goma?» se rechazaba).
  Vocabulario de objetos, personajes y bromas del género en 4 idiomas (`guard.py → TRIVIA`: pollo de goma, grog, mono de
  tres cabezas, duelo de insultos…). Nuevo veredicto «likely»: el mensaje comparte un par de palabras con las fichas o
  `history.json` (no con el catálogo ni Wikipedia). No se acepta directamente porque frases genéricas como «guerra
  mundial» o «United States» también aparecen; lo decide el clasificador, y sin modelo pasa. El clasificador recibe
  las 3 fichas más relacionadas y la instrucción «en caso de duda, ON».

- **2026-11-05 · Murray contesta antes** (petición del usuario: «tarda mucho; ¿seguro que va en stream?»). El stream
  funcionaba de punta a punta; el retraso estaba antes de la primera palabra: el clasificador de tema se esperaba
  entero, el pensamiento de Qwen (`<think>` o `reasoning_content`) se ocultaba sin mostrar nada, y la ronda de
  herramientas. Ahora el clasificador corre en un hilo a la vez que la respuesta (retenida hasta el veredicto; si es
  OFF se corta el stream del modelo), `MURRAY_LLM_THINK=0` por defecto envía `chat_template_kwargs.enable_thinking=false`
  (se deja de enviar si el servidor responde 400/422 mencionándolo), el log mide cada ronda y
  `server/murray.py --probe "pregunta"` mide una pregunta. Pendiente: medir con el Qwen real del usuario.

- **2026-11-05 · Cabecera sin parpadeo y panel de Murray siempre alcanzable** (petición del usuario). La cabecera es
  `sticky` (en el flujo): al compactarse pierde la fila de puertas, la página se acorta y `scrollY` volvía a cruzar el
  umbral (24 px), así que alternaba sin parar en páginas cortas. Ahora hay histéresis (compacta a partir de 96 px y
  solo si después aún queda recorrido; se expande por debajo de 8 px) y `overflow-anchor: none`. En el panel de Murray,
  solo la conversación encoge (el resto `flex: none`); las sugerencias se reparten en filas con su propio scroll, la
  altura máxima descuenta el botón y el panel tiene scroll como último recurso.

- **2026-11-05 · Carpeta de juegos en el servidor** (petición del usuario: «dejar zips en el servidor y que se
  detecten y carguen»). Nuevo servicio `builder` (`deploy/builder.Dockerfile`, `tools/games_inbox.py`): monta
  `GAMES_DIR` (por defecto `./games`, en `.gitignore` y `.dockerignore`) en solo lectura, cada `GAMES_WATCH` s mira si
  hay ficheros nuevos, cambiados o borrados (espera a que dejen de cambiar), los importa con `add_game.add()`
  (caché por ruta+tamaño+fecha+JSON de opciones en el volumen `games-cache`), los marca `"inbox": true` en
  `arcade.local.json` sin tocar los añadidos a mano ni sus ficheros, y genera el sitio en `/site/build-*`, que activa
  cambiando el enlace `/site/current` (atómico; guarda el anterior). `web` ya no genera el sitio: nginx sirve
  `/site/current` del volumen `site` (sustituye al build dentro de `web.Dockerfile` del Docker Compose del 2026-11-05);
  los `.jsdos` pasan a `no-cache` porque un zip sustituido conserva el nombre. Opciones por juego en `<zip>.json`.
  Probado en Docker: PAINT.COM en un zip aparece en la sala, arranca en DOSBox y desaparece al borrar el zip.
  ScummVM en Docker solo si `vendor/scummvm/` está compilado en el servidor antes de `docker compose build`.

- **2026-11-05 · La sala DOSBox del servidor lista solo los juegos de la carpeta, identificados y con portada**
  (petición del usuario). `games_inbox.py` construye con `build.py --arcade-local-only` (sin la demo ni los freeware
  sin paquete; los zips oficiales de los freeware conservan su ficha; `--all-games` vuelve a la lista del museo).
  `tools/identify_game.py` identifica cada juego: ficheros de datos con el id de ScummVM (`MONKEY2.000`, `FT.LA0`,
  `KQ4DIR`), nombres del zip y de sus carpetas contra `timeline.json` y el catálogo de ScummVM (difflib + palabras,
  sin «The», números romanos → arábigos, números distintos penalizan: Larry 1 ≠ Larry 7); un nombre de ejecutable solo
  cuenta si el zip no se llama de otra forma (PRINCE.EXE de *Prince of Persia* no es *The Prince and the Coward*).
  Con ficha del museo: su título, año, estudio, descripción en 4 idiomas, enlace «Ver ficha» y su portada revisada
  (`media.json`). Sin ficha: portada de PC de libretro-thumbnails (DOS, luego ScummVM; se evitan demos, remasters y
  versiones de Windows) vía API de GitHub (o `git`), fijada al commit, reducida con `fetch_media.shrink_png` y
  mostrada con crédito; se guarda en `assets/games/covers/` (ignorado) y se reintenta a diario si no hay red.
  «Trae tu propio juego» se mantiene (solo en el navegador). Control de volumen en la sala (`#dosVol`, recordado):
  js-dos `setVolume` y, en el iframe de ScummVM, un `GainNode` maestro interceptando `AudioNode.connect` hacia el
  destino (`PCM_SET_VOLUME`). Probado: juegos sintéticos (solo nombres de ficheros) identificados, portadas reales
  descargadas fuera de Docker; en Docker, solo los juegos de la carpeta y Pixel Paint arranca. Pendiente: probar la
  identificación con los zips reales del usuario.

- **2026-11-05 · Catálogo automático de aventuras** (petición del usuario: «automatizar el catálogo desde ScummVM y
  archive.org, con enlace a jugar en nuestro DOSBox y a comprar en GOG»). `tools/sync_catalog.py` (diario en el
  `builder`, `CATALOG_EVERY`) une la línea temporal con ScummVM (freeware y demos de `scummvm-web`, fijado a un commit;
  solo motores de aventura: fuera *Crime Patrol*, *Castle Master*, *Griffon Legend*…), Internet Archive
  (`advancedsearch`, `metadata`, `download`) y GOG (solo enlace de tienda, título exacto). Una ficha por juego con sus
  ediciones y tres estados: **jugable** (derechos en `game_fetch.RIGHTS_PLAYABLE` + validación automática: host,
  tamaño, md5/sha1, zip, programa DOS no Windows o motor compilado), **pendiente** y **solo ficha**.
  **Decisión sobre derechos:** el usuario pidió incluir «abandonware» jugable; no se hace. Abandonware no es una
  licencia: los juegos comerciales de Internet Archive quedan como «solo ficha» (con GOG si se vende), y un elemento
  de IA solo es jugable con licencia explícita en sus metadatos o con permiso documentado en
  `data/catalog.overrides.json`. dos.zone y eXoDOS no se usan como fuentes (distribuyen juegos comerciales).
  Descarga **bajo demanda** por el proxy `server/games.py` (contenedor `games`, `/api/games/<edición>`, CORS y
  conversión a `.jsdos`), solo ediciones jugables, caché LRU (`GAMES_CACHE_MB`), límite por IP. Navegador: Cache
  Storage para los juegos descargados, partidas de ScummVM en IndexedDB (copia periódica de `/home/web_user/saves`).
  Un fallo de red no es suspenso (se reintenta); un motor no compilado se revalida cuando se compila. Motores
  añadidos a `build_scummvm.sh`: cge2, parallaction, adl (sin dependencias); sludge, wage, sword25 y wintermute
  necesitan png/lua/jpeg y siguen fuera; `got` no existe en 2.9.1. Probado con fuentes simuladas (`test_catalog.py`,
  `npm run test:catalog`) y en Docker; **las fuentes reales no eran accesibles desde la sesión**: pendiente la
  primera sincronización en el servidor, revisar los nombres de colecciones de IA y la respuesta real de GOG.

- **2026-11-05 · `games/` existe en el repositorio** (solo con su README; el resto sigue ignorado). En Docker Desktop
  para Mac, `docker compose up` fallaba con «error while creating mount source path …/games: chown … permission
  denied» porque Docker no puede crear la carpeta de un bind mount. Si se cambia `GAMES_DIR`, hay que crearla antes.

- **2026-11-05 · Panel de control del catálogo** (petición del usuario: «panel con usuario y contraseña para lanzar
  descargas, ver errores y fuentes, probar en DOSBox antes de validar; localízalos todos, yo marco los que tengan
  permiso»). `server/admin.py` + `server/admin/` en el contenedor `games`, en `/admin/` (nginx lo pasa, `noindex`,
  fuera de `robots.txt`). Credenciales solo en `.env` (`ADMIN_USER`, `ADMIN_PASSWORD`); sin ellas, 404. Sesión en
  memoria con cookie `HttpOnly`+`SameSite=Strict`, cabecera `X-PCM-Admin` en los POST, 5 fallos por IP = 15 min.
  La sincronización ahora **localiza todo**: catálogo completo de aventuras de ScummVM (sin edición), Internet Archive
  paginado (`maxResults`) con metadatos de todos sus elementos (cacheados, `metadataPerRun`), comerciales incluidos.
  El panel puede descargar cualquier edición para probarla (`game_fetch.prepare(admin=True)`), validarla, marcar
  derechos (`permission` exigía enlace de prueba: sustituido el mismo día, ver «el usuario decide qué es jugable»; queda `rightsBy`/`rightsAt`), cambiar el arranque, el enlace de GOG,
  forzar «solo ficha» y adjuntar elementos de IA a un juego. Decisiones en `catalog.admin.json` (junto al catálogo,
  gana a `data/catalog.overrides.json`); la sincronización las aplica antes de decidir si una validación sigue
  valiendo y conserva las validaciones del panel hechas mientras corría. El `builder` atiende `sync.request.json`,
  escribe `sync.status.json` y `sync.log`, y regenera la web cuando cambia el catálogo. Registro de descargas en
  `downloads.jsonl` (caché del proxy). La web pública solo lista los «solo ficha» de la línea temporal (el resto, ~800,
  solo en el panel). Panel solo en español: herramienta privada, no contenido del museo. Probado con `npm run
  test:admin` (fuentes falsas) y en Docker (login, sincronización pedida desde el panel, regeneración).

- **2026-11-05 · El usuario decide qué es jugable** (petición del usuario: «ese requisito no te lo he dado; yo lo
  validaré, ya he hecho toda la autorización»). Sustituye la exigencia de un enlace de prueba para `permission` y la de
  una validación automática correcta: el botón «Marcar como disponible» del panel pone `approved: true` (con
  `rightsBy`/`rightsAt`; nota y enlace opcionales) y eso basta para que sea jugable (`edition_status`, y el proxy lo
  sirve aunque la etiqueta de derechos no sea de `RIGHTS_PLAYABLE`). La validación automática informa (si falló, el
  panel lo avisa) pero no bloquea. «Retirar de la web» lo devuelve a lo que dice la fuente. El proxy responde con
  `Cache-Control: no-cache` + ETag (antes `max-age=86400`), para que un juego retirado deje de servirse al momento
  (los navegadores revalidan y reciben 304 si no cambió).

- **2026-11-05 · Eliminar ediciones en el panel** (petición del usuario: «cuando hay varias ediciones se deberían
  poder eliminar, no solo añadir»). Botón «Eliminar edición» (con confirmación): se guarda en
  `catalog.admin.json → <juego>.removedEditions` con lo que era, la sincronización la salta (`merge`), se borra su
  descarga de la caché, y la ficha lista las eliminadas con «Restaurar» (vuelve al momento, sin esperar a sincronizar).

- **2026-11-05 · Catálogo de la sala DOSBox por páginas** (petición del usuario: «de 10 en 10, manteniendo la
  búsqueda, las letras y el orden»). `arcade.js` filtra (búsqueda, compañía, motor, estado, letra), ordena (año o A–Z)
  y muestra solo la página actual (`arcade.json → catalogue.pageSize`, 10); cambiar un filtro vuelve a la página 1.
  Paginador con primera, última y ±2 alrededor de la actual (`catPrev`, `catNext`, `catPage`, `catPages` en los cuatro
  idiomas). Llegar con `#play=<id>` abre la página donde está ese juego (limpia los filtros si lo ocultaban). Se quitó
  la caja con scroll propio de la lista (`max-height`), innecesaria con páginas.

- **2026-11-05 · ScummVM con todos los motores** (petición del usuario). `tools/build_scummvm.sh` acepta
  `ENGINES=all` (sin `--disable-all-engines`: todos los estables, que es lo que hace `configure` por defecto) y
  `ENGINES=all-unstable` (`--enable-all-engines`), y en ambos activa `--enable-ogg --enable-zlib --enable-png
  --enable-jpeg --enable-gif --enable-freetype2 --enable-theoradec --enable-mpeg2 --enable-a52 --enable-faad` (en
  Emscripten 2.9.1 png/jpeg/gif/freetype/ogg/zlib son ports que solo se usan si se piden; a52/faad/mpeg2/theora los
  compila `dists/emscripten/build.sh`). La compilación por defecto no cambia. `vendor/scummvm/ENGINES` se escribe
  ahora a partir de los plugins compilados (`data/plugins/lib*.so`). Listas vacías con `${A[@]+"${A[@]}"}` por el
  bash 3.2 de macOS. Sin probar la compilación completa en la sesión (no se puede ejecutar Emscripten aquí).

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

- **Generar la parte de Wikipedia de Murray:** `python3 tools/build_murray_kb.py wikipedia` en local o en el servidor
  (en la nube Wikipedia estaba bloqueada) y hacer commit de `data/murray_kb/wikipedia-*.jsonl`.
- **Probar Murray con el modelo real** (Qwen 3.8 en el servidor del usuario): en la sesión solo se probó con un
  servidor falso compatible con OpenAI. Revisar el tono, la latencia (`--probe`, líneas «model round» del log), si su
  servidor admite *function calling* y si respeta `enable_thinking=false` (en Ollama puede que haya que desactivar el
  pensamiento en el propio servidor).
- Verificar los enlaces externos (Wikipedia y webs oficiales): no se pudieron comprobar desde el entorno en la nube.
- Probar la captura del ratón con un juego DOS real en un navegador de escritorio.
- **Compilar ScummVM de verdad** (`tools/build_scummvm.sh`) y probar los freeware: en la sesión en la nube se bloqueó la
  ejecución del script oficial (descarga y ejecuta Emscripten). La integración está probada con un ScummVM simulado;
  pueden hacer falta ajustes (nombres de plugins, rutas) con el build real.
  2026-11-05: la primera compilación del usuario falló en `backends/midi/seq.cpp` (`sys/soundcard.h` no existe en
  Emscripten): el `configure` de 2.9.1 activa el MIDI de `/dev/sequencer` en cualquier host «posix». El script pasa
  ahora `--disable-seq-midi --disable-timidity --disable-alsa --disable-sndio` (y `SCUMMVM_CONFIGURE` para extras).
  2026-11-05: en el Mac del usuario, la descarga de Emscripten falló con «Can't timestamp and not clobber old files at
  the same time»: `dists/emscripten/build.sh` usa `wget -nc` y su configuración de wget tenía `timestamping = on`.
  El script pone ahora delante en el PATH un `wget` envoltorio con `--no-config` (`.cache/wget-shim/`), y avisa si
  no hay wget. Después, `npm install` (dentro de la instalación de Emscripten) falló por la caché de npm dañada del usuario
  (`~/.npm/_cacache`, ENOENT): el script usa ahora su propia caché (`npm_config_cache=.cache/npm`). Luego, con
  `ENGINES=all`, la descarga de a52dec falló (404 en `liba52.sourceforge.io`): las bibliotecas que baja el script de
  ScummVM (theora, mpeg2, faad, a52) son ahora opcionales; se comprueba su URL con `wget --spider` (o que ya estén
  compiladas) y, si no responde, se compila sin ella con un aviso. Solo afectan a algunos códecs de vídeo. Después, el
  motor `grim` falló en `gfx_opengl_shaders.cpp` (`GL_DRAW_FRAMEBUFFER_BINDING`, de OpenGL ES 3, no existe en el
  GLES2 de Emscripten): el modo `all` pasa `--disable-opengl-game --enable-tinygl` (los motores 3D usan TinyGL,
  el renderizado por software de ScummVM) y `SKIP_ENGINES=a,b` añade `--disable-engine=a,b` para saltar motores.
- ~~Guardar partidas de ScummVM entre visitas~~ hecho el 2026-11-05 (IndexedDB). Las de DOSBox dependen de js-dos (sin comprobar).
- **Primera sincronización real del catálogo** en el servidor: `docker compose logs builder` tras arrancar; comprobar
  los nombres de colecciones de Internet Archive (`data/catalog.sources.json`), que GOG devuelve `products` y que las
  descargas de ScummVM validan. Compilar ScummVM con `ENGINES` ampliado si se quieren más freeware jugables.
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
- 2026-11-05 · v11: paleta «museo de época» sin morados, EGA con tramado, Docker Compose y Murray (chat con RAG).
- 2026-11-04 · v10: 118 aventuras, laboratorio de interfaces, tres técnicas nuevas, logos de estudios y `find_media`.
- 2026-11-03 · v9: línea temporal como eje con carteles de época, imágenes reales con créditos (portadas, capturas, logos).
