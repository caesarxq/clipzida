from datetime import datetime, timezone

from clipping_tools import db
from clipping_tools.models import ClipCandidate, Platform


def _clip(ext="abc", views=100):
    return ClipCandidate(source_platform=Platform.TWITCH, external_id=ext, url="https://x",
                         view_count=views, duration=25.0, language="en",
                         created_at=datetime.now(timezone.utc))


def test_upsert_dedupe(tmp_path):
    conn = db.init_db(tmp_path / "t.db")
    id1 = db.upsert_clip(conn, _clip())
    id2 = db.upsert_clip(conn, _clip(views=999))
    assert id1 == id2
    row = conn.execute("SELECT view_count FROM clips_raw WHERE id=?", (id1,)).fetchone()
    assert row[0] == 999


def test_quota_counters(tmp_path):
    conn = db.init_db(tmp_path / "t.db")
    db.incr_quota(conn, "youtube", 1600, day="2026-11-20")
    db.incr_quota(conn, "youtube", 1600, day="2026-11-20")
    assert db.get_quota(conn, "youtube", day="2026-11-20") == 3200
    assert db.get_quota(conn, "youtube", day="2026-11-21") == 0


def test_audit(tmp_path):
    conn = db.init_db(tmp_path / "t.db")
    db.audit(conn, "ingest", "clip", 1, "fetched", {"n": 5})
    row = conn.execute("SELECT event, detail_json FROM audit_log").fetchone()
    assert row[0] == "fetched" and '"n": 5' in row[1]