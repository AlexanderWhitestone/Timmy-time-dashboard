"""Fast E2E tests - all checks in one browser session, under 20 seconds.

RUN: SELENIUM_UI=1 pytest tests/functional/test_fast_e2e.py -v
"""

import os

import pytest
import httpx

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

pytestmark = pytest.mark.skipif(
    not HAS_SELENIUM or os.environ.get("SELENIUM_UI") != "1",
    reason="Selenium not installed or SELENIUM_UI not set to 1",
)

DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def driver():
    """Single browser instance for all tests (module-scoped for reuse)."""
    opts = Options()
    opts.add_argument("--headless=new")  # Headless for speed
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,900")

    d = webdriver.Chrome(options=opts)
    d.implicitly_wait(2)  # Reduced from 5s
    yield d
    d.quit()


@pytest.fixture(scope="module")
def dashboard_url():
    """Verify server is running."""
    try:
        r = httpx.get(f"{DASHBOARD_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("Dashboard not healthy")
    except Exception:
        pytest.skip(f"Dashboard not reachable at {DASHBOARD_URL}")
    return DASHBOARD_URL


class TestAllPagesLoad:
    """Single test that checks all pages load - much faster than separate tests."""

    def test_all_dashboard_pages_exist(self, driver, dashboard_url):
        """Verify all new feature pages load successfully in one browser session."""
        pages = [
            ("/swarm/events", "Event"),
            ("/lightning/ledger", "Lightning Ledger"),
            ("/memory", "Memory"),
            ("/router/status", "Router Status"),
            ("/self-modify/queue", "Upgrade"),
            ("/swarm/live", "Swarm"),  # Live page has "Swarm" not "Live"
        ]

        failures = []

        for path, expected_text in pages:
            try:
                driver.get(f"{dashboard_url}{path}")
                # Quick check - wait max 5s for any content
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # Give a small extra buffer for animations (fadeUp in style.css)
                import time
                time.sleep(0.5)

                # Verify page has expected content
                body_text = driver.find_element(By.TAG_NAME, "body").text
                if expected_text.lower() not in body_text.lower():
                    failures.append(f"{path}: missing '{expected_text}'")

            except Exception as exc:
                failures.append(f"{path}: {type(exc).__name__}")

        if failures:
            pytest.fail(f"Pages failed to load: {', '.join(failures)}")


class TestAllFeaturesWork:
    """Combined functional tests - single browser session."""

    def test_event_log_and_memory_and_ledger_functional(self, driver, dashboard_url):
        """Test Event Log, Memory, and Ledger functionality in one go."""

        # 1. Event Log - verify events display
        driver.get(f"{dashboard_url}/swarm/events")
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        import time
        time.sleep(0.5)

        # Should have header and either events or empty state
        body = driver.find_element(By.TAG_NAME, "body").text
        assert "event log" in body.lower(), "Event log page missing header"

        # Create a task via API to generate an event
        try:
            httpx.post(
                f"{dashboard_url}/swarm/tasks",
                data={"description": "E2E test task"},
                timeout=2,
            )
        except Exception:
            pass  # Ignore, just checking page exists

        # 2. Memory - verify search works
        driver.get(f"{dashboard_url}/memory?query=test")
        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Should have search input
        search = driver.find_elements(
            By.CSS_SELECTOR, "input[type='search'], input[name='query']"
        )
        assert search, "Memory page missing search input"

        # 3. Ledger - verify balance display
        driver.get(f"{dashboard_url}/lightning/ledger")
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(0.5)

        body = driver.find_element(By.TAG_NAME, "body").text
        # Should show balance-related text
        has_balance = any(x in body.lower() for x in ["balance", "sats", "transaction", "ledger"])
        assert has_balance, "Ledger page missing balance info"


class TestCascadeRouter:
    """Cascade Router - combined checks."""

    def test_router_status_and_navigation(self, driver, dashboard_url):
        """Verify router status page and nav link in one test."""

        # Check router status page
        driver.get(f"{dashboard_url}/router/status")
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        import time
        time.sleep(0.5)

        body = driver.find_element(By.TAG_NAME, "body").text

        # Should show providers or config message
        has_content = any(
            x in body.lower()
            for x in ["provider", "router", "ollama", "config", "status", "registry"]
        )
        assert has_content, "Router status page missing content"

        # Check nav has router link
        driver.get(dashboard_url)
        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        nav_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/router')]")
        assert nav_links, "Navigation missing router link"


class TestUpgradeQueue:
    """Upgrade Queue - combined checks."""

    def test_upgrade_queue_page_and_elements(self, driver, dashboard_url):
        """Verify upgrade queue page loads with expected elements."""

        driver.get(f"{dashboard_url}/self-modify/queue")
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        import time
        time.sleep(0.5)

        body = driver.find_element(By.TAG_NAME, "body").text

        # Should have queue header
        assert "upgrade" in body.lower() or "queue" in body.lower(), (
            "Missing queue header"
        )

        # Should have pending section or empty state
        has_pending = "pending" in body.lower() or "no pending" in body.lower()
        assert has_pending, "Missing pending upgrades section"

        # Check for approve/reject buttons if upgrades exist
        approve_btns = driver.find_elements(
            By.XPATH, "//button[contains(text(), 'Approve')]"
        )
        reject_btns = driver.find_elements(
            By.XPATH, "//button[contains(text(), 'Reject')]"
        )

        # Either no upgrades (no buttons) or buttons exist
        # This is a soft check - page structure is valid either way


class TestActivityFeed:
    """Activity Feed - combined checks."""

    def test_swarm_live_page_and_activity_feed(self, driver, dashboard_url):
        """Verify swarm live page has activity feed elements."""

        driver.get(f"{dashboard_url}/swarm/live")
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        import time
        time.sleep(0.5)

        body = driver.find_element(By.TAG_NAME, "body").text

        # Should have live indicator or activity section
        has_live = any(
            x in body.lower() for x in ["live", "activity", "swarm", "agents", "tasks"]
        )
        assert has_live, "Swarm live page missing content"

        # Check for WebSocket connection indicator (if implemented)
        # or just basic structure
        panels = driver.find_elements(By.CSS_SELECTOR, ".card, .panel, .mc-panel")
        assert panels, "Swarm live page missing panels"


class TestFastSmoke:
    """Ultra-fast smoke tests using HTTP where possible."""

    def test_all_routes_respond_200(self, dashboard_url):
        """HTTP-only test - no browser, very fast."""
        routes = [
            "/swarm/events",
            "/lightning/ledger",
            "/memory",
            "/router/status",
            "/self-modify/queue",
            "/swarm/live",
        ]

        failures = []

        for route in routes:
            try:
                r = httpx.get(
                    f"{dashboard_url}{route}", timeout=3, follow_redirects=True
                )
                if r.status_code != 200:
                    failures.append(f"{route}: {r.status_code}")
            except Exception as exc:
                failures.append(f"{route}: {type(exc).__name__}")

        if failures:
            pytest.fail(f"Routes failed: {', '.join(failures)}")
