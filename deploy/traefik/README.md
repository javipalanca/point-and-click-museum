# El museo detrás del Traefik de pointandclickle (misma máquina)

pointandclickle (cookiecutter-django) ya tiene un Traefik con los puertos 80/443 y los certificados de Let's Encrypt.
No hace falta otro router: ese Traefik también enruta al museo por una red de Docker compartida, `edge`.

| URL | Va a |
|---|---|
| `pointandclickle.com`, `www.pointandclickle.com` | Django de pointandclickle (sin cambios) |
| `museum.pointandclickle.com` | el `web` (nginx) del museo |
| `pointandclickle.com/museum/…` | redirección 301 a `museum.pointandclickle.com/…` |

`/museum` es una redirección y no una copia bajo esa ruta: el museo usa rutas absolutas (`/api/games/`, `/api/stats`,
`/admin/`) y una sola dirección canónica es mejor para el SEO (canonical, hreflang, sitemap).

## 1. DNS y red (una vez)

- Registro `A` (o `CNAME`) de `museum.pointandclickle.com` a la IP del servidor.
- `docker network create edge`

## 2. Museo (`.env`)

```
COMPOSE_FILE=docker-compose.yml:docker-compose.edge.yml
PORT=127.0.0.1:8080
BASE_URL=https://museum.pointandclickle.com
ADMIN_COOKIE_SECURE=1
```

`docker compose up -d --build`. El puerto 8080 queda solo en local (para probar con `curl`); al público se llega por Traefik.

## 3. pointandclickle

a) Copia los bloques de `museum.yml` (esta carpeta) en `compose/production/traefik/traefik.yml`, dentro de
`http.routers`, `http.middlewares` y `http.services`.

b) Crea `production.edge.yml` junto a `production.yml`:

```yaml
services:
  traefik:
    networks: [default, edge]
networks:
  edge:
    external: true
```

c) Reconstruye solo Traefik (el fichero va dentro de su imagen):

```
docker compose -f production.yml -f production.edge.yml up -d --build traefik
```

Let's Encrypt emite el certificado de `museum.pointandclickle.com` en la primera visita (reto HTTP por el puerto 80).

## Notas

- nginx del museo confía en `X-Forwarded-For` solo desde redes privadas de Docker, así que los límites por IP y las
  estadísticas ven al visitante real. Traefik descarta los `X-Forwarded-For` que mande el visitante (probado).
- Arranca primero el museo: si Traefik no encuentra `museum-web`, responde 502 solo en esas rutas.
- Probado en Docker con Traefik 2.2.11 (la versión de pointandclickle) y la configuración de su `traefik.yml`.
