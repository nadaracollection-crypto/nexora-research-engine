FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1
ENV CHROME_BIN=/usr/bin/chromium
ENV HOME=/tmp

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium chromium-driver \
    ca-certificates fonts-liberation \
    libnss3 libxss1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .


CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 1 --timeout 180 server:app"]
