# AGENTS.md · Point and Click Museum

Guía para agentes de código (Claude Code, Codex, Cursor…) que trabajen en este repositorio.
Lee también `MEMORY.md`: contiene las decisiones tomadas y por qué.

## Qué es

Sitio estático en pixel art sobre la historia de las aventuras gráficas, en **español, inglés, alemán y francés**.
Un generador en Python (`build.py`, solo biblioteca estándar) lee los JSON de `data/` y produce `dist/`:
una página prerenderizada por idioma y sala (44 páginas), imágenes, sitemap y la sala DOSBox (js-dos).

## Comandos

```bash
python3 build.py                 # genera dist/ (valida los datos antes)
python3 build.py --check         # solo valida datos y traducciones
python3 -m http.server -d dist 8000   # http://localhost:8000/es/
npm install && npx playwright install chromium   # una vez, para las pruebas
npm test                         # pruebas de humo sobre dist/ (requiere build previo)
python3 tools/export_artifact.py --out /tmp/artifact   # copia para publicar como Artifact de claude.ai
python3 tools/add_game.py ~/Downloads/*.zip [--yes]   # añade juegos DOS o ScummVM locales (no versionados)
python3 tools/games_inbox.py ~/juegos [--once]   # vigila una carpeta de zips, los importa y regenera el sitio (servicio builder)
python3 tools/identify_game.py juego.zip --cover   # qué juego es (ficheros, nombres, línea temporal, catálogo ScummVM) y su portada
tools/build_scummvm.sh           # compila ScummVM web en vendor/scummvm/ (no versionado; 30-60 min)
npm run test:scummvm             # prueba la integración de ScummVM con tests/fixtures/fake-scummvm
python3 -m unittest discover -s tests        # pruebas de tools/add_game.py
python3 build.py --no-local      # build público sin la colección local
python3 tools/make_jsdos_bundle.py <carpeta|zip> --exe GAME.EXE --out assets/games/x.jsdos
python3 tools/fetch_jsdos.py     # vuelve a descargar js-dos en vendor/
python3 tools/fetch_media.py     # descarga portadas, capturas y logos de data/media.json (--check, --only grupo/id)
python3 tools/find_media.py "Título" [--kind cover|screenshot|logo]   # busca imágenes en GitHub (libretro, scummvm-web, logos)
docker compose up -d --build    # despliegue: builder (genera y vigila GAMES_DIR) + nginx (web) + Murray; configuración en .env
python3 tools/build_murray_kb.py scummvm|wikipedia|all   # regenera la base de conocimiento externa de Murray
python3 server/murray.py         # Murray en local (puerto 8080); MURRAY_LLM_BASE_URL/MODEL/API_KEY en el entorno
nasm -f bin tools/dos/paint.asm -o tools/dos/PAINT.COM   # solo si cambias el programa DOS de prueba
```

**Antes de dar un cambio por terminado:** `python3 build.py && npm test`. Si tocas algo visual, mira una captura
(escritorio y móvil). No dejes `build.py` con avisos de traducción pendientes.

## Mapa del código

