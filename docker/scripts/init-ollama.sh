#!/bin/bash
# ── Ollama Initialization Script ──────────────────────────────────────────────
#
# Starts Ollama and pulls models on first run.

set -e

echo "🚀 Ollama startup — checking for models..."

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
  echo "  Attempt $i/60..."
  sleep 1
done

# Check if models are already present
echo "📋 Checking available models..."
MODELS=$(curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*"' | wc -l)

if [ "$MODELS" -eq 0 ]; then
  echo "📥 No models found. Pulling llama3.2..."
  ollama pull llama3.2 || echo "⚠️  Failed to pull llama3.2 (may already be pulling)"
else
  echo "✓ Models available: $MODELS"
fi

echo "✓ Ollama initialization complete"

# Keep process running
wait $OLLAMA_PID
