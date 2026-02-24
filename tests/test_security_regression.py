import hmac
import hashlib
import base64
import pytest
from timmy_serve.l402_proxy import create_l402_challenge, verify_l402_token, Macaroon, _sign

def test_l402_macaroon_forgery_prevention():
    """Test that knowing the hmac_secret is not enough to forge a macaroon.
    
    The forgery attempt uses the same hmac_secret found in a valid macaroon
    but doesn't know the server's internal _MACAROON_SECRET.
    """
    # 1. Create a valid challenge
    challenge = create_l402_challenge(100, "valid")
    valid_token = challenge["macaroon"]
    
    # 2. Extract components from the valid macaroon
    valid_mac = Macaroon.deserialize(valid_token)
    assert valid_mac is not None
    
    # 3. Attempt to forge a macaroon for a different (unpaid) identifier
    # but using the same hmac_secret and the same signing logic a naive 
    # attacker might assume (if it was just hmac(hmac_secret, identifier)).
    fake_identifier = "forged-payment-hash"
    
    # Naive forgery attempt:
    fake_signature = hmac.new(
        valid_mac.hmac_secret.encode(), 
        fake_identifier.encode(), 
        hashlib.sha256
    ).hexdigest()
    
    fake_mac = Macaroon(
        identifier=fake_identifier,
        signature=fake_signature,
        hmac_secret=valid_mac.hmac_secret,
        version=valid_mac.version,
        location=valid_mac.location
    )
    fake_token = fake_mac.serialize()
    
    # 4. Verification should fail because the server uses two-key derivation
    assert verify_l402_token(fake_token) is False

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

def test_macaroon_serialization_v2():
    """Test that the new serialization format includes the hmac_secret."""
    mac = Macaroon(identifier="id", signature="sig", hmac_secret="secret")
    serialized = mac.serialize()
    
    # Decode manually to check parts
    raw = base64.urlsafe_b64decode(serialized.encode()).decode()
    parts = raw.split(":")
    assert len(parts) == 5
    assert parts[2] == "id"
    assert parts[3] == "sig"
    assert parts[4] == "secret"
    
    # Test deserialization
    restored = Macaroon.deserialize(serialized)
    assert restored.hmac_secret == "secret"
