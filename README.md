# Point and Click Museum

Museo interactivo en pixel art sobre la historia de las aventuras gráficas, en español, inglés, alemán y francés.
Es un sitio estático: un generador en Python (solo biblioteca estándar) lee los JSON de `data/` y produce `dist/`.

```bash
python3 build.py                                   # genera dist/
python3 -m http.server -d dist 8000                # http://localhost:8000/es/
python3 build.py --base-url https://tu-dominio.org # URL pública para canonical, hreflang y sitemap
python3 build.py --check                           # solo valida los datos
```

## Qué se configura con ficheros

| Fichero | Contenido |
|---|---|
| `data/site.json` | idiomas, idioma por defecto, URL base, tabla de puntuación (debe sumar 100) |
| `data/i18n/<idioma>.json` | textos de la interfaz, uno por idioma |
| `data/timeline.json` | épocas y juegos de la línea temporal |
| `data/studios.json` | estudios y su árbol de diálogo |
| `data/engines.json` | cartuchos de motores |
| `data/techniques.json` | evolución de la interfaz, demos e ideas de diseño |
| `data/hero.json` | zonas interactivas de la fachada |
| `data/minigames/text-adventure.json` | aventura de texto: vocabulario por idioma, salas, objetos y reglas |
| `data/minigames/restoration-room.json` | sala de verbos: escena (rectángulos), zonas, objetos y reglas |
| `data/minigames/pixel-hunt.json` | caza del píxel: rondas, tiempos, colores y mensajes |
| `data/minigames/chronology.json` | reto de cronología (usa los juegos de la línea temporal) |
| `data/arcade.json` | sala DOSBox: versión de js-dos y lista de juegos |
| `data/sprites.json`, `data/pixelfont.json` | sprites de 12×12 y fuente de 5 píxeles |
| `data/characters.json` | personajes animados (conservador, visitante, gato): cabeza y torso a mano, piernas animadas por código |
| `data/site.json` → `pages` | páginas del sitio: ruta, icono, scripts y datos que carga cada una |

Cualquier texto puede ser una cadena o un objeto por idioma: `{"es": "...", "en": "...", "de": "...", "fr": "..."}`.
Si falta una traducción se usa el idioma por defecto y `build.py` avisa.

**Añadir un idioma:** añádelo a `site.json`, crea `data/i18n/<código>.json` y agrega la clave del idioma a los textos
(y al `vocab` de la aventura de texto). Ejecuta `build.py` y te listará todo lo que falta.

### Reglas de los minijuegos

La aventura de texto y la sala de verbos comparten un motor de reglas (`src/js/rules.js`). La primera regla que coincide gana:

```json
{ "verb": "use", "item": "key", "noun": "door",
  "if": ["!doorOpen"], "do": ["set:doorOpen", "remove:key", "win"],
  "say": { "es": "La llave gira.", "en": "The key turns." } }
```

Condiciones: `flag`, `!flag`, `has:objeto`, `room:sala`, `count:contador>=2`.
Efectos: `set:`, `unset:`, `give:`, `remove:`, `drop:`, `inc:`, `award:`, `sound:`, `look`, `win`.

## Páginas y navegación

Cada sala es una página propia (`/es/timeline/`, `/es/studios/`, `/es/engines/`, `/es/techniques/`, `/es/arcade/`) y cada
minijuego también (`/es/games/pixel-hunt/`…). La cabecera es un pasillo de puertas (la de la sala actual está
encendida) con la puntuación, el idioma y los ajustes; el botón «Plano» abre el plano del museo con las salas
visitadas y «Estás aquí». Las páginas largas tienen una franja «En esta sala» que marca la sección que lees, y todas
tienen migas de pan y sala anterior/siguiente. En móvil las salas, idiomas y ajustes están dentro del plano. Para añadir una página: entrada en `site.json` → `pages`, plantilla en
`src/pages/<id>.html` y textos `page_<id>_title` / `page_<id>_meta` en cada `data/i18n/<idioma>.json`.

La escena de la sala de restauración se describe con primitivas (`r`, `stripes`, `grad`, `books`, `sprite`, `glow`, `px`);
están documentadas en `src/js/scene.js`. La caza del píxel genera un desván procedural distinto en cada ronda.

## SEO

- Una página prerenderizada por idioma (`/es/`, `/en/`, `/de/`, `/fr/`) con todo el contenido en el HTML.
- `canonical`, `hreflang` (más `x-default`), Open Graph, Twitter Card y JSON-LD (`WebSite` + `ItemList` de `VideoGame`).
- `sitemap.xml` con alternativas por idioma, `robots.txt`, `manifest.webmanifest`, favicons e imagen OG generados.
- Cambia `baseUrl` en `site.json` (o usa `--base-url`) antes de publicar.

## Sala DOSBox

