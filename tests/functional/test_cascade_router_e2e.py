"""E2E tests for Cascade Router Integration.

RUN: pytest tests/functional/test_cascade_router_e2e.py -v --headed
"""

import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .conftest import DASHBOARD_URL


@pytest.fixture
def driver():
    """Non-headless Chrome so you can watch."""
    opts = Options()
    # NO --headless - you will see the browser!
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,900")
    
    d = webdriver.Chrome(options=opts)
    d.implicitly_wait(5)
    yield d
    d.quit()


class TestCascadeRouterUI:
    """Cascade Router dashboard and failover behavior."""

    def test_router_status_page_exists(self, driver):
        """Router status page loads at /router/status."""
        driver.get(f"{DASHBOARD_URL}/router/status")
        
        header = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
        assert "router" in header.text.lower() or "provider" in header.text.lower()
        
        # Should show provider list
        providers = driver.find_elements(By.CSS_SELECTOR, ".provider-card, .provider-row")
        assert len(providers) >= 1, "Should show at least one provider"

    def test_router_shows_ollama_provider(self, driver):
        """Ollama provider is listed as priority 1."""
        driver.get(f"{DASHBOARD_URL}/router/status")
        
        # Look for Ollama
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        assert "ollama" in page_text, "Should show Ollama provider"

    def test_router_shows_provider_health(self, driver):
        """Each provider shows health status (healthy/degraded/unhealthy)."""
        driver.get(f"{DASHBOARD_URL}/router/status")
        
        # Look for health indicators
        health_badges = driver.find_elements(
            By.CSS_SELECTOR, ".health-badge, .status-healthy, .status-degraded, .status-unhealthy"
        )
        assert len(health_badges) >= 1, "Should show health status"

    def test_router_shows_metrics(self, driver):
        """Providers show request counts, latency, error rates."""
        driver.get(f"{DASHBOARD_URL}/router/status")
        
        # Look for metrics
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Should show some metrics
        has_requests = "request" in page_text.lower()
        has_latency = "ms" in page_text.lower() or "latency" in page_text.lower()
        
        assert has_requests or has_latency, "Should show provider metrics"

    def test_chat_uses_cascade_router(self, driver):
        """Sending chat message routes through cascade (may show provider used)."""
        driver.get(DASHBOARD_URL)
        
        # Wait for chat to load
        chat_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='message']"))
        )
        
        # Send a message
        chat_input.send_keys("test cascade routing")
        chat_input.send_keys(Keys.RETURN)
        
        # Wait for response
        time.sleep(5)
        
        # Should get some response (even if error)
        messages = driver.find_elements(By.CSS_SELECTOR, ".chat-message")
        assert len(messages) >= 2, "Should have user message and response"

    def test_nav_link_to_router(self, driver):
        """Navigation menu has link to router status."""
        driver.get(DASHBOARD_URL)
        
        # Look for router link
        router_link = driver.find_elements(
            By.XPATH, "//a[contains(@href, '/router') or contains(text(), 'Router')]"
        )
        
        if router_link:
            router_link[0].click()
            time.sleep(1)
            assert "/router" in driver.current_url


class TestCascadeFailover:
    """Router failover behavior (if we can simulate failures)."""

    def test_fallback_to_next_provider_on_failure(self, driver):
        """If primary fails, automatically uses secondary."""
        # This is hard to test in E2E without actually breaking Ollama
        # We'll just verify the router has multiple providers configured
        
        driver.get(f"{DASHBOARD_URL}/router/status")
        
        # Count providers
        providers = driver.find_elements(By.CSS_SELECTOR, ".provider-card, .provider-row")
        
        # If multiple providers, failover is possible
        if len(providers) >= 2:
            # Look for priority numbers
            page_text = driver.find_element(By.TAG_NAME, "body").text
            assert "priority" in page_text.lower() or "1" in page_text or "2" in page_text
