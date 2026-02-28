"""End-to-end tests for microservices architecture.

These tests verify that the microservices-based deployment works correctly
with proper service isolation, communication, and orchestration.
"""

import pytest
from pathlib import Path


class TestMicroservicesArchitecture:
    """Test microservices architecture and Docker setup."""

    def test_microservices_compose_file_exists(self):
        """Test that docker-compose.microservices.yml exists."""
        compose_file = Path(__file__).parent.parent.parent / "docker-compose.microservices.yml"
        assert compose_file.exists(), "docker-compose.microservices.yml should exist"

    def test_microservices_compose_valid_yaml(self):
        """Test that microservices compose file is valid YAML."""
        import yaml
        compose_file = Path(__file__).parent.parent.parent / "docker-compose.microservices.yml"
        
        with open(compose_file) as f:
            config = yaml.safe_load(f)
        
        assert config is not None, "Compose file should be valid YAML"
        assert "services" in config, "Compose file should define services"

    def test_microservices_defines_all_services(self):
        """Test that all required services are defined."""
        import yaml
        compose_file = Path(__file__).parent.parent.parent / "docker-compose.microservices.yml"
        
        with open(compose_file) as f:
            config = yaml.safe_load(f)
        
        services = config.get("services", {})
        required_services = ["ollama", "dashboard", "timmy", "worker"]
        
        for service in required_services:
            assert service in services, f"Service '{service}' should be defined"

    def test_ollama_service_configuration(self):
        """Test that Ollama service is properly configured."""
        import yaml
        compose_file = Path(__file__).parent.parent.parent / "docker-compose.microservices.yml"
        
        with open(compose_file) as f:
            config = yaml.safe_load(f)
        
        ollama = config["services"]["ollama"]
        
        # Check required fields
        assert "image" in ollama or "build" in ollama, "Ollama should have image or build"
        assert "ports" in ollama, "Ollama should expose port 11434"
        assert "healthcheck" in ollama, "Ollama should have healthcheck"
        assert "volumes" in ollama, "Ollama should have volume for models"

    def test_dashboard_service_configuration(self):
        """Test that Dashboard service is properly configured."""
        import yaml
        compose_file = Path(__file__).parent.parent.parent / "docker-compose.microservices.yml"
        
        with open(compose_file) as f:
            config = yaml.safe_load(f)
        
        dashboard = config["services"]["dashboard"]
        
        # Check required fields
        assert "image" in dashboard or "build" in dashboard, "Dashboard should have image or build"
        assert "ports" in dashboard, "Dashboard should expose port 8000"
        assert "depends_on" in dashboard, "Dashboard should depend on ollama"
        assert "healthcheck" in dashboard, "Dashboard should have healthcheck"

    def test_timmy_agent_service_configuration(self):
        """Test that Timmy agent service is properly configured."""
        import yaml
        compose_file = Path(__file__).parent.parent.parent / "docker-compose.microservices.yml"
        
        with open(compose_file) as f:
            config = yaml.safe_load(f)
        
        timmy = config["services"]["timmy"]
        
        # Check required fields
        assert "image" in timmy or "build" in timmy, "Timmy should have image or build"
        assert "depends_on" in timmy, "Timmy should depend on dashboard and ollama"
        assert "environment" in timmy, "Timmy should have environment variables"

    def test_worker_service_is_scalable(self):
        """Test that worker service is configured for scaling."""
        import yaml
        compose_file = Path(__file__).parent.parent.parent / "docker-compose.microservices.yml"
        
        with open(compose_file) as f:
            config = yaml.safe_load(f)
        
        worker = config["services"]["worker"]
        
        # Check for scaling configuration
        assert "profiles" in worker, "Worker should have profiles for optional scaling"
        assert "workers" in worker["profiles"], "Worker should be in 'workers' profile"

    def test_network_configuration(self):
        """Test that services are on the same network."""
        import yaml
        compose_file = Path(__file__).parent.parent.parent / "docker-compose.microservices.yml"
        
        with open(compose_file) as f:
            config = yaml.safe_load(f)
        
        # Check networks exist
        assert "networks" in config, "Compose should define networks"
        assert "timmy-net" in config["networks"], "Should have timmy-net network"
        
        # Check all services use the network
        for service_name, service in config["services"].items():
            assert "networks" in service, f"Service {service_name} should be on a network"

    def test_volume_configuration(self):
        """Test that volumes are properly configured."""
        import yaml
        compose_file = Path(__file__).parent.parent.parent / "docker-compose.microservices.yml"
        
        with open(compose_file) as f:
            config = yaml.safe_load(f)
        
        # Check volumes exist
        assert "volumes" in config, "Compose should define volumes"
        assert "timmy-data" in config["volumes"], "Should have timmy-data volume"
        assert "ollama-data" in config["volumes"], "Should have ollama-data volume"