Usa [js-dos](https://js-dos.com) 8.3.20. Para alojarlo junto a la web (necesario si el hosting tiene una CSP estricta):

```bash
python3 tools/fetch_jsdos.py
```

Si `vendor/js-dos/` no existe, la página carga js-dos desde jsDelivr.

### ScummVM

Muchos juegos no traen `.exe`: son datos que ejecuta ScummVM (Beneath a Steel Sky, Flight of the Amazon Queen,
Drascula, Lure of the Temptress, Dreamweb, Teen Agent, Soltys, los datos de LucasArts/Sierra o los juegos de AGS).
La sala DOSBox incluye un reproductor de ScummVM web (`src/scummvm/player.*`), pero el motor hay que compilarlo una vez:

```bash
tools/build_scummvm.sh      # ScummVM 2.9.1 → vendor/scummvm/ (30–60 min la primera vez; descarga Emscripten)
python3 build.py
```

Requisitos: git, python3, make y herramientas de compilación de C/C++ (en macOS, `xcode-select --install`).
`vendor/scummvm/` no se versiona (pesa varios MB y es GPLv3); sin compilar, las fichas de ScummVM avisan de que falta.
Cada partida carga solo el plugin de detección y el del motor del juego. ScummVM usa el ratón directamente.

### Añadir juegos desde el zip descargado

```bash
python3 tools/add_game.py ~/Downloads/juego.zip                       # detecta el ejecutable; pregunta si duda
python3 tools/add_game.py ~/Downloads/*.zip --yes                     # muchos a la vez, sin preguntas
python3 tools/add_game.py juego.zip --title "Título" --year 1993 --studio "Estudio" --exe JUEGO/START.BAT
python3 tools/add_game.py --list                                      # ver la colección local
python3 tools/add_game.py --remove titulo                             # quitar uno
python3 build.py
```

El script abre el zip (también un zip dentro de otro) y decide el motor:

- **ScummVM** si reconoce los datos (`sky.dnr`, `queen.1`, `resource.map`, `*.000`, `ac2game.dat`, juegos AGS de Windows…):
  guarda los datos en `assets/scummvm/<id>.zip`. Si es uno de los freeware del catálogo, rellena su ficha.
- **DOSBox** si hay un programa DOS: elige el que arranca el juego descartando instaladores y utilidades
  (`INSTALL`, `SETUP`, `DOS4GW`…) y crea `assets/games/<id>.jsdos`.
- Los juegos de Windows que no son de AGS se rechazan. Fuerza el motor con `--engine dosbox|scummvm`.

Mientras no hayas compilado ScummVM, un juego que funcione en los dos motores va a DOSBox.
El juego queda apuntado en `data/arcade.local.json`. **Nada de esto se versiona** (están en `.gitignore`), así que tu colección no llega al
repositorio ni a GitHub. Para una versión pública sin tus juegos: `python3 build.py --no-local`
(`tools/export_artifact.py` ya lo hace).

Con 8 juegos o más, la sala DOSBox muestra un catálogo compacto con buscador (título o compañía), filtro por compañía,
índice alfabético (ignora «The», «El», «La»…) y orden por título o año. Pulsa `/` para ir al buscador.

Para juegos que **sí** se pueden redistribuir y quieres versionar, añádelos a `data/arcade.json`
(usa `tools/make_jsdos_bundle.py` y quita su ruta del `.gitignore`).

Todo lo que hay en `assets/` se copia tal cual a `dist/`. Solo empaqueta juegos que tengas derecho a redistribuir
(freeware, dominio público o con permiso). Los visitantes también pueden cargar su propia copia (`.jsdos` o `.zip`)
desde la propia página; se ejecuta en su navegador y no se sube a ningún sitio.

El paquete de prueba trae `MUSEUM.COM` (comprueba que arranca) y `PAINT.COM`, un programa de dibujo para probar el ratón
(fuente en `tools/dos/paint.asm`; se ensambla con `nasm -f bin paint.asm -o PAINT.COM`).

**Ratón:** los juegos DOS leen el ratón en modo relativo, así que por defecto se captura (como `autolock` en DOSBox): clic en
la pantalla para capturarlo y Esc para soltarlo. El botón «Ratón: captura/directo» cambia al modo directo, y la página pasa
a ese modo sola si el navegador no permite capturar el puntero (por ejemplo, dentro de un iframe). También hay un control de
velocidad. Los paquetes generados con `make_jsdos_bundle.py` llevan `autolock=true`.

## Estructura

```
build.py            generador del sitio
data/               contenido (JSON)
src/layout.html     plantilla común con marcadores {{t:clave}}, {{v:var}}, {{raw:bloque}}
src/pages/          contenido de cada página
src/css, src/js     estilos y scripts (sin dependencias)
tools/              bundles de js-dos, descarga del emulador y programas DOS de prueba
vendor/js-dos/      js-dos alojado localmente (opcional)
```

## Transiciones entre páginas

Al cambiar de sala la pantalla se cierra con un efecto clásico y la siguiente se abre con el mismo: iris hacia el
punto donde hiciste clic, estrella, rombo, reloj, persianas, disolución o fundido a negro tramado. Se configuran en
`data/site.json → transitions` (`pool` de efectos, `byTarget` para fijar uno por página, `duration`, `pixel`).
No se reproducen si el sistema pide reducir el movimiento.

## Pruebas

```bash
npm install && npx playwright install chromium   # una vez
python3 build.py && npm test
python3 -m unittest discover -s tests            # pruebas de tools/add_game.py
npm run test:scummvm                             # sala ScummVM con un ScummVM simulado (no hace falta compilarlo)
```

`tests/site.test.js` comprueba las 44 páginas (errores, desbordamiento en móvil y tableta, enlaces internos), resuelve la
aventura de texto en los cuatro idiomas y la sala de restauración, y arranca DOSBox.

## Para agentes de código

- `AGENTS.md`: reglas del proyecto y comandos. `CLAUDE.md` lo importa para Claude Code.
- `MEMORY.md`: decisiones tomadas, estado y pendientes.
- `.claude/skills/`: tareas frecuentes (añadir juegos o idiomas, editar minijuegos, pixel art, juegos DOS, verificar, publicar).
