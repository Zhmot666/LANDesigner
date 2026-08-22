FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    "fastapi>=0.110" \
    "uvicorn>=0.27" \
    "psycopg[binary]>=3.1"

COPY server/ server/

ENV PYTHONPATH=/app

EXPOSE 8765

HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health')" || exit 1

CMD ["python", "-m", "server", "--host", "0.0.0.0", "--port", "8765"]
