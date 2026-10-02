# ==============================================================================
# ThermalIntel V2 Production Backend Container
# ==============================================================================
FROM python:3.11-slim-bookworm AS runtime

# Security and deterministic runtime environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    HOST=0.0.0.0 \
    ENVIRONMENT=production \
    LOG_FORMAT=json \
    LOG_LEVEL=INFO \
    DATABASE_PATH=/app/data/thermalintel.db \
    CACHE_DIR=/app/data/cache \
    DATA_MODE=demo

# Create unprivileged system user and group
RUN groupadd -g 10001 thermalintel && \
    useradd -u 10001 -g thermalintel -s /bin/bash -m thermalintel

WORKDIR /app

# Install dependencies in a single lean layer
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code and seed/sample data
COPY services/ ./services/
COPY data/ ./data/
COPY scripts/ ./scripts/
COPY observability/ ./observability/

# Create persistent state directories and set non-root ownership
RUN mkdir -p /app/data/cache /app/data/raw /app/data/quarantine && \
    chown -R thermalintel:thermalintel /app

# Switch to unprivileged runtime user
USER thermalintel

# Declare persistence volume for SQLite database and cached assets
VOLUME ["/app/data"]

EXPOSE 8000

# Health check using native Python health probe (no external curl dependency required)
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -m services.observability.health --type=readiness || exit 1

# Graceful signal propagation to uvicorn
CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "15"]
