"""X (Twitter) v2 publish adapter.
OAuth 2.0 with PKCE + hybrid media upload (v2 media upload -> v2 POST /2/tweets).

Credentials (env vars):
- X_CLIENT_ID — OAuth 2.0 client ID
- X_CLIENT_SECRET — OAuth 2.0 client secret
- X_ACCESS_TOKEN — bearer token (from OAuth flow, stored in DB tokens table)
- X_ACCESS_TOKEN_SECRET — refresh token (stored in DB tokens table)

Endpoints:
- OAuth token: POST https://api.x.com/2/oauth2/token
- Media upload: POST https://api.x.com/2/media/upload (INIT/APPEND/FINALIZE)
- Tweet create: POST https://api.x.com/2/tweets
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from ..db import utcnow

MEDIA_UPLOAD = "https://api.x.com/2/media/upload"
TWEET_CREATE = "https://api.x.com/2/tweets"
TOKEN_URL = "https://api.x.com/2/oauth2/token"


def _http_post(transport, url: str, **kwargs):
    """POST via transport if it has .post or is callable, else via httpx."""
    if transport is not None:
        if hasattr(transport, "post"):
            return transport.post(url, **kwargs)
        if callable(transport):
            return transport(url, **kwargs)
    return httpx.post(url, **kwargs)


def _http_get(transport, url: str, **kwargs):
    """GET via transport if it has .get or is callable, else via httpx."""
    if transport is not None:
        if hasattr(transport, "get"):
            return transport.get(url, **kwargs)
        if callable(transport):
            return transport(url, **kwargs)
    return httpx.get(url, **kwargs)


def build_post_metadata(post: dict) -> dict:
    """Build the tweet text from the post caption + hashtags."""
    hook = str(post.get("caption") or "").strip() or "GTA 6 moment"
    hashtags = str(post.get("hashtags") or "").strip()
    text = f"{hook} {hashtags}".strip() if hashtags else hook
    # X hard limit is 280 chars; truncate from the middle if needed.
    if len(text) > 280:
        half = (280 - 3) // 2
        text = text[:half] + "..." + text[-half:]
    return {"text": text}


# ── OAuth 2.0 helpers ───────────────────────────────────────────────

def _require_env() -> None:
    missing = [k for k in ("X_CLIENT_ID", "X_CLIENT_SECRET") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"X credentials missing: {', '.join(missing)}")


def _get_access_token(conn) -> str:
    """Get a valid X access token from the DB tokens table, refreshing if needed.

    Falls back to X_ACCESS_TOKEN env var if no DB row exists.
    """
    row = conn.execute(
        "SELECT access_token, refresh_token, expires_at FROM tokens WHERE service='x'"
    ).fetchone()
    if row and row["expires_at"]:
        expires = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) < expires:
            return row["access_token"]
    # Try refresh
    if row and row["refresh_token"]:
        return _refresh_token(conn, row["refresh_token"])
    # Fall back to env var
    token = os.environ.get("X_ACCESS_TOKEN")
    if token:
        return token
    raise RuntimeError(
        "X access token not found — complete OAuth 2.0 authorization flow first "
        "(see docs/X_SETUP_GUIDE.md)"
    )


def _refresh_token(conn, refresh_token: str) -> str:
    """Refresh an expired X access token using the refresh token."""
    client_id = os.environ["X_CLIENT_ID"]
    client_secret = os.environ["X_CLIENT_SECRET"]
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    resp = httpx.post(TOKEN_URL, data=data, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    conn.execute(
        "UPDATE tokens SET access_token=?, refresh_token=?, expires_at=? WHERE service='x'",
        (
            data["access_token"],
            data.get("refresh_token", refresh_token),
            _expires_at(data.get("expires_in")),
        ),
    )
    conn.commit()
    return data["access_token"]


def _expires_at(seconds: int | None) -> str | None:
    if not seconds:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


# ── Media upload (hybrid v2: INIT → APPEND → FINALIZE) ────────────────

def init_media_upload(video_path: str, size: int, access_token: str, *,
                      transport=None) -> str:
    """INIT step: register the upload, returns media_id."""
    params = {
        "command": "INIT",
        "media_type": "video/mp4",
        "total_bytes": str(size),
        "media_category": "tweet_video",
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = _http_post(transport, MEDIA_UPLOAD, data=params, headers=headers, timeout=60)
    resp.raise_for_status()
    return str(resp.json()["media_id"])


def append_media_chunk(video_path: str, media_id: str, segment: int, *,
                       access_token: str, transport=None) -> None:
    """APPEND step: send one chunk of the media file (4 MB chunks)."""
    with open(video_path, "rb") as fh:
        fh.seek(segment * 4 * 1024 * 1024)
        chunk = fh.read(4 * 1024 * 1024)
    params = {
        "command": "APPEND",
        "media_id": media_id,
        "segment_index": str(segment),
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    files = {"media": (os.path.basename(video_path), chunk, "video/mp4")}
    resp = _http_post(transport, MEDIA_UPLOAD, data=params, files=files, headers=headers, timeout=300)
    resp.raise_for_status()


def finalize_media(media_id: str, access_token: str, *,
                   transport=None) -> str:
    """FINALIZE step: signal upload complete, wait for processing, return media_id."""
    params = {"command": "FINALIZE", "media_id": media_id}
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = _http_post(transport, MEDIA_UPLOAD, data=params, headers=headers, timeout=60)
    resp.raise_for_status()
    result = resp.json()
    # Poll until processing finishes
    for _ in range(60):  # up to ~60 seconds
        info = result.get("processing_info", {})
        state = info.get("state")
        if state == "succeeded":
            return str(result["media_id"])
        if state == "failed":
            raise RuntimeError(f"media processing failed: {info}")
        check_after = info.get("check_after_secs", 1)
        time.sleep(min(check_after, 5))
        status_params = {"command": "STATUS", "media_id": media_id}
        status_headers = {"Authorization": f"Bearer {access_token}"}
        resp = _http_get(transport, MEDIA_UPLOAD, params=status_params, headers=status_headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()
    raise RuntimeError("media processing timed out")


# ── Create post ──────────────────────────────────────────────────────

def create_post(text: str, media_ids: list[str], access_token: str, *,
                transport=None) -> dict:
    """POST /2/tweets with optional media attachment."""
    payload: dict[str, Any] = {"text": text}
    if media_ids:
        payload["media"] = {"media_ids": media_ids}
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = _http_post(transport, TWEET_CREATE, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()["data"]


# ── Full flow ────────────────────────────────────────────────────────

def publish_to_x(post_id: int, db_path, video_path: str, *,
                 transport=None) -> dict:
    """Upload one rendered mp4 to X and write back external id + url."""
    from ..db import init_db
    conn = init_db(db_path)
    post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not post:
        raise RuntimeError(f"post {post_id} not found")
    _require_env()
    post_dict = dict(post)
    md = build_post_metadata(post_dict)
    size = os.path.getsize(video_path)
    token = _get_access_token(conn)
    media_id = init_media_upload(video_path, size, token, transport=transport)
    # APPEND in 4 MB chunks
    segment = 0
    offset = 0
    with open(video_path, "rb") as fh:
        while offset < size:
            append_media_chunk(video_path, media_id, segment, access_token=token,
                               transport=transport)
            segment += 1
            offset += 4 * 1024 * 1024
    finalize_media(media_id, token, transport=transport)
    created = create_post(md["text"], [media_id], token, transport=transport)
    ext = str(created["id"])
    url = f"https://x.com/i/status/{ext}"
    with conn:
        conn.execute("UPDATE posts SET external_post_id=?, url=?, status='published', "
                     "platform=?, published_at=? WHERE id=?",
                     (ext, url, "x", utcnow(), post_id))
    return {"external_id": ext, "url": url, "platform": "x"}
