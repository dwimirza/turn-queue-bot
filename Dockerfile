FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    DB_PATH=/data/queue.db \
    TZ=Asia/Jakarta

WORKDIR /app

# Run as an unprivileged user; /data is a volume and inherits this ownership.
RUN useradd --create-home --uid 10001 bot \
    && mkdir -p /data \
    && chown bot:bot /data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=bot:bot core ./core
COPY --chown=bot:bot bot ./bot
COPY --chown=bot:bot scripts ./scripts
COPY --chown=bot:bot schema.sql .

USER bot

CMD ["python", "-m", "bot.main"]
