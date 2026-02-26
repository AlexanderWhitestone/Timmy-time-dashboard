#!/bin/bash
# Run E2E tests in non-headless mode (visible browser)

echo "==============================================="
echo "Timmy Time E2E Test Runner"
echo "==============================================="
echo ""

# Check if server is running
echo "Checking if server is running..."
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ Server is running at http://localhost:8000"
else
    echo "❌ Server not running. Starting server..."
    source .venv/bin/activate
    make dev &
    SERVER_PID=$!
    
    # Wait for server
    echo "Waiting for server to start..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/health > /dev/null; then
            echo "✅ Server started!"
            break
        fi
        sleep 1
        echo -n "."
    done
    
    if ! curl -s http://localhost:8000/health > /dev/null; then
        echo "❌ Server failed to start"
        exit 1
    fi
fi

echo ""
echo "==============================================="
echo "Running E2E Tests (Non-Headless / Visible)"
echo "==============================================="
echo ""
echo "You will see Chrome browser windows open and execute tests."
echo ""

source .venv/bin/activate

# Check for pytest option
if [ "$1" == "--headed" ] || [ "$2" == "--headed" ]; then
    HEADED="--headed"
else
    HEADED=""
fi

# Run specific test file or all
if [ -n "$1" ] && [ "$1" != "--headed" ]; then
    TEST_FILE="$1"
    echo "Running: $TEST_FILE"
    SELENIUM_UI=1 pytest "$TEST_FILE" -v $HEADED
else
    echo "Running all E2E tests..."
    SELENIUM_UI=1 pytest tests/functional/test_new_features_e2e.py tests/functional/test_cascade_router_e2e.py tests/functional/test_upgrade_queue_e2e.py tests/functional/test_activity_feed_e2e.py -v $HEADED
fi

echo ""
echo "==============================================="
echo "E2E Tests Complete"
echo "==============================================="
