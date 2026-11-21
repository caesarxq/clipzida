"""RED: Phase 6 — Measurement & Optimization.
Retention tracking, A/B test framework, auto-optimization, kill underperformers.
"""
from __future__ import annotations

from clipping_tools.review.render import (
    record_metrics,
    get_avg_retention,
    should_kill_underperformer,
    ab_test_variant,
    select_best_variant,
    auto_optimize_angle,
)

import os


def _seed_posts(db: str, count: int = 2, angle: str | None = None) -> list[int]:
    """Insert `count` published posts, optionally with an angle. Returns ids."""
    from clipping_tools.db import init_db
    conn = init_db(db)
    ids = []
    for i in range(count):
        pid = 100 + i
        conn.execute(
            "INSERT INTO posts(id, caption, status, angle) "
            "VALUES(?, ?, 'published', ?)",
            (pid, f"post {pid}", angle),
        )
        ids.append(pid)
    conn.commit()
    conn.close()
    return ids


def _seed_metrics(db: str, rows: list[tuple[int, str, int, int]]) -> None:
    """Insert metrics rows: (post_id, fetched_at, views, approved_views)."""
    from clipping_tools.db import init_db
    conn = init_db(db)
    for post_id, fetched_at, views, approved in rows:
        conn.execute(
            "INSERT INTO metrics(post_id, fetched_at, views, likes, comments, "
            "shares, approved_views, payout) VALUES(?, ?, ?, 0, 0, 0, ?, 0.0)",
            (post_id, fetched_at, views, approved),
        )
    conn.commit()
    conn.close()


# ── Metrics recording ──────────────────────────────────────────────────────

def test_record_metrics_stores_views_likes_comments_shares(tmp_path):
    """Metrics row is created with all engagement fields."""
    db = os.path.join(tmp_path, "state.db")
    from clipping_tools.db import init_db
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id, caption, status) VALUES(16, 'test', 'published')")
    conn.commit()
    conn.close()

    record_metrics(db, post_id=16, views=1000, likes=50, comments=10, shares=5,
                   fetched_at="2026-11-20T12:00:00+00:00")

    conn = init_db(db)
    row = conn.execute("SELECT views, likes, comments, shares FROM metrics WHERE post_id=16").fetchone()
    assert row["views"] == 1000
    assert row["likes"] == 50
    assert row["comments"] == 10
    assert row["shares"] == 5


def test_record_metrics_upserts_on_same_fetched_at(tmp_path):
    """Same post_id + fetched_at updates instead of duplicating."""
    db = os.path.join(tmp_path, "state.db")
    from clipping_tools.db import init_db
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id, caption, status) VALUES(16, 'test', 'published')")
    conn.commit()
    conn.close()

    record_metrics(db, post_id=16, views=1000, likes=50, comments=10, shares=5,
                   fetched_at="2026-11-20T12:00:00+00:00")
    record_metrics(db, post_id=16, views=1500, likes=75, comments=15, shares=8,
                   fetched_at="2026-11-20T12:00:00+00:00")

    conn = init_db(db)
    rows = conn.execute("SELECT views FROM metrics WHERE post_id=16").fetchall()
    assert len(rows) == 1
    assert rows[0]["views"] == 1500


# ── Retention ──────────────────────────────────────────────────────────────

def test_get_avg_retention_computes_from_metrics(tmp_path):
    """Average view % = total approved_views / (views * duration) * 100."""
    db = os.path.join(tmp_path, "state.db")
    from clipping_tools.db import init_db
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id, caption, status) VALUES(16, 'test', 'published')")
    conn.execute("INSERT INTO posts(id, caption, status) VALUES(17, 'test2', 'published')")
    conn.execute("INSERT INTO metrics(post_id, fetched_at, views, approved_views) "
                 "VALUES(16, 't1', 1000, 600), (17, 't1', 500, 250)")
    conn.commit()
    conn.close()

    avg = get_avg_retention(db, post_id=16)
    assert avg == 60.0  # 600/1000 * 100

    avg_all = get_avg_retention(db)
    # (600+250)/(1000+500) * 100 = 56.67
    assert abs(avg_all - 56.67) < 0.1


def test_get_avg_retention_no_metrics_returns_zero(tmp_path):
    """No metrics → 0.0 retention."""
    db = os.path.join(tmp_path, "state.db")
    from clipping_tools.db import init_db
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id, caption, status) VALUES(16, 'test', 'published')")
    conn.commit()
    conn.close()

    assert get_avg_retention(db, post_id=16) == 0.0


# ── Kill underperformer ────────────────────────────────────────────────────

