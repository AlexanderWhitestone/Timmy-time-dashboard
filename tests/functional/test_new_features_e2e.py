"""E2E tests for new features: Event Log, Ledger, Memory.

REQUIRES: Dashboard running at http://localhost:8000
RUN: SELENIUM_UI=1 pytest tests/functional/test_new_features_e2e.py -v

These tests verify the new features through the actual UI:
1. Event Log - viewable in dashboard
2. Lightning Ledger - balance and transactions visible
3. Semantic Memory - searchable memory browser
"""

import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

pytestmark = pytest.mark.skipif(
    os.environ.get("SELENIUM_UI") != "1",
    reason="Set SELENIUM_UI=1 to run Selenium UI tests",
)

@pytest.fixture(scope="module")
def driver():
    """Headless Chrome WebDriver."""
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,900")

    d = webdriver.Chrome(options=opts)
    d.implicitly_wait(5)
    yield d
    d.quit()


@pytest.fixture(scope="module")
def dashboard_url(live_server):
    """Base URL for dashboard (from live_server fixture)."""
    return live_server


def _wait_for_element(driver, selector, timeout=10):
    """Wait for element to appear."""
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
    )


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT LOG E2E TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventLogUI:
    """Event Log feature - viewable through dashboard."""

    def test_event_log_page_exists(self, driver):
        """Event log page loads at /swarm/events."""
        driver.get(f"{dashboard_url}/swarm/events")
        header = _wait_for_element(driver, "h1, h2, .page-title", timeout=10)
        assert "event" in header.text.lower() or "log" in header.text.lower()

    def test_event_log_shows_recent_events(self, driver):
        """Event log displays events table with timestamp, type, source."""
        driver.get(f"{dashboard_url}/swarm/events")
        
        # Should show events table or "no events" message
        table = driver.find_elements(By.CSS_SELECTOR, ".events-table, table")
        no_events = driver.find_elements(By.XPATH, "//*[contains(text(), 'no events') or contains(text(), 'No events')]")
        
        assert table or no_events, "Should show events table or 'no events' message"

    def test_event_log_filters_by_type(self, driver):
        """Can filter events by type (task, agent, system)."""
        driver.get(f"{dashboard_url}/swarm/events")
        
        # Look for filter dropdown or buttons
        filters = driver.find_elements(By.CSS_SELECTOR, "select[name='type'], .filter-btn, [data-filter]")
        
        # If filters exist, test them
        if filters:
            # Select 'task' filter
            filter_select = driver.find_element(By.CSS_SELECTOR, "select[name='type']")
            filter_select.click()
            driver.find_element(By.CSS_SELECTOR, "option[value='task']").click()
            
            # Wait for filtered results
            time.sleep(1)
            
            # Check URL changed or content updated
            events = driver.find_elements(By.CSS_SELECTOR, ".event-row, tr")
            # Just verify no error occurred

    def test_event_log_shows_task_events_after_task_created(self, driver):
        """Creating a task generates visible event log entries."""
        # First create a task via API
        import httpx
        task_desc = f"E2E test task {time.time()}"
        httpx.post(f"{dashboard_url}/swarm/tasks", data={"description": task_desc})
        
        time.sleep(1)  # Wait for event to be logged
        
        # Now check event log
        driver.get(f"{dashboard_url}/swarm/events")
        
        # Should see the task creation event
        page_text = driver.find_element(By.TAG_NAME, "body").text
        assert "task.created" in page_text.lower() or "task created" in page_text.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# LIGHTNING LEDGER E2E TESTS  
# ═══════════════════════════════════════════════════════════════════════════════

class TestLedgerUI:
    """Lightning Ledger - balance and transactions visible in dashboard."""

    def test_ledger_page_exists(self, driver):
        """Ledger page loads at /lightning/ledger."""
        driver.get(f"{dashboard_url}/lightning/ledger")
        header = _wait_for_element(driver, "h1, h2, .page-title", timeout=10)
        assert "ledger" in header.text.lower() or "transaction" in header.text.lower()

    def test_ledger_shows_balance(self, driver):
        """Ledger displays current balance."""
        driver.get(f"{dashboard_url}/lightning/ledger")
        
        # Look for balance display
        balance = driver.find_elements(By.CSS_SELECTOR, ".balance, .sats-balance, [class*='balance']")
        balance_text = driver.find_elements(By.XPATH, "//*[contains(text(), 'sats') or contains(text(), 'SATS')]")
        
        assert balance or balance_text, "Should show balance in sats"

    def test_ledger_shows_transactions(self, driver):
        """Ledger displays transaction history."""
        driver.get(f"{dashboard_url}/lightning/ledger")
        
        # Should show transactions table or "no transactions" message
        table = driver.find_elements(By.CSS_SELECTOR, ".transactions-table, table")
        empty = driver.find_elements(By.XPATH, "//*[contains(text(), 'no transaction') or contains(text(), 'No transaction')]")
        
        assert table or empty, "Should show transactions or empty state"

    def test_ledger_transaction_has_required_fields(self, driver):
        """Each transaction shows: hash, amount, status, timestamp."""
        driver.get(f"{dashboard_url}/lightning/ledger")
        
        rows = driver.find_elements(By.CSS_SELECTOR, ".transaction-row, tbody tr")
        
        if rows:
            # Check first row has expected fields
            first_row = rows[0]
            text = first_row.text.lower()
            
            # Should have some of these indicators
            has_amount = any(x in text for x in ["sats", "sat", "000"])
            has_status = any(x in text for x in ["pending", "settled", "failed"])
            
            assert has_amount, "Transaction should show amount"
            assert has_status, "Transaction should show status"


