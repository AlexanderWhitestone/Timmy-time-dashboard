"""Mobile-first quality tests — automated validation of mobile UX requirements.

These tests verify the HTML, CSS, and HTMX attributes that make the dashboard
work correctly on phones.  No browser / Playwright required: we parse the
static assets and server responses directly.

Categories:
  M1xx  Viewport & meta tags
  M2xx  Touch target sizing
  M3xx  iOS keyboard & zoom prevention
  M4xx  HTMX robustness (double-submit, sync)
  M5xx  Safe-area / notch support
  M6xx  AirLLM backend interface contract
"""

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _css() -> str:
    """Read the main stylesheet."""
    css_path = Path(__file__).parent.parent / "static" / "style.css"
    return css_path.read_text()


def _index_html(client) -> str:
    return client.get("/").text


def _timmy_panel_html(client) -> str:
    """Fetch the Timmy chat panel (loaded dynamically from index via HTMX)."""
    return client.get("/agents/timmy/panel").text


# ── M1xx — Viewport & meta tags ───────────────────────────────────────────────

def test_M101_viewport_meta_present(client):
    """viewport meta tag must exist for correct mobile scaling."""
    html = _index_html(client)
    assert 'name="viewport"' in html


def test_M102_viewport_includes_width_device_width(client):
    html = _index_html(client)
    assert "width=device-width" in html


def test_M103_viewport_includes_initial_scale_1(client):
    html = _index_html(client)
    assert "initial-scale=1" in html


def test_M104_viewport_includes_viewport_fit_cover(client):
    """viewport-fit=cover is required for iPhone notch / Dynamic Island support."""
    html = _index_html(client)
    assert "viewport-fit=cover" in html


def test_M105_apple_mobile_web_app_capable(client):
    """Enables full-screen / standalone mode when added to iPhone home screen."""
    html = _index_html(client)
    assert "apple-mobile-web-app-capable" in html


def test_M106_theme_color_meta_present(client):
    """theme-color sets the browser chrome colour on Android Chrome."""
    html = _index_html(client)
    assert 'name="theme-color"' in html


def test_M107_apple_status_bar_style_present(client):
    html = _index_html(client)
    assert "apple-mobile-web-app-status-bar-style" in html


def test_M108_lang_attribute_on_html(client):
    """lang attribute aids screen readers and mobile TTS."""
    html = _index_html(client)
    assert '<html lang="en"' in html


# ── M2xx — Touch target sizing ────────────────────────────────────────────────

def test_M201_send_button_min_height_44px():
    """SEND button must be at least 44 × 44 px — Apple HIG minimum."""
    css = _css()
    # Inside the mobile media query the send button must have min-height: 44px
    assert "min-height: 44px" in css


def test_M202_input_min_height_44px():
    """Chat input must meet 44 px touch target height on mobile."""
    css = _css()
    assert "min-height: 44px" in css


def test_M203_send_button_min_width_64px():
    """Send button needs sufficient width so it isn't accidentally missed."""
    css = _css()
    assert "min-width: 64px" in css


def test_M204_touch_action_manipulation_on_buttons():
    """touch-action: manipulation removes 300ms tap delay on mobile browsers."""
    css = _css()
    assert "touch-action: manipulation" in css


# ── M3xx — iOS keyboard & zoom prevention ─────────────────────────────────────

def test_M301_input_font_size_16px_in_mobile_query():
    """iOS Safari zooms in when input font-size < 16px.  Must be exactly 16px."""
    css = _css()
    # The mobile media-query block must override to 16px
    mobile_block_match = re.search(
        r"@media\s*\(max-width:\s*768px\)(.*)", css, re.DOTALL
    )
    assert mobile_block_match, "Mobile media query not found"
    mobile_block = mobile_block_match.group(1)
    assert "font-size: 16px" in mobile_block


def test_M302_input_autocapitalize_none(client):
    """autocapitalize=none prevents iOS from capitalising chat commands."""
    html = _timmy_panel_html(client)
    assert 'autocapitalize="none"' in html


