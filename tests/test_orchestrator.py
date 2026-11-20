"""RED: the autonomous cycle renders approved posts and publishes rendered ones."""
import os
import tempfile

from clipping_tools.db import init_db
from clipping_tools.review.orchestrator import run_cycle


def _seed():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "state.db")
    conn = init_db(db)
    conn.execute("INSERT INTO sources(id,platform,external_id,name) VALUES(1,'twitch','s','s')")
    for cid, title in ((1, "A"), (2, "B"), (3, "C")):
        conn.execute("INSERT INTO clips_raw(id,source_id,external_id,url,title,duration,created_at,status) "
                     "VALUES(?,1,?,'u',?,20,'2026-01-01T00:00:00+00:00','new')", (cid, f"c{cid}", title))
    conn.execute("INSERT INTO posts(id,render_id,caption,status,idempotency_key) VALUES(1,NULL,'A','approved','clip-1')")
    conn.execute("INSERT INTO posts(id,render_id,caption,status,idempotency_key) VALUES(2,9,'B','rendered','clip-2')")
    conn.execute("INSERT INTO posts(id,render_id,caption,status,idempotency_key) VALUES(3,NULL,'C','pending','clip-3')")
    conn.execute("INSERT INTO renders(id,clip_id,variant,path) VALUES(9,2,'vertical-1080x1920','/tmp/b.mp4')")
    conn.commit(); conn.close()
    return db


def test_run_cycle_renders_only_approved_and_publishes_only_rendered():
    db = _seed()
    calls = {"rendered": [], "published": []}

    def fake_render(post_id, db_path):
        calls["rendered"].append(post_id)
        conn = init_db(db_path)
        conn.execute("UPDATE posts SET render_id=100, status='rendered' WHERE id=?", (post_id,))
        conn.commit(); conn.close()
        return {}

    def fake_publish(post_id, db_path, path, platform="youtube"):
        calls["published"].append(post_id)
        conn = init_db(db_path)
        conn.execute("UPDATE posts SET status='published' WHERE id=?", (post_id,))
        conn.commit(); conn.close()
        return {}

    def noop(*a, **k):
        return None

    result = run_cycle(db, render_fn=fake_render, publish_fn=fake_publish,
                       ingest_fn=noop, review_publish_fn=noop)
    assert calls["rendered"] == [1]
    assert calls["published"] == [2]
    assert result == {"rendered": 1, "published": 1}


def test_run_cycle_skips_publish_when_gate_blocks():
    db = _seed()
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id,render_id,caption,status,idempotency_key) "
                 "VALUES(4,9,'D','rendered','clip-4')")
    conn.commit(); conn.close()
    published = []
    result = run_cycle(db, ingest_fn=lambda: None, review_publish_fn=lambda: None,
                       render_fn=lambda *a: None,
                       publish_fn=lambda pid, dbp, path: published.append(pid),
                       gate_fn=lambda conn, platform, account: (False, "cap reached"))
    assert published == []
    assert result["published"] == 0


def test_run_cycle_is_idempotent_when_nothing_to_do():
    db = _seed()
    conn = init_db(db)
    conn.execute("UPDATE posts SET status='published', render_id=9 WHERE id=2")
    conn.execute("UPDATE posts SET render_id=5, status='rendered' WHERE id=1")
    conn.commit(); conn.close()
    calls = {"rendered": [], "published": []}
    result = run_cycle(db, render_fn=lambda *a: calls["rendered"].append(1),
                       publish_fn=lambda *a: calls["published"].append(1),
                       ingest_fn=lambda: None, review_publish_fn=lambda: None)
    assert calls == {"rendered": [], "published": []}
    assert result == {"rendered": 0, "published": 0}
