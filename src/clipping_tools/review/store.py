"""Approval store + role gate for the Discord review surface (P7.3)."""
from __future__ import annotations

import json
import sqlite3

from ..db import audit, utcnow


def is_reviewer(member_role_ids: list[str] | set[str], required_role_id: str) -> bool:
    """Fail closed: only a member holding the configured Reviewer role may decide."""
    return bool(required_role_id) and required_role_id in set(member_role_ids)


def record_decision(
    conn: sqlite3.Connection,
    post_id: int,
    decision: str,
    reviewer: str,
    reason: str | None = None,
    edits: dict | None = None,
) -> None:
    """Write an approval row and move the post to approved/rejected.

    Edits are applied to the post caption in the same transaction so the publish
    queue sees the final caption. An edited approval is still an approval; the
    graduation policy reads edits_json to count unchanged approvals.
    """
    if decision not in {"approve", "reject"}:
        raise ValueError(f"unsupported decision: {decision}")
    detail: dict = {}
    if reason:
        detail["reason"] = reason
    if edits:
        detail["edits"] = edits
    payload = json.dumps(detail) if detail else "{}"
    with conn:
        conn.execute(
            "INSERT INTO approvals(post_id, decision, reviewer, edits_json, decided_at) "
            "VALUES(?,?,?,?,?)",
            (post_id, decision, reviewer, payload, utcnow()),
        )
        if edits and "caption" in edits:
            conn.execute(
                "UPDATE posts SET caption=? WHERE id=?", (str(edits["caption"]), post_id)
            )
        conn.execute(
            "UPDATE posts SET status=? WHERE id=?",
            ("approved" if decision == "approve" else "rejected", post_id),
        )
    audit(conn, "review", "post", post_id, decision, detail)
