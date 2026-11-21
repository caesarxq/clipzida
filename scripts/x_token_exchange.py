"""Exchange an X OAuth 2.0 authorization code for access + refresh tokens.

Uses Basic Auth header (client_id:client_secret) as X requires for confidential clients.

Usage:
    export X_CLIENT_ID=...
    export X_CLIENT_SECRET=...
    python3 scripts/x_token_exchange.py <AUTH_CODE> <CODE_VERIFIER> [REDIRECT_URI]
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://api.x.com/2/oauth2/token"


def exchange_code(
    auth_code: str,
    code_verifier: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str = "http://localhost:8765/callback/x",
) -> dict:
    """Exchange authorization code for tokens using Basic Auth header."""
    auth_string = f"{client_id}:{client_secret}"
    auth_b64 = base64.b64encode(auth_string.encode()).decode()

    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    body = urllib.parse.urlencode(data).encode()

    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    client_id = os.environ.get("X_CLIENT_ID")
    client_secret = os.environ.get("X_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("Set X_CLIENT_ID and X_CLIENT_SECRET env vars first")
        sys.exit(1)

    if len(sys.argv) < 3:
        print("Usage: python3 scripts/x_token_exchange.py <AUTH_CODE> <CODE_VERIFIER> [REDIRECT_URI]")
        print()
        print("Get AUTH_CODE and CODE_VERIFIER from:")
        print("  1. Run: python3 scripts/x_oauth_setup.py  (prints CODE_VERIFIER + AUTHORIZE URL)")
        print("  2. Open the AUTHORIZE URL in a browser, approve Read + Write")
        print("  3. Copy ?code= from the redirect URL -> AUTH_CODE")
        sys.exit(1)

    auth_code = sys.argv[1]
    code_verifier = sys.argv[2]
    redirect_uri = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8765/callback/x"

    try:
        tokens = exchange_code(auth_code, code_verifier, client_id, client_secret, redirect_uri)
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        print(f"Token exchange failed: HTTP {e.code} {body}")
        sys.exit(1)

    print("=" * 60)
    print("TOKEN EXCHANGE SUCCESSFUL")
    print("=" * 60)
    print(f"access_token:  {tokens.get('access_token')}")
    print(f"refresh_token: {tokens.get('refresh_token')}")
    print(f"expires_in:    {tokens.get('expires_in')} seconds")
    print(f"scope:         {tokens.get('scope')}")
    print()
    print("Set these on the VPS:")
    print(f"  export X_ACCESS_TOKEN={tokens.get('access_token')}")
    print(f"  export X_ACCESS_TOKEN_SECRET={tokens.get('refresh_token')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