class TestDockerfiles:
    """Test individual Dockerfiles for microservices."""

    def test_dashboard_dockerfile_exists(self):
        """Test that dashboard Dockerfile exists."""
        dockerfile = Path(__file__).parent.parent.parent / "docker" / "Dockerfile.dashboard"
        assert dockerfile.exists(), "docker/Dockerfile.dashboard should exist"

    def test_agent_dockerfile_exists(self):
        """Test that agent Dockerfile exists."""
        dockerfile = Path(__file__).parent.parent.parent / "docker" / "Dockerfile.agent"
        assert dockerfile.exists(), "docker/Dockerfile.agent should exist"

    def test_ollama_dockerfile_exists(self):
        """Test that Ollama Dockerfile exists."""
        dockerfile = Path(__file__).parent.parent.parent / "docker" / "Dockerfile.ollama"
        assert dockerfile.exists(), "docker/Dockerfile.ollama should exist"

    def test_init_ollama_script_exists(self):
        """Test that Ollama init script exists."""
        script = Path(__file__).parent.parent.parent / "docker" / "scripts" / "init-ollama.sh"
        assert script.exists(), "docker/scripts/init-ollama.sh should exist"

    def test_dashboard_dockerfile_multistage(self):
        """Test that dashboard Dockerfile uses multi-stage build."""
        dockerfile = Path(__file__).parent.parent.parent / "docker" / "Dockerfile.dashboard"
        
        with open(dockerfile) as f:
            content = f.read()
        
        # Count FROM statements (should be 2 for multi-stage)
        from_count = content.count("FROM ")
        assert from_count >= 2, "Dashboard Dockerfile should use multi-stage build"

    def test_agent_dockerfile_multistage(self):
        """Test that agent Dockerfile uses multi-stage build."""
        dockerfile = Path(__file__).parent.parent.parent / "docker" / "Dockerfile.agent"
        
        with open(dockerfile) as f:
            content = f.read()
        
        from_count = content.count("FROM ")
        assert from_count >= 2, "Agent Dockerfile should use multi-stage build"

    def test_dashboard_dockerfile_has_healthcheck(self):
        """Test that dashboard Dockerfile includes healthcheck."""
        dockerfile = Path(__file__).parent.parent.parent / "docker" / "Dockerfile.dashboard"
        
        with open(dockerfile) as f:
            content = f.read()
        
        assert "HEALTHCHECK" in content, "Dashboard should have healthcheck"

    def test_ollama_dockerfile_has_healthcheck(self):
        """Test that Ollama Dockerfile includes healthcheck."""
        dockerfile = Path(__file__).parent.parent.parent / "docker" / "Dockerfile.ollama"
        
        with open(dockerfile) as f:
            content = f.read()
        
        assert "HEALTHCHECK" in content, "Ollama should have healthcheck"

    def test_dockerfiles_use_nonroot_user(self):
        """Test that Dockerfiles run as non-root user."""
        for dockerfile_name in ["Dockerfile.dashboard", "Dockerfile.agent"]:
            dockerfile = Path(__file__).parent.parent.parent / "docker" / dockerfile_name
            
            with open(dockerfile) as f:
                content = f.read()
            
            assert "USER " in content, f"{dockerfile_name} should specify a USER"


class TestTestFixtures:
    """Test that test fixtures are properly configured."""

    def test_conftest_exists(self):
        """Test that conftest.py exists."""
        conftest = Path(__file__).parent.parent / "conftest.py"
        assert conftest.exists(), "tests/conftest.py should exist"

    def test_conftest_has_mock_fixtures(self):
        """Test that conftest has mock fixtures."""
        conftest = Path(__file__).parent.parent / "conftest.py"
        
        with open(conftest) as f:
            content = f.read()
        
        required_fixtures = [
            "mock_ollama_client",
            "mock_timmy_agent",
            "mock_swarm_coordinator",
            "mock_memory_system",
        ]
        
        for fixture in required_fixtures:
            assert fixture in content, f"conftest should define {fixture}"

    def test_conftest_has_sample_data_fixtures(self):
        """Test that conftest has sample data fixtures."""
        conftest = Path(__file__).parent.parent / "conftest.py"
        
        with open(conftest) as f:
            content = f.read()
        
        required_fixtures = [
            "sample_interview_data",
            "sample_task_data",
            "sample_agent_data",
        ]
        
        for fixture in required_fixtures:
            assert fixture in content, f"conftest should define {fixture}"
