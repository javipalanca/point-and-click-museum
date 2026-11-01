---
name: add-timeline-game
description: Añade o corrige un juego en la línea temporal del Point and Click Museum (data/timeline.json) con textos en los cuatro idiomas, icono, época y enlace externo. Úsala cuando pidan añadir, quitar o corregir una aventura gráfica de la cronología.
---

# Añadir un juego a la línea temporal

1. Abre `data/timeline.json`. Cada juego tiene esta forma (el orden del fichero da igual: se ordena por año):

```json
{ "id": "kebab-case-unico", "year": 1995, "title": "Título original", "studio": "Estudio · Autores",
  "engine": "Motor", "era": "golden", "icon": "skull", "link": "https://en.wikipedia.org/wiki/...",
  "text": {
    "es": { "d": "Descripción (1–2 frases).", "f": "Curiosidad (1 frase)." },
    "en": { "d": "...", "f": "..." }, "de": { "d": "...", "f": "..." }, "fr": { "d": "...", "f": "..." } } }
```

2. Reglas:
   - `era` debe existir en `eras` (`text`, `parser`, `golden`, `3d`, `revival`, `now`) y encajar con `year`.
   - `icon` debe existir en `data/sprites.json → sprites` (si hace falta uno nuevo, usa la skill `pixel-art`).
   - `studio`: la parte antes de « · » se muestra en la tarjeta; después van los autores.
   - Solo hechos verificables. Si no estás seguro de un dato (fecha, motor, autor), dilo al usuario en vez de inventarlo.
   - `link`: artículo de Wikipedia en inglés o web oficial. Comprueba que la URL existe si tienes red.
   - Textos breves y naturales en cada idioma, no traducciones literales. Usa «» en es/fr y „“ en de.
3. Si el juego merece un estudio o motor nuevo, añádelo también en `studios.json` / `engines.json`.
4. Ejecuta `python3 build.py` (sin avisos) y `npm test`. La prueba de cronología usa estos juegos automáticamente.
5. Commit: «Añade <título> a la línea temporal». Actualiza MEMORY.md si cambia el recuento de juegos.
