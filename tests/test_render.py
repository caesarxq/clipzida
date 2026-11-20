"""RED: render stage resolves an approved post to its source clip for download."""
import os
import tempfile

from clipping_tools.db import init_db
from clipping_tools.review.render import (
    build_filter, font_path, select_moment, source_clip_for_post,
)


def test_select_moment_respects_min_and_max_bounds():
    words = [{"word": "a", "start": 0.0, "end": 2.0}, {"word": "b", "start": 40.0, "end": 60.0}]
    m = select_moment(words, target_min=18, target_max=45)
    assert m["end"] - m["start"] <= 45.0
    assert m["start"] >= 0.0


def test_select_moment_handles_empty_transcript():
    m = select_moment([])
    assert m["start"] == 0.0 and m["end"] <= 30.0


def test_build_filter_is_portable_libx264_friendly():
    from pathlib import Path
    vf = build_filter(Path("/tmp/c.ass"), "TEST: HOOK")
    assert "subtitles=" in vf and "drawtext=" in vf
    assert "1080:1920" in vf
    assert font_path().endswith((".ttf", ".otf"))



def _seed():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "state.db")
    conn = init_db(db)
    conn.execute("INSERT INTO sources(id,platform,external_id,name) VALUES(1,'twitch','s','s')")
    conn.execute("INSERT INTO clips_raw(id,source_id,external_id,url,title,duration,created_at,status) "
                 "VALUES(16,1,'clip16','https://clips.twitch.tv/clip16','HOOK',25,'2026-01-01T00:00:00+00:00','new')")
    conn.execute("INSERT INTO posts(id,render_id,caption,status,idempotency_key) "
                 "VALUES(16,NULL,'HOOK','approved','clip-16')")
    conn.commit(); conn.close()
    return db


def test_source_clip_for_post_resolves_via_idempotency_key():
    db = _seed()
    clip = source_clip_for_post(init_db(db), 16)
    assert clip["url"] == "https://clips.twitch.tv/clip16"
    assert clip["id"] == 16


def test_source_clip_for_post_rejects_wrong_status():
    db = _seed()
    conn = init_db(db)
    conn.execute("UPDATE posts SET status='pending' WHERE id=16")
    conn.commit()
    assert source_clip_for_post(conn, 16) is None


def test_source_clip_for_post_allows_rendered_for_re_render():
    db = _seed()
    conn = init_db(db)
    conn.execute("UPDATE posts SET status='rendered' WHERE id=16")
    conn.commit()
    assert source_clip_for_post(conn, 16) is not None
