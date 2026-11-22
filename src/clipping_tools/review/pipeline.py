"""Turn stored clips into post drafts and expose the review queue (P7.3 bridge)."""
from __future__ import annotations

import sqlite3

from ..db import utcnow


def create_drafts_for_pending_clips(conn: sqlite3.Connection) -> int:
    """Create one pending post per clip that has no draft yet. Idempotent via idempotency_key."""
    rows = conn.execute(
        "SELECT c.id, c.title FROM clips_raw c WHERE NOT EXISTS ("
        "  SELECT 1 FROM posts p WHERE p.idempotency_key = 'clip-' || c.id"
        ")"
    ).fetchall()
    from .angles import classify_angle
    for row in rows:
        conn.execute(
            "INSERT INTO posts(render_id, caption, status, angle, idempotency_key) "
            "VALUES(NULL, ?, 'pending', ?, ?)",
            (row["title"] or f"Clip #{row['id']}", classify_angle(row["title"] or ""),
             f"clip-{row['id']}"),
        )
    conn.commit()
    return len(rows)


def pending_posts(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT p.id, p.render_id, p.caption, p.status, p.campaign_id, p.platform,
                  p.review_message_id, p.angle, p.url AS post_url,
                  c.broadcaster, c.duration, c.view_count, c.fetched_at, c.url AS clip_url
           FROM posts p
           LEFT JOIN renders r ON r.id = p.render_id
           LEFT JOIN clips_raw c ON c.id = r.clip_id
           WHERE p.status='pending'
           ORDER BY p.id"""
    ).fetchall()]