| Ruta | Para qué |
|---|---|
| `build.py` | validación, localización, render de páginas, imágenes PNG, sitemap |
| `data/site.json` | idiomas, `baseUrl`, `pages` (ruta, icono, scripts y datos de cada página), `nav`, tabla de puntos |
| `data/i18n/<lang>.json` | textos de interfaz; claves `page_<id>_title` y `page_<id>_meta` por página |
| `data/timeline.json`, `studios.json`, `engines.json`, `techniques.json`, `hero.json` | contenido de las salas |
| `data/minigames/*.json` | los cuatro minijuegos (reglas, escenas, textos, parámetros) |
| `data/arcade.json` | emulador y juegos DOS versionados; `catalogue.filtersFrom` = nº de juegos a partir del que aparecen los filtros |
| `data/arcade.local.json` + `assets/games/` | colección local creada por `tools/add_game.py` (**ignorada por git**, nunca la añadas) |
| `tools/games_inbox.py` + `games/` | carpeta de juegos del servidor: importa zips con `add_game`, identifica el juego y su portada, caché por fichero, build atómico (`<site>/current`) con `build.py --arcade-local-only` (la sala lista solo esos juegos); `games/` está en `.gitignore` |
| `tools/identify_game.py` | identificación de juegos (firmas de ficheros SCUMM/AGI, nombres, `timeline.json` + catálogo de ScummVM) y portadas (`media.json` del museo o libretro-thumbnails) |
| `data/media.json` + `assets/media/` | imágenes reales (portadas, capturas, logos) con su fuente exacta; `refs` reutiliza imágenes entre fichas |
| `data/sprites.json`, `characters.json`, `pixelfont.json` | gráficos de la interfaz y los minijuegos |
| `src/layout.html` | plantilla común; `src/pages/<id>.html` contenido de cada página |
| `src/js/core.js` | datos, i18n `t()`, sonido, puntuación `award()`, modal, utilidades |
| `src/js/rules.js` | motor de reglas de los minijuegos |
| `src/js/scene.js` | primitivas de escena y desván procedural de la caza del píxel |
| `src/js/characters.js` | personajes animados |
| `src/js/nav.js` | navegación: cabecera de puertas, submenú de minijuegos, menú de idioma, plano del museo, salas visitadas y franja «En esta sala» |
| `src/js/transitions.js` | transiciones entre páginas (iris, estrella, disolución, fundido tramado…); config en `site.json → transitions` |
| `src/js/sections.js`, `games.js`, `arcade.js` | lógica de cada página (cada bloque se activa solo si existe su elemento) |
| `src/js/interfaces.js` | laboratorio de interfaces (técnicas): parser, verbos SCUMM, menú de Full Throttle, moneda de CMI, dos botones, un clic; datos en `techniques.json → interfaces, lab` |
| `src/js/techlab.js` | demos de cajas de paseo, pantalla de prioridad y paletas CGA/EGA/VGA |
| `src/js/murray.js` | widget de chat de Murray (botón abajo a la derecha en todas las páginas); textos en `data/murray.json` |
| `server/murray.py`, `server/knowledge.py`, `server/guard.py` | servicio de Murray: RAG (BM25) y herramientas sobre `data/` y `data/murray_kb/`, API compatible con OpenAI, límites y guardarraíles de tema |
| `data/murray_kb/` | conocimiento externo de Murray: `history.json` (artículos con fuentes web), catálogo de ScummVM, Wikipedia (`tools/build_murray_kb.py`) |
| `deploy/`, `docker-compose.yml`, `.env.example` | imágenes Docker (builder + nginx + Murray), configuración de nginx y variables |
| `src/scummvm/player.*` | reproductor de ScummVM (iframe): copia datos y juego al sistema de ficheros de Emscripten |
| `vendor/scummvm/` | ScummVM web compilado por `tools/build_scummvm.sh` (ignorado salvo `NOTICE.md`) |
| `tests/site.test.js` | pruebas de humo con Playwright |
| `tests/scummvm.test.js`, `tests/fixtures/` | integración de ScummVM con un ScummVM simulado |
| `tools/` | bundles js-dos, descarga del emulador, exportación a Artifact, programas DOS |

## Reglas del proyecto

1. **Todo el contenido vive en `data/`.** No escribas textos ni datos de juegos en el JS o el HTML.
   Los textos pueden ser cadena o `{"es","en","de","fr"}`; `build.py` los resuelve por idioma.
2. **Siempre los cuatro idiomas.** Cualquier texto nuevo va en es/en/de/fr. `build.py` avisa de lo que falte.
   Vocabulario de la aventura de texto: palabras sin tildes ni diéresis (se normalizan), incluye sinónimos.
3. **Python sin dependencias** (stdlib, 3.9+). JS sin frameworks ni build step: scripts clásicos con `defer`,
   todo cuelga de `window.PCM`. Nada de `fetch` de datos: van incrustados en `<script id="pcm-data">`.
