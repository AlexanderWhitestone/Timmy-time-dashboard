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

FROM python:3.12-slim

# ── System deps ──────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps (install before copying src for layer caching) ───────────────
COPY pyproject.toml .

# Install production deps only (no dev/test extras in the image)
RUN pip install --no-cache-dir \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.32.0" \
        "jinja2>=3.1.0" \
        "httpx>=0.27.0" \
        "python-multipart>=0.0.12" \
        "aiofiles>=24.0.0" \
        "typer>=0.12.0" \
        "rich>=13.0.0" \
        "pydantic-settings>=2.0.0" \
        "websockets>=12.0" \
        "agno[sqlite]>=1.4.0" \
        "ollama>=0.3.0" \
        "openai>=1.0.0" \
        "python-telegram-bot>=21.0"

# ── Application source ───────────────────────────────────────────────────────
COPY src/ ./src/
COPY static/ ./static/

# Create data directory (mounted as a volume in production)
RUN mkdir -p /app/data

# ── Environment ──────────────────────────────────────────────────────────────
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# ── Default: run the dashboard ───────────────────────────────────────────────
CMD ["uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", "8000"]
