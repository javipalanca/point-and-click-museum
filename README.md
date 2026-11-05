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

### Catálogo automático (ScummVM, Internet Archive, GOG)

`tools/sync_catalog.py` escribe `data/catalog.json` (en el servidor, cada `CATALOG_EVERY` horas) con una ficha por
juego: todas las aventuras de la línea temporal y las que encuentra en las fuentes. Cada ficha tiene uno de tres
estados, que se ven en la sala DOSBox (con filtro) y en la línea temporal:

| Estado | Qué significa |
|---|---|
| **Jugable** | una edición con distribución autorizada (freeware, demo, shareware, dominio público, licencia libre o permiso documentado) que ha pasado las comprobaciones automáticas. Se descarga **bajo demanda** cuando alguien la abre |
| **Pendiente de validar** | localizada automáticamente, pero sin confirmar sus derechos o su compatibilidad (motor no compilado, descarga aún no comprobada…) |
| **Solo ficha** | documentada, sin distribución autorizada: los juegos comerciales, también los llamados «abandonware» |

- **ScummVM**: los juegos freeware y las demos que distribuye su web con permiso de los autores (`scummvm-web`, fijado a
  un commit), solo de sus motores de aventuras. Son la fuente de juegos jugables.
- **Internet Archive**: `advancedsearch.php` para descubrir aventuras de MS-DOS, `metadata/{id}` para ficheros,
  sumas md5/sha1 y el programa que arranca (`emulator_start`), y `download/{id}/{fichero}` para descargar. **Un
  elemento de Internet Archive solo es jugable con una licencia explícita en sus metadatos** (Creative Commons o
  dominio público) o cuando lo marcas como disponible en el panel de control (o en `data/catalog.overrides.json`).
  Que lo haya subido alguien no lo autoriza: los juegos comerciales quedan como «solo ficha».
- **GOG.com**: solo para el enlace «Comprar en GOG» de los juegos que aún se venden (búsqueda del catálogo de gog.com,
  coincidencia exacta del título: la *Special Edition* no es el original).
- No se usan **dos.zone** ni **eXoDOS**: distribuyen juegos comerciales sin autorización.

Las comprobaciones (`tools/game_fetch.py`): host permitido, tamaño, suma de control, zip válido, programa DOS que no
sea de Windows (o motor de ScummVM incluido en nuestra compilación). El resultado se convierte en un paquete `.jsdos`
con su `dosbox.conf`, o en los datos de ScummVM sin la carpeta que los envuelve. Cada pasada valida como mucho
`GAMES_VALIDATE_PER_RUN` ediciones nuevas; un fallo de red no cuenta como suspenso y se reintenta.

El navegador no descarga de las fuentes (CORS y la conversión lo impiden): lo hace el **proxy de descarga**
(`server/games.py`, contenedor `games`, ruta `/api/games/<edición>`). Solo sirve ediciones jugables, solo desde
`downloads.scummvm.org` y `archive.org`, guarda como mucho `GAMES_CACHE_MB` en el servidor (lo menos usado sale
primero) y limita las descargas nuevas por IP (`GAMES_RATE` por hora). El navegador guarda los juegos ya descargados
en Cache Storage y las partidas de ScummVM en IndexedDB, así que sobreviven a la siguiente visita.

```bash
python3 tools/sync_catalog.py --validate 0             # refresca las fichas sin descargar nada
python3 tools/sync_catalog.py --only scummvm           # una fuente; las demás se conservan
python3 tools/game_fetch.py beneath-a-steel-sky-full-bass-cd-1-2   # descarga y valida una edición
python3 server/games.py                                 # el proxy en local (puerto 8081)
```

Correcciones a mano (enlace de GOG, ejecutable, permiso de un autor, dejar un juego como solo ficha) en
`data/catalog.overrides.json` o, mejor, desde el **panel de control**; siempre ganan a las fuentes.

### Panel de control (`/admin/`)

Con `ADMIN_USER` y `ADMIN_PASSWORD` en `.env`, el contenedor `games` sirve un panel privado en `/admin/`
(`server/admin.py`, `server/admin/`). Desde él:

