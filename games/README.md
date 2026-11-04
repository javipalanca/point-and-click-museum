# Carpeta de juegos del servidor

Deja aquí los `.zip` (o `.jsdos`) de los juegos que quieras en la sala DOSBox/ScummVM: el servicio `builder` de
Docker Compose los detecta en unos segundos, los identifica y regenera el sitio (ver «Juegos en el servidor» en el
README principal). Se admiten subcarpetas y un `.json` con el mismo nombre para fijar título, ejecutable, etc.

Esta carpeta existe en el repositorio para que Docker no tenga que crearla (en macOS no puede: «chown … permission
denied»). Su contenido está en `.gitignore`: tus juegos nunca se suben al repositorio. Todo lo que pongas aquí lo
puede descargar cualquier visitante de la web: deja solo juegos que tengas derecho a compartir.

Si prefieres otra carpeta, pon su ruta en `GAMES_DIR` dentro de `.env` (y créala antes de `docker compose up`).
