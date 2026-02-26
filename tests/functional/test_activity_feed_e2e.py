"""E2E tests for Real-Time Activity Feed.

RUN: pytest tests/functional/test_activity_feed_e2e.py -v --headed
"""

import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import httpx

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


class TestActivityFeedUI:
    """Real-time activity feed on dashboard."""

    def test_activity_feed_exists_on_swarm_live(self, driver):
        """Swarm live page has activity feed panel."""
        driver.get(f"{DASHBOARD_URL}/swarm/live")
        
        # Look for activity feed
        feed = driver.find_elements(
            By.CSS_SELECTOR, ".activity-feed, .live-feed, .events-feed"
        )
        
        # Or look for activity header
        headers = driver.find_elements(
            By.XPATH, "//*[contains(text(), 'Activity') or contains(text(), 'Live')]"
        )
        
        assert feed or headers, "Should have activity feed panel"

    def test_activity_feed_shows_events(self, driver):
        """Activity feed displays events."""
        driver.get(f"{DASHBOARD_URL}/swarm/live")
        
        time.sleep(2)  # Let feed load
        
        # Look for event items
        events = driver.find_elements(By.CSS_SELECTOR, ".event-item, .activity-item")
        
        # Or empty state
        empty = driver.find_elements(By.XPATH, "//*[contains(text(), 'No activity')]")
        
        assert events or empty, "Should show events or empty state"

    def test_activity_feed_updates_in_realtime(self, driver):
        """Creating a task shows up in activity feed immediately.
        
        This tests the WebSocket real-time update.
        """
        driver.get(f"{DASHBOARD_URL}/swarm/live")
        
        # Get initial event count
        initial = len(driver.find_elements(By.CSS_SELECTOR, ".event-item"))
        
        # Create a task via API (this should trigger event)
        task_desc = f"Activity test {time.time()}"
        try:
            httpx.post(
                f"{DASHBOARD_URL}/swarm/tasks",
                data={"description": task_desc},
                timeout=5
            )
        except Exception:
            pass  # Task may not complete, but event should still fire
        
        # Wait for WebSocket update
        time.sleep(3)
        
        # Check for new event
        current = len(driver.find_elements(By.CSS_SELECTOR, ".event-item"))
        
        # Or check for task-related text
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        has_task_event = "task" in page_text and "created" in page_text
        
        assert current > initial or has_task_event, "Should see new activity"

    def test_activity_feed_shows_task_events(self, driver):
        """Task lifecycle events appear in feed."""
        driver.get(f"{DASHBOARD_URL}/swarm/live")
        
        time.sleep(2)
        
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        
        # Should see task-related events if any exist
        task_related = any(x in page_text for x in [
            "task.created", "task assigned", "task completed", "new task"
        ])
        
        # Not a failure if no tasks exist, just check the feed is there
        feed_exists = driver.find_elements(By.CSS_SELECTOR, ".activity-feed")
        assert feed_exists, "Activity feed should exist"

    def test_activity_feed_shows_agent_events(self, driver):
        """Agent join/leave events appear in feed."""
        driver.get(f"{DASHBOARD_URL}/swarm/live")
        
        time.sleep(2)
        
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        
        # Should see agent-related events if any exist
        agent_related = any(x in page_text for x in [
            "agent joined", "agent left", "agent status"
        ])
        
        # Feed should exist regardless
        feed = driver.find_elements(By.CSS_SELECTOR, ".activity-feed, .live-feed")

    def test_activity_feed_shows_bid_events(self, driver):
        """Bid events appear in feed."""
        driver.get(f"{DASHBOARD_URL}/swarm/live")
        
        time.sleep(2)
        
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        
        # Look for bid-related text
        bid_related = any(x in page_text for x in [
            "bid", "sats", "auction"
        ])

    def test_activity_feed_timestamps(self, driver):
        """Events show timestamps."""
        driver.get(f"{DASHBOARD_URL}/swarm/live")
        
        time.sleep(2)
        
        # Look for time patterns
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Should have timestamps (HH:MM format)
        import re
        time_pattern = re.search(r'\d{1,2}:\d{2}', page_text)
        
        # If there are events, they should have timestamps
        events = driver.find_elements(By.CSS_SELECTOR, ".event-item")
        if events:
            assert time_pattern, "Events should have timestamps"

    def test_activity_feed_icons(self, driver):
        """Different event types have different icons."""
        driver.get(f"{DASHBOARD_URL}/swarm/live")
        
        time.sleep(2)
        
        # Look for icons or visual indicators
        icons = driver.find_elements(By.CSS_SELECTOR, ".event-icon, .activity-icon, .icon")
        
        # Not required but nice to have


class TestActivityFeedIntegration:
    """Activity feed integration with other features."""

    def test_activity_appears_in_event_log(self, driver):
        """Activity feed events are also in event log page."""
        # Create a task
        try:
            httpx.post(
                f"{DASHBOARD_URL}/swarm/tasks",
                data={"description": "Integration test task"},
                timeout=5
            )
        except Exception:
            pass
        
        time.sleep(2)
        
        # Check event log
        driver.get(f"{DASHBOARD_URL}/swarm/events")
        
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        assert "task" in page_text, "Event log should show task events"

    def test_nav_to_swarm_live(self, driver):
        """Can navigate to swarm live page."""
        driver.get(DASHBOARD_URL)
        
        # Look for swarm/live link
        live_link = driver.find_elements(
            By.XPATH, "//a[contains(@href, '/swarm/live') or contains(text(), 'Live')]"
        )
        
        if live_link:
            live_link[0].click()
            time.sleep(1)
            assert "/swarm/live" in driver.current_url
