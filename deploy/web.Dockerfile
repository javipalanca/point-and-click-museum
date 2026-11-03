# Point and Click Museum · nginx serves the site that the builder container writes to the shared volume
# (/site/current, swapped at once on every rebuild) and passes /api/murray/ on to Murray.
FROM nginx:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
