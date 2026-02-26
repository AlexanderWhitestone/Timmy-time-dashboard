"""Regression tests for XSS prevention in the dashboard."""

import pytest
from fastapi.testclient import TestClient

def test_mobile_test_page_xss_prevention(client: TestClient):
    """
    Verify that the mobile-test page uses safer DOM manipulation.
    This test checks the template content for the presence of textContent 
    and proper usage of innerHTML for known safe constants.
    """
    response = client.get("/mobile-test")
    assert response.status_code == 200
    content = response.text
    
    # Check that we are using textContent for dynamic content
    assert "textContent =" in content
    
    # Check that we've updated the summaryBody.innerHTML usage to be safer
    # or replaced with appendChild/textContent where appropriate.
    # The fix uses innerHTML with template literals for structural parts 
    # but textContent for data parts.
    assert "summaryBody.innerHTML = '';" in content
    assert "p.textContent =" in content
    assert "statusMsg.textContent =" in content
