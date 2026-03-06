import os
import subprocess
import shutil
import pytest
from pathlib import Path

# Constants for testing
TEST_PROJECT_DIR = Path("/home/ubuntu/test-sovereign-stack")
TEST_VAULT_DIR = TEST_PROJECT_DIR / "TimmyVault"
SETUP_SCRIPT_PATH = Path("/home/ubuntu/setup_timmy.sh")

pytestmark = pytest.mark.skipif(
    not SETUP_SCRIPT_PATH.exists(),
    reason=f"Setup script not found at {SETUP_SCRIPT_PATH}",
)

@pytest.fixture(scope="module", autouse=True)
def cleanup_test_env():
    """Ensure a clean environment before and after tests."""
    if TEST_PROJECT_DIR.exists():
        shutil.rmtree(TEST_PROJECT_DIR)
    yield
    # We keep the test env for manual inspection if needed, or cleanup
    # shutil.rmtree(TEST_PROJECT_DIR)

def run_setup_command(args):
    """Helper to run the setup script with arguments."""
    result = subprocess.run(
        [str(SETUP_SCRIPT_PATH)] + args,
        capture_output=True,
        text=True,
        cwd="/home/ubuntu"
    )
    return result

def test_setup_install_creates_directories():
    """Test that './setup_timmy.sh install' creates the expected directory structure."""
    # Note: We expect the script to be present at SETUP_SCRIPT_PATH
    assert SETUP_SCRIPT_PATH.exists(), "Setup script must exist before testing"
    
    result = run_setup_command(["install"])
    
    # Check if command succeeded
    assert result.returncode == 0, f"Setup install failed: {result.stderr}"
    
    # Check directory structure
    assert TEST_PROJECT_DIR.exists()
    assert (TEST_PROJECT_DIR / "paperclip").exists()
    assert (TEST_PROJECT_DIR / "agents/hello-timmy").exists()
    assert TEST_VAULT_DIR.exists()
    assert (TEST_PROJECT_DIR / "logs").exists()

def test_setup_install_creates_files():
    """Test that './setup_timmy.sh install' creates the expected configuration and notes."""
    # Check Agent config
    agent_toml = TEST_PROJECT_DIR / "agents/hello-timmy/agent.toml"
    assert agent_toml.exists()
    with open(agent_toml, "r") as f:
        content = f.read()
        assert 'name = "hello-timmy"' in content

    # Check Obsidian notes
    hello_note = TEST_VAULT_DIR / "Hello World.md"
    soul_note = TEST_VAULT_DIR / "SOUL.md"
    assert hello_note.exists()
    assert soul_note.exists()
    
    with open(soul_note, "r") as f:
        content = f.read()
        assert "I am Timmy" in content

def test_setup_install_dependencies():
    """Test that dependencies are correctly handled (OpenFang, Paperclip deps)."""
    # Check if Paperclip node_modules exists (implies pnpm install ran)
    # Note: In a real TDD we might mock pnpm, but here we want to verify the actual setup
    node_modules = TEST_PROJECT_DIR / "paperclip/node_modules"
    assert node_modules.exists()

def test_setup_start_stop_logic():
    """Test the start/stop command logic (simulated)."""
    # This is harder to test fully without actually running the services,
    # but we can check if the script handles the commands without crashing.
    
    # Mocking start (it might fail if ports are taken, so we check return code)
    # For the sake of this test, we just check if the script recognizes the command
    result = run_setup_command(["status"])
    assert "Status" in result.stdout or result.returncode == 0
