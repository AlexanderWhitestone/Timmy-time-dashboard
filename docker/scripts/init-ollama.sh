#!/bin/bash
# ── Ollama Initialization Script ──────────────────────────────────────────────
#
# Starts Ollama and pulls models on first run.
# Requires: curl (ships with the ollama image).
# jq is installed at runtime if missing so we can parse /api/tags reliably
# instead of fragile grep-based JSON extraction.

set -e

echo "🚀 Ollama startup — checking for models..."

# ── Ensure jq is available (ollama image is Debian-based) ────────────────────
if ! command -v jq &>/dev/null; then
  echo "📦 Installing jq for reliable JSON parsing..."
  apt-get update -qq && apt-get install -y -qq jq >/dev/null 2>&1 || true
fi

# Start Ollama in background
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "⏳ Waiting for Ollama to be ready..."
for i in {1..60}; do
  if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✓ Ollama is ready"
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "❌ Ollama failed to start after 60 s"
    exit 1
  fi
  echo "  Attempt $i/60..."
  sleep 1
done

# Check if models are already present (jq with grep fallback)
echo "📋 Checking available models..."
TAGS_JSON=$(curl -s http://localhost:11434/api/tags)

if command -v jq &>/dev/null; then
  MODELS=$(echo "$TAGS_JSON" | jq '.models | length')
else
  # Fallback: count "name" keys (less reliable but functional)
  MODELS=$(echo "$TAGS_JSON" | grep -o '"name"' | wc -l)
fi

if [ "${MODELS:-0}" -eq 0 ]; then
  echo "📥 No models found. Pulling llama3.2..."
  ollama pull llama3.2 || echo "⚠️  Failed to pull llama3.2 (may already be pulling)"
else
  echo "✓ Models available: $MODELS"
fi

echo "✓ Ollama initialization complete"

# Keep process running
wait $OLLAMA_PID
