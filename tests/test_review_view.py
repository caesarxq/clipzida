"""RED: bot builds a real ReviewView with the post id in custom_ids."""
from clipping_tools.review.bot import ReviewView


def test_review_view_custom_ids_carry_post_id():
    view = ReviewView(42, "reviewer-role", "/tmp/x.db")
    ids = {child.custom_id for child in view.children}
    assert "clipzida:approve:42" in ids
    assert "clipzida:reject:42" in ids
    assert "clipzida:edit:42" in ids