def test_M303_input_autocorrect_off(client):
    """autocorrect=off prevents iOS from mangling technical / proper-noun input."""
    html = _timmy_panel_html(client)
    assert 'autocorrect="off"' in html


def test_M304_input_enterkeyhint_send(client):
    """enterkeyhint=send labels the iOS return key 'Send' for clearer UX."""
    html = _timmy_panel_html(client)
    assert 'enterkeyhint="send"' in html


def test_M305_input_spellcheck_false(client):
    """spellcheck=false prevents red squiggles on technical terms."""
    html = _timmy_panel_html(client)
    assert 'spellcheck="false"' in html


# ── M4xx — HTMX robustness ────────────────────────────────────────────────────

def test_M401_form_hx_sync_drop(client):
    """hx-sync=this:drop discards duplicate submissions (fast double-tap)."""
    html = _timmy_panel_html(client)
    assert 'hx-sync="this:drop"' in html


def test_M402_form_hx_disabled_elt(client):
    """hx-disabled-elt disables the SEND button while a request is in-flight."""
    html = _timmy_panel_html(client)
    assert "hx-disabled-elt" in html


def test_M403_form_hx_indicator(client):
    """hx-indicator wires up the loading spinner to the in-flight state."""
    html = _timmy_panel_html(client)
    assert "hx-indicator" in html


def test_M404_health_panel_auto_refreshes(client):
    """Health panel must poll via HTMX trigger — 'every 30s' confirms this."""
    html = _index_html(client)
    assert "every 30s" in html


def test_M405_chat_log_loads_history_on_boot(client):
    """Chat log fetches history via hx-trigger=load so it's populated on open."""
    html = _index_html(client)
    assert 'hx-trigger="load"' in html


# ── M5xx — Safe-area / notch support ─────────────────────────────────────────

def test_M501_safe_area_inset_top_in_header():
    """Header padding must accommodate the iPhone notch / status bar."""
    css = _css()
    assert "safe-area-inset-top" in css


def test_M502_safe_area_inset_bottom_in_footer():
    """Chat footer padding must clear the iPhone home indicator bar."""
    css = _css()
    assert "safe-area-inset-bottom" in css


def test_M503_overscroll_behavior_none():
    """overscroll-behavior: none prevents the jarring rubber-band effect."""
    css = _css()
    assert "overscroll-behavior: none" in css


def test_M504_webkit_overflow_scrolling_touch():
    """-webkit-overflow-scrolling: touch gives momentum scrolling on iOS."""
    css = _css()
    assert "-webkit-overflow-scrolling: touch" in css


def test_M505_dvh_units_used():
    """Dynamic viewport height (dvh) accounts for collapsing browser chrome."""
    css = _css()
    assert "dvh" in css


# ── M6xx — AirLLM backend interface contract ──────────────────────────────────

def test_M601_airllm_agent_has_run_method():
    """TimmyAirLLMAgent must expose run() so the dashboard route can call it."""
    from timmy.backends import TimmyAirLLMAgent
    assert hasattr(TimmyAirLLMAgent, "run"), (
        "TimmyAirLLMAgent is missing run() — dashboard will fail with AirLLM backend"
    )


def test_M602_airllm_run_returns_content_attribute():
    """run() must return an object with a .content attribute (Agno RunResponse compat)."""
    with patch("timmy.backends.is_apple_silicon", return_value=False):
        from timmy.backends import TimmyAirLLMAgent
        agent = TimmyAirLLMAgent(model_size="8b")

    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    input_ids_mock = MagicMock()
    input_ids_mock.shape = [1, 5]
    mock_tokenizer.return_value = {"input_ids": input_ids_mock}
    mock_tokenizer.decode.return_value = "Sir, affirmative."
    mock_model.tokenizer = mock_tokenizer
    mock_model.generate.return_value = [list(range(10))]
    agent._model = mock_model

    result = agent.run("test")
    assert hasattr(result, "content"), "run() result must have a .content attribute"
    assert isinstance(result.content, str)


