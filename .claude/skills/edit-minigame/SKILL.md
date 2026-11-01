---
name: edit-minigame
description: Modifica o crea puzles de los minijuegos del Point and Click Museum (aventura de texto, sala de restauración, caza del píxel, cronología) usando el motor de reglas y las primitivas de escena. Úsala para cambiar puzles, objetos, salas, escenas o dificultad.
---

# Editar minijuegos

Los minijuegos se definen en `data/minigames/*.json`; el código (`src/js/games.js`, `rules.js`, `scene.js`) es genérico.

## Motor de reglas (aventura de texto y sala de restauración)

Gana la **primera** regla que coincide, así que pon las específicas (con `if`) antes que las generales.

```json
{ "verb": "use" | ["open","push"], "noun": "door" | ["hatch", null], "item": "key",
  "room": "basement", "arg": "1976" | "none",
  "if": ["flag", "!flag", "has:item", "room:id", "count:c>=2"],
  "do": ["set:f", "unset:f", "give:i", "remove:i", "drop:i", "inc:c", "award:<clave>", "sound:open|bad|click", "look", "win"],
  "say": {"es": "...", ...}  |  "sayList": [...], "counter": "c" }
```

- `noun` coincide con el nombre o con el segundo nombre; `null` = sin nombre. `item` solo en la sala (usar X con Y; se prueba en ambos sentidos).
- `win` concede el premio del juego (`award` del JSON); `award:<clave>` debe existir en `site.json → score.awards` y la suma total debe seguir siendo 100.
- Aventura de texto: salas en `rooms` (`desc` como fragmentos condicionales, `exits`, `scenery`, `darkUnless`), objetos en `items` con `at`.
- Sala de restauración: `spots` (zonas clicables, la primera de la lista tiene prioridad), `items` (inventario con `icon` de sprites), `verbs`.

## Primitivas de escena (`scene` / `foreground`)

`r`, `stripes`, `grad`, `books`, `sprite`, `glow`, `px`; todas aceptan `if`, `hot` (id de spot) y `hc` (color al pasar el ratón).
Están documentadas en la cabecera de `src/js/scene.js`. Coordenadas en píxeles de la escena (320×150).

## Caza del píxel y cronología

Parámetros en `pixel-hunt.json` (rondas, tiempo, `clutter`, `darkness`, `torchRadius`, `hitTolerance`) y `chronology.json` (`count`).

## Comprobar

1. `python3 build.py` (valida awards y salidas entre salas).
2. Juega el puzle completo en los cuatro idiomas; actualiza las soluciones de `tests/site.test.js` si cambian.
3. `npm test` y una captura de la escena si cambiaste gráficos.
