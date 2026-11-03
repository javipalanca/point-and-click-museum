# Point and Click Museum · static site served by nginx.
# Stage 1 builds dist/ with the Python generator (standard library only); stage 2 serves it.
FROM python:3.12-slim AS build
WORKDIR /src
COPY . .
# PUBLIC=1 (default) leaves out your local game collection (assets/games, data/arcade.local.json).
ARG PUBLIC=1
ARG BASE_URL=http://localhost:8080
RUN if [ "$PUBLIC" = "1" ]; then python3 build.py --no-local --base-url "$BASE_URL"; \
    else python3 build.py --base-url "$BASE_URL"; fi

FROM nginx:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
