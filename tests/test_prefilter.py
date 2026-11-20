from datetime import datetime, timedelta, timezone

from clipping_tools.models import ClipCandidate, Platform
from clipping_tools.prefilter import passes_gates, score

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def _clip(duration=25.0, language="en", views=1000, age_h=2.0):
    return ClipCandidate(source_platform=Platform.TWITCH, external_id="x", url="u",
                         duration=duration, language=language, view_count=views,
                         created_at=NOW - timedelta(hours=age_h))


def test_duration_gates():
    assert not passes_gates(_clip(duration=5.0))
    assert passes_gates(_clip(duration=25.0))
    assert not passes_gates(_clip(duration=61.0))


def test_language_gate():
    assert not passes_gates(_clip(language="de"))
    assert passes_gates(_clip(language="en"))


def test_velocity_beats_stale_views():
    fresh = score(_clip(views=5000, age_h=1.0), now=NOW)
    stale = score(_clip(views=50000, age_h=240.0), now=NOW)
    assert fresh > stale


def test_source_weight_boost():
    base = score(_clip(), now=NOW)
    boosted = score(_clip(), source_weight=1.0, now=NOW)
    assert abs(boosted - base - 0.2) < 1e-6