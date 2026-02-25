.PHONY: install install-bigbrain install-creative dev nuke test test-cov test-cov-html watch lint clean help \
        up down logs \
        docker-build docker-up docker-down docker-agent docker-logs docker-shell \
        cloud-deploy cloud-up cloud-down cloud-logs cloud-status cloud-update

VENV        := .venv
PYTHON      := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
PYTEST      := $(VENV)/bin/pytest
UVICORN     := $(VENV)/bin/uvicorn
SELF_TDD    := $(VENV)/bin/self-tdd

# ── Setup ─────────────────────────────────────────────────────────────────────

install: $(VENV)/bin/activate
	$(PIP) install --quiet -e ".[dev]"
	@echo "✓ Ready. Run 'make dev' to start the dashboard."

install-bigbrain: $(VENV)/bin/activate
	$(PIP) install --quiet -e ".[dev,bigbrain]"
	@if [ "$$(uname -m)" = "arm64" ] && [ "$$(uname -s)" = "Darwin" ]; then \
	    $(PIP) install --quiet "airllm[mlx]"; \
	    echo "✓ AirLLM + MLX installed (Apple Silicon detected)"; \
	else \
	    echo "✓ AirLLM installed (PyTorch backend)"; \
	fi

install-creative: $(VENV)/bin/activate
	$(PIP) install --quiet -e ".[dev,creative]"
	@if [ "$$(uname -m)" = "arm64" ] && [ "$$(uname -s)" = "Darwin" ]; then \
	    echo "  Apple Silicon detected — installing PyTorch with Metal (MPS) support..."; \
	    $(PIP) install --quiet --pre torch torchvision torchaudio \
	        --index-url https://download.pytorch.org/whl/nightly/cpu; \
	    echo "✓ Creative extras installed with Metal GPU acceleration"; \
	else \
	    echo "✓ Creative extras installed (diffusers, torch, ace-step)"; \
	fi

$(VENV)/bin/activate:
	python3 -m venv $(VENV)

# ── Development ───────────────────────────────────────────────────────────────

dev: nuke
	PYTHONDONTWRITEBYTECODE=1 $(UVICORN) dashboard.app:app --reload --host 0.0.0.0 --port 8000

# Kill anything on port 8000, stop Docker containers, clear stale state.
# Safe to run anytime — idempotent, never errors out.
nuke:
	@echo "  Cleaning up dev environment..."
	@# Stop Docker containers (if any are running)
	@docker compose down --remove-orphans 2>/dev/null || true
	@# Kill any process holding port 8000 (errno 48 fix)
	@lsof -ti :8000 | xargs kill -9 2>/dev/null || true
	@# Purge stale bytecache to prevent loading old .pyc files
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@# Brief pause to let the OS release the socket
	@sleep 0.5
	@echo "  ✓ Port 8000 free, containers stopped, caches cleared"

# Print the local IP addresses your phone can use to reach this machine.
# Connect your phone to the same hotspot your Mac is sharing from,
# then open  http://<IP>:8000  in your phone browser.
# The server auto-reloads on Python/template changes (--reload above).
# For CSS/static changes, just pull-to-refresh on your phone.
ip:
	@echo ""
	@echo "  Open one of these on your phone:  http://<IP>:8000"
	@echo ""
	@if [ "$$(uname -s)" = "Darwin" ]; then \
	    ipconfig getifaddr en0  2>/dev/null | awk '{print "  en0 (Wi-Fi):    http://" $$1 ":8000"}' || true; \
	    ipconfig getifaddr en1  2>/dev/null | awk '{print "  en1 (Ethernet): http://" $$1 ":8000"}' || true; \
	    ipconfig getifaddr en2  2>/dev/null | awk '{print "  en2:            http://" $$1 ":8000"}' || true; \
	fi
	@# Generic fallback — works on both macOS and Linux
	@ifconfig 2>/dev/null | awk '/inet / && !/127\.0\.0\.1/ && !/::1/{print "  " $$2 "  →  http://" $$2 ":8000"}' | head -5 \
	    || ip -4 addr show 2>/dev/null | awk '/inet / && !/127\.0\.0\.1/{split($$2,a,"/"); print "  " a[1] "  →  http://" a[1] ":8000"}' | head -5 \
	    || true
	@echo ""

watch:
	$(SELF_TDD) watch --interval 60

# ── Testing ───────────────────────────────────────────────────────────────────

test:
	$(PYTEST) tests/ -q --tb=short

test-cov:
	$(PYTEST) tests/ --cov=src --cov-report=term-missing --cov-report=xml -q

test-cov-html:
	$(PYTEST) tests/ --cov=src --cov-report=term-missing --cov-report=html -q
	@echo "✓ HTML coverage report: open htmlcov/index.html"

# Full-stack functional test: spins up Ollama (CPU, qwen2.5:0.5b) + dashboard
# in Docker and verifies real LLM chat end-to-end.
# Override model: make test-ollama OLLAMA_TEST_MODEL=tinyllama
test-ollama:
	FUNCTIONAL_DOCKER=1 $(PYTEST) tests/functional/test_ollama_chat.py -v --tb=long -x

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	@$(PYTHON) -m ruff check src/ tests/ 2>/dev/null || \
	 $(PYTHON) -m flake8 src/ tests/ 2>/dev/null || \
	 echo "No linter installed — run: pip install ruff"

