"""RED: drafts get an angle tag at creation; schema exposes it."""
import os
import tempfile

from clipping_tools.db import init_db
from clipping_tools.review.pipeline import create_drafts_for_pending_clips


def _seed(title="lacy got caught creeping around mandy house"):
    d = tempfile.mkdtemp()
    db = os.path.join(d, "state.db")
    conn = init_db(db)
    conn.execute("INSERT INTO sources(id,platform,external_id,name) VALUES(1,'twitch','s','s')")
    conn.execute("INSERT INTO clips_raw(id,source_id,external_id,url,title,created_at,status) "
                 "VALUES(1,1,'c','u',?,'2026-01-01T00:00:00+00:00','new')", (title,))
    conn.commit(); conn.close()
    return db


def test_drafts_are_tagged_with_angle():
    db = _seed()
    conn = init_db(db)
    create_drafts_for_pending_clips(conn)
    row = conn.execute("SELECT caption, angle FROM posts").fetchone()
    assert row["caption"] == "lacy got caught creeping around mandy house"
    assert row["angle"] == "funny"


def test_unclear_title_tags_none_for_human_review():
    db = _seed("someone walks across a street")
    conn = init_db(db)
    create_drafts_for_pending_clips(conn)
    assert conn.execute("SELECT angle FROM posts").fetchone()[0] is None
