---
name: find-media
description: Busca y añade imágenes reales (portadas, capturas, logotipos de estudios y motores) al Point and Click Museum, con su fuente fijada y verificada. Úsala cuando falte una portada o un logo, cuando pidan «buscar imágenes», «poner la portada real», «buscar en Google Images» o revisar que una imagen sea la correcta.
---

# Buscar imágenes reales para el museo

El museo solo muestra imágenes reales con su procedencia exacta (regla 12 de `AGENTS.md`). Nunca dibujes una portada
ni un logo «parecido»: si no hay imagen fiable, la ficha se queda con texto o monograma.

## 1. Buscar candidatos (de más a menos fiable)

1. **Repositorios con historial fijo** (funcionan incluso en la sesión en la nube, que solo deja salir a GitHub):
   ```bash
   python3 tools/find_media.py "Título del juego" --kind cover        # portadas (libretro-thumbnails)
   python3 tools/find_media.py "Título del juego" --kind screenshot   # capturas (libretro + scummvm-web)
   python3 tools/find_media.py "Editora" --kind logo                  # logos (HVR88/Monochrome-Gaming-Logos)
   ```
   - `libretro-thumbnails/<plataforma>`: el nombre del fichero dice la edición; prefiere DOS/ScummVM (versión
     original de PC) y luego Amiga, Atari ST, Spectrum… Las consolas solo si el juego salió allí primero.
   - `scummvm/scummvm-web` (`public_html/data/screenshots/<motor>/<juego>/…_full.png`): capturas oficiales de
     ScummVM, muy útiles para interfaces (verbos, inventarios) y para juegos AGS modernos.
   - Repositorios oficiales de motores (ScummVM, AGS, Godot…) para sus logos, con su licencia.
2. **Wikipedia / Wikimedia Commons** (portada de la ficha del juego, logo de Wikidata P154):
   `"src": "wikipedia:en:Título del artículo"` o `"commons:File:Nombre.svg"`. `tools/fetch_media.py` guarda licencia,
   autor y si la imagen es no libre. En la nube estos dominios suelen estar bloqueados: ejecútalo en local o pide al
   usuario que permita `en.wikipedia.org`, `commons.wikimedia.org`, `upload.wikimedia.org` y `www.wikidata.org`.
3. **Búsqueda web** (`WebSearch`, el equivalente a «buscar en Google Images»): sirve para *localizar* la imagen
   y su fuente (web oficial, kit de prensa, Wikipedia). Si el host no es accesible, apunta la URL en el resumen
   para el usuario; no inventes ni redibujes la imagen.

## 2. Registrar la imagen

Añade a `data/media.json → items`:
```json
{ "group": "games|studios|engines|techniques", "id": "<id de la ficha>", "role": "cover|screenshot|logo",
  "src": "github:owner/repo@<commit>/ruta.png", "rights": "boxart|screenshot|logo" }
```
- Logos redibujados (no el fichero original de la empresa): `"recreation": true`; si son blancos, `"plate": "dark"`.
- Para reutilizar una imagen en otra ficha usa `refs` (p. ej. el motor SCUMM muestra una captura de Monkey Island).

Descarga: `python3 tools/fetch_media.py --only games/<id>` (reduce y cuantiza; las capturas de pixel art se
reducen por un factor entero para que los píxeles sigan nítidos).

## 3. Verificar (obligatorio)

- **Mira la imagen** (`Read` sobre `assets/media/...` o una hoja de contactos con varias). Comprueba que es el juego,
  la edición y la plataforma correctos. Ejemplos ya descartados: la «portada» de Colossal Cave era un port de C64
  de los 80; la de «Edna» era otro juego.
- Si la edición no es la original (remasterización, reedición, consola), se acepta solo si el crédito lo dice:
  el nombre del fichero de libretro aparece en el pie de la imagen.
- `python3 tools/fetch_media.py --check` lista lo que falta; `python3 build.py && npm test` antes del commit.
- Commit: «Añade la portada de <juego>» y actualiza `MEMORY.md → Pendiente` si quedan imágenes sin fuente.
