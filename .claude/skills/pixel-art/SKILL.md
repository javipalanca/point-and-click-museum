---
name: pixel-art
description: Crea o mejora sprites, personajes y escenas de pixel art del Point and Click Museum (data/sprites.json, data/characters.json, escenas JSON y dibujo en canvas). Úsala cuando pidan iconos nuevos, personajes, animaciones o mejorar la calidad gráfica.
---

# Pixel art del museo

## Formatos

- **Sprites** (`data/sprites.json`): filas de 12 caracteres; cada carácter es una clave de `palette` y `.` es transparente.
  `build.py` genera `img/sprites/<nombre>.png` a 6× y valida que sean 12×12.
- **Personajes** (`data/characters.json`): `art` = cabeza y torso, 16 columnas; `talk`/`blink` sustituyen filas concretas;
  `legs` define cadera, longitud, colores y zancada (las piernas se dibujan por código en `src/js/characters.js`).
  `PCM.Chars.actor(nombre, x, pies, velocidad)` da `walkTo()`, `say(ms)`, `update()`, `draw(ctx)`.
- **Escenas**: primitivas JSON (ver skill `edit-minigame`) o código canvas en `sections.js` / `scene.js`.

## Criterios de calidad

- Contorno oscuro (`#1a1022`) alrededor de siluetas; luz desde arriba a la izquierda: brillo de 1 px arriba, sombra abajo/derecha.
- 3–4 tonos por material (base, sombra, brillo, contorno). Usa la paleta del sitio (tokens de `style.css` y `sprites.json`).
- Personajes legibles a 1×: ojos de 1 px, rasgos distintivos (gafas, gorro, bigote), sombra en el suelo.
- Tramado (Bayer 4×4) para degradados de cielo, paredes y suelos; nada de degradados suaves salvo luces (`glow`).
- Nada que reproduzca personajes o escenarios de juegos existentes: todo original.

## Flujo de trabajo

1. Dibuja y valida longitudes de fila (un script rápido en Python que compruebe `len(row)`).
2. Previsualiza a 8× en una página HTML temporal con Playwright y mira la captura antes de integrarlo.
3. `python3 build.py && npm test`; captura de la página afectada en escritorio y móvil.
