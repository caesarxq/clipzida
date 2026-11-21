"""X (Twitter) v2 publish adapter.
Hybrid media upload: v1.1 chunked upload (INIT/APPEND/FINALIZE) then
v2 POST /2/tweets with media_ids. OAuth 1.0a user context (implemented
manually to avoid the requests_oauthlib dependency).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

import httpx

from ..db import utcnow

MEDIA_UPLOAD = "https://upload.twitter.com/1.1/media/upload.json"
TWEET_CREATE = "https://api.x.com/2/tweets"


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


# ── OAuth 1.0a (manual, no requests_oauthlib dependency) ──────────────

def _oauth_header(method: str, url: str, params: dict[str, str]) -> str:
    """Build an OAuth 1.0a Authorization header."""
    consumer_key = os.environ["X_API_KEY"]
    consumer_secret = os.environ["X_API_SECRET"]
    token = os.environ["X_ACCESS_TOKEN"]
    token_secret = os.environ["X_ACCESS_TOKEN_SECRET"]

    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": _nonce(),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    # Merge request params for signing
    all_params = {**oauth_params, **params}
    base_string = _signature_base_string(method, url, all_params)
    signing_key = _encode(consumer_secret) + "&" + _encode(token_secret)
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    oauth_params["oauth_signature"] = signature

    parts = [f'{_encode(k)}="{_encode(v)}"' for k, v in sorted(oauth_params.items())]
    return "OAuth " + ", ".join(parts)


def _nonce() -> str:
    return base64.b64encode(os.urandom(18)).decode()[:32]


def _encode(s: str) -> str:
    """RFC 3986 percent-encode."""
    import urllib.parse
    return urllib.parse.quote(s, safe="")


def _signature_base_string(method: str, url: str, params: dict[str, str]) -> str:
    import urllib.parse
    encoded_params = "&".join(
        f"{_encode(k)}={_encode(v)}" for k, v in sorted(params.items())
    )
    return (
        f"{method.upper()}&{_encode(url)}&{_encode(encoded_params)}"
    )


def _require_env() -> None:
    missing = [k for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
               if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"X credentials missing: {', '.join(missing)}")


def init_media_upload(video_path: str, size: int, *,
                      transport=None) -> str:
    """INIT step: register the upload, returns media_id."""
    _require_env()
    params = {
        "command": "INIT",
        "media_type": "video/mp4",
        "total_bytes": str(size),
        "media_category": "tweet_video",
    }
    headers = {"Authorization": _oauth_header("POST", MEDIA_UPLOAD, params)}
    resp = _http_post(transport, MEDIA_UPLOAD, data=params, headers=headers, timeout=60)
    resp.raise_for_status()
    return str(resp.json()["media_id"])


def append_media_chunk(video_path: str, media_id: str, segment: int, *,
                       transport=None) -> None:
    """APPEND step: send one chunk of the media file (4 MB chunks)."""
    _require_env()
    with open(video_path, "rb") as fh:
        fh.seek(segment * 4 * 1024 * 1024)
        chunk = fh.read(4 * 1024 * 1024)
    params = {
        "command": "APPEND",
        "media_id": media_id,
        "segment_index": str(segment),
    }
    headers = {"Authorization": _oauth_header("POST", MEDIA_UPLOAD, params)}
    files = {"media": (os.path.basename(video_path), chunk, "video/mp4")}
    resp = _http_post(transport, MEDIA_UPLOAD, data=params, files=files, headers=headers, timeout=300)
    resp.raise_for_status()


def finalize_media(media_id: str, *,
                   transport=None) -> str:
    """FINALIZE step: signal upload complete, wait for processing, return media_id."""
    _require_env()
    params = {"command": "FINALIZE", "media_id": media_id}
    headers = {"Authorization": _oauth_header("POST", MEDIA_UPLOAD, params)}
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
        status_headers = {"Authorization": _oauth_header("GET", MEDIA_UPLOAD, status_params)}
        resp = _http_get(transport, MEDIA_UPLOAD, params=status_params, headers=status_headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()
    raise RuntimeError("media processing timed out")


def create_post(text: str, media_ids: list[str], *,
                transport=None) -> dict:
    """POST /2/tweets with optional media attachment."""
    _require_env()
    payload: dict[str, Any] = {"text": text}
    if media_ids:
        payload["media"] = {"media_ids": media_ids}
    headers = {"Authorization": _oauth_header("POST", TWEET_CREATE, {})}
    resp = _http_post(transport, TWEET_CREATE, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()["data"]


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
    media_id = init_media_upload(video_path, size, transport=transport)
    # APPEND in 4 MB chunks
    segment = 0
    offset = 0
    with open(video_path, "rb") as fh:
        while offset < size:
            append_media_chunk(video_path, media_id, segment, transport=transport)
            segment += 1
            offset += 4 * 1024 * 1024
    finalize_media(media_id, transport=transport)
    created = create_post(md["text"], [media_id], transport=transport)
    ext = str(created["id"])
    url = f"https://x.com/i/status/{ext}"
    with conn:
        conn.execute("UPDATE posts SET external_post_id=?, url=?, status='published', "
                     "platform=?, published_at=? WHERE id=?",
                     (ext, url, "x", utcnow(), post_id))
    return {"external_id": ext, "url": url, "platform": "x"}
