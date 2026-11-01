---
name: verify-site
description: Construye y verifica el Point and Click Museum (validación de datos, pruebas Playwright, capturas en escritorio y móvil). Úsala antes de cada commit o cuando pidan comprobar que todo funciona.
---

# Verificar el sitio

1. `python3 build.py` — debe terminar sin `warning:` ni `error:` (traducciones, sprites, awards, páginas).
2. `npm test` — comprueba las 44 páginas (errores JS, desbordamiento, enlaces internos), móvil/tableta,
   las soluciones de la aventura de texto en los 4 idiomas, la sala de restauración y el arranque de DOSBox.
   Primera vez: `npm install && npx playwright install chromium`.
3. Si hubo cambios visuales, haz **una** captura de la página afectada a 1280×900 y en `iPhone 13`
   (Playwright `devices`), y revísala: textos cortados, solapes con la barra de verbos, contraste.
4. Enlaces externos: si hay red, comprueba con `curl -sIL` que las URLs nuevas devuelven 200.
5. Informa de lo que pasó y de lo que no se pudo comprobar (por ejemplo, el pointer lock real del ratón).
