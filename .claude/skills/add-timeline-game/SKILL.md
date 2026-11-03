---
name: add-timeline-game
description: Añade o corrige un juego en la línea temporal del Point and Click Museum (data/timeline.json) con textos en los cuatro idiomas, época, enlace externo e imágenes reales (portada y captura) con su fuente. Úsala cuando pidan añadir, quitar o corregir una aventura gráfica de la cronología.
---

# Añadir un juego a la línea temporal

1. Abre `data/timeline.json`. Cada juego tiene esta forma (el orden del fichero da igual: se ordena por año):

```json
{ "id": "kebab-case-unico", "year": 1995, "title": "Título original", "studio": "Estudio · Autores",
  "engine": "Motor", "era": "golden", "link": "https://en.wikipedia.org/wiki/...",
  "text": {
    "es": { "d": "Descripción (1–2 frases).", "f": "Curiosidad (1 frase)." },
    "en": { "d": "...", "f": "..." }, "de": { "d": "...", "f": "..." }, "fr": { "d": "...", "f": "..." } } }
```

2. Reglas:
   - `era` debe existir en `eras` (`text`, `parser`, `golden`, `3d`, `revival`, `now`) y encajar con `year`.
   - Nada de iconos de pixel art inventados para juegos reales: la imagen es la portada real (ver paso 3).
   - `studio`: la parte antes de « · » se muestra en la tarjeta; después van los autores.
   - Solo hechos verificables. Si no estás seguro de un dato (fecha, motor, autor), dilo al usuario en vez de inventarlo.
   - `link`: artículo de Wikipedia en inglés o web oficial. Comprueba que la URL existe si tienes red.
   - Textos breves y naturales en cada idioma, no traducciones literales. Usa «» en es/fr y „“ en de.
3. Imágenes: añade en `data/media.json → items` una portada (`role: cover`, `rights: boxart`) y, si puedes, una
   captura (`role: screenshot`, `rights: screenshot`). Fuentes, por orden de preferencia:
   `github:libretro-thumbnails/<DOS|ScummVM|…>@<commit>/Named_Boxarts/<fichero>.png` (busca el nombre exacto en el
   repositorio y comprueba que la imagen es de ese juego y edición, no de un port o remake) o `wikipedia:en:<Artículo>`.
   Ejecuta `python3 tools/fetch_media.py --only games/<id>` y mira la imagen antes de darla por buena.
   Añade el id a `games` del estudio en `studios.json` si el estudio está en el museo.
4. Si el juego merece un estudio o motor nuevo, añádelo también en `studios.json` / `engines.json`.
5. Ejecuta `python3 build.py` (sin avisos) y `npm test`. La prueba de cronología usa estos juegos automáticamente.
6. Commit: «Añade <título> a la línea temporal». Actualiza MEMORY.md si cambia el recuento de juegos.
