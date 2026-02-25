#!/usr/bin/env bash
# activate_self_tdd.sh — Timmy Time dev environment bootstrapper
#
# Usage:
#   bash activate_self_tdd.sh              # standard (Ollama) setup
#   bash activate_self_tdd.sh --big-brain  # install AirLLM extra too
#
# What it does:
#   1. Creates a Python venv (or reuses an existing one)
#   2. Installs Timmy Time (+ dev deps, optionally bigbrain)
#   3. Runs the full test suite — aborts if anything fails
#   4. Launches the self-TDD watchdog in the background
#   5. Starts the dashboard
#
# Everything stays local. No cloud. Sats are sovereignty, boss.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
BIG_BRAIN=0

for arg in "$@"; do
  case $arg in
    --big-brain) BIG_BRAIN=1 ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

echo "==> Timmy Time — sovereign AI agent bootstrapper"
echo "    Working directory: $REPO_DIR"

# ── 1. Virtual environment ────────────────────────────────────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
  echo "==> Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
echo "==> Virtual environment active: $VENV_DIR"

# ── 2. Install dependencies ───────────────────────────────────────────────────
if [[ $BIG_BRAIN -eq 1 ]]; then
  echo "==> Installing with bigbrain extra (AirLLM)..."
  pip install --quiet -e "$REPO_DIR[dev,bigbrain]"
  # On Apple Silicon, also install the MLX backend.
  if [[ "$(uname -m)" == "arm64" && "$(uname -s)" == "Darwin" ]]; then
    echo "==> Apple Silicon detected — installing AirLLM MLX backend..."
    pip install --quiet "airllm[mlx]"
  fi
else
  echo "==> Installing standard dependencies..."
  pip install --quiet -e "$REPO_DIR[dev]"
fi

# ── 3. Run tests ──────────────────────────────────────────────────────────────
echo "==> Running test suite..."
python -m pytest "$REPO_DIR/tests/" -q --tb=short
echo "==> All tests passed."

# ── 4. Self-TDD watchdog (background) ────────────────────────────────────────
WATCHDOG_PID_FILE="$REPO_DIR/.watchdog.pid"

# Kill any previously orphaned watchdog
if [[ -f "$WATCHDOG_PID_FILE" ]]; then
  OLD_PID=$(cat "$WATCHDOG_PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "==> Stopping previous watchdog (PID $OLD_PID)..."
    kill "$OLD_PID" 2>/dev/null || true
  fi
  rm -f "$WATCHDOG_PID_FILE"
fi

echo "==> Starting self-TDD watchdog (60s interval) in background..."
self-tdd watch --interval 60 &
WATCHDOG_PID=$!
echo "$WATCHDOG_PID" > "$WATCHDOG_PID_FILE"
echo "    Watchdog PID: $WATCHDOG_PID (saved to .watchdog.pid)"
echo "    Kill with: kill $WATCHDOG_PID"

# Clean up watchdog when the script exits (Ctrl-C, etc.)
cleanup() {
  echo ""
  echo "==> Stopping watchdog (PID $WATCHDOG_PID)..."
  kill "$WATCHDOG_PID" 2>/dev/null || true
  rm -f "$WATCHDOG_PID_FILE"
}
trap cleanup EXIT

# ── 5. Dashboard ─────────────────────────────────────────────────────────────
echo ""
echo "==> Starting Timmy Time dashboard at http://localhost:8000"
echo "    Ctrl-C stops both the dashboard and the watchdog"
echo ""
uvicorn dashboard.app:app --reload --host 0.0.0.0 --port 8000
