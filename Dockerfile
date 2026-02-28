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

FROM python:3.12-slim AS base

# ── System deps ──────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc curl fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps (install before copying src for layer caching) ───────────────
# Copy only pyproject.toml first so Docker can cache the dep-install layer.
# The editable install (-e) happens after src is copied below.
COPY pyproject.toml .

# Create a minimal src layout so `pip install` can resolve the package metadata
# without copying the full source tree (preserves Docker layer caching).
RUN mkdir -p src/timmy src/timmy_serve src/self_tdd src/dashboard && \
    touch src/timmy/__init__.py src/timmy/cli.py \
          src/timmy_serve/__init__.py src/timmy_serve/cli.py \
          src/self_tdd/__init__.py src/self_tdd/watchdog.py \
          src/dashboard/__init__.py src/config.py

RUN pip install --no-cache-dir -e ".[swarm,telegram]"

# ── Application source ───────────────────────────────────────────────────────
# Overwrite the stubs with real source code
COPY src/ ./src/
COPY static/ ./static/

# Create data directory (mounted as a volume in production)
RUN mkdir -p /app/data

# ── Non-root user for production ─────────────────────────────────────────────
RUN groupadd -r timmy && useradd -r -g timmy -d /app -s /sbin/nologin timmy \
    && chown -R timmy:timmy /app
# Ensure static/ and data/ are world-readable so bind-mounted files
# from the macOS host remain accessible when running as the timmy user.
# Docker Desktop for Mac bind mounts inherit host permissions, which may
# not include the container's timmy UID — chmod o+rX fixes 403 errors.
RUN chmod -R o+rX /app/static /app/data
USER timmy

# ── Environment ──────────────────────────────────────────────────────────────
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# ── Healthcheck ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Default: run the dashboard ───────────────────────────────────────────────
CMD ["uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", "8000"]
