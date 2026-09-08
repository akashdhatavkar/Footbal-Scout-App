# Containerised FastAPI backend — used for Cloudflare Containers (beta) or any
# standard container runtime (Docker, Kubernetes, Fly.io, etc.).
#
#   docker build -t football-stats-api .
#   docker run --rm -p 8000:8000 football-stats-api
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application and seed corpus.
COPY app ./app
COPY scripts ./scripts
COPY data ./data
COPY ui ./ui

# Expose the FastAPI port.
EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
