"""TikTok Content Posting API adapter.

Inbox mode (scope video.upload) sends a draft to the creator's TikTok inbox and
needs no Direct Post audit — the right mode for a fresh account. Direct mode
(scope video.publish) posts straight to the profile once the app is approved.
"""
from __future__ import annotations

import json
import os
import sqlite3

import httpx

from ..db import utcnow

BASE = "https://open.tiktokapis.com/v2/post/publish"
INBOX_INIT = f"{BASE}/inbox/video/init/"
DIRECT_INIT = f"{BASE}/video/init/"
STATUS = f"{BASE}/status/fetch/"


def build_post_info(post: dict) -> dict:
    # Editable title: the posting form sends the final title; hashtags are
    # appended only if the user removed them (brand default, still editable).
    title = str(post.get("title") or post.get("caption") or "").strip() or "GTA 6 moment"
    tags = "#gta6 #shorts"
    if tags not in title:
        title = f"{title[:200 - len(tags) - 1]} {tags}"
    return {
        "title": title,
        "description": f"{title} #gta6 #gta6clips #fyp",
        # Default SELF_ONLY pre-audit; the posting form sends the user's
        # explicit choice (unaudited clients are limited to SELF_ONLY anyway).
        "privacy_level": post.get("privacy_level") or "SELF_ONLY",
        # Interaction toggles default OFF on the form → disabled unless user opted in.
        "disable_comment": not post.get("allow_comment"),
        "disable_stitch": not post.get("allow_stitch"),
        "disable_duet": not post.get("allow_duet"),
    }


def init_publish(access_token: str, post: dict, video_path: str, *,
                 transport=None, mode: str = "inbox") -> tuple[str, str]:
    http = transport or httpx
    size = os.path.getsize(video_path)
    url = INBOX_INIT if mode == "inbox" else DIRECT_INIT
    payload = {
        "post_info": build_post_info(post),
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": size,
            "total_chunk_count": 1,
        },
    }
    resp = http.post(url, json=payload, headers={"Authorization": f"Bearer {access_token}"}, timeout=60)
    resp.raise_for_status()
    data = resp.json().get("data", {})
    return str(data.get("publish_id", "")), str(data.get("upload_url", ""))


def upload_video(upload_url: str, video_path: str, *, transport=None) -> None:
    http = transport or httpx
    with open(video_path, "rb") as fh:
        resp = http.put(upload_url, content=fh.read(),
                        headers={"Content-Type": "video/mp4"}, timeout=600)
    resp.raise_for_status()


def fetch_status(access_token: str, publish_id: str, *, transport=None) -> str:
    http = transport or httpx
    resp = http.post(STATUS, json={"publish_id": publish_id},
                     headers={"Authorization": f"Bearer {access_token}"}, timeout=60)
    resp.raise_for_status()
    return str(resp.json().get("data", {}).get("status", ""))


def publish_to_tiktok(post_id: int, db_path, video_path: str, *, access_token: str = "",
                      transport=None, mode: str = "inbox", poll: bool = True) -> dict:
    from ..db import init_db
    conn = init_db(db_path)
    post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not post:
        raise RuntimeError(f"post {post_id} not found")
    token = access_token or os.environ.get("TIKTOK_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("TIKTOK_ACCESS_TOKEN not set")
    publish_id, upload_url = init_publish(token, dict(post), video_path,
                                          transport=transport, mode=mode)
    upload_video(upload_url, video_path, transport=transport)
    status = ""
    if poll:
        for _ in range(30):
            status = fetch_status(token, publish_id, transport=transport)
            if status in {"PUBLISH_COMPLETE", "FAILED"}:
                break
    with conn:
        conn.execute("UPDATE posts SET status=?, platform='tiktok', external_post_id=?, "
                     "published_at=? WHERE id=?",
                     ("published" if status != "FAILED" else "failed", publish_id, utcnow(), post_id))
    return {"publish_id": publish_id, "status": status, "mode": mode}
