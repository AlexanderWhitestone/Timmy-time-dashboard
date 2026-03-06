#!/usr/bin/env python3
"""Tiny auth gate for nginx auth_request. Sets a cookie after successful basic auth."""
import hashlib, hmac, http.server, time, base64, os

SECRET = "sovereign-timmy-gate-2026"
USER = "Rockachopa"
PASS = "Iamrockachopathegend"
COOKIE_NAME = "sovereign_gate"
COOKIE_MAX_AGE = 86400 * 7  # 7 days

def make_token(ts):
    msg = f"{USER}:{ts}".encode()
    return hmac.new(SECRET.encode(), msg, hashlib.sha256).hexdigest()[:32]

def verify_token(token):
    try:
        # Token format: timestamp.signature
        parts = token.split(".")
        if len(parts) != 2:
            return False
        ts, sig = int(parts[0]), parts[1]
        if time.time() - ts > COOKIE_MAX_AGE:
            return False
        return sig == make_token(ts)
    except:
        return False

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        # Check cookie first
        cookies = self.headers.get("Cookie", "")
        for c in cookies.split(";"):
            c = c.strip()
            if c.startswith(f"{COOKIE_NAME}="):
                token = c[len(COOKIE_NAME)+1:]
                if verify_token(token):
                    self.send_response(200)
                    self.end_headers()
                    return

        # Check basic auth header (forwarded by nginx)
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth[6:]).decode()
                u, p = decoded.split(":", 1)
                if u == USER and p == PASS:
                    ts = int(time.time())
                    token = f"{ts}.{make_token(ts)}"
                    self.send_response(200)
                    self.send_header("Set-Cookie",
                        f"{COOKIE_NAME}={token}; Path=/; Max-Age={COOKIE_MAX_AGE}; HttpOnly; SameSite=Lax")
                    self.end_headers()
                    return
            except:
                pass

        # Deny
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Sovereign Stack"')
        self.end_headers()

if __name__ == "__main__":
    s = http.server.HTTPServer(("127.0.0.1", 9876), Handler)
    print("Auth gate listening on 127.0.0.1:9876")
    s.serve_forever()
