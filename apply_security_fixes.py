import os

def fix_l402_proxy():
    path = "src/timmy_serve/l402_proxy.py"
    with open(path, "r") as f:
        content = f.read()
    
    # 1. Add hmac_secret to Macaroon dataclass
    old_dataclass = "@dataclass\nclass Macaroon:\n    \"\"\"Simplified HMAC-based macaroon for L402 authentication.\"\"\"\n    identifier: str  # payment_hash\n    signature: str   # HMAC signature\n    location: str = \"timmy-time\"\n    version: int = 1"
    new_dataclass = "@dataclass\nclass Macaroon:\n    \"\"\"Simplified HMAC-based macaroon for L402 authentication.\"\"\"\n    identifier: str  # payment_hash\n    signature: str   # HMAC signature\n    location: str = \"timmy-time\"\n    version: int = 1\n    hmac_secret: str = \"\"  # Added for multi-key support"
    content = content.replace(old_dataclass, new_dataclass)

    # 2. Update _MACAROON_SECRET logic
    old_secret_logic = """_MACAROON_SECRET_DEFAULT = "timmy-macaroon-secret"
_MACAROON_SECRET_RAW = os.environ.get("L402_MACAROON_SECRET", _MACAROON_SECRET_DEFAULT)
_MACAROON_SECRET = _MACAROON_SECRET_RAW.encode()

if _MACAROON_SECRET_RAW == _MACAROON_SECRET_DEFAULT:
    logger.warning(
        "SEC: L402_MACAROON_SECRET is using the default value — set a unique "
        "secret in .env before deploying to production."
    )"""
    new_secret_logic = """_MACAROON_SECRET_DEFAULT = "timmy-macaroon-secret"
_MACAROON_SECRET_RAW = os.environ.get("L402_MACAROON_SECRET", _MACAROON_SECRET_DEFAULT)
_MACAROON_SECRET = _MACAROON_SECRET_RAW.encode()

_HMAC_SECRET_DEFAULT = "timmy-hmac-secret"
_HMAC_SECRET_RAW = os.environ.get("L402_HMAC_SECRET", _HMAC_SECRET_DEFAULT)
_HMAC_SECRET = _HMAC_SECRET_RAW.encode()

if _MACAROON_SECRET_RAW == _MACAROON_SECRET_DEFAULT or _HMAC_SECRET_RAW == _HMAC_SECRET_DEFAULT:
    logger.warning(
        "SEC: L402 secrets are using default values — set L402_MACAROON_SECRET "
        "and L402_HMAC_SECRET in .env before deploying to production."
    )"""
    content = content.replace(old_secret_logic, new_secret_logic)

    # 3. Update _sign to use the two-key derivation
    old_sign = """def _sign(identifier: str) -> str:
    \"\"\"Create an HMAC signature for a macaroon identifier.\"\"\"
    return hmac.new(_MACAROON_SECRET, identifier.encode(), hashlib.sha256).hexdigest()"""
    new_sign = """def _sign(identifier: str, hmac_secret: Optional[str] = None) -> str:
    \"\"\"Create an HMAC signature for a macaroon identifier using two-key derivation.
    
    The base macaroon secret is used to derive a key-specific secret from the
    hmac_secret, which is then used to sign the identifier. This prevents
    macaroon forgery if the hmac_secret is known but the base secret is not.
    \"\"\"
    key = hmac.new(
        _MACAROON_SECRET, 
        (hmac_secret or _HMAC_SECRET_RAW).encode(), 
        hashlib.sha256
    ).digest()
    return hmac.new(key, identifier.encode(), hashlib.sha256).hexdigest()"""
    content = content.replace(old_sign, new_sign)

    # 4. Update create_l402_challenge
    old_create = """    invoice = payment_handler.create_invoice(amount_sats, memo)
    signature = _sign(invoice.payment_hash)
    macaroon = Macaroon(
        identifier=invoice.payment_hash,
        signature=signature,
    )"""
    new_create = """    invoice = payment_handler.create_invoice(amount_sats, memo)
    hmac_secret = _HMAC_SECRET_RAW
    signature = _sign(invoice.payment_hash, hmac_secret)
    macaroon = Macaroon(
        identifier=invoice.payment_hash,
        signature=signature,
        hmac_secret=hmac_secret,
    )"""
    content = content.replace(old_create, new_create)

    # 5. Update Macaroon.serialize and deserialize
    old_serialize = """    def serialize(self) -> str:
        \"\"\"Encode the macaroon as a base64 string.\"\"\"
        raw = f"{self.version}:{self.location}:{self.identifier}:{self.signature}"
        return base64.urlsafe_b64encode(raw.encode()).decode()"""
    new_serialize = """    def serialize(self) -> str:
        \"\"\"Encode the macaroon as a base64 string.\"\"\"
        raw = f"{self.version}:{self.location}:{self.identifier}:{self.signature}:{self.hmac_secret}"
        return base64.urlsafe_b64encode(raw.encode()).decode()"""
    content = content.replace(old_serialize, new_serialize)

    old_deserialize = """    @classmethod
    def deserialize(cls, token: str) -> Optional["Macaroon"]:
        \"\"\"Decode a base64 macaroon string.\"\"\"
        try:
            raw = base64.urlsafe_b64decode(token.encode()).decode()
            parts = raw.split(":")
            if len(parts) != 4:
                return None
            return cls(
                version=int(parts[0]),
                location=parts[1],
                identifier=parts[2],
                signature=parts[3],
            )
        except Exception:
            return None"""
    new_deserialize = """    @classmethod
    def deserialize(cls, token: str) -> Optional["Macaroon"]:
        \"\"\"Decode a base64 macaroon string.\"\"\"
        try:
            raw = base64.urlsafe_b64decode(token.encode()).decode()
            parts = raw.split(":")
            if len(parts) < 4:
                return None
            return cls(
                version=int(parts[0]),
                location=parts[1],
                identifier=parts[2],
                signature=parts[3],
                hmac_secret=parts[4] if len(parts) > 4 else "",
            )
        except Exception:
            return None"""
    content = content.replace(old_deserialize, new_deserialize)

    # 6. Update verify_l402_token
    old_verify_sig = """    # Check HMAC signature
    expected_sig = _sign(macaroon.identifier)
    if not hmac.compare_digest(macaroon.signature, expected_sig):"""
    new_verify_sig = """    # Check HMAC signature
    expected_sig = _sign(macaroon.identifier, macaroon.hmac_secret)
    if not hmac.compare_digest(macaroon.signature, expected_sig):"""
    content = content.replace(old_verify_sig, new_verify_sig)

    with open(path, "w") as f:
        f.write(content)

