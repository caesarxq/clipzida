"""RED: TikTok Login Kit OAuth v2 — PKCE, authorize URL, token exchange, creator info."""
from __future__ import annotations

import base64
import hashlib
import json
import urllib.parse

from clipping_tools.publish.tiktok_oauth import (
    generate_pkce,
    build_authorize_url,
    exchange_code,
    fetch_creator_info,
)


def test_generate_pkce_verifier_length_and_challenge_matches():
    verifier, challenge = generate_pkce()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    assert challenge == expected


def test_build_authorize_url_contains_required_params():
    url = build_authorize_url("ck123", "https://ex.com/cb", "cc456", state="st789")
    q = urllib.parse.parse_qs(url.split("?", 1)[1])
    assert url.startswith("https://www.tiktok.com/v2/auth/authorize/?")
    assert q["client_key"] == ["ck123"]
    assert q["response_type"] == ["code"]
    assert q["scope"] == ["user.info.basic,video.publish,video.upload"]
    assert q["redirect_uri"] == ["https://ex.com/cb"]
    assert q["state"] == ["st789"]
    assert q["code_challenge"] == ["cc456"]
    assert q["code_challenge_method"] == ["S256"]


def test_build_authorize_url_generates_state_when_missing():
    url = build_authorize_url("ck123", "https://ex.com/cb", "cc456")
    q = urllib.parse.parse_qs(url.split("?", 1)[1])
    assert q["state"][0]  # non-empty


class FakeResp:
    status_code = 200
    def __init__(self, data):
        self._data = data
    def json(self):
        return self._data
    def raise_for_status(self):
        pass


def test_exchange_code_sends_form_encoded_secret_pair(monkeypatch):
    captured = {}
    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["data"] = dict(data)
        return FakeResp({
            "access_token": "at1", "refresh_token": "rt1",
            "open_id": "oid1", "scope": "user.info.basic,video.publish,video.upload",
            "token_type": "access-token", "expires_in": 86400,
        })

    result = exchange_code("ck", "cs", "authcode", "https://ex.com/cb", "verifier",
                           transport=fake_post)
    assert captured["url"] == "https://open.tiktokapis.com/v2/oauth/token/"
    assert captured["data"]["client_key"] == "ck"
    assert captured["data"]["client_secret"] == "cs"
    assert captured["data"]["code"] == "authcode"
    assert captured["data"]["grant_type"] == "authorization_code"
    assert captured["data"]["redirect_uri"] == "https://ex.com/cb"
    assert captured["data"]["code_verifier"] == "verifier"
    assert result["access_token"] == "at1"
    assert result["open_id"] == "oid1"


def test_fetch_creator_info_returns_data():
    captured = {}
    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["auth"] = headers["Authorization"]
        return FakeResp({"data": {
            "creator_nickname": "CLIPZIDA",
            "creator_avatar_url": "http://x/a.png",
            "privacy_level_options": ["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "PUBLIC_TO_EVERYONE"],
            "max_video_post_duration_sec": 600,
        }})

    data = fetch_creator_info("tok", transport=fake_post)
    assert captured["url"].endswith("/creator_info/query/")
    assert captured["auth"] == "Bearer tok"
    assert data["creator_nickname"] == "CLIPZIDA"
    assert "SELF_ONLY" in data["privacy_level_options"]
    assert data["max_video_post_duration_sec"] == 600
