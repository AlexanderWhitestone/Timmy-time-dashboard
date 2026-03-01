"""Chunk 1: OpenFang config settings — test first, implement second."""


def test_openfang_url_default():
    """Settings should expose openfang_url with a sensible default."""
    from config import settings

    assert hasattr(settings, "openfang_url")
    assert settings.openfang_url == "http://localhost:8080"


def test_openfang_enabled_default_false():
    """OpenFang integration should be opt-in (disabled by default)."""
    from config import settings

    assert hasattr(settings, "openfang_enabled")
    assert settings.openfang_enabled is False


def test_openfang_timeout_default():
    """Timeout should be generous (some hands are slow)."""
    from config import settings

    assert hasattr(settings, "openfang_timeout")
    assert settings.openfang_timeout == 120