4. **La puntuación suma 100.** Si añades premios en `site.json → score.awards`, reajusta otros. `build.py` lo valida.
5. **Prefijos de clase CSS:** js-dos carga Tailwind/daisyUI, que define `.btn`, `.modal`, `.toast`, `.card`, `.title`.
   Por eso usamos `.pbtn`, `.pmodal`, `.ptoast`. No crees clases genéricas que choquen en la página `arcade`.
6. **Estética:** pixel art, `image-rendering: pixelated`, paleta «museo de época» (verde botella, nogal, latón, pergamino;
   **nada de morados**) de tokens en `:root` de `style.css`
   (`--ink`, `--panel`, `--well` para superficies hundidas, `--shade` para sombras; no uses `#000` salvo en pantallas),
   fuentes Press Start 2P (títulos) y VT323 (texto). Nada de emoji como iconos. Respeta `prefers-reduced-motion`
   (las transiciones se desactivan solas). La clase `.cur` es el cursor parpadeante: no la reutilices.
7. **Responsive:** ninguna página puede desbordar en horizontal (iPhone SE incluido). `npm test` lo comprueba.
8. **Legalidad:** nada de juegos comerciales ni recreaciones de juegos existentes en el repositorio. La colección
   personal del usuario va en `assets/games/`, `assets/scummvm/` y `data/arcade.local.json`, que están en `.gitignore`: no los fuerces
   con `git add -f` ni los publiques (los builds públicos usan `--no-local`). Los minijuegos y gráficos de interfaz son originales.
12. **Rigor e imágenes reales.** Juegos, estudios y motores reales se ilustran con imágenes reales (portada, captura,
    logotipo), nunca con sprites inventados. Cada imagen va en `data/media.json` con su fuente fijada (commit de GitHub o
    fichero de Wikimedia) y se muestra con su crédito; revisa que sea del juego y edición correctos (no un port posterior).
    Sin logo descargado, el estudio lleva un monograma tipográfico. Solo hechos verificables; ante la duda, pregunta.
13. **Secretos fuera del cliente.** La URL, la clave y el nombre del modelo de Murray solo viven en el entorno del
    contenedor `murray` (`.env`, ignorado por git). Nunca en `data/`, `src/`, `dist/` ni en logs. El navegador solo
    llama a `/api/murray/chat`. El servidor de Murray usa solo la biblioteca estándar.
9. **Enlaces externos:** a Wikipedia o a webs oficiales; `target="_blank" rel="noopener"`. Verifica que existen.
10. **SEO:** cada página nueva necesita título, descripción, entrada en `site.json → pages` y queda en el sitemap.
11. **Navegación:** las salas salen de `site.json → nav` (puertas de la cabecera, plano del museo y pie) con su etiqueta
    corta `navLabel_<id>`; los minijuegos cuelgan de `games` (`parent`). Para una sala larga, añade sus anclas a la
    franja «En esta sala» en `render_blocks()` de `build.py` (bloque `subnav`). Etiquetas en minúsculas de frase,
    sin versalitas decorativas.

## Convenciones de commits

Mensajes en español, en imperativo y concretos («Añade Loom a la línea temporal»). Un cambio lógico por commit.
`dist/` no se versiona; `vendor/js-dos/` sí (GPL-2.0, ver `vendor/js-dos/NOTICE.md`).

## Skills disponibles

Propias, en `.claude/skills/`: `add-timeline-game`, `add-language`, `edit-minigame`, `pixel-art`, `add-dos-game`,
`verify-site`, `publish-artifact`, `find-media`. Úsalas para las tareas que describen.

De terceros (de skills.sh, fijadas a un commit; ver `.claude/skills/THIRD_PARTY.md`): `frontend-design` y
`web-design-guidelines` (revisión visual y de accesibilidad), `webapp-testing` (Playwright en Python),
`seo-audit` y `schema` (SEO multilingüe y JSON-LD). Las reglas de este archivo mandan sobre sus consejos genéricos.
