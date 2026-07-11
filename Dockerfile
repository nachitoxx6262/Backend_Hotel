# Backend Dockerfile para FastAPI — multi-stage
# ── Stage 1: builder (compila wheels con toolchain) ──────────────
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ── Stage 2: runtime (sin toolchain de build) ────────────────────
FROM python:3.11-slim

WORKDIR /app

# Solo runtime deps: curl para healthcheck, postgresql-client para migraciones
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias desde los wheels precompilados
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# Copiar código de la aplicación
COPY . .

# Usuario no-root
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

# Gunicorn con workers uvicorn: escala CPU y no bloquea en requests lentos.
# WEB_CONCURRENCY (default 3) permite ajustar la cantidad de workers por entorno.
ENV WEB_CONCURRENCY=3
CMD ["sh", "-c", "gunicorn main:app --worker-class uvicorn.workers.UvicornWorker --workers ${WEB_CONCURRENCY:-3} --bind 0.0.0.0:8000 --timeout 60 --access-logfile - --error-logfile -"]
