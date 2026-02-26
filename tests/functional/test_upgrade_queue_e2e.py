"""E2E tests for Self-Upgrade Approval Queue.

RUN: pytest tests/functional/test_upgrade_queue_e2e.py -v --headed
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
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,900")
    
    d = webdriver.Chrome(options=opts)
    d.implicitly_wait(5)
    yield d
    d.quit()


class TestUpgradeQueueUI:
    """Upgrade queue dashboard functionality."""

    def test_upgrade_queue_page_exists(self, driver):
        """Upgrade queue loads at /self-modify/queue."""
        driver.get(f"{DASHBOARD_URL}/self-modify/queue")
        
        header = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
        assert "upgrade" in header.text.lower() or "queue" in header.text.lower()

    def test_queue_shows_pending_upgrades(self, driver):
        """Queue shows pending upgrades with status."""
        driver.get(f"{DASHBOARD_URL}/self-modify/queue")
        
        # Should show either pending upgrades or empty state
        pending = driver.find_elements(By.CSS_SELECTOR, ".upgrade-pending, .upgrade-card")
        empty = driver.find_elements(By.XPATH, "//*[contains(text(), 'No pending') or contains(text(), 'empty')]")
        
        assert pending or empty, "Should show pending upgrades or empty state"

    def test_queue_shows_upgrade_details(self, driver):
        """Each upgrade shows description, files changed, test status."""
        driver.get(f"{DASHBOARD_URL}/self-modify/queue")
        
        upgrades = driver.find_elements(By.CSS_SELECTOR, ".upgrade-card")
        
        if upgrades:
            first = upgrades[0]
            text = first.text.lower()
            
            # Should have description
            assert len(text) > 20, "Should show upgrade description"
            
            # Should show status
            has_status = any(x in text for x in ["pending", "proposed", "waiting"])
            assert has_status, "Should show upgrade status"

    def test_approve_button_exists(self, driver):
        """Pending upgrades have approve button."""
        driver.get(f"{DASHBOARD_URL}/self-modify/queue")
        
        approve_btns = driver.find_elements(
            By.XPATH, "//button[contains(text(), 'Approve') or contains(text(), 'APPROVE')]"
        )
        
        # If there are pending upgrades, there should be approve buttons
        pending = driver.find_elements(By.CSS_SELECTOR, ".upgrade-pending")
        if pending:
            assert len(approve_btns) >= 1, "Should have approve buttons for pending upgrades"

    def test_reject_button_exists(self, driver):
        """Pending upgrades have reject button."""
        driver.get(f"{DASHBOARD_URL}/self-modify/queue")
        
        reject_btns = driver.find_elements(
            By.XPATH, "//button[contains(text(), 'Reject') or contains(text(), 'REJECT')]"
        )
        
        pending = driver.find_elements(By.CSS_SELECTOR, ".upgrade-pending")
        if pending:
            assert len(reject_btns) >= 1, "Should have reject buttons for pending upgrades"

    def test_upgrade_history_section(self, driver):
        """Queue page shows history of past upgrades."""
        driver.get(f"{DASHBOARD_URL}/self-modify/queue")
        
        # Look for history section
        history = driver.find_elements(
            By.XPATH, "//*[contains(text(), 'History') or contains(text(), 'Past')]"
        )
        
        # Or look for applied/rejected upgrades
        past = driver.find_elements(By.CSS_SELECTOR, ".upgrade-applied, .upgrade-rejected, .upgrade-failed")
        
        assert history or past, "Should show upgrade history section or past upgrades"

    def test_view_diff_button(self, driver):
        """Can view diff for an upgrade."""
        driver.get(f"{DASHBOARD_URL}/self-modify/queue")
        
        view_btns = driver.find_elements(
            By.XPATH, "//button[contains(text(), 'View') or contains(text(), 'Diff')]"
        )
        
        upgrades = driver.find_elements(By.CSS_SELECTOR, ".upgrade-card")
        if upgrades and view_btns:
            # Click view
            view_btns[0].click()
            time.sleep(1)
            
            # Should show diff or modal
            diff = driver.find_elements(By.CSS_SELECTOR, ".diff, .code-block, pre")
            assert diff or "diff" in driver.page_source.lower(), "Should show diff view"

    def test_nav_link_to_queue(self, driver):
        """Navigation has link to upgrade queue."""
        driver.get(DASHBOARD_URL)
        
        queue_link = driver.find_elements(
            By.XPATH, "//a[contains(@href, 'self-modify') or contains(text(), 'Upgrade')]"
        )
        
        if queue_link:
            queue_link[0].click()
            time.sleep(1)
            assert "self-modify" in driver.current_url or "upgrade" in driver.current_url


class TestUpgradeWorkflow:
    """Full upgrade approval workflow."""

    def test_full_approve_workflow(self, driver):
        """Propose → Review → Approve → Applied.
        
        This test requires a pre-existing pending upgrade.
        """
        driver.get(f"{DASHBOARD_URL}/self-modify/queue")
        
        # Find first pending upgrade
        pending = driver.find_elements(By.CSS_SELECTOR, ".upgrade-pending")
        
        if not pending:
            pytest.skip("No pending upgrades to test workflow")
        
        # Click approve
        approve_btn = driver.find_element(
            By.XPATH, "(//button[contains(text(), 'Approve')])[1]"
        )
        approve_btn.click()
        
        # Wait for confirmation or status change
        time.sleep(2)
        
        # Should show success or status change
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        assert any(x in page_text for x in ["approved", "applied", "success"])

    def test_full_reject_workflow(self, driver):
        """Propose → Review → Reject."""
        driver.get(f"{DASHBOARD_URL}/self-modify/queue")
        
        pending = driver.find_elements(By.CSS_SELECTOR, ".upgrade-pending")
        
        if not pending:
            pytest.skip("No pending upgrades to test workflow")
        
        # Click reject
        reject_btn = driver.find_element(
            By.XPATH, "(//button[contains(text(), 'Reject')])[1]"
        )
        reject_btn.click()
        
        time.sleep(2)
        
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        assert "rejected" in page_text or "removed" in page_text
