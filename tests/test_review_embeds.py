"""Tests for the enriched Discord review embed (P7.3)."""
from __future__ import annotations

import pytest

from clipping_tools.review.embeds import _badge, build_alert_embed, build_digest, build_review_embed


def test_badge_verified():
    assert _badge("verified") == "✅ verified"
    assert _badge("ok") == "✅ ok"
    assert _badge("registered") == "✅ registered"
    assert _badge("supported") == "✅ supported"


def test_badge_unverified():
    assert _badge("unverified") == "⚠️ unverified"
    assert _badge("review") == "⚠️ review"


def test_badge_reject():
    assert _badge("unlicensed") == "❌ unlicensed"
    assert _badge("strike-risk") == "❌ strike-risk"
    assert _badge("not-registered") == "❌ not-registered"
    assert _badge("unsupported") == "❌ unsupported"


def test_badge_unknown_defaults_to_warning():
    assert _badge("weird_value") == "⚠️ weird_value"


def test_review_embed_contains_hook_and_gate_badges():
    post = {
        "id": 7, "caption": "HOOK TITLE",
        "rights": "verified", "rockstar": "ok",
        "campaign": "registered", "platform": "supported",
    }
    embed = build_review_embed(post)

    assert embed.title == "HOOK TITLE"
    badges = " ".join(f.value for f in embed.fields)
    assert "rights: ✅ verified" in badges
    assert "platform: ✅ supported" in badges
    assert "Post #7" in embed.footer.text


def test_review_embed_gates_default_to_unverified():
    post = {"id": 1, "caption": "HOOK TITLE"}
    embed = build_review_embed(post)
    gates = [f for f in embed.fields if f.name == "Gates"][0]
    assert "⚠️ unverified" in gates.value


def test_review_embed_rejects_missing_hook():
    with pytest.raises(ValueError):
        build_review_embed({"id": 1, "caption": ""})


def test_clip_embed_includes_streamer_angle_duration_views():
    post = {
        "id": 42, "caption": "HUGE GTA 6 LEAK",
        "render_id": 7, "angle": "hype",
        "broadcaster": "Kai Cenat", "duration": 45.5,
        "view_count": 12345, "fetched_at": "2026-11-22T10:00:00Z",
        "clip_url": "https://clips.twitch.tv/example",
    }
    embed = build_review_embed(post)
    desc = embed.description or ""
    assert "Kai Cenat" in desc
    assert "hype" in desc
    assert "12,345" in desc
    type_field = [f for f in embed.fields if f.name == "Type"][0]
    assert "Clip" in type_field.value
    preview_fields = [f for f in embed.fields if f.name == "Preview"]
    assert len(preview_fields) == 1


def test_news_embed_includes_source_and_url():
    post = {
        "id": 99,
        "caption": "GTA 6 sales hit $3.8bn in a day",
        "render_id": None, "angle": "news",
        "source": "BBC News", "posted_at": "Mon, 22 Nov 2026 10:00:00 GMT",
        "post_url": "https://www.bbc.com/news/example",
    }
    embed = build_review_embed(post)
    assert embed.title == "GTA 6 sales hit $3.8bn in a day"
    desc = embed.description or ""
    assert "BBC News" in desc
    assert "https://www.bbc.com/news/example" in desc
    type_field = [f for f in embed.fields if f.name == "Type"][0]
    assert "News" in type_field.value
    preview_fields = [f for f in embed.fields if f.name == "Preview"]
    assert preview_fields == []


def test_embed_title_truncated_at_256():
    long_caption = "A" * 400
    post = {"id": 1, "caption": long_caption, "render_id": None, "angle": "news", "source": "X"}
    embed = build_review_embed(post)
    assert len(embed.title) == 256


def test_alert_embed_marks_strike_and_halt():
    embed = build_alert_embed("strike", "takedown on post #7 — publishing halted")
    assert "STRIKE" in embed.title.upper()
    assert "takedown" in embed.description


def test_digest_counts_pending_published_and_revenue():
    text = build_digest({"pending": 3, "published": 5, "views": 12000, "revenue": 24.5})
    assert "3" in text and "5" in text and "12,000" in text and "24.50" in text