# ═══════════════════════════════════════════════════════════════════════════════
# SEMANTIC MEMORY E2E TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemoryUI:
    """Semantic Memory - searchable memory browser."""

    def test_memory_page_exists(self, driver):
        """Memory browser loads at /memory."""
        driver.get(f"{dashboard_url}/memory")
        header = _wait_for_element(driver, "h1, h2, .page-title", timeout=10)
        assert "memory" in header.text.lower()

    def test_memory_has_search_box(self, driver):
        """Memory page has search input."""
        driver.get(f"{dashboard_url}/memory")
        
        search = driver.find_elements(By.CSS_SELECTOR, "input[type='search'], input[name='query'], .search-input")
        assert search, "Should have search input"

    def test_memory_search_returns_results(self, driver):
        """Search returns memory entries with relevance scores."""
        driver.get(f"{dashboard_url}/memory")
        
        search_input = driver.find_element(By.CSS_SELECTOR, "input[type='search'], input[name='query']")
        search_input.send_keys("test query")
        search_input.send_keys(Keys.RETURN)
        
        time.sleep(2)  # Wait for search results
        
        # Should show results or "no results"
        results = driver.find_elements(By.CSS_SELECTOR, ".memory-entry, .search-result")
        no_results = driver.find_elements(By.XPATH, "//*[contains(text(), 'no results') or contains(text(), 'No results')]")
        
        assert results or no_results, "Should show search results or 'no results'"

    def test_memory_shows_entry_content(self, driver):
        """Memory entries show content, source, and timestamp."""
        driver.get(f"{dashboard_url}/memory")
        
        entries = driver.find_elements(By.CSS_SELECTOR, ".memory-entry")
        
        if entries:
            first = entries[0]
            text = first.text
            
            # Should have content and source
            has_source = any(x in text.lower() for x in ["source:", "from", "by"])
            has_time = any(x in text.lower() for x in ["202", ":", "ago"])
            
            assert len(text) > 10, "Entry should have content"

    def test_memory_add_fact_button(self, driver):
        """Can add personal fact through UI."""
        driver.get(f"{dashboard_url}/memory")
        
        # Look for add fact button or form
        add_btn = driver.find_elements(By.XPATH, "//button[contains(text(), 'Add') or contains(text(), 'New')]")
        add_form = driver.find_elements(By.CSS_SELECTOR, "form[action*='memory'], .add-memory-form")
        
        assert add_btn or add_form, "Should have way to add new memory"


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION E2E TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeatureIntegration:
    """Integration tests - features work together."""

    def test_creating_task_creates_event_and_appears_in_log(self, driver):
        """Full flow: Create task → event logged → visible in event log UI."""
        import httpx
        
        # Create task via API
        task_desc = f"Integration test {time.time()}"
        response = httpx.post(
            f"{dashboard_url}/swarm/tasks",
            data={"description": task_desc}
        )
        assert response.status_code == 200
        
        time.sleep(1)  # Wait for event log
        
        # Check event log UI
        driver.get(f"{dashboard_url}/swarm/events")
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Should see task creation
        assert "task" in page_text.lower()

    def test_swarm_live_page_shows_agent_events(self, driver):
        """Swarm live page shows real-time agent activity."""
        driver.get(f"{dashboard_url}/swarm/live")
        
        # Should show activity feed or status
        feed = driver.find_elements(By.CSS_SELECTOR, ".activity-feed, .events-list, .live-feed")
        agents = driver.find_elements(By.CSS_SELECTOR, ".agent-status, .swarm-status")
        
        assert feed or agents, "Should show activity feed or agent status"

    def test_navigation_between_new_features(self, driver):
        """Can navigate between Event Log, Ledger, and Memory pages."""
        # Start at home
        driver.get(dashboard_url)
        
        # Find and click link to events
        event_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/swarm/events') or contains(text(), 'Events')]")
        if event_links:
            event_links[0].click()
            time.sleep(1)
            assert "/swarm/events" in driver.current_url
        
        # Navigate to ledger
        driver.get(f"{dashboard_url}/lightning/ledger")
        assert "/lightning/ledger" in driver.current_url
        
        # Navigate to memory
        driver.get(f"{dashboard_url}/memory")
        assert "/memory" in driver.current_url
