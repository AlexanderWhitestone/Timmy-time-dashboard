"""Selenium UI tests — green-path smoke tests for the dashboard.

Requires:
  - Dashboard running at http://localhost:8000 (make up DEV=1)
  - Chrome installed (headless mode, no display needed)
  - selenium pip package

Run:
  SELENIUM_UI=1 pytest tests/functional/test_ui_selenium.py -v
"""

import os

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Skip entire module unless SELENIUM_UI=1 is set
pytestmark = pytest.mark.skipif(
    os.environ.get("SELENIUM_UI") != "1",
    reason="Set SELENIUM_UI=1 to run Selenium UI tests",
)

DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def driver():
    """Headless Chrome WebDriver, shared across tests in this module."""
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


@pytest.fixture(autouse=True)
def _check_dashboard():
    """Skip all tests if the dashboard isn't reachable."""
    import httpx

    try:
        r = httpx.get(f"{DASHBOARD_URL}/health", timeout=5)
        if r.status_code != 200:
            pytest.skip("Dashboard not healthy")
    except Exception:
        pytest.skip("Dashboard not reachable at " + DASHBOARD_URL)


def _load_dashboard(driver):
    """Navigate to dashboard and wait for Timmy panel to load."""
    driver.get(DASHBOARD_URL)
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located(
            (By.XPATH, "//*[contains(text(), 'TIMMY INTERFACE')]")
        )
    )


def _wait_for_sidebar(driver):
    """Wait for the agent sidebar to finish its HTMX load."""
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located(
            (By.XPATH, "//*[contains(text(), 'SWARM AGENTS')]")
        )
    )


def _has_registered_agents(driver):
    """Check if there are any registered agent cards in the sidebar."""
    cards = driver.find_elements(By.CSS_SELECTOR, ".mc-agent-card")
    return len(cards) > 0


def _send_chat_and_wait(driver, message):
    """Send a chat message and wait for the NEW agent response.

    Returns the number of agent messages before and after sending.
    """
    existing = len(driver.find_elements(By.CSS_SELECTOR, ".chat-message.agent"))

    inp = driver.find_element(By.CSS_SELECTOR, "input[name='message']")
    inp.send_keys(message)
    inp.send_keys(Keys.RETURN)

    # Wait for a NEW agent response (not one from a prior test)
    WebDriverWait(driver, 30).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, ".chat-message.agent"))
        > existing
    )

    return existing


# ── Page load tests ─────────────────────────────────────────────────────────


class TestPageLoad:
    """Dashboard loads and shows expected structure."""

    def test_homepage_loads(self, driver):
        driver.get(DASHBOARD_URL)
        assert driver.title != ""

    def test_header_visible(self, driver):
        _load_dashboard(driver)
        header = driver.find_element(By.CSS_SELECTOR, ".mc-header, header, nav")
        assert header.is_displayed()

    def test_sidebar_loads(self, driver):
        _load_dashboard(driver)
        _wait_for_sidebar(driver)

    def test_timmy_panel_loads(self, driver):
        _load_dashboard(driver)

    def test_chat_input_exists(self, driver):
        _load_dashboard(driver)
        inp = driver.find_element(By.CSS_SELECTOR, "input[name='message']")
        assert inp.is_displayed()
        assert "timmy" in inp.get_attribute("placeholder").lower()

    def test_send_button_exists(self, driver):
        _load_dashboard(driver)
        btn = driver.find_element(By.CSS_SELECTOR, "button.mc-btn-send")
        assert btn.is_displayed()
        assert "SEND" in btn.text

    def test_health_panel_loads(self, driver):
        _load_dashboard(driver)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(), 'SYSTEM HEALTH')]")
            )
        )


# ── Chat interaction tests ──────────────────────────────────────────────────


