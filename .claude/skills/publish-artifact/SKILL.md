---
name: publish-artifact
description: Publica o actualiza el Point and Click Museum como Artifact de claude.ai desde una sesión de Claude. Úsala cuando pidan publicar, compartir o actualizar la versión online en Claude.
---

# Publicar como Artifact

1. Verifica antes (skill `verify-site`).
2. Exporta: `python3 tools/export_artifact.py --out <scratchpad>/artifact > <scratchpad>/files.json`
   (enlaces a `index.html`, bundles dentro de `games/bundles.js`, `index.html` raíz sin esqueleto).
3. Publica con la herramienta Artifact: `file_path` = `<scratchpad>/artifact/index.html`, `root` = `<scratchpad>/artifact`,
   `files` = la lista del JSON. Para actualizar el existente usa `url` del Artifact guardado en MEMORY.md.
   Título fijo: «Point and Click Museum». Icono solo en la primera publicación.
4. Recuerda al usuario que el Artifact es privado hasta que lo comparta desde claude.ai.
5. Producción (GitHub Pages, Netlify…): `python3 build.py --base-url https://dominio-real` y sube `dist/`.
