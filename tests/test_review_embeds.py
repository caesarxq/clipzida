"""RED tests for review embed + alert + digest formatting (P7.3)."""
import pytest

from clipping_tools.review.embeds import build_alert_embed, build_digest, build_review_embed


def test_review_embed_contains_hook_campaign_score_and_gate_badges():
    post = {
        "id": 7, "caption": "HOOK TITLE", "campaign": "Ruckus/Dom", "score": 0.82,
        "angle": "funny", "broadcaster": "dinah", "status": "pending",
        "rights": "pass", "rockstar": "pass", "campaign_gate": "pass", "platform": "review",
    }
    embed = build_review_embed(post)

    assert embed.title == "HOOK TITLE"
    assert "Ruckus/Dom" in embed.description
    assert "0.82" in embed.description
    assert "funny" in embed.description
    badges = " ".join(f.value for f in embed.fields)
    assert "rights: pass" in badges
    assert "platform: review" in badges
    assert "Post #7" in embed.title or "Post #7" in embed.description or embed.footer.text


def test_review_embed_rejects_missing_hook():
    with pytest.raises(ValueError):
        build_review_embed({"id": 1, "caption": "", "score": 0.5})


def test_alert_embed_marks_strike_and_halt():
    embed = build_alert_embed("strike", "takedown on post #7 — publishing halted")
    assert "STRIKE" in embed.title.upper()
    assert "takedown" in embed.description


def test_digest_counts_pending_published_and_revenue():
    text = build_digest({"pending": 3, "published": 5, "views": 12000, "revenue": 24.5})
    assert "3" in text and "5" in text and "12,000" in text and "24.50" in text
