import os
import subprocess
import shutil
import pytest
from pathlib import Path
import time

# Production-like paths for functional testing
PROD_PROJECT_DIR = Path("/home/ubuntu/prod-sovereign-stack")
PROD_VAULT_DIR = PROD_PROJECT_DIR / "TimmyVault"
SETUP_SCRIPT_PATH = Path("/home/ubuntu/setup_timmy.sh")

@pytest.fixture(scope="module", autouse=True)
def setup_prod_env():
    """Ensure a clean environment and run the full installation."""
    if PROD_PROJECT_DIR.exists():
        shutil.rmtree(PROD_PROJECT_DIR)
    
    # Run the actual install command
    env = os.environ.copy()
    env["PROJECT_DIR"] = str(PROD_PROJECT_DIR)
    env["VAULT_DIR"] = str(PROD_VAULT_DIR)
    
    result = subprocess.run(
        [str(SETUP_SCRIPT_PATH), "install"],
        capture_output=True,
        text=True,
        env=env
    )
    
    assert result.returncode == 0, f"Install failed: {result.stderr}"
    yield
    # Cleanup after all tests in module
    # shutil.rmtree(PROD_PROJECT_DIR)

def test_prod_directory_structure():
    """Verify the directory structure matches production expectations."""
    assert PROD_PROJECT_DIR.exists()
    assert (PROD_PROJECT_DIR / "paperclip").exists()
    assert (PROD_PROJECT_DIR / "agents/hello-timmy").exists()
    assert PROD_VAULT_DIR.exists()
    assert (PROD_PROJECT_DIR / "logs").exists()
    assert (PROD_PROJECT_DIR / "pids").exists()

def test_prod_paperclip_dependencies():
    """Verify that Paperclip dependencies were actually installed (node_modules exists)."""
    node_modules = PROD_PROJECT_DIR / "paperclip/node_modules"
    assert node_modules.exists(), "Paperclip node_modules should exist after installation"
    # Check for a common package to ensure it's not just an empty dir
    assert (node_modules / "typescript").exists() or (node_modules / "vite").exists() or (node_modules / "next").exists() or any(node_modules.iterdir())

def test_prod_openfang_config():
    """Verify OpenFang agent configuration."""
    agent_toml = PROD_PROJECT_DIR / "agents/hello-timmy/agent.toml"
    assert agent_toml.exists()
    with open(agent_toml, "r") as f:
        content = f.read()
        assert 'name = "hello-timmy"' in content
        assert 'model = "default"' in content

def test_prod_obsidian_vault_content():
    """Verify the initial content of the Obsidian vault."""
    hello_note = PROD_VAULT_DIR / "Hello World.md"
    soul_note = PROD_VAULT_DIR / "SOUL.md"
    
    assert hello_note.exists()
    assert soul_note.exists()
    
    with open(hello_note, "r") as f:
        content = f.read()
        assert "# Hello World" in content
        assert "Paperclip" in content
        assert "OpenFang" in content

    with open(soul_note, "r") as f:
        content = f.read()
        assert "I am Timmy" in content
        assert "sovereign AI agent" in content

def test_prod_service_lifecycle():
    """Verify that services can be started, checked, and stopped."""
    env = os.environ.copy()
    env["PROJECT_DIR"] = str(PROD_PROJECT_DIR)
    env["VAULT_DIR"] = str(PROD_VAULT_DIR)

    # Start services
    start_result = subprocess.run(
        [str(SETUP_SCRIPT_PATH), "start"],
        capture_output=True,
        text=True,
        env=env
    )
    assert start_result.returncode == 0
    
    # Wait a moment for processes to initialize
    time.sleep(2)
    
    # Check status
    status_result = subprocess.run(
        [str(SETUP_SCRIPT_PATH), "status"],
        capture_output=True,
        text=True,
        env=env
    )
    assert "running" in status_result.stdout
    
    # Stop services
    stop_result = subprocess.run(
        [str(SETUP_SCRIPT_PATH), "stop"],
        capture_output=True,
        text=True,
        env=env
    )
    assert stop_result.returncode == 0
    
    # Final status check
    final_status = subprocess.run(
        [str(SETUP_SCRIPT_PATH), "status"],
        capture_output=True,
        text=True,
        env=env
    )
    assert "stopped" in final_status.stdout