- **Resumen**: cuántos juegos hay en cada estado, lanzar una sincronización (fuentes, cuántas ediciones validar,
  reintentar las fallidas) y ver cómo va.
- **Juegos**: los ~1000 juegos localizados (la línea temporal, el catálogo completo de ScummVM e Internet Archive,
  **también los comerciales**), con filtros. En cada edición: **Probar** (el servidor la descarga solo para ti y se
  abre en DOSBox o ScummVM dentro del panel), **Validar** (las comprobaciones automáticas, informativas), **Marcar como
  disponible** / **Retirar de la web** (tu decisión: queda anotado quién y cuándo; nota y enlace opcionales) y
  **Arranque** (ejecutable y `cycles`) y **Eliminar edición** (la sincronización no la vuelve a traer; las eliminadas se
  listan al final de la ficha con «Restaurar»). También el enlace de GOG, dejar un juego como solo ficha y **buscar en Internet Archive**
  para añadir un elemento a un juego que no lo tenía. Cada resultado enlaza a su página de archive.org y tiene **«Ver qué
  contiene»**: lee solo el índice de cada zip (sin descargarlo) y dice si hay un programa de DOS, solo de Windows, solo
  un instalador o datos de ScummVM, con el programa que arranca el juego ya sugerido. Desde ahí, **Probar** ese zip con
  ese programa (no guarda nada) y **Añadir como edición** con lo que has probado (`tools/ia_inspect.py`). Además de zips:
  **imágenes de CD** (.iso: se listan sin descargarlas y DOSBox las monta como unidad D:) y **.7z/RAR** (también dentro de
  un zip con el manual y la portada: se abren al probarlos con el programa 7-Zip, que las imágenes Docker instalan; en
  local, `apt install p7zip-full` o `brew install sevenzip`). Si la búsqueda no lo encuentra, **pega el enlace** de
  archive.org (`/details/…` o `/download/…`) en la misma ficha.
- **Fuentes**, **Descargas y errores** (públicas y del panel, con el motivo) y **Registro** de la sincronización.

Un juego pasa a jugable en la web pública cuando **tú lo marcas como disponible** en el panel (la validación
automática no lo bloquea: si falló, el panel lo avisa), o automáticamente si es freeware, demo o similar y pasa la
validación. Probarlo en el panel no lo publica; retirarlo lo deja de servir al momento. Tus decisiones se guardan en `catalog.admin.json` (volumen `catalog`) y la
sincronización diaria las respeta. Seguridad: sesión en cookie `HttpOnly`/`SameSite=Strict` (`ADMIN_COOKIE_SECURE=1`
detrás de HTTPS), cabecera obligatoria en los POST, bloqueo tras 5 intentos fallidos, `noindex` y fuera de
`robots.txt`. Si no defines usuario y contraseña, el panel no existe. Fuentes y nombres de colecciones en
`data/catalog.sources.json`.

### Detrás de otro proxy (pointandclickle)

Para servirlo en la misma máquina que pointandclickle, con `museum.pointandclickle.com` y una redirección desde
`pointandclickle.com/museum`, usando el Traefik que ya tiene: `deploy/traefik/README.md` (red `edge`,
`docker-compose.edge.yml` y los routers de `deploy/traefik/museum.yml`).

### Estadísticas

Dos capas independientes, apagadas en un build normal (`python3 build.py`) y en el Artifact:

- **Google Analytics 4** (`GA_MEASUREMENT_ID=G-…` en `.env`, o `build.py --ga-id`). Solo se carga si el visitante
  acepta el aviso de cookies (Consent Mode con todo denegado por defecto, sin señales de Google ni publicidad); la
  decisión se recuerda y se cambia desde «Cookies» en el pie. Con GPC o «Do Not Track» no se muestra el aviso ni se carga.
  Los eventos de abajo también llegan a GA como eventos personalizados.
