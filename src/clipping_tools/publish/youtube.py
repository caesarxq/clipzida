"""YouTube Data API v3 uploader (Shorts, unlisted-first, OAuth token from vault table)."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.parse

import httpx

from ..db import utcnow

API = "https://www.googleapis.com/upload/youtube/v3/videos"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CATEGORY_GAMING = "20"


def build_upload_metadata(post: dict) -> dict:
    """Shorts-friendly snippet: title with #Shorts, hashtags in description, gaming category."""
    hook = str(post.get("caption") or "").strip() or "GTA 6 moment"
    hashtags = str(post.get("hashtags") or "#gta6 #gta6clips #shorts")
    return {
        "snippet": {
            "title": f"{hook[:90]} #Shorts",
            "description": f"{hook}\n\n{hashtags} #Shorts #fyp",
            "tags": ["gta6", "gta6clips", "shorts", "gaming"],
            "categoryId": CATEGORY_GAMING,
        },
        "status": {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False},
    }


def _refresh_token(conn: sqlite3.Connection, client_id: str, client_secret: str) -> str:
    row = conn.execute("SELECT refresh_token, access_token FROM tokens WHERE service='youtube'").fetchone()
    if not row or not row["refresh_token"]:
        raise RuntimeError("no youtube refresh token — authorise via Google OAuth first")
    r = httpx.post(TOKEN_URL, data={
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": row["refresh_token"], "grant_type": "refresh_token",
    }, timeout=30)
    r.raise_for_status()
    data = r.json()
    conn.execute("UPDATE tokens SET access_token=?, expires_at=? WHERE service='youtube'",
                 (data["access_token"], utcnow()))
    conn.commit()
    return data["access_token"]


def upload_to_youtube(post_id: int, db_path, video_path: str, *, transport=None,
                     client_id: str | None = None, client_secret: str | None = None) -> dict:
    """Upload one rendered mp4 to YouTube and write back external id + url."""
    from ..db import init_db
    conn = init_db(db_path)
    post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not post:
        raise RuntimeError(f"post {post_id} not found")
    token = os.environ.get("YOUTUBE_ACCESS_TOKEN") or _refresh_token(
        conn, client_id or os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret or os.environ.get("GOOGLE_CLIENT_SECRET", ""))
    metadata = build_upload_metadata(dict(post))
    params = urllib.parse.urlencode({"part": "snippet,status", "uploadType": "multipart"})
    http = transport or httpx
    body = (
        "--clipzida\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        + json.dumps(metadata)
        + "\r\n--clipzida\r\nContent-Type: video/mp4\r\n\r\n"
    ).encode()
    with open(video_path, "rb") as fh:
        payload = body + fh.read() + b"\r\n--clipzida--\r\n"
    resp = http.post(f"{API}?{params}", content=payload, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "multipart/related; boundary=clipzida",
    }, timeout=600)
    resp.raise_for_status()
    data = resp.json()
    ext = str(data.get("id") or "")
    url = f"https://www.youtube.com/watch?v={ext}"
    with conn:
        conn.execute("UPDATE posts SET external_post_id=?, url=?, published_at=? WHERE id=?",
                     (ext, url, utcnow(), post_id))
        conn.execute("INSERT INTO post_platforms(post_id, platform, status, external_id, url, published_at) "
                     "VALUES(?, 'youtube', 'published', ?, ?, ?) "
                     "ON CONFLICT(post_id, platform) DO UPDATE SET status='published', "
                     "external_id=excluded.external_id, url=excluded.url, published_at=excluded.published_at",
                     (post_id, ext, url, utcnow()))
    return {"external_id": ext, "url": url, "privacy": "unlisted"}