def test_M603_airllm_run_updates_history():
    """run() must update _history so multi-turn context is preserved."""
    with patch("timmy.backends.is_apple_silicon", return_value=False):
        from timmy.backends import TimmyAirLLMAgent
        agent = TimmyAirLLMAgent(model_size="8b")

    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    input_ids_mock = MagicMock()
    input_ids_mock.shape = [1, 5]
    mock_tokenizer.return_value = {"input_ids": input_ids_mock}
    mock_tokenizer.decode.return_value = "Acknowledged."
    mock_model.tokenizer = mock_tokenizer
    mock_model.generate.return_value = [list(range(10))]
    agent._model = mock_model

    assert len(agent._history) == 0
    agent.run("hello")
    assert len(agent._history) == 2
    assert any("hello" in h for h in agent._history)


def test_M604_airllm_print_response_delegates_to_run():
    """print_response must use run() so both interfaces share one inference path."""
    with patch("timmy.backends.is_apple_silicon", return_value=False):
        from timmy.backends import TimmyAirLLMAgent, RunResult
        agent = TimmyAirLLMAgent(model_size="8b")

    with patch.object(agent, "run", return_value=RunResult(content="ok")) as mock_run, \
         patch.object(agent, "_render"):
        agent.print_response("hello", stream=True)

    mock_run.assert_called_once_with("hello", stream=True)


def test_M605_health_status_passes_model_to_template(client):
    """Health status partial must receive the configured model name, not a hardcoded string."""
    with patch("dashboard.routes.health.check_ollama", new_callable=AsyncMock, return_value=True):
        response = client.get("/health/status")
    # The default model is llama3.2 — it should appear in the partial from settings, not hardcoded
    assert response.status_code == 200
    assert "llama3.2" in response.text  # rendered via template variable, not hardcoded literal


# ── M7xx — XSS prevention ─────────────────────────────────────────────────────

def _mobile_html() -> str:
    """Read the mobile template source."""
    path = Path(__file__).parent.parent / "src" / "dashboard" / "templates" / "mobile.html"
    return path.read_text()


def _swarm_live_html() -> str:
    """Read the swarm live template source."""
    path = Path(__file__).parent.parent / "src" / "dashboard" / "templates" / "swarm_live.html"
    return path.read_text()


def test_M701_mobile_chat_no_raw_message_interpolation():
    """mobile.html must not interpolate ${message} directly into innerHTML — XSS risk."""
    html = _mobile_html()
    # The vulnerable pattern is `${message}` inside a template literal assigned to innerHTML
    # After the fix, message must only appear via textContent assignment
    assert "textContent = message" in html or "textContent=message" in html, (
        "mobile.html still uses innerHTML + ${message} interpolation — XSS vulnerability"
    )


def test_M702_mobile_chat_user_input_not_in_innerhtml_template_literal():
    """${message} must not appear inside a backtick string that is assigned to innerHTML."""
    html = _mobile_html()
    # Find all innerHTML += `...` blocks and verify none contain ${message}
    blocks = re.findall(r"innerHTML\s*\+=?\s*`([^`]*)`", html, re.DOTALL)
    for block in blocks:
        assert "${message}" not in block, (
            "innerHTML template literal still contains ${message} — XSS vulnerability"
        )


def test_M703_swarm_live_agent_name_not_interpolated_in_innerhtml():
    """swarm_live.html must not put ${agent.name} inside innerHTML template literals."""
    html = _swarm_live_html()
    blocks = re.findall(r"innerHTML\s*=\s*agents\.map\([^;]+\)\.join\([^)]*\)", html, re.DOTALL)
    assert len(blocks) == 0, (
        "swarm_live.html still uses innerHTML=agents.map(…) with interpolated agent data — XSS vulnerability"
    )


def test_M704_swarm_live_uses_textcontent_for_agent_data():
    """swarm_live.html must use textContent (not innerHTML) to set agent name/description."""
    html = _swarm_live_html()
    assert "textContent" in html, (
        "swarm_live.html does not use textContent — agent data may be raw-interpolated into DOM"
    )
