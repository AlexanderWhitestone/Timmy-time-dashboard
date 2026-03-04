from timmy.prompts import TIMMY_SYSTEM_PROMPT, TIMMY_STATUS_PROMPT, get_system_prompt


def test_system_prompt_not_empty():
    assert TIMMY_SYSTEM_PROMPT.strip()


def test_system_prompt_no_persona_identity():
    """System prompt should NOT contain persona identity references."""
    prompt = TIMMY_SYSTEM_PROMPT.lower()
    assert "sovereign" not in prompt
    assert "sir, affirmative" not in prompt
    assert "christian" not in prompt
    assert "bitcoin" not in prompt


def test_system_prompt_references_local():
    assert "local" in TIMMY_SYSTEM_PROMPT.lower()


def test_system_prompt_is_multiline():
    assert "\n" in TIMMY_SYSTEM_PROMPT


def test_status_prompt_not_empty():
    assert TIMMY_STATUS_PROMPT.strip()


def test_status_prompt_no_persona():
    """Status prompt should not reference a persona."""
    assert "Timmy" not in TIMMY_STATUS_PROMPT


def test_prompts_are_distinct():
    assert TIMMY_SYSTEM_PROMPT != TIMMY_STATUS_PROMPT


def test_get_system_prompt_injects_model_name():
    """System prompt should inject actual model name from config."""
    prompt = get_system_prompt(tools_enabled=False)
    # Should contain the model name from settings, not the placeholder
    assert "{model_name}" not in prompt
    assert "llama3.1" in prompt or "qwen" in prompt
