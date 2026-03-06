#!/usr/bin/env bash
# Pre-commit hook: run tests with a wall-clock limit.
# Blocks the commit if tests fail or take too long.
# Current baseline: ~18s wall-clock. Limit set to 30s for headroom.

MAX_SECONDS=30

echo "Running tests (${MAX_SECONDS}s limit)..."

timeout "${MAX_SECONDS}" poetry run pytest tests -q --tb=short --timeout=10
exit_code=$?

if [ "$exit_code" -eq 124 ]; then
    echo ""
    echo "BLOCKED: tests exceeded ${MAX_SECONDS}s wall-clock limit."
    echo "Speed up slow tests before committing."
    exit 1
elif [ "$exit_code" -ne 0 ]; then
    echo ""
    echo "BLOCKED: tests failed."
    exit 1
fi
