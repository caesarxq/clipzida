"""Publish pending post drafts as Discord review embeds with working buttons.

Clip posts (render_id set) get a downscaled proxy MP4 attached so reviewers
can see the video before approving. Proxy generation is cached in
posts.review_proxy_path so each render is transcoded at most once.
"""
from __future__ import annotations

import os

import discord

from ..db import init_db
from .bot import ReviewView
from .embeds import build_review_embed
from .pipeline import create_drafts_for_pending_clips, pending_posts
from .proxy import make_proxy
from .orchestrator import render_path

# Discord file-size ceiling for direct uploads (conservative 10 MB).
DISCORD_FILE_CEILING = 10_000_000


async def _proxy_for_post(conn, post: dict) -> str | None:
    """Return a local path to a Discord-safe proxy MP4 for a clip post.

    Returns None for text-only posts (render_id is None) or if no render
    path is available. Caches the generated proxy path in posts.review_proxy_path
    so ffmpeg runs at most once per render.
    """
    render_id = post.get("render_id")
    if render_id is None:
        return None

    cached = post.get("review_proxy_path")
    if cached:
        return cached

    path = render_path(conn, int(render_id))
    if not path:
        return None

    proxy = make_proxy(path)
    if proxy is None:
        # Master already under ceiling — use it directly.
        proxy = path

    if proxy:
        conn.execute(
            "UPDATE posts SET review_proxy_path=? WHERE id=?",
            (str(proxy), int(post["id"])),
        )
        conn.commit()
    return str(proxy) if proxy else None


async def publish_pending_reviews(client, db_path: str, channel_id: str,
                                  reviewer_role: str) -> int:
    """Create drafts for stored clips and post one embed (+ proxy video) per pending post.

    Clip posts include a downscaled proxy MP4 attachment so reviewers can
    watch the video before clicking Approve / Reject / Edit-caption.
    """
    conn = init_db(db_path)
    create_drafts_for_pending_clips(conn)
    posts = [p for p in pending_posts(conn) if not p.get("review_message_id")]
    conn.close()

    channel = client.get_channel(int(channel_id))
    if channel is None and hasattr(client, "fetch_channel"):
        channel = await client.fetch_channel(int(channel_id))
    if channel is None:
        return 0

    posted = 0
    for post in posts:
        # Attach proxy video for clip posts.
        file_attachment = None
        has_video = False
        conn = init_db(db_path)
        proxy_path = await _proxy_for_post(conn, post)
        conn.close()
        if proxy_path and os.path.exists(proxy_path):
            file_attachment = discord.File(proxy_path)
            has_video = True

        embed = build_review_embed(post, has_video=has_video)
        view = ReviewView(int(post["id"]), reviewer_role, db_path)

        kwargs = {"embed": embed, "view": view}
        if file_attachment:
            kwargs["file"] = file_attachment

        message = await channel.send(**kwargs)

        conn = init_db(db_path)
        conn.execute("UPDATE posts SET review_message_id=? WHERE id=?",
                     (str(getattr(message, "id", "")), int(post["id"])))
        conn.commit()
        conn.close()
        posted += 1

    return posted
