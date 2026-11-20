"""RED: stored clips must become queued post drafts with review embeds."""
import os
import tempfile

from clipping_tools.db import init_db
from clipping_tools.models import ClipCandidate, Platform
from clipping_tools.review.pipeline import create_drafts_for_pending_clips, pending_posts
from datetime import datetime, timezone


def _seed_clip(conn, external_id="clip1", title="HOOK TITLE"):
    conn.execute("INSERT INTO sources(id,platform,external_id,name) VALUES(1,'twitch','s','s')")
    conn.execute(
        "INSERT INTO clips_raw(id,source_id,external_id,url,title,broadcaster,view_count,duration,language,created_at,status) "
        "VALUES(1,1,?,'https://clips.twitch.tv/clip1',?,'kaicenat',50000,20,'en','2026-01-01T00:00:00+00:00','new')",
        (external_id, title),
    )
    conn.commit()


def test_create_drafts_makes_one_pending_post_per_new_clip():
    with tempfile.TemporaryDirectory() as d:
        conn = init_db(os.path.join(d, "state.db"))
        _seed_clip(conn)
        n = create_drafts_for_pending_clips(conn)
        assert n == 1
        posts = pending_posts(conn)
        assert len(posts) == 1
        assert posts[0]["caption"] == "HOOK TITLE"
        assert posts[0]["status"] == "pending"


def test_create_drafts_is_idempotent():
    with tempfile.TemporaryDirectory() as d:
        conn = init_db(os.path.join(d, "state.db"))
        _seed_clip(conn)
        assert create_drafts_for_pending_clips(conn) == 1
        assert create_drafts_for_pending_clips(conn) == 0
        assert len(pending_posts(conn)) == 1
