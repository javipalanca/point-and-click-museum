# Point and Click Museum · builds the static site and keeps it up to date with the games inbox.
# It watches /inbox (your GAMES_DIR on the server) and rebuilds into /site/current, which the web container serves.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /src
COPY . .
# PUBLIC=1 (default) leaves out the local collection that may be in the build context (assets/games,
# assets/scummvm, data/arcade.local.json); the games you drop in the inbox are always included.
ARG PUBLIC=1
RUN if [ "$PUBLIC" = "1" ]; then rm -rf assets/games assets/scummvm data/arcade.local.json; fi && python3 build.py --check
ENV BASE_URL=http://localhost:8080 GAMES_WATCH=15
HEALTHCHECK --interval=10s --timeout=3s --start-period=120s CMD test -f /site/current/index.html
CMD ["sh", "-c", "exec python3 tools/games_inbox.py /inbox --site /site --cache /cache --watch \"$GAMES_WATCH\" --base-url \"$BASE_URL\""]
