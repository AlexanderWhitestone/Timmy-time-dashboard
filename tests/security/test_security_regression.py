import pytest

def test_xss_protection_in_templates():
    """Verify that templates now use the escape filter for user-controlled content."""
    templates_to_check = [
        ("src/dashboard/templates/partials/chat_message.html", "{{ user_message | e }}"),
        ("src/dashboard/templates/partials/history.html", "{{ msg.content | e }}"),
        ("src/dashboard/templates/briefing.html", "{{ briefing.summary | e }}"),
        ("src/dashboard/templates/partials/approval_card_single.html", "{{ item.title | e }}"),
        ("src/dashboard/templates/marketplace.html", "{{ agent.name | e }}"),
    ]
    
    for path, expected_snippet in templates_to_check:
        with open(path, "r") as f:
            content = f.read()
            assert expected_snippet in content, f"XSS fix missing in {path}"

