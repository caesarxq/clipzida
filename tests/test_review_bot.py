"""RED tests for the Discord interaction decision path (P7.3)."""
import pytest

from clipping_tools.review.bot import decide


def test_unreviewed_user_cannot_approve():
    result = decide(
        member_role_ids=["123", "456"], required_role="reviewer-role",
        decision="approve", post_id=1, reviewer="user-1",
    )
    assert result == "ignored"


def test_reviewer_can_approve():
    result = decide(
        member_role_ids=["reviewer-role"], required_role="reviewer-role",
        decision="approve", post_id=1, reviewer="user-1",
    )
    assert result == "approved"


def test_reviewer_can_reject_with_reason():
    result = decide(
        member_role_ids=["reviewer-role"], required_role="reviewer-role",
        decision="reject", post_id=1, reviewer="user-1", reason="wrong clip",
    )
    assert result == "rejected"
