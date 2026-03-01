# ── Timmy Time — agent image ────────────────────────────────────────────────
#
# Serves two purposes:
#   1. `make docker-up`    → runs the FastAPI dashboard (default CMD)
#   2. `make docker-agent` → runs a swarm agent worker (override CMD)
#
# Build:  docker build -t timmy-time:latest .
# Dash:   docker run -p 8000:8000 -v $(pwd)/data:/app/data timmy-time:latest
# Agent:  docker run -e COORDINATOR_URL=http://dashboard:8000 \
#                    -e AGENT_NAME=Worker-1 \
#                    timmy-time:latest \
#                    python -m swarm.agent_runner --agent-id w1 --name Worker-1

# ── Stage 1: Builder — export deps via Poetry, install via pip ──────────────
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install Poetry + export plugin (only needed for export, not in runtime)
RUN pip install --no-cache-dir poetry poetry-plugin-export

# Copy dependency files only (layer caching)
COPY pyproject.toml poetry.lock ./

# Export pinned requirements and install with pip cache mount
RUN poetry export --extras swarm --extras telegram --extras discord --without-hashes \
        -f requirements.txt -o requirements.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ───────────────────────────────────────────────────────
FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# ── Application source ───────────────────────────────────────────────────────
COPY src/ ./src/
COPY static/ ./static/

# Create data directory (mounted as a volume in production)
RUN mkdir -p /app/data

# ── Non-root user for production ─────────────────────────────────────────────
RUN groupadd -r timmy && useradd -r -g timmy -d /app -s /sbin/nologin timmy \
    && chown -R timmy:timmy /app
# Ensure static/ and data/ are world-readable so bind-mounted files
# from the macOS host remain accessible when running as the timmy user.
RUN chmod -R o+rX /app/static /app/data
USER timmy

# ── Environment ──────────────────────────────────────────────────────────────
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# ── Healthcheck ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Default: run the dashboard ───────────────────────────────────────────────
CMD ["uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", "8000"]
