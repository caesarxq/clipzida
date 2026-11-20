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
    for row in rows:
        conn.execute(
            "INSERT INTO posts(render_id, caption, status, idempotency_key) "
            "VALUES(NULL, ?, 'pending', ?)",
            (row["title"] or f"Clip #{row['id']}", f"clip-{row['id']}"),
        )
    conn.commit()
    return len(rows)


def pending_posts(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id, render_id, caption, status, campaign_id, platform FROM posts "
        "WHERE status='pending' ORDER BY id"
    ).fetchall()]
