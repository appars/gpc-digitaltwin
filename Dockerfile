# Use a small Python base
FROM python:3.11-slim

# Optional: faster, reproducible installs
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps (often not required, but useful for builds)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Copy only requirements first (for Docker layer caching)
COPY requirements.txt /app/
RUN pip install -r requirements.txt

# Copy the rest of the app
COPY . /app

# Cloud Run expects the container to listen on $PORT (default 8080)
ENV PORT=8080 \
    PYTHONPATH=/app

# Gunicorn with eventlet worker (WebSockets-friendly)
# -w 1 is enough for demo; bump if needed. Eventlet handles many sockets per worker.
CMD exec gunicorn --bind 0.0.0.0:$PORT \
    --worker-class eventlet --workers 1 \
    --log-level info app:app

