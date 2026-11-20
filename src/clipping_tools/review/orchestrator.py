"""Autonomous pipeline cycle: ingest -> review -> render -> publish (VPS 24/7)."""
from __future__ import annotations

import sqlite3

from ..db import init_db


def approved_unrendered(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id FROM posts WHERE status='approved' AND render_id IS NULL ORDER BY id"
    ).fetchall()]


def rendered_unpublished(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id, render_id FROM posts WHERE status='rendered' ORDER BY id"
    ).fetchall()]


def render_path(conn: sqlite3.Connection, render_id: int) -> str | None:
    row = conn.execute("SELECT path FROM renders WHERE id=?", (render_id,)).fetchone()
    return row["path"] if row else None


def run_cycle(db_path, *, ingest_fn=None, review_publish_fn=None,
              render_fn=None, publish_fn=None, gate_fn=None,
              publish_platform: str = "youtube", publish_account: str | None = None) -> dict:
    """One autonomous pass. All stages injectable for testing.

    Order: ingest new clips -> post drafts to Discord -> render approved ->
    publish rendered. Each stage is idempotent via post status.
    """
    conn = init_db(db_path)
    if ingest_fn:
        ingest_fn()
    if review_publish_fn:
        review_publish_fn()
    counts = {"rendered": 0, "published": 0}
    for post in approved_unrendered(conn):
        if render_fn:
            render_fn(post["id"], db_path)
            counts["rendered"] += 1
    conn.close()
    if publish_fn:
        conn = init_db(db_path)
        for post in rendered_unpublished(conn):
            path = render_path(conn, post["render_id"])
            if not path:
                continue
            if gate_fn:
                allowed, reason = gate_fn(conn, publish_platform, publish_account)
                if not allowed:
                    print(f"publish gate blocked post {post['id']}: {reason}")
                    continue
            publish_fn(post["id"], db_path, path)
            counts["published"] += 1
        conn.close()
    return counts
