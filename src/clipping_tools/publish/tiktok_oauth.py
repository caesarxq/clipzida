"""TikTok Login Kit OAuth (v2): authorization URL, PKCE, token exchange, creator info.

Docs: developers.tiktok.com — Login Kit v2 uses PKCE (S256). The client secret
never leaves the server; the token exchange happens on the VPS.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import urllib.parse
from typing import Any

import httpx

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"

SCOPES = "user.info.basic,video.publish,video.upload"


def _http_post(transport, url: str, **kwargs):
    """POST via transport if it has .post or is callable, else via httpx."""
    if transport is not None:
        if hasattr(transport, "post"):
            return transport.post(url, **kwargs)
        if callable(transport):
            return transport(url, **kwargs)
    return httpx.post(url, **kwargs)


def generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for TikTok Login Kit PKCE."""
    verifier = secrets.token_urlsafe(64)[:128]  # 43-128 chars allowed
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def build_authorize_url(client_key: str, redirect_uri: str,
                        code_challenge: str, state: str | None = None,
                        scopes: str = SCOPES) -> str:
    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": scopes,
        "redirect_uri": redirect_uri,
        "state": state or secrets.token_urlsafe(16),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(client_key: str, client_secret: str, code: str,
                  redirect_uri: str, code_verifier: str, *,
                  transport=None) -> dict[str, Any]:
    """Exchange an authorization code for user access + refresh tokens."""
    resp = _http_post(transport, TOKEN_URL, data={
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_creator_info(access_token: str, *, transport=None) -> dict[str, Any]:
    """Query creator info — nickname, privacy options, max video duration.

    TikTok compliance: the posting screen MUST display creator_nickname and
    honor privacy_level_options (no default selection) before upload.
    """
    resp = _http_post(transport, CREATOR_INFO_URL, json={},
                      headers={"Authorization": f"Bearer {access_token}"},
                      timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", {})
