"""RED: warm-up ramp + quota gates protect fresh accounts."""
import os
import tempfile
from datetime import datetime, timedelta, timezone

import yaml
from pathlib import Path

from clipping_tools.db import init_db
from clipping_tools.review.warmup import (
    account_age_days, can_publish, daily_cap, posts_today, record_publish, warmup_stage,
)

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config/platforms.yaml").read_text())


def _seed(created_days_ago=0):
    d = tempfile.mkdtemp()
    db = os.path.join(d, "state.db")
    conn = init_db(db)
    created = (datetime.now(timezone.utc) - timedelta(days=created_days_ago)).isoformat()
    conn.execute("INSERT INTO accounts(id,platform,handle,created_at,status) VALUES(1,'tiktok','@clipzida',?,'active')", (created,))
    conn.commit(); conn.close()
    return db


def test_warmup_stage_by_account_age():
    assert warmup_stage(0) == 0
    assert warmup_stage(8) == 1
    assert warmup_stage(20) == 2


def test_daily_cap_follows_platform_warmup_ramp():
    assert daily_cap(CFG["tiktok"], 0) == 1
    assert daily_cap(CFG["tiktok"], 8) == 2
    assert daily_cap(CFG["tiktok"], 20) == 3


def test_account_age_days_computes_from_created_at():
    assert account_age_days((datetime.now(timezone.utc) - timedelta(days=10)).isoformat()) == 10


def test_can_publish_blocks_when_daily_cap_reached():
    db = _seed(created_days_ago=0)
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id,platform,status,published_at) VALUES(9,'tiktok','published',?)",
                 (datetime.now(timezone.utc).isoformat(),))
    conn.commit()
    ok, reason = can_publish(conn, "tiktok", "@clipzida")
    assert ok is False and "cap" in reason


def test_can_publish_allows_under_cap():
    db = _seed(created_days_ago=10)
    conn = init_db(db)
    assert can_publish(conn, "tiktok", "@clipzida")[0] is True


def test_youtube_api_unit_gate_pauses_at_threshold():
    db = _seed(created_days_ago=30)
    conn = init_db(db)
    from clipping_tools.db import incr_quota
    incr_quota(conn, "youtube", 6400)
    assert can_publish(conn, "youtube", "@clipzida")[0] is True
    incr_quota(conn, "youtube", 8400)  # at pause threshold
    ok, reason = can_publish(conn, "youtube", "@clipzida")
    assert ok is False and "quota" in reason