# ── Housekeeping ──────────────────────────────────────────────────────────────

# ── One-command startup ──────────────────────────────────────────────────────
#   make up           build + start everything in Docker
#   make up DEV=1     same, with hot-reload on Python/template/CSS changes

up:
	mkdir -p data
ifdef DEV
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
	@echo ""
	@echo "  ✓ Timmy Time running in DEV mode at http://localhost:8000"
	@echo "    Hot-reload active — Python, template, and CSS changes auto-apply"
	@echo "    Logs: make logs"
	@echo ""
else
	docker compose up -d --build
	@echo ""
	@echo "  ✓ Timmy Time running at http://localhost:8000"
	@echo "    Logs: make logs"
	@echo ""
endif

down:
	docker compose down

logs:
	docker compose logs -f

# ── Docker ────────────────────────────────────────────────────────────────────

docker-build:
	docker build -t timmy-time:latest .

docker-up:
	mkdir -p data
	docker compose up -d dashboard

docker-down:
	docker compose down

# Spawn one agent worker connected to the running dashboard.
# Override name/capabilities: make docker-agent AGENT_NAME=Echo AGENT_CAPABILITIES=summarise
docker-agent:
	AGENT_NAME=$${AGENT_NAME:-Worker} \
	AGENT_CAPABILITIES=$${AGENT_CAPABILITIES:-general} \
	docker compose --profile agents up -d --scale agent=1 agent

docker-logs:
	docker compose logs -f

docker-shell:
	docker compose exec dashboard bash

# ── Cloud Deploy ─────────────────────────────────────────────────────────────

# One-click production deployment (run on your cloud server)
cloud-deploy:
	@bash deploy/setup.sh

# Start the production stack (Caddy + Ollama + Dashboard + Timmy)
cloud-up:
	docker compose -f docker-compose.prod.yml up -d

# Stop the production stack
cloud-down:
	docker compose -f docker-compose.prod.yml down

# Tail production logs
cloud-logs:
	docker compose -f docker-compose.prod.yml logs -f

# Show status of all production containers
cloud-status:
	docker compose -f docker-compose.prod.yml ps

# Pull latest code and rebuild
cloud-update:
	git pull
	docker compose -f docker-compose.prod.yml up -d --build

# Create a DigitalOcean droplet (requires doctl CLI)
cloud-droplet:
	@bash deploy/digitalocean/create-droplet.sh

# Scale agent workers in production: make cloud-scale N=4
cloud-scale:
	docker compose -f docker-compose.prod.yml --profile agents up -d --scale agent=$${N:-2}

# Pull a model into Ollama: make cloud-pull-model MODEL=llama3.2
cloud-pull-model:
	docker exec timmy-ollama ollama pull $${MODEL:-llama3.2}

# ── Housekeeping ──────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage coverage.xml

help:
	@echo ""
	@echo "  Quick Start"
	@echo "  ─────────────────────────────────────────────────"
	@echo "  make up               build + start everything in Docker"
	@echo "  make up DEV=1         same, with hot-reload on file changes"
	@echo "  make down             stop all containers"
	@echo "  make logs             tail container logs"
	@echo ""
	@echo "  Local Development"
	@echo "  ─────────────────────────────────────────────────"
	@echo "  make install          create venv + install dev deps"
	@echo "  make install-bigbrain install with AirLLM (big-model backend)"
	@echo "  make install-creative install with creative extras (torch, diffusers)"
	@echo "  make dev              clean up + start dashboard (auto-fixes errno 48)"
	@echo "  make nuke             kill port 8000, stop containers, reset state"
	@echo "  make ip               print local IP addresses for phone testing"
	@echo "  make test             run all tests"
	@echo "  make test-cov         tests + coverage report (terminal + XML)"
	@echo "  make test-cov-html    tests + HTML coverage report"
	@echo "  make watch            self-TDD watchdog (60s poll)"
	@echo "  make lint             run ruff or flake8"
	@echo "  make clean            remove build artefacts and caches"
	@echo ""
	@echo "  Docker (Advanced)"
	@echo "  ─────────────────────────────────────────────────"
	@echo "  make docker-build     build the timmy-time:latest image"
	@echo "  make docker-up        start dashboard container"
	@echo "  make docker-agent     add one agent worker (AGENT_NAME=Echo)"
	@echo "  make docker-down      stop all containers"
	@echo "  make docker-logs      tail container logs"
	@echo "  make docker-shell     open a bash shell in the dashboard container"
	@echo ""
	@echo "  Cloud Deploy (Production)"
	@echo "  ─────────────────────────────────────────────────"
	@echo "  make cloud-deploy     one-click server setup (run as root)"
	@echo "  make cloud-up         start production stack"
	@echo "  make cloud-down       stop production stack"
	@echo "  make cloud-logs       tail production logs"
	@echo "  make cloud-status     show container status"
	@echo "  make cloud-update     pull + rebuild from git"
	@echo "  make cloud-droplet    create DigitalOcean droplet (needs doctl)"
	@echo "  make cloud-scale N=4  scale agent workers"
	@echo "  make cloud-pull-model MODEL=llama3.2  pull LLM model"
	@echo ""
