"""News ingest for the CLIPZIDA pipeline.

Fetches GTA 6 news from free sources (Google News RSS for GTA 6, Reddit r/GTA6)
and persists draft posts to the pipeline DB for Discord review.

News posts are text-only (render_id = NULL). Approved news posts are published
to X (text) by the cycle's text-publish stage.
"""
from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

# Google News RSS for GTA 6 (no API key, free). Reddit JSON as fallback.
NEWS_SOURCES = [
    (
        "google_news_gta6",
        "https://news.google.com/rss/search?q=GTA+6&hl=en-US&gl=US&ceid=US:en",
    ),
    ("reddit_gta6", "https://www.reddit.com/r/GTA6/new.json?limit=10"),
]


def _text(node) -> str:
    """Return concatenated text content of an XML element's children."""
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _parse_rss(resp_content: bytes, source_name: str) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(resp_content)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        title = _text(item.find("title")) or ""
        link = _text(item.find("link")) or ""
        description = _text(item.find("description")) or ""
        pub_date = _text(item.find("pubDate")) or ""
        guid = _text(item.find("guid")) or link
        publisher = _text(item.find("source")) or source_name
        if not title or not link:
            continue
        items.append(
            {
                "external_id": guid,
                "title": title,
                "url": link,
                "description": description,
                "posted_at": pub_date,
                "source": publisher or source_name,
            }
        )
    return items


def _parse_reddit_json(resp_content: bytes, source_name: str) -> list[dict]:
    import json

    items: list[dict] = []
    try:
        data = json.loads(resp_content)
    except (ValueError, json.JSONDecodeError):
        return items
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        title = post.get("title") or ""
        link = post.get("url") or ""
        if not title or not link:
            continue
        # Only keep self-posts or external links pointing at GTA 6 content
        items.append(
            {
                "external_id": f"reddit:{post.get('id')}",
                "title": title,
                "url": link,
                "description": post.get("selftext") or "",
                "posted_at": str(post.get("created_utc") or ""),
                "source": "reddit_gta6",
            }
        )
    return items


def fetch_news_items(http_get=None) -> list[dict]:
    """Fetch candidate news items from official GTA 6 sources.

    Returns a list of dicts: {external_id, title, url, posted_at, source}.

    ``http_get`` is an injectable callable ``f(url, headers=None, timeout=None)
    -> response`` where response has ``.content`` (bytes) and ``.raise_for_status()``.
    Defaults to ``httpx.get``.
    """
    http_get = http_get or httpx.get
    headers = {"User-Agent": "CLIPZIDA news ingest (contact: privacy@clipzida.com)"}
    items: list[dict] = []

    for source_name, url in NEWS_SOURCES:
        try:
            resp = http_get(url, headers=headers, timeout=30)
            resp.raise_for_status()
        except Exception:  # noqa: BLE001 — one source failing must not kill ingest
            continue

        if "reddit" in url:
            items.extend(_parse_reddit_json(resp.content, source_name))
        else:
            items.extend(_parse_rss(resp.content, source_name))

    # Dedupe by external_id, preserving first occurrence.
    seen: set[str] = set()
    unique: list[dict] = []
    for item in items:
        if item["external_id"] in seen:
            continue
        seen.add(item["external_id"])
        unique.append(item)
    return unique


def news_caption(item: dict) -> str:
    """Build a news recap caption for a news item (X-friendly, no hashtags)."""
    lines = [item["title"]]
    if item.get("description"):
        lines.append("")
        lines.append(html.unescape(item["description"])[:280])
    lines.append("")
    lines.append("🎥 @RockstarGames")
    lines.append("")
    lines.append(item["url"])
    return "\n".join(lines)


def init_post(conn, item: dict) -> int:
    """Insert a news post draft (status='pending', render_id=NULL).

    Idempotent via idempotency_key='news:<external_id>'. Returns the post id.
    """
    key = "news:" + item["external_id"]
    existing = c = conn.execute(
        "SELECT id FROM posts WHERE idempotency_key=?", (key,)
    ).fetchone()
    if existing:
        return int(existing[0])

    caption = news_caption(item)
    cur = conn.execute(
        """INSERT INTO posts(render_id, caption, status, angle, platform, idempotency_key)
           VALUES(NULL, ?, 'pending', 'news', 'x', ?)""",
        (caption, key),
    )
    conn.commit()
    return int(cur.lastrowid)
