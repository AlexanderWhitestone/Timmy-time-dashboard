"""Paperclip AI config settings."""


def test_paperclip_url_default():
    from config import settings

    assert hasattr(settings, "paperclip_url")
    assert settings.paperclip_url == "http://localhost:3100"


def test_paperclip_enabled_default_false():
    from config import settings

    assert hasattr(settings, "paperclip_enabled")
    assert settings.paperclip_enabled is False


def test_paperclip_timeout_default():
    from config import settings

    assert hasattr(settings, "paperclip_timeout")
    assert settings.paperclip_timeout == 30


def test_paperclip_agent_id_default_empty():
    from config import settings

    assert hasattr(settings, "paperclip_agent_id")
    assert settings.paperclip_agent_id == ""


def test_paperclip_company_id_default_empty():
    from config import settings

    assert hasattr(settings, "paperclip_company_id")
    assert settings.paperclip_company_id == ""


def test_paperclip_poll_interval_default_zero():
    from config import settings

    assert hasattr(settings, "paperclip_poll_interval")
    assert settings.paperclip_poll_interval == 0
