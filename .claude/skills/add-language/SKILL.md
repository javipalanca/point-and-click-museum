---
name: add-language
description: Añade un idioma nuevo al Point and Click Museum (además de es, en, de, fr) o revisa traducciones incompletas. Úsala cuando pidan otro idioma, corregir traducciones o completar textos que faltan.
---

# Añadir un idioma

1. `data/site.json → languages`: añade `{ "code": "it", "label": "IT", "name": "Italiano", "locale": "it_IT" }`.
2. Copia `data/i18n/en.json` a `data/i18n/<code>.json` y traduce **todas** las claves (incluidas `page_<id>_title`,
   `page_<id>_meta`, `langHintText`, `langHintLink`). Mantén los marcadores `{score}`, `{name}`, `{n}`… intactos.
3. Ejecuta `python3 build.py --check`: lista cada texto localizado sin la nueva clave. Tradúcelos en:
   `timeline.json`, `studios.json`, `engines.json`, `techniques.json`, `hero.json`, `arcade.json`, `minigames/*.json`.
4. La aventura de texto necesita además un bloque `vocab.<code>` en `data/minigames/text-adventure.json`:
   `stop` (artículos/preposiciones), `verbs`, `dirs` y `nouns`. Escribe las palabras sin tildes (se normalizan) e
   incluye varios sinónimos y formas verbales (infinitivo e imperativo). Los verbos de dos palabras («turn on») van
   como frase; también funciona el verbo separable al final («mach … an»).
5. Añade la solución completa del idioma en `SOLUTIONS` de `tests/site.test.js` y en `LANGS`.
6. `python3 build.py && npm test`. Revisa una captura en móvil: los idiomas con palabras largas (alemán) pueden desbordar.
