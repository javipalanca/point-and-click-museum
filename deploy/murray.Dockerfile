# Point and Click Museum · Murray, the talking skull (chat API). Standard library only, no pip install.
# Only reachable through the web container; it calls your OpenAI-compatible model server.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    MURRAY_PORT=8080 MURRAY_TRUST_PROXY=1 MURRAY_DATA=/app/data
WORKDIR /app
RUN useradd --system --no-create-home murray && mkdir /stats && chown murray /stats
COPY server/ server/
COPY data/site.json data/timeline.json data/studios.json data/engines.json data/techniques.json data/murray.json data/
COPY data/murray_kb/ data/murray_kb/
USER murray
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/murray/health')"
CMD ["python", "server/murray.py"]
