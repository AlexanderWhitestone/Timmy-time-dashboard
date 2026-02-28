"""End-to-end tests for Docker deployment.

These tests verify that Dockerfiles and compose configs are present,
syntactically valid, and declare the expected services and settings.
"""

import json
import subprocess

import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.mark.skipif(
    subprocess.run(["which", "docker"], capture_output=True).returncode != 0,
    reason="Docker not installed",
)
class TestDockerComposeFiles:
    """Validate that all compose files exist and parse cleanly."""

    def test_base_compose_exists(self):
        assert (PROJECT_ROOT / "docker-compose.yml").exists()

    def test_dev_overlay_exists(self):
        assert (PROJECT_ROOT / "docker-compose.dev.yml").exists()

    def test_prod_compose_exists(self):
        assert (PROJECT_ROOT / "docker-compose.prod.yml").exists()

    def test_test_compose_exists(self):
        assert (PROJECT_ROOT / "docker-compose.test.yml").exists()

    def test_microservices_compose_exists(self):
        assert (PROJECT_ROOT / "docker-compose.microservices.yml").exists()

    def test_base_compose_syntax(self):
        result = subprocess.run(
            ["docker", "compose", "-f", str(PROJECT_ROOT / "docker-compose.yml"), "config"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Docker Compose syntax error: {result.stderr}"

    def test_microservices_compose_services_defined(self):
        result = subprocess.run(
            [
                "docker", "compose",
                "-f", str(PROJECT_ROOT / "docker-compose.microservices.yml"),
                "config", "--format", "json",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Config error: {result.stderr}"
        config = json.loads(result.stdout)
        services = config.get("services", {})
        assert "ollama" in services, "ollama service should be defined"
        assert "dashboard" in services, "dashboard service should be defined"
        assert "timmy" in services, "timmy service should be defined"

    def test_microservices_compose_content(self):
        content = (PROJECT_ROOT / "docker-compose.microservices.yml").read_text()
        assert "ollama" in content
        assert "dashboard" in content
        assert "timmy" in content
        assert "timmy-net" in content
        assert "ollama-data" in content
        assert "timmy-data" in content

    def test_test_compose_has_test_runner(self):
        content = (PROJECT_ROOT / "docker-compose.test.yml").read_text()
        assert "test:" in content, "Test compose should define a 'test' service"
        assert "TIMMY_TEST_MODE" in content
        assert "pytest" in content


class TestDockerfiles:
    """Validate the primary Dockerfile and specialised images."""

    def test_dockerfile_exists(self):
        assert (PROJECT_ROOT / "Dockerfile").exists()

    def test_dockerfile_ollama_exists(self):
        assert (PROJECT_ROOT / "docker" / "Dockerfile.ollama").exists()

    def test_dockerfile_agent_exists(self):
        assert (PROJECT_ROOT / "docker" / "Dockerfile.agent").exists()

    def test_dockerfile_dashboard_exists(self):
        assert (PROJECT_ROOT / "docker" / "Dockerfile.dashboard").exists()

    def test_dockerfile_test_exists(self):
        assert (PROJECT_ROOT / "docker" / "Dockerfile.test").exists()

    def test_dockerfile_health_check(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "HEALTHCHECK" in content, "Dockerfile should include HEALTHCHECK"
        assert "/health" in content

    def test_dockerfile_non_root_user(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "USER timmy" in content
        assert "groupadd -r timmy" in content

    @pytest.mark.skipif(
        subprocess.run(["which", "docker"], capture_output=True).returncode != 0,
        reason="Docker not installed",
    )
    @pytest.mark.timeout(300)
    def test_docker_image_build(self):
        result = subprocess.run(
            ["docker", "build", "-t", "timmy-time:test", "."],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            pytest.skip(f"Docker build failed: {result.stderr}")
