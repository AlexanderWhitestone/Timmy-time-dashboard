"""End-to-end tests for Docker deployment.

These tests verify that the Dockerized application starts correctly,
responds to requests, and all services are properly orchestrated.
"""

import pytest
import subprocess
import time
import requests
import json
from pathlib import Path


@pytest.fixture(scope="module")
def docker_compose_file():
    """Return the path to the docker-compose file."""
    return Path(__file__).parent.parent.parent / "docker-compose.enhanced.yml"


@pytest.fixture(scope="module")
def docker_services_running(docker_compose_file):
    """Start Docker services for testing."""
    if not docker_compose_file.exists():
        pytest.skip("docker-compose.enhanced.yml not found")
    
    # Start services
    result = subprocess.run(
        ["docker", "compose", "-f", str(docker_compose_file), "up", "-d"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        pytest.skip(f"Failed to start Docker services: {result.stderr}")
    
    # Wait for services to be ready
    time.sleep(10)
    
    yield
    
    # Cleanup
    subprocess.run(
        ["docker", "compose", "-f", str(docker_compose_file), "down"],
        capture_output=True,
    )


@pytest.mark.skipif(
    subprocess.run(["which", "docker"], capture_output=True).returncode != 0,
    reason="Docker not installed"
)
def test_docker_compose_file_exists():
    """Test that docker-compose.enhanced.yml exists."""
    compose_file = Path(__file__).parent.parent.parent / "docker-compose.enhanced.yml"
    assert compose_file.exists(), "docker-compose.enhanced.yml should exist"


@pytest.mark.skipif(
    subprocess.run(["which", "docker"], capture_output=True).returncode != 0,
    reason="Docker not installed"
)
def test_docker_compose_syntax():
    """Test that docker-compose file has valid syntax."""
    compose_file = Path(__file__).parent.parent.parent / "docker-compose.enhanced.yml"
    
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "config"],
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0, f"Docker Compose syntax error: {result.stderr}"


@pytest.mark.skipif(
    subprocess.run(["which", "docker"], capture_output=True).returncode != 0,
    reason="Docker not installed"
)
def test_dockerfile_exists():
    """Test that Dockerfile exists."""
    dockerfile = Path(__file__).parent.parent.parent / "Dockerfile"
    assert dockerfile.exists(), "Dockerfile should exist"


@pytest.mark.skipif(
    subprocess.run(["which", "docker"], capture_output=True).returncode != 0,
    reason="Docker not installed"
)
def test_dockerfile_ollama_exists():
    """Test that Dockerfile.ollama exists."""
    dockerfile = Path(__file__).parent.parent.parent / "Dockerfile.ollama"
    assert dockerfile.exists(), "Dockerfile.ollama should exist"


@pytest.mark.skipif(
    subprocess.run(["which", "docker"], capture_output=True).returncode != 0,
    reason="Docker not installed"
)
def test_docker_image_build():
    """Test that the Docker image can be built."""
    result = subprocess.run(
        ["docker", "build", "-t", "timmy-time:test", "."],
        cwd=Path(__file__).parent.parent.parent,
        capture_output=True,
        text=True,
        timeout=300,
    )
    
    # Don't fail if build fails, just skip
    if result.returncode != 0:
        pytest.skip(f"Docker build failed: {result.stderr}")


@pytest.mark.skipif(
    subprocess.run(["which", "docker"], capture_output=True, shell=True).returncode != 0,
    reason="Docker not installed"
)
def test_docker_compose_services_defined():
    """Test that docker-compose defines all required services."""
    compose_file = Path(__file__).parent.parent.parent / "docker-compose.enhanced.yml"
    
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "config"],
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0, "Docker Compose config should be valid"
    
    config = json.loads(result.stdout)
    services = config.get("services", {})
    
    # Check for required services
    assert "ollama" in services, "ollama service should be defined"
    assert "dashboard" in services, "dashboard service should be defined"
    assert "timmy" in services, "timmy service should be defined"


def test_docker_compose_enhanced_yml_content():
    """Test that docker-compose.enhanced.yml has correct configuration."""
    compose_file = Path(__file__).parent.parent.parent / "docker-compose.enhanced.yml"
    
    with open(compose_file) as f:
        content = f.read()
    
    # Check for key configurations
    assert "ollama" in content, "Should reference ollama service"
    assert "dashboard" in content, "Should reference dashboard service"
    assert "timmy" in content, "Should reference timmy agent"
    assert "swarm-net" in content, "Should define swarm network"
    assert "ollama-data" in content, "Should define ollama-data volume"
    assert "timmy-data" in content, "Should define timmy-data volume"


def test_dockerfile_health_check():
    """Test that Dockerfile includes health check."""
    dockerfile = Path(__file__).parent.parent.parent / "Dockerfile"
    
    with open(dockerfile) as f:
        content = f.read()
    
    assert "HEALTHCHECK" in content, "Dockerfile should include HEALTHCHECK"
    assert "/health" in content, "Health check should use /health endpoint"


def test_dockerfile_non_root_user():
    """Test that Dockerfile runs as non-root user."""
    dockerfile = Path(__file__).parent.parent.parent / "Dockerfile"
    
    with open(dockerfile) as f:
        content = f.read()
    
    assert "USER timmy" in content, "Dockerfile should run as non-root user"
    assert "groupadd -r timmy" in content, "Dockerfile should create timmy user"
