#!/bin/bash
# One-liner to get status and prompt for Kimi

cd "$(dirname "$0")/.."

echo "=== STATUS ==="
git log --oneline -1
git status --short
echo ""
echo "Tests: $(make test 2>&1 | grep -o '[0-9]* passed' | tail -1)"
echo ""

echo "=== PROMPT (copy/paste to Kimi) ==="
echo ""
echo "cd Timmy-time-dashboard && cat .handoff/CHECKPOINT.md"
echo ""
echo "Continue from checkpoint. Read the file above and execute the NEXT TASK from .handoff/TODO.md. Run 'make test' after changes."
echo ""