- **Estadísticas propias** (`STATS_URL=/api/stats`, por defecto en Docker; vacío para apagarlas): sin cookies, sin
  nada guardado en el navegador y sin IPs. Los visitantes únicos se cuentan con un hash de IP + navegador con una sal que
  cambia cada día y solo vive en memoria. Se ven en el panel, pestaña «Estadísticas»: visitantes y páginas por día,
  salas, sala de entrada, de dónde llegan (solo el dominio), idiomas, dispositivo, tiempo en cada sala y hasta dónde
  se lee, Core Web Vitals (LCP, INP, CLS, FCP, TTFB), fichas abiertas, juegos arrancados (y con qué emulador), puntos,
  enlaces externos, cambios de idioma, búsquedas del catálogo con o sin resultados, errores de JavaScript; del servidor,
  preguntas a Murray (idioma, sala, respuesta con modelo o sin él, negativas del guardarraíl, errores, latencia de la
  primera palabra y total, nunca el texto) y el proxy de juegos (pedidos, caché, KB servidos, tiempo de preparación,
  errores). Un fichero JSON por día en los volúmenes `stats` y `murray-stats` (`server/stats.py`).

### ScummVM

Muchos juegos no traen `.exe`: son datos que ejecuta ScummVM (Beneath a Steel Sky, Flight of the Amazon Queen,
Drascula, Lure of the Temptress, Dreamweb, Teen Agent, Soltys, los datos de LucasArts/Sierra o los juegos de AGS).
La sala DOSBox incluye un reproductor de ScummVM web (`src/scummvm/player.*`), pero el motor hay que compilarlo una vez:

```bash
tools/build_scummvm.sh      # ScummVM 2.9.1 → vendor/scummvm/ (30–60 min la primera vez; descarga Emscripten)
python3 build.py
```

Por defecto compila los motores de aventura que usa el museo. Para **todos** los motores:

```bash
ENGINES=all tools/build_scummvm.sh            # todos los motores estables, con png, jpeg, freetype, theora, mpeg2…
ENGINES=all-unstable tools/build_scummvm.sh   # también los que ScummVM marca como inestables (pueden no funcionar)
ENGINES=scumm,sky,sword1 tools/build_scummvm.sh   # o una lista concreta
```

