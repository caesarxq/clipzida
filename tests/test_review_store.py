"""RED tests for the Discord review store + role gate (P7.3)."""
import sqlite3

import pytest

from clipping_tools.db import init_db
from clipping_tools.review.store import is_reviewer, record_decision


def _seed_post(conn: sqlite3.Connection) -> int:
    conn.execute(
        "INSERT INTO sources(id, platform, external_id, name) VALUES(1,'twitch','src1','src')"
    )
    conn.execute(
        "INSERT INTO clips_raw(id, source_id, external_id, url, title, created_at, status) "
        "VALUES(1, 1, 'clip1', 'https://clips.twitch.tv/clip1', 'clip', "
        "'2026-11-20T00:00:00+00:00', 'new')"
    )
    conn.execute(
        "INSERT INTO renders(id, clip_id, variant, path) VALUES(1, 1, 'v1', '/tmp/a.mp4')"
    )
    conn.execute(
        "INSERT INTO posts(id, render_id, caption, status) VALUES(1, 1, 'caption', 'pending')"
    )
    conn.commit()
    return 1


def test_record_decision_approve_writes_approval_and_releases_post():
    conn = init_db(":memory:")
    post_id = _seed_post(conn)

    record_decision(conn, post_id, "approve", "reviewer-1")

    row = conn.execute(
        "SELECT decision, reviewer, edits_json FROM approvals WHERE post_id=?", (post_id,)
    ).fetchone()
    assert row is not None
    assert row["decision"] == "approve"
    assert row["reviewer"] == "reviewer-1"
    status = conn.execute("SELECT status FROM posts WHERE id=?", (post_id,)).fetchone()[0]
    assert status == "approved"


def test_record_decision_reject_marks_post_rejected():
    conn = init_db(":memory:")
    post_id = _seed_post(conn)

    record_decision(conn, post_id, "reject", "reviewer-1", reason="bad clip")

    status = conn.execute("SELECT status FROM posts WHERE id=?", (post_id,)).fetchone()[0]
    assert status == "rejected"
    edits = conn.execute(
        "SELECT edits_json FROM approvals WHERE post_id=?", (post_id,)
    ).fetchone()[0]
    assert "bad clip" in edits


def test_record_decision_edit_approval_stores_edited_caption():
    conn = init_db(":memory:")
    post_id = _seed_post(conn)

    record_decision(conn, post_id, "approve", "reviewer-1", edits={"caption": "new caption"})

    row = conn.execute(
        "SELECT decision, edits_json FROM approvals WHERE post_id=?", (post_id,)
    ).fetchone()
    assert row["decision"] == "approve"
    assert "new caption" in row["edits_json"]
    assert conn.execute("SELECT caption FROM posts WHERE id=?", (post_id,)).fetchone()[0] == "new caption"


@pytest.mark.parametrize("roles", [[], ["123"], ["other", "456"]])
def test_is_reviewer_rejects_when_required_role_absent(roles):
    assert is_reviewer(roles, "required") is False


def test_is_reviewer_accepts_when_required_role_present():
    assert is_reviewer(["123", "required"], "required") is True
