"""Platform metrics collection for Phase 6 measurement.

Fetches engagement data (views, likes, comments, shares, impressions) from
each platform's public API and writes it to the pipeline DB via
`record_metrics()`. Platforms without public share/approved_views data use
conservative estimates.

Usage:
    clipping-tools metrics-collect   # collect for all published posts
    clipping-tools metrics-collect --platform youtube   # one platform only
"""
from __future__ import annotations

import httpx
import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..db import init_db, utcnow
from ..review.render import record_metrics

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "state.db"


def _first_item(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Safely return the first item of a list, or {} if missing/empty."""
    items = data.get(key) or []
    return items[0] if items else {}


# ── Platform metric fetchers ──────────────────────────────────────────────

def fetch_youtube_metrics(video_id: str, api_key: str | None = None,
                          db_path: str | Path | None = None,
                          transport=None) -> dict[str, int | str | None]:
    """Fetch public video statistics from YouTube Data API v3.

    Returns: views, likes, comments. shares and approved_views are not
    available from the free v3 API — they default to 0 / None.

    Tries API key first, then falls back to an OAuth bearer token from
    the DB tokens table (set by Google OAuth flow).
    """
    key = api_key or os.environ.get("YOUTUBE_API_KEY", "")
    token = None
    if not key and db_path:
        conn = init_db(str(db_path))
        row = conn.execute(
            "SELECT access_token, refresh_token, expires_at FROM tokens WHERE service='youtube'"
        ).fetchone()
        conn.close()
        if row and row["access_token"]:
            from datetime import datetime, timezone
            if row["expires_at"]:
                expires = datetime.fromisoformat(row["expires_at"])
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) >= expires and row["refresh_token"]:
                    # Refresh the token
                    import httpx as _httpx
                    resp = _httpx.post(
                        "https://oauth2.googleapis.com/token",
                        data={
                            "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
                            "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
                            "refresh_token": row["refresh_token"],
                            "grant_type": "refresh_token",
                        },
                        timeout=30,
                    )
                    if resp.status_code == 200:
                        token = resp.json()["access_token"]
            else:
                token = row["access_token"]

    if key:
        params = urllib.parse.urlencode({
            "part": "statistics",
            "id": video_id,
            "key": key,
        })
        url = f"https://www.googleapis.com/youtube/v3/videos?{params}"
        http = transport or _http_get_json
        data = http(url) if transport is None else http(url)
    elif token:
        url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={video_id}"
        http = transport or _http_get_json
        headers = {"Authorization": f"Bearer {token}"}
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    else:
        return {"views": 0, "likes": 0, "comments": 0, "shares": 0,
                "approved_views": None, "error": "no api key or oauth token"}

    stats = _first_item(data, "items").get("statistics", {})
    return {
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
        "shares": 0,  # not available in free v3 API
        "approved_views": None,  # need YouTube Analytics API
    }


# ── X (Twitter) ───────────────────────────────────────────────────────────

def fetch_x_metrics(tweet_id: str, bearer_token: str | None = None,
                    transport=None) -> dict[str, int | str | None]:
    """Fetch public tweet metrics from X API v2.

    Returns: views (impression_count), likes, comments (reply_count),
    shares (retweet_count). approved_views is not available.
    """
    token = bearer_token or os.environ.get("X_ACCESS_TOKEN", "")
    if not token:
        return {"views": 0, "likes": 0, "comments": 0, "shares": 0,
                "approved_views": None, "error": "no bearer token"}

    params = urllib.parse.urlencode({
        "tweet.fields": "public_metrics",
    })
    url = f"https://api.x.com/2/tweets/{tweet_id}?{params}"
    headers = {"Authorization": f"Bearer {token}"}

    class _Transport:
        def __call__(self, u: str) -> dict[str, Any]:
            req = urllib.request.Request(u, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())

    http = transport or _Transport()
    data = http(url)

    m = data.get("data", {}).get("public_metrics", {})
    return {
        "views": int(m.get("impression_count", 0)),
        "likes": int(m.get("like_count", 0)),
        "comments": int(m.get("reply_count", 0)),
        "shares": int(m.get("retweet_count", 0)),
        "approved_views": None,
    }


# ── TikTok ────────────────────────────────────────────────────────────────


def fetch_tiktok_metrics(publish_id: str, access_token: str | None = None,
                         db_path: str | Path | None = None,
                         transport=None) -> dict[str, int | str | None]:
    """Fetch publish status from TikTok Content Posting API.

    Returns publish status (PUBLISH_COMPLETE / FAILED / PROCESSING_UPLOAD
    / UNDER_REVIEW / SCHEDULED). View/like/comment counts require TikTok's
    Data API, which needs app review — not available pre-audit.
    """
    token = access_token or os.environ.get("TIKTOK_ACCESS_TOKEN", "")
    if not token and db_path:
        # Fall back to DB tokens table (set by OAuth Login Kit flow)
        conn = init_db(str(db_path))
        row = conn.execute(
            "SELECT access_token, expires_at FROM tokens WHERE service='tiktok'"
        ).fetchone()
        conn.close()
        if row and row["expires_at"]:
            from datetime import datetime, timezone
            expires = datetime.fromisoformat(row["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < expires:
                token = row["access_token"]
    if not token:
        return {"views": 0, "likes": 0, "comments": 0, "shares": 0,
                "approved_views": None, "error": "no access token"}

    http = transport or httpx.post
    url = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
    body = {"publish_id": publish_id}
    headers = {"Authorization": f"Bearer {token}"}

    try:
        resp = http(url, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        status = data.get("status", "")
        return {
            "views": 0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "approved_views": None,
            "status": status,
            "error": None if status == "PUBLISH_COMPLETE" else status,
        }
    except Exception:  # noqa: BLE001
        return {"views": 0, "likes": 0, "comments": 0, "shares": 0,
                "approved_views": None, "error": "fetch failed"}


# ── Collection ────────────────────────────────────────────────────────────

def published_posts_with_external_ids(db_path) -> list[dict]:
    """Return all published posts that have an external_post_id and platform."""
    conn = init_db(db_path)
    rows = conn.execute(
        "SELECT id, external_post_id, platform FROM posts "
        "WHERE status='published' AND external_post_id IS NOT NULL "
        "AND platform IS NOT NULL"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def collect_for_post(post: dict, db_path, transport=None) -> dict | None:
    """Collect metrics for one published post via its platform API.

    Returns the metrics dict that was written to the DB, or None on failure.
    """
    post_id = post["id"]
    platform = post["platform"]
    external_id = post["external_post_id"]

    try:
        if platform == "youtube":
            metrics = fetch_youtube_metrics(external_id, db_path=db_path,
                                            transport=transport)
        elif platform == "x":
            metrics = fetch_x_metrics(external_id, transport=transport)
        elif platform == "tiktok":
            metrics = fetch_tiktok_metrics(external_id, db_path=db_path,
                                           transport=transport)
        else:
            return None  # unsupported platform

        if metrics.get("error"):
            return None

        fetched_at = utcnow()
        approved = metrics["approved_views"]
        approved_views = int(approved) if approved is not None else None
        record_metrics(
            str(db_path),
            post_id=post_id,
            views=int(metrics["views"] or 0),
            likes=int(metrics["likes"] or 0),
            comments=int(metrics["comments"] or 0),
            shares=int(metrics["shares"] or 0),
            fetched_at=fetched_at,
            approved_views=approved_views,
            payout=0.0,
        )
        return {"post_id": post_id, "platform": platform,
                "external_id": external_id, "metrics": metrics,
                "fetched_at": fetched_at}
    except Exception:  # noqa: BLE001 — one platform failure must not stop others
        return None


def collect_all(platform: str | None = None, db_path=None,
                transport=None) -> list[dict | None]:
    """Collect metrics for all published posts, optionally filtered by platform."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    posts = published_posts_with_external_ids(db_path)
    if platform:
        posts = [p for p in posts if p["platform"] == platform]
    results = []
    for post in posts:
        results.append(collect_for_post(post, db_path, transport=transport))
    return results


def _http_get_json(url: str, headers: dict[str, str] | None = None,
                   timeout: int = 30) -> dict[str, Any]:
    """GET a URL and return parsed JSON."""
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())
