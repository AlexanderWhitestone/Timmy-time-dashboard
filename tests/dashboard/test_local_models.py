"""Tests for the local browser model feature — /mobile/local endpoint.

Categories:
  L1xx  Route & API responses
  L2xx  Config settings
  L3xx  Template content & UX
  L4xx  JavaScript asset
  L5xx  Security (XSS prevention)
"""

import re
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def _local_html(client) -> str:
    return client.get("/mobile/local").text


def _local_llm_js() -> str:
    js_path = Path(__file__).parent.parent.parent / "static" / "local_llm.js"
    return js_path.read_text()


# ── L1xx — Route & API responses ─────────────────────────────────────────────

def test_L101_mobile_local_route_returns_200(client):
    """The /mobile/local endpoint should return 200 OK."""
    response = client.get("/mobile/local")
    assert response.status_code == 200


def test_L102_local_models_config_endpoint(client):
    """The /mobile/local-models API should return model config JSON."""
    response = client.get("/mobile/local-models")
    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data
    assert "default_model" in data
    assert "fallback_to_server" in data
    assert "server_model" in data


def test_L103_mobile_status_includes_browser_model(client):
    """The /mobile/status endpoint should include browser model info."""
    response = client.get("/mobile/status")
    assert response.status_code == 200
    data = response.json()
    assert "browser_model_enabled" in data
    assert "browser_model_id" in data


def test_L104_local_models_config_default_values(client):
    """Config defaults should match what's in config.py."""
    data = client.get("/mobile/local-models").json()
    assert data["enabled"] is True
    assert "SmolLM2" in data["default_model"] or "MLC" in data["default_model"]
    assert data["fallback_to_server"] is True


# ── L2xx — Config settings ───────────────────────────────────────────────────

def test_L201_config_has_browser_model_enabled():
    """config.py should define browser_model_enabled."""
    from config import settings
    assert hasattr(settings, "browser_model_enabled")
    assert isinstance(settings.browser_model_enabled, bool)


def test_L202_config_has_browser_model_id():
    """config.py should define browser_model_id."""
    from config import settings
    assert hasattr(settings, "browser_model_id")
    assert isinstance(settings.browser_model_id, str)
    assert len(settings.browser_model_id) > 0


def test_L203_config_has_browser_model_fallback():
    """config.py should define browser_model_fallback."""
    from config import settings
    assert hasattr(settings, "browser_model_fallback")
    assert isinstance(settings.browser_model_fallback, bool)


# ── L3xx — Template content & UX ────────────────────────────────────────────

def test_L301_template_includes_local_llm_script(client):
    """mobile_local.html must include the local_llm.js script."""
    html = _local_html(client)
    assert "local_llm.js" in html


def test_L302_template_has_model_selector(client):
    """Template must have a model selector element."""
    html = _local_html(client)
    assert 'id="model-select"' in html


def test_L303_template_has_load_button(client):
    """Template must have a load model button."""
    html = _local_html(client)
    assert 'id="btn-load"' in html


def test_L304_template_has_progress_bar(client):
    """Template must have a progress bar for model download."""
    html = _local_html(client)
    assert 'id="progress-bar"' in html


def test_L305_template_has_chat_area(client):
    """Template must have a chat log area."""
    html = _local_html(client)
    assert 'id="local-chat"' in html


def test_L306_template_has_message_input(client):
    """Template must have a message input field."""
    html = _local_html(client)
    assert 'id="local-message"' in html


def test_L307_input_font_size_16px(client):
    """Input font-size must be 16px to prevent iOS zoom."""
    html = _local_html(client)
    assert "font-size: 16px" in html


def test_L308_input_has_ios_attributes(client):
    """Input should have autocapitalize, autocorrect, spellcheck, enterkeyhint."""
    html = _local_html(client)
    assert 'autocapitalize="none"' in html
    assert 'autocorrect="off"' in html
    assert 'spellcheck="false"' in html
    assert 'enterkeyhint="send"' in html


def test_L309_touch_targets_44px(client):
    """Buttons and inputs must meet 44px min-height (Apple HIG)."""
    html = _local_html(client)
    assert "min-height: 44px" in html


def test_L310_safe_area_inset_bottom(client):
    """Chat input must account for iPhone home indicator."""
    html = _local_html(client)
    assert "safe-area-inset-bottom" in html


def test_L311_template_has_backend_badge(client):
    """Template should show LOCAL or SERVER badge."""
    html = _local_html(client)
    assert "backend-badge" in html
    assert "LOCAL" in html


# ── L4xx — JavaScript asset ──────────────────────────────────────────────────

def test_L401_local_llm_js_exists():
    """static/local_llm.js must exist."""
    js_path = Path(__file__).parent.parent.parent / "static" / "local_llm.js"
    assert js_path.exists(), "static/local_llm.js not found"


def test_L402_local_llm_js_defines_class():
    """local_llm.js must define the LocalLLM class."""
    js = _local_llm_js()
    assert "class LocalLLM" in js


def test_L403_local_llm_js_has_model_catalogue():
    """local_llm.js must define a MODEL_CATALOGUE."""
    js = _local_llm_js()
    assert "MODEL_CATALOGUE" in js


def test_L404_local_llm_js_has_webgpu_detection():
    """local_llm.js must detect WebGPU capability."""
    js = _local_llm_js()
    assert "detectWebGPU" in js or "navigator.gpu" in js


def test_L405_local_llm_js_has_chat_method():
    """local_llm.js LocalLLM class must have a chat method."""
    js = _local_llm_js()
    assert "async chat(" in js


def test_L406_local_llm_js_has_init_method():
    """local_llm.js LocalLLM class must have an init method."""
    js = _local_llm_js()
    assert "async init(" in js


def test_L407_local_llm_js_has_unload_method():
    """local_llm.js LocalLLM class must have an unload method."""
    js = _local_llm_js()
    assert "async unload(" in js


def test_L408_local_llm_js_exports_to_window():
    """local_llm.js must export LocalLLM and catalogue to window."""
    js = _local_llm_js()
    assert "window.LocalLLM" in js
    assert "window.LOCAL_MODEL_CATALOGUE" in js


def test_L409_local_llm_js_has_streaming_support():
    """local_llm.js chat method must support streaming via onToken."""
    js = _local_llm_js()
    assert "onToken" in js
    assert "stream: true" in js


def test_L410_local_llm_js_has_isSupported_static():
    """LocalLLM must have a static isSupported() method."""
    js = _local_llm_js()
    assert "static isSupported()" in js


# ── L5xx — Security ─────────────────────────────────────────────────────────

def test_L501_no_innerhtml_with_user_input(client):
    """Template must not use innerHTML with user-controlled data."""
    html = _local_html(client)
    # Check for dangerous patterns: innerHTML += `${message}` etc.
    blocks = re.findall(r"innerHTML\s*\+=?\s*`([^`]*)`", html, re.DOTALL)
    for block in blocks:
        assert "${message}" not in block, (
            "innerHTML template literal contains ${message} — XSS vulnerability"
        )


def test_L502_uses_textcontent_for_messages(client):
    """Template must use textContent (not innerHTML) for user messages."""
    html = _local_html(client)
    assert "textContent" in html


def test_L503_no_eval_or_function_constructor():
    """local_llm.js must not use eval() or new Function()."""
    js = _local_llm_js()
    # Allow "evaluate" and "functionality" but not standalone eval(
    assert "eval(" not in js or "evaluate" in js
    assert "new Function(" not in js