class TestChatInteraction:
    """Send a single message and verify all chat-related behaviors at once.

    We only send ONE message to avoid spamming Ollama and crashing the browser.
    """

    def test_chat_roundtrip(self, driver):
        """Full chat roundtrip: send message, get response, input clears, chat scrolls."""
        _load_dashboard(driver)

        # Wait for page to be ready
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        existing_agents = len(
            driver.find_elements(By.CSS_SELECTOR, ".chat-message.agent")
        )

        inp = driver.find_element(By.CSS_SELECTOR, "input[name='message']")
        inp.send_keys("hello from selenium")
        inp.send_keys(Keys.RETURN)

        # 1. User bubble appears immediately
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".chat-message.user"))
        )

        # 2. Agent response arrives
        WebDriverWait(driver, 30).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, ".chat-message.agent"))
            > existing_agents
        )

        # 3. Input cleared (regression test)
        # Already waited for agent response via WebDriverWait above
        inp = driver.find_element(By.CSS_SELECTOR, "input[name='message']")
        assert inp.get_attribute("value") == "", "Input should be empty after sending"

        # 4. Chat scrolled to bottom (regression test)
        chat_log = driver.find_element(By.ID, "chat-log")
        scroll_top = driver.execute_script("return arguments[0].scrollTop", chat_log)
        scroll_height = driver.execute_script(
            "return arguments[0].scrollHeight", chat_log
        )
        client_height = driver.execute_script(
            "return arguments[0].clientHeight", chat_log
        )

        if scroll_height > client_height:
            gap = scroll_height - scroll_top - client_height
            assert gap < 50, f"Chat not scrolled to bottom (gap: {gap}px)"


# ── Task panel tests ────────────────────────────────────────────────────────


class TestTaskPanel:
    """Task creation panel works correctly."""

    def test_task_panel_via_url(self, driver):
        """Task panel loads correctly when navigated to directly."""
        driver.get(f"{DASHBOARD_URL}/swarm/tasks/panel")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(), 'CREATE TASK')]")
            )
        )

    def test_task_panel_has_form(self, driver):
        """Task creation panel has description and agent fields."""
        driver.get(f"{DASHBOARD_URL}/swarm/tasks/panel")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(), 'CREATE TASK')]")
            )
        )

        driver.find_element(By.CSS_SELECTOR, "textarea[name='description']")
        driver.find_element(By.CSS_SELECTOR, "select[name='agent_id']")

    def test_task_button_on_agent_card(self, driver):
        """If agents are registered, TASK button on agent card opens task panel."""
        _load_dashboard(driver)
        _wait_for_sidebar(driver)

        if not _has_registered_agents(driver):
            pytest.skip("No agents registered — TASK button not available")

        task_btn = driver.find_element(
            By.XPATH,
            "//div[contains(@class, 'mc-agent-card')]//button[contains(text(), 'TASK')]",
        )
        task_btn.click()

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(), 'CREATE TASK')]")
            )
        )


# ── Agent sidebar tests ─────────────────────────────────────────────────────


class TestAgentSidebar:
    """Agent sidebar displays correctly."""

    def test_sidebar_header_shows(self, driver):
        _load_dashboard(driver)
        _wait_for_sidebar(driver)
        header = driver.find_element(By.XPATH, "//*[contains(text(), 'SWARM AGENTS')]")
        assert header.is_displayed()

    def test_sidebar_shows_status_when_agents_exist(self, driver):
        """If agents are registered, cards show status dots."""
        _load_dashboard(driver)
        _wait_for_sidebar(driver)

        if not _has_registered_agents(driver):
            pytest.skip("No agents registered — skipping card test")

        cards = driver.find_elements(By.CSS_SELECTOR, ".mc-agent-card")
        for card in cards:
            dots = card.find_elements(By.CSS_SELECTOR, ".status-dot")
            assert len(dots) >= 1, "Agent card should show a status dot"

    def test_no_agents_fallback(self, driver):
        """When no agents registered, sidebar shows fallback message."""
        _load_dashboard(driver)
        _wait_for_sidebar(driver)

        if _has_registered_agents(driver):
            pytest.skip("Agents are registered — fallback not shown")

        body = driver.find_element(By.CSS_SELECTOR, ".mc-sidebar").text
        assert "NO AGENTS REGISTERED" in body


# ── Navigation tests ────────────────────────────────────────────────────────


class TestNavigation:
    """Basic navigation flows work end-to-end."""

    def test_clear_chat_button(self, driver):
        _load_dashboard(driver)
        clear_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'CLEAR')]")
        assert clear_btn.is_displayed()

    def test_health_endpoint_returns_200(self, driver):
        driver.get(f"{DASHBOARD_URL}/health")
        assert "ok" in driver.page_source

    def test_nav_links_visible(self, driver):
        _load_dashboard(driver)
        links = driver.find_elements(By.CSS_SELECTOR, ".mc-desktop-nav .mc-test-link")
        assert len(links) >= 3, "Navigation should have multiple links"
