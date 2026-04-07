# TradingCat V1 — multi-stage production image
# Stage 1: build dependencies in a venv
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install --no-cache-dir .

COPY tradingcat/ tradingcat/
COPY templates/ templates/
COPY static/ static/
RUN /opt/venv/bin/pip install --no-cache-dir -e .

# Stage 2: lean runtime image
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN groupadd -r tradingcat && useradd -r -g tradingcat -d /app tradingcat

WORKDIR /app

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY tradingcat/ tradingcat/
COPY templates/ templates/
COPY static/ static/
COPY scripts/ scripts/
COPY pyproject.toml ./

# Create data directory (will be volume-mounted in production)
RUN mkdir -p /app/data && chown -R tradingcat:tradingcat /app

USER tradingcat

# Default environment
ENV TRADINGCAT_DATA_DIR=/app/data \
    TRADINGCAT_FUTU_ENABLED=false \
    TRADINGCAT_FUTU_HOST=host.docker.internal \
    TRADINGCAT_FUTU_PORT=11111 \
    TRADINGCAT_FUTU_ENVIRONMENT=SIMULATE \
    TRADINGCAT_POSTGRES_ENABLED=false \
    TRADINGCAT_DUCKDB_ENABLED=false \
    TRADINGCAT_SCHEDULER_AUTOSTART=true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/preflight/startup')" || exit 1

ENTRYPOINT ["uvicorn", "tradingcat.main:app", "--host", "0.0.0.0", "--port", "8000"]
