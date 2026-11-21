"""Helper: generate PKCE pair + X OAuth 2.0 authorization URL.

Usage:
    python scripts/x_oauth_setup.py

Prints the code_verifier (save it!), code_challenge, and the full authorize URL.
Open that URL in a browser, authorize, then exchange the returned ?code= for tokens.
"""
from __future__ import annotations

import base64
import hashlib
import os
import urllib.parse
import sys

CLIENT_ID = os.environ.get("X_CLIENT_ID", "YOUR_CLIENT_ID_HERE")
REDIRECT_URI = os.environ.get(
    "X_REDIRECT_URI", "http://localhost:8765/callback/x"
)
SCOPES = "tweet.read tweet.write users.read media.write"


def generate_pkce() -> tuple[str, str]:
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return code_verifier, code_challenge


def build_authorize_url(client_id: str, redirect_uri: str, code_challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode(),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return "https://twitter.com/i/oauth2/authorize?" + urllib.parse.urlencode(params)


def main() -> None:
    if CLIENT_ID == "YOUR_CLIENT_ID_HERE":
        print("Set X_CLIENT_ID env var first (e.g. export X_CLIENT_ID=your_client_id)")
        sys.exit(1)

    verifier, challenge = generate_pkce()
    url = build_authorize_url(CLIENT_ID, REDIRECT_URI, challenge)

    print("=" * 60)
    print("CODE_VERIFIER (SAVE THIS — you need it for the token exchange):")
    print(verifier)
    print()
    print("CODE_CHALLENGE:")
    print(challenge)
    print()
    print("AUTHORIZE URL (open this in a browser):")
    print(url)
    print()
    print("After authorizing, X redirects to your callback URI with ?code=...")
    print("Exchange that code at: POST https://api.x.com/2/oauth2/token")
    print("=" * 60)


if __name__ == "__main__":
    main()
