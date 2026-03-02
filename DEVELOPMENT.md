# Timmy Development Environment — Optimized Setup

This guide covers the optimized development environment with **BuildKit layer caching** for Poetry dependencies.

## Quick Start

### First Time Setup (2-3 minutes)

```bash
# Build the dev image with cached layers
DOCKER_BUILDKIT=1 docker compose -f docker-compose.dev-optimized.yml build

# Start the dev environment
docker compose -f docker-compose.dev-optimized.yml up -d

# Enter the container
docker compose -f docker-compose.dev-optimized.yml exec dev bash
```

### Or Use the Makefile

```bash
# Build and start
make -f Makefile.dev build
make -f Makefile.dev up

# Enter shell
make -f Makefile.dev shell

# Run tests
make -f Makefile.dev test

# Watch tests
make -f Makefile.dev test-watch
```

## How It Works

The optimized setup uses **Docker BuildKit** to cache layers:

1. **Stage 1: Base** — Installs Python 3.12 and Poetry (cached)
   - Runs once, reused across all builds
   - Uses `--mount=type=cache` for pip downloads

2. **Stage 2: Dependencies** — Exports and installs all packages
   - Only rebuilds when `pyproject.toml` or `poetry.lock` changes
   - Uses `--mount=type=cache` for Poetry and pip caches

3. **Stage 3: Development** — Adds source code and dev tools
   - Changes frequently, but doesn't invalidate dependency cache
   - Bind-mounted volumes for hot-reload

## Performance

| Scenario | Time |
| :--- | :--- |
| **First build** (no cache) | ~2-3 minutes |
| **Rebuild after code change** | ~10-15 seconds |
| **Rebuild after dependency change** | ~1-2 minutes |
| **Rebuild with full cache** | ~5-10 seconds |

## Development Workflow

### Run Tests

```bash
# In container
pytest tests/ -v

# Or from host
make -f Makefile.dev test
```

### Watch Tests

```bash
# In container
pytest-watch tests/ -- -v

# Or from host
make -f Makefile.dev test-watch
```

### Interactive Development

```bash
# Enter shell
make -f Makefile.dev shell

# Code changes are hot-reloaded
# Edit src/ or tests/ on your host, changes appear in container
```

### Start Services

```bash
# Redis is included for testing event bus and task queue
docker compose -f docker-compose.dev-optimized.yml up -d

# Check services
docker compose -f docker-compose.dev-optimized.yml ps
```

## Troubleshooting

### BuildKit Not Available

If you get an error about BuildKit, enable it:

```bash
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
```

### Clear Cache and Rebuild

```bash
# Full clean
make -f Makefile.dev clean

# Or manual
docker compose -f docker-compose.dev-optimized.yml down -v
rm -rf .docker-buildkit-cache
docker compose -f docker-compose.dev-optimized.yml build --no-cache
```

### Check Layer Cache

```bash
# See what layers are cached
docker compose -f docker-compose.dev-optimized.yml build --progress=plain
```

## Environment Variables

The dev container sets:

- `PYTHONUNBUFFERED=1` — Immediate output
- `PYTHONDONTWRITEBYTECODE=1` — No .pyc files
- `TIMMY_DEV_MODE=1` — Development mode flag
- `PYTHONPATH=/app/src:/app/tests` — Module discovery

## Volumes

| Mount | Purpose |
| :--- | :--- |
| `./src:/app/src` | Source code (hot-reload) |
| `./tests:/app/tests` | Tests (hot-reload) |
| `./static:/app/static` | Static assets |
| `timmy-dev-data:/app/data` | Persistent data |

## Next Steps

- See [REFACTORING_PLAN.md](REFACTORING_PLAN.md) for the 10 darlings being killed
- Run tests: `make -f Makefile.dev test`
- Enter shell: `make -f Makefile.dev shell`
