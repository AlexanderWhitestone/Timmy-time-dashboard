from timmy.prompts import TIMMY_SYSTEM_PROMPT, TIMMY_STATUS_PROMPT


def test_system_prompt_not_empty():
    assert TIMMY_SYSTEM_PROMPT.strip()


def test_system_prompt_has_timmy_identity():
    assert "Timmy" in TIMMY_SYSTEM_PROMPT


def test_system_prompt_mentions_sovereignty():
    assert "sovereignty" in TIMMY_SYSTEM_PROMPT.lower()


def test_system_prompt_references_local():
    assert "local" in TIMMY_SYSTEM_PROMPT.lower()


def test_system_prompt_is_multiline():
    assert "\n" in TIMMY_SYSTEM_PROMPT


def test_status_prompt_not_empty():
    assert TIMMY_STATUS_PROMPT.strip()


def test_status_prompt_has_timmy():
    assert "Timmy" in TIMMY_STATUS_PROMPT


def test_prompts_are_distinct():
    assert TIMMY_SYSTEM_PROMPT != TIMMY_STATUS_PROMPT