Con `ENGINES=all` la compilación tarda unas horas y ocupa ~15 GB en `.cache/`; `configure` deja fuera (y lo dice en
su salida) los motores cuyas bibliotecas no consiga. Al terminar, `vendor/scummvm/ENGINES` lista los motores
realmente compilados; el catálogo lo lee para revalidar los juegos que esperaban su motor. Después, en Docker,
`docker compose up -d --build` (el `builder` y `games` copian `vendor/scummvm/`). Cada plugin es un fichero aparte:
el reproductor solo descarga el del juego que se abre, pero la web generada ocupa más (todos los plugins).

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
server/             Murray: chat con RAG sobre data/ y API compatible con OpenAI
deploy/, docker-compose.yml   imágenes Docker (builder + nginx + Murray) y configuración de nginx
tools/              bundles de js-dos, descarga del emulador y programas DOS de prueba
vendor/js-dos/      js-dos alojado localmente (opcional)
```

## Despliegue con Docker Compose

```bash
cp .env.example .env            # ajusta BASE_URL, PORT y, si quieres, el modelo de Murray
docker compose up -d --build    # http://localhost:8080/
```

Cuatro contenedores:

| Servicio | Qué hace |
|---|---|
| `builder` | genera el sitio con `build.py` en el volumen `site` y lo vuelve a generar cada vez que añades, cambias o quitas un juego de la carpeta de juegos (`tools/games_inbox.py`). Cada build va a una carpeta nueva y se activa de golpe (enlace `current`), así que nadie ve un sitio a medias. Con `PUBLIC=1` (por defecto) deja fuera la colección local que hubiera en el contexto de la imagen |
| `web` | sirve el sitio con nginx: gzip, caché de recursos, cabeceras de seguridad, `/healthz`, y proxy de `/api/murray/` y `/api/games/` con límite de peticiones |
| `games` | panel de control en `/admin/` (si hay `ADMIN_USER`/`ADMIN_PASSWORD`) y proxy de descarga del catálogo (`server/games.py`): trae un juego jugable de ScummVM o Internet Archive la primera vez que alguien lo abre, lo comprueba, lo convierte y lo guarda en una caché limitada. El `builder` además refresca el catálogo cada `CATALOG_EVERY` horas (24 por defecto) |
| `murray` | el chat de Murray (`server/murray.py`, solo biblioteca estándar). No publica puertos: solo se llega a él a través de `web`. Usuario sin privilegios, sistema de ficheros de solo lectura, sin capacidades |

### Juegos en el servidor: deja los zips en una carpeta

```bash
cp ~/Descargas/MiJuego.zip games/      # GAMES_DIR en .env; por defecto ./games junto a docker-compose.yml
# si cambias GAMES_DIR, crea esa carpeta antes de docker compose up (Docker Desktop para Mac no puede crearla)
docker compose logs -f builder         # importing MiJuego.zip · ok: … DOSBox runs MIJUEGO.EXE · built 44 pages
```

En unos segundos (`GAMES_WATCH`, 15 por defecto) el juego aparece en la sala DOSBox, que lista **solo los juegos de
esa carpeta** (sin la demo del museo ni los freeware que no tengas). Cada zip pasa por `tools/add_game.py`: va a
ScummVM si reconoce sus datos y ScummVM está compilado (`vendor/scummvm/` en el servidor antes de `docker compose
build`); si no, a DOSBox con el ejecutable más probable. Después, `tools/identify_game.py` averigua qué juego es: por
los ficheros de datos (`MONKEY2.000`, `TENTACLE.000`, `FT.LA0`, `KQ4DIR`…) y por el nombre del zip y de sus carpetas,
comparados con la línea temporal y el catálogo de ScummVM (unos 1200 juegos). Así obtiene título, año, estudio y, si
el museo tiene ficha, su descripción, un enlace a ella y su portada revisada; si no, la portada de la edición de PC
de libretro-thumbnails (GitHub, fijada a un commit y con su crédito). Si no lo reconoce, sale con el nombre del
fichero. El servidor necesita acceso a `api.github.com` y `raw.githubusercontent.com` para esas portadas; sin red el
juego funciona igual y la portada se vuelve a buscar al día siguiente. Se admiten subcarpetas y
`.jsdos` ya hechos. Los ficheros que aún se están copiando esperan a la siguiente vuelta. Si borras o sustituyes un
zip, el catálogo se actualiza; cada juego se convierte una sola vez (volumen `games-cache`). Para fijar título, año,
estudio, ejecutable o velocidad (o quitar la portada con `"cover": false`), pon al lado un JSON con el mismo nombre
(`MiJuego.json`):

```json
{"title": "Mi Juego", "year": 1993, "studio": "Estudio", "exe": "JUEGO/START.BAT", "cycles": 20000, "license": "Freeware"}
```

Los zips que no se pueden importar (por ejemplo, juegos de Windows) aparecen en el log y se ignoran. **Todo lo que
pongas en esa carpeta se sirve a cualquier visitante**: deja solo juegos que tengas derecho a compartir. Sin Docker:
`python3 tools/games_inbox.py ~/juegos` (vigila la carpeta y regenera `dist/`; `--once` para una sola pasada,
`--all-games` para conservar también la lista del museo). Para ver qué detectaría con un zip:
`python3 tools/identify_game.py MiJuego.zip --cover`.

«Trae tu propio juego» sigue disponible en la sala: el zip se lee y se ejecuta en el navegador del visitante y nunca
se envía al servidor. Debajo de la pantalla hay un control de **volumen** (DOSBox y ScummVM) que se recuerda entre
visitas.

Detrás de un dominio con HTTPS, pon un proxy inverso (Caddy, Traefik, nginx…) delante del puerto `PORT` y define
`BASE_URL=https://tu-dominio` para que canonical, hreflang y sitemap usen la URL buena.

## Murray, la calavera parlante

