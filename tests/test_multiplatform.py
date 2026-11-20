"""RED: posts publish to multiple platforms, each recorded in post_platforms."""
import os
import tempfile

from clipping_tools.db import init_db
from clipping_tools.review.orchestrator import run_cycle


def _seed():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "state.db")
    conn = init_db(db)
    conn.execute("INSERT INTO sources(id,platform,external_id,name) VALUES(1,'twitch','s','s')")
    conn.execute("INSERT INTO clips_raw(id,source_id,external_id,url,title,created_at,status) "
                 "VALUES(7,1,'c','u','H','2026-01-01T00:00:00+00:00','new')")
    conn.execute("INSERT INTO renders(id,clip_id,variant,path) VALUES(3,7,'v','/tmp/v.mp4')")
    conn.execute("INSERT INTO posts(id,render_id,caption,status,idempotency_key) "
                 "VALUES(7,3,'H','rendered','clip-7')")
    conn.commit(); conn.close()
    return db


def test_run_cycle_publishes_to_each_target_and_records_rows():
    db = _seed()
    published = []
    def pub(post_id, db_path, path, platform):
        published.append((post_id, platform))
        conn = init_db(db_path)
        conn.execute("INSERT INTO post_platforms(post_id,platform,status,external_id) VALUES(?,?,?,?)",
                     (post_id, platform, "published", f"id-{platform}"))
        conn.commit(); conn.close()
        return {}
    result = run_cycle(db, ingest_fn=lambda: None, review_publish_fn=lambda: None,
                       render_fn=lambda *a: None, publish_fn=pub,
                       targets=["youtube", "tiktok"])
    assert sorted(published) == [(7, "tiktok"), (7, "youtube")]
    assert result["published"] == 2
    conn = init_db(db)
    rows = [tuple(r) for r in conn.execute("SELECT post_id, platform, status FROM post_platforms ORDER BY platform")]
    assert rows == [(7, "tiktok", "published"), (7, "youtube", "published")]


def test_run_cycle_skips_platform_already_published():
    db = _seed()
    conn = init_db(db)
    conn.execute("INSERT INTO post_platforms(post_id,platform,status) VALUES(7,'youtube','published')")
    conn.commit(); conn.close()
    published = []
    result = run_cycle(db, ingest_fn=lambda: None, review_publish_fn=lambda: None,
                       render_fn=lambda *a: None,
                       publish_fn=lambda pid, dbp, path, plat: published.append(plat),
                       targets=["youtube", "tiktok"])
    assert published == ["tiktok"]
