# -- Builder stage ----------------------------------------------------------
# Pin to a specific digest for reproducible builds in CI, e.g.:
#   FROM python:3.12-slim@sha256:<digest> AS builder
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install dependencies first (layer caching optimisation)
COPY backend/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /build/requirements.txt

# -- Runtime stage ----------------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL maintainer="Aurion Team" \
      version="0.5.0" \
      description="Aurion Market Intelligence API"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN groupadd --system appgroup && \
    useradd --system --gid appgroup --no-create-home appuser

WORKDIR /app

# Copy application code
COPY . .

# Own the workdir so the app can write to artifacts if needed
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