Un botón abajo a la derecha, en todas las páginas, abre un chat con Murray (la calavera de *The Curse of Monkey
Island*), que responde sobre la historia de las aventuras gráficas a partir de la base de datos del museo:

- **RAG**: `server/knowledge.py` indexa (BM25) los juegos, estudios, motores, épocas y técnicas de `data/*.json` en los
  cuatro idiomas y la base de conocimiento externa de `data/murray_kb/`:
  - `history.json`: artículos sobre la historia del género (orígenes, Sierra, Lucasfilm y SCUMM, Myst, el declive,
    Telltale, Kickstarter, ScummVM, AGS, aventuras españolas, ficción interactiva…) redactados a partir de fuentes
    web, cada uno con sus URL;
  - `scummvm-games.jsonl`: el catálogo de la web de ScummVM (unos 1200 juegos con compañía, año, motor y serie);
  - `wikipedia-<idioma>.jsonl`: fragmentos de Wikipedia en es/en/de/fr de todos los juegos, estudios y motores del
    museo y de los temas de historia del género (CC BY-SA 4.0, con su URL). Se generan con
    `python3 tools/build_murray_kb.py wikipedia` donde Wikipedia sea accesible (en la sesión en la nube no lo era).

  Las fichas más relevantes van en cada petición al modelo, y Murray cita las «vitrinas consultadas» (las externas
  enlazan a su fuente). Una ficha «sobre el museo» deja claro que es un museo virtual sin relación con otros museos.
- **Herramientas**: si el servidor del modelo admite *function calling*, el modelo puede además buscar
  (`search_museum`), leer una ficha (`get_record`) o listar juegos por año, estudio o motor (`list_games`). Si el
  servidor rechaza las herramientas, se reintenta automáticamente solo con RAG.
- **Modelo**: cualquier API compatible con OpenAI (`/v1/chat/completions`): Ollama, vLLM, llama.cpp, LM Studio,
  LocalAI, OpenRouter… Se configura en `.env`:

  ```bash
  MURRAY_LLM_BASE_URL=http://host.docker.internal:11434/v1   # p. ej. Ollama en la misma máquina
  MURRAY_LLM_MODEL=qwen3.8                                   # el nombre del modelo en tu servidor
  MURRAY_LLM_API_KEY=                                        # si tu servidor lo pide
  ```

  Sin URL o sin modelo, Murray responde en «modo vitrina», citando las fichas más parecidas a la pregunta.
  Las etiquetas `<think>…</think>` de los modelos de razonamiento (Qwen) se eliminan; con vLLM puedes desactivar el
  razonamiento con `MURRAY_LLM_EXTRA={"chat_template_kwargs": {"enable_thinking": false}}`.
- **La clave no se filtra**: la URL, la clave y el modelo solo existen como variables de entorno del contenedor
  `murray`. El navegador habla únicamente con `/api/murray/chat` del propio museo; ningún HTML o JS publicado las
  contiene (`npm test` lo comprueba) y el servicio no las registra en los logs. `.env` está en `.gitignore`.
- **Murray te lleva de visita**: con la herramienta `go_to` (o, en modelos sin herramientas, escribiendo
  `[[go:destino]]`, que se retira del texto) Murray cambia de página cuando el visitante se lo pide o acepta su
  propuesta: una sala (`timeline`, `studios`, `arcade`…) o una ficha (`game:loom` abre su ficha en la línea temporal,
  `engine:scumm` inserta el cartucho, `studio:lucasarts` resalta la vitrina, `era:golden`, `technique:cycle`…). El
  servidor valida el destino, el chat anuncia «Rumbo a…», viaja con la transición clásica y sigue abierto en la página
  nueva. Murray sabe en qué sala está el visitante.
- **Streaming**: el modelo responde con `stream: true` y el servidor reenvía cada fragmento al navegador por
  Server-Sent Events (`data: {"delta": …}` y al final `data: {"done": true, "sources": …}`), así que la respuesta se
  escribe mientras Murray mueve la boca. Las llamadas a herramientas también llegan en streaming y el `<think>` de Qwen se
  filtra al vuelo. nginx no almacena la respuesta en búfer. Si el servidor del modelo ignora `stream`, también funciona.
