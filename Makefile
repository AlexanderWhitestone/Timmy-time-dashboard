.PHONY: install install-bigbrain dev test test-cov watch lint clean help

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

$(VENV)/bin/activate:
	python3 -m venv $(VENV)

# ── Development ───────────────────────────────────────────────────────────────

dev:
	$(UVICORN) dashboard.app:app --reload --host 0.0.0.0 --port 8000

watch:
	$(SELF_TDD) watch --interval 60

# ── Testing ───────────────────────────────────────────────────────────────────

test:
	$(PYTEST) tests/ -q --tb=short

test-cov:
	$(PYTEST) tests/ --cov=src --cov-report=term-missing --cov-report=xml -q

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	@$(PYTHON) -m ruff check src/ tests/ 2>/dev/null || \
	 $(PYTHON) -m flake8 src/ tests/ 2>/dev/null || \
	 echo "No linter installed — run: pip install ruff"

# ── Housekeeping ──────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage coverage.xml

help:
	@echo ""
	@echo "  make install          create venv + install dev deps"
	@echo "  make install-bigbrain install with AirLLM (big-model backend)"
	@echo "  make dev              start dashboard at http://localhost:8000"
	@echo "  make test             run all 228 tests"
	@echo "  make test-cov         tests + coverage report"
	@echo "  make watch            self-TDD watchdog (60s poll)"
	@echo "  make lint             run ruff or flake8"
	@echo "  make clean            remove build artefacts and caches"
	@echo ""