def fix_xss():
    # Fix chat_message.html
    path = "src/dashboard/templates/partials/chat_message.html"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace("{{ user_message }}", "{{ user_message | e }}")
    content = content.replace("{{ response }}", "{{ response | e }}")
    content = content.replace("{{ error }}", "{{ error | e }}")
    with open(path, "w") as f:
        f.write(content)

    # Fix history.html
    path = "src/dashboard/templates/partials/history.html"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace("{{ msg.content }}", "{{ msg.content | e }}")
    with open(path, "w") as f:
        f.write(content)

    # Fix briefing.html
    path = "src/dashboard/templates/briefing.html"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace("{{ briefing.summary }}", "{{ briefing.summary | e }}")
    with open(path, "w") as f:
        f.write(content)

    # Fix approval_card_single.html
    path = "src/dashboard/templates/partials/approval_card_single.html"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace("{{ item.title }}", "{{ item.title | e }}")
    content = content.replace("{{ item.description }}", "{{ item.description | e }}")
    content = content.replace("{{ item.proposed_action }}", "{{ item.proposed_action | e }}")
    with open(path, "w") as f:
        f.write(content)

    # Fix marketplace.html
    path = "src/dashboard/templates/marketplace.html"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace("{{ agent.name }}", "{{ agent.name | e }}")
    content = content.replace("{{ agent.role }}", "{{ agent.role | e }}")
    content = content.replace("{{ agent.description or 'No description' }}", "{{ (agent.description or 'No description') | e }}")
    content = content.replace("{{ cap.strip() }}", "{{ cap.strip() | e }}")
    with open(path, "w") as f:
        f.write(content)

if __name__ == "__main__":
    fix_l402_proxy()
    fix_xss()
    print("Security fixes applied successfully.")