- **Rapidez**: el clasificador de tema corre en paralelo con la respuesta (que se retiene hasta su veredicto) y, por
  defecto, se pide al modelo que no «piense» antes de contestar (`MURRAY_LLM_THINK=0` →
  `chat_template_kwargs.enable_thinking=false`; si el servidor lo rechaza, deja de enviarse). El log indica, por cada
  llamada, los segundos hasta la primera palabra visible, el pensamiento oculto y las herramientas usadas; para medir
  una pregunta: `python3 server/murray.py --probe "¿Qué es SCUMM?"` (en Docker, con `docker compose exec murray`).
- **Solo aventuras gráficas** (`server/guard.py`, `MURRAY_GUARD`): antes de llamar al modelo, unas reglas reconocen
  los mensajes del tema (títulos, estudios, motores y personas de la base de conocimiento, sagas, vocabulario del
  género y objetos, personajes y bromas míticas como el pollo de goma o el grog en cuatro idiomas, saludos), detectan intentos de manipulación («ignora tus instrucciones», «ahora eres…»,
  «dime tu prompt») y las preguntas sobre otros museos. Lo dudoso lo clasifica el propio modelo con una llamada corta
  que ve la respuesta anterior (para que pasen los «¿y quién lo hizo?») y las fichas relacionadas que encuentra la
  búsqueda; en caso de duda deja pasar. También le llegan los mensajes que comparten una expresión con las fichas o los
  artículos de historia («cajas de paseo»), que sin modelo pasan directamente. Lo que queda fuera recibe una negativa de
  Murray sin que el modelo llegue a responder. Además, el prompt prohíbe cualquier otro tema y cada mensaje del
  visitante va con un recordatorio. `MURRAY_GUARD=rules` evita la llamada extra (lo dudoso se rechaza); `off` lo desactiva.
- **Límites**: cuerpo de 16 KB, 12 mensajes de hasta 600 caracteres, `MURRAY_RATE` peticiones por IP cada 10 minutos
  (más el límite de nginx) y `MURRAY_DAILY_LIMIT` llamadas al modelo al día.
- **Sin Docker**: `MURRAY_LLM_BASE_URL=… MURRAY_LLM_MODEL=… python3 server/murray.py` (puerto 8080) y un proxy de
  `/api/murray/` hacia él. En el Artifact o en `python3 -m http.server`, Murray avisa de que no hay servidor.

## Transiciones entre páginas

Al cambiar de sala la pantalla se cierra con un efecto clásico y la siguiente se abre con el mismo: iris hacia el
punto donde hiciste clic, estrella, rombo, reloj, persianas, disolución o fundido a negro tramado. Se configuran en
`data/site.json → transitions` (`pool` de efectos, `byTarget` para fijar uno por página, `duration`, `pixel`).
No se reproducen si el sistema pide reducir el movimiento.

## Pruebas

```bash
npm install && npx playwright install chromium   # una vez
python3 build.py && npm test
python3 -m unittest discover -s tests            # tools/add_game.py y el servidor de Murray (con un modelo simulado)
npm run test:scummvm                             # sala ScummVM con un ScummVM simulado (no hace falta compilarlo)
npm run test:catalog                             # catálogo: línea temporal → Jugar → proxy → ScummVM/DOSBox, caché y partidas
npm run test:admin                               # panel: acceso, probar en DOSBox, validar, permiso con prueba, búsqueda en IA
```

`tests/site.test.js` comprueba las 44 páginas (errores, desbordamiento en móvil y tableta, enlaces internos), resuelve la
aventura de texto en los cuatro idiomas y la sala de restauración, y arranca DOSBox.

## Para agentes de código

- `AGENTS.md`: reglas del proyecto y comandos. `CLAUDE.md` lo importa para Claude Code.
- `MEMORY.md`: decisiones tomadas, estado y pendientes.
- `.claude/skills/`: tareas frecuentes (añadir juegos o idiomas, editar minijuegos, pixel art, juegos DOS, verificar, publicar).