def test_should_kill_underperformer_below_threshold():
    """<30% retention after 50 views → kill."""
    assert should_kill_underperformer(retention_pct=25.0, views=100) is True


def test_should_kill_underperformer_above_threshold():
    """≥30% retention → don't kill."""
    assert should_kill_underperformer(retention_pct=35.0, views=100) is False


def test_should_kill_underperformer_insufficient_views():
    """<50 views → don't kill even with low retention."""
    assert should_kill_underperformer(retention_pct=10.0, views=10) is False


def test_should_kill_underperformer_exactly_50_views():
    """50 views is the threshold boundary."""
    assert should_kill_underperformer(retention_pct=25.0, views=50) is True


# ── A/B test framework ─────────────────────────────────────────────────────

def test_ab_test_variant_records_variant_assignment(tmp_path):
    """A/B test records which variant a post was assigned to."""
    db = os.path.join(tmp_path, "state.db")
    from clipping_tools.db import init_db
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id, caption, status) VALUES(16, 'test', 'published')")
    conn.execute("INSERT INTO posts(id, caption, status) VALUES(17, 'test', 'published')")
    conn.commit()
    conn.close()

    ab_test_variant(db, post_id=16, variant="hook_a")
    ab_test_variant(db, post_id=17, variant="hook_b")

    conn = init_db(db)
    row = conn.execute("SELECT variant FROM ab_tests WHERE post_id=16").fetchone()
    assert row["variant"] == "hook_a"


def test_select_best_variant_picks_highest_retention(tmp_path):
    """Select variant with highest avg retention across posts."""
    db = os.path.join(tmp_path, "state.db")
    from clipping_tools.db import init_db
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id, caption, status) VALUES(16, 'a', 'published')")
    conn.execute("INSERT INTO posts(id, caption, status) VALUES(17, 'b', 'published')")
    conn.execute("INSERT INTO posts(id, caption, status) VALUES(18, 'c', 'published')")
    conn.execute("INSERT INTO ab_tests(post_id, test_name, variant) "
                 "VALUES(16, 'hook_test', 'hook_a'), (17, 'hook_test', 'hook_a'), "
                 "(18, 'hook_test', 'hook_b')")
    # hook_a: 80% + 70% = 75% avg; hook_b: 40%
    conn.execute("INSERT INTO metrics(post_id, fetched_at, views, approved_views) "
                 "VALUES(16, 't1', 1000, 800), (17, 't1', 1000, 700), (18, 't1', 1000, 400)")
    conn.commit()
    conn.close()

    best = select_best_variant(db, test_name="hook_test")
    assert best == "hook_a"


def test_select_best_variant_no_data_returns_none(tmp_path):
    """No A/B test data → None."""
    db = os.path.join(tmp_path, "state.db")
    from clipping_tools.db import init_db
    conn = init_db(db)
    conn.commit()
    conn.close()

    assert select_best_variant(db, test_name="empty_test") is None


# ── Auto-optimize angle ────────────────────────────────────────────────────

def test_auto_optimize_angle_switches_to_better_performing(tmp_path):
    """If 'hype' outperforms 'funny' by >10pt, switch default angle."""
    db = os.path.join(tmp_path, "state.db")
    from clipping_tools.db import init_db
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id, caption, status, angle) VALUES(16, 'a', 'published', 'funny')")
    conn.execute("INSERT INTO posts(id, caption, status, angle) VALUES(17, 'b', 'published', 'hype')")
    # funny: 40%, hype: 80% → diff = 40pt > 10pt threshold → switch
    conn.execute("INSERT INTO metrics(post_id, fetched_at, views, approved_views) "
                 "VALUES(16, 't1', 1000, 400), (17, 't1', 1000, 800)")
    conn.commit()
    conn.close()

    new_angle = auto_optimize_angle(db, current_angle="funny")
    assert new_angle == "hype"


def test_auto_optimize_angle_no_switch_when_margin_small(tmp_path):
    """<10pt difference → keep current angle."""
    db = os.path.join(tmp_path, "state.db")
    from clipping_tools.db import init_db
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id, caption, status, angle) VALUES(16, 'a', 'published', 'funny')")
    conn.execute("INSERT INTO posts(id, caption, status, angle) VALUES(17, 'b', 'published', 'hype')")
    # funny: 70%, hype: 75% → diff = 5pt, not enough
    conn.execute("INSERT INTO metrics(post_id, fetched_at, views, approved_views) "
                 "VALUES(16, 't1', 1000, 700), (17, 't1', 1000, 750)")
    conn.commit()
    conn.close()

    new_angle = auto_optimize_angle(db, current_angle="funny")
    assert new_angle == "funny"
