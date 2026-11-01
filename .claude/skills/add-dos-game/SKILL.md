---
name: add-dos-game
description: Añade juegos jugables a la sala DOSBox/ScummVM del Point and Click Museum (programas MS-DOS con js-dos o datos de juegos con ScummVM web), revisa la configuración de los emuladores o problemas de ratón. Úsala cuando pidan añadir juegos, compilar ScummVM o arreglar la sala de juegos.
---

# Añadir un juego a la sala DOSBox

## Colección personal (lo normal): desde el zip descargado

```bash
python3 tools/add_game.py ~/Downloads/juego.zip [--title --year --studio --exe --cycles --icon --desc]
python3 tools/add_game.py ~/Downloads/*.zip --yes      # en lote
python3 tools/add_game.py --list | --remove <id>
python3 build.py
```

Escribe `assets/games/<id>.jsdos` y `data/arcade.local.json`, ambos en `.gitignore`. Nunca los añadas al repositorio
ni los publiques: los builds públicos (`tools/export_artifact.py`, `build.py --no-local`) los excluyen.
Si el ejecutable elegido no es el correcto, repite con `--exe RUTA/PROGRAMA.EXE --force`. Si el juego necesita
instalarse, instálalo antes en DOSBox de escritorio y comprime la carpeta instalada.

## ScummVM

- `add_game.py` detecta el motor (firmas de ficheros en `SCUMMVM_SIGNATURES`; mantén la copia JS de `src/js/arcade.js`
  sincronizada si añades motores). Fuerza con `--engine`.
- El motor se compila con `tools/build_scummvm.sh` (variables `SCUMMVM_VERSION`, `ENGINES`). Si añades un motor a
  `ENGINES`, añade su firma en ambos detectores y, si sus plugins se llaman distinto, revisa `wanted()` en `src/scummvm/player.js`.
- Prueba la integración sin compilar: `npm run test:scummvm` (usa `tests/fixtures/fake-scummvm`).
- Con el build real, prueba al menos Beneath a Steel Sky (zip oficial de scummvm.org) en escritorio y móvil.

## Juegos versionados (solo redistribuibles)

1. **Licencia primero.** Solo software redistribuible: freeware con permiso de distribución, dominio público o propio.
   Nunca abandonware ni juegos comerciales. Si no está claro, pregunta al usuario y no lo incluyas.
2. Empaqueta los ficheros DOS (carpeta o zip) indicando el ejecutable:
   ```bash
   python3 tools/make_jsdos_bundle.py ruta/juego --exe JUEGO.EXE --out assets/games/juego.jsdos [--cycles 20000]
   ```
   El `dosbox.conf` generado monta el juego como `C:`, activa `autolock=true` (captura del ratón) y SB16.
3. Añade la entrada a `data/arcade.json → games`:
   ```json
   { "id": "juego", "title": "Título", "year": 1993, "studio": "Estudio", "icon": "cd",
     "bundle": "games/juego.jsdos", "license": "Freeware", "source": "https://…",
     "desc": { "es": "…", "en": "…", "de": "…", "fr": "…" } }
   ```
   Todo `assets/` se copia a `dist/`. Sin `bundle`, la tarjeta muestra «falta el paquete».
4. `python3 build.py && npm test`, y prueba el juego a mano en un navegador de escritorio: el ratón en modo captura
   (clic en la pantalla, Esc para soltar) y en modo directo.

## Ratón

- Los juegos DOS usan ratón relativo: el modo captura (pointer lock) es el fiable. `src/js/arcade.js` cambia solo a modo
  directo si llega `pointerlockerror`. La velocidad se ajusta con `setMouseSensitivity`.
- `tools/dos/PAINT.COM` (fuente `paint.asm`, `nasm -f bin`) sirve para probar el ratón: botón izquierdo dibuja.
- En pruebas automáticas (Playwright) el pointer lock no genera movimiento relativo: prueba el modo directo allí.
