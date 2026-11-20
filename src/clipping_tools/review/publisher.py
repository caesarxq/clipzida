"""Publish pending post drafts as Discord review embeds with working buttons."""
from __future__ import annotations

import os

from ..db import init_db
from .bot import ReviewView
from .embeds import build_review_embed
from .pipeline import create_drafts_for_pending_clips, pending_posts


async def publish_pending_reviews(client, db_path, channel_id: str,
                                  reviewer_role: str) -> int:
    """Create drafts for stored clips and post one embed+view per pending post."""
    conn = init_db(db_path)
    create_drafts_for_pending_clips(conn)
    posts = pending_posts(conn)
    conn.close()
    channel = client.get_channel(int(channel_id))
    if channel is None and hasattr(client, "fetch_channel"):
        channel = await client.fetch_channel(int(channel_id))
    if channel is None:
        return 0
    for post in posts:
        embed = build_review_embed(post)
        view = ReviewView(int(post["id"]), reviewer_role, db_path)
        await channel.send(embed=embed, view=view)
    return len(posts)
