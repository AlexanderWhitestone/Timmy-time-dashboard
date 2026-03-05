"""Pytest configuration for test markers and categorization.

This module registers pytest markers for test categorization without modifying
individual test files. All tests are automatically categorized based on their
location in the test directory structure.
"""

import pytest


def pytest_configure(config):
    """Register custom pytest markers."""
    markers = [
        "unit: Unit tests (fast, no I/O, no external services)",
        "integration: Integration tests (may use SQLite, in-process agents)",
        "functional: Functional tests (real HTTP requests, no mocking)",
        "e2e: End-to-end tests (full system, may be slow)",
        "slow: Tests that take >1 second",
        "selenium: Requires Selenium and Chrome (browser automation)",
        "docker: Requires Docker and docker-compose",
        "ollama: Requires Ollama service running",
        "external_api: Requires external API access",
        "skip_ci: Skip in CI environment (local development only)",
    ]
    for marker in markers:
        config.addinivalue_line("markers", marker)


def pytest_collection_modifyitems(config, items):
    """Automatically assign markers to tests based on file location."""
    for item in items:
        test_path = str(item.fspath)
        
        # Categorize based on directory
        if "e2e" in test_path:
            item.add_marker(pytest.mark.e2e)
            item.add_marker(pytest.mark.slow)
        elif "functional" in test_path:
            item.add_marker(pytest.mark.functional)
        elif "infrastructure" in test_path or "integration" in test_path:
            item.add_marker(pytest.mark.integration)
        else:
            item.add_marker(pytest.mark.unit)
        
        # Add additional markers based on test name/path
        if "selenium" in test_path or "ui_" in item.name:
            item.add_marker(pytest.mark.selenium)
            item.add_marker(pytest.mark.skip_ci)
        
        if "docker" in test_path:
            item.add_marker(pytest.mark.docker)
            item.add_marker(pytest.mark.skip_ci)
        
        if "ollama" in test_path or "test_ollama" in item.name:
            item.add_marker(pytest.mark.ollama)
        
        # Mark slow tests
        if "slow" in item.name:
            item.add_marker(pytest.mark.slow)
