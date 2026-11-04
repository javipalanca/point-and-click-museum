# Point and Click Museum · download proxy of the DOSBox/ScummVM room (server/games.py). Standard library only.
# Brings a "playable" game of the catalogue from ScummVM or Internet Archive the first time a visitor opens it,
# checks it, turns it into a js-dos bundle or ScummVM data, and keeps it in a size-limited cache.
# Also serves the control panel (/admin/, server/admin.py) when ADMIN_USER and ADMIN_PASSWORD are set.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 GAMES_PORT=8081 GAMES_TRUST_PROXY=1 \
    PCM_CATALOG=/catalog/catalog.json GAMES_CACHE=/games-cache
WORKDIR /app
COPY server/games.py server/admin.py server/stats.py server/
COPY server/admin/ server/admin/
COPY tools/ tools/
COPY vendor/scummvm/ vendor/scummvm/
COPY data/ data/
EXPOSE 8081
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/api/games/health')"
CMD ["python", "server/games.py"]
