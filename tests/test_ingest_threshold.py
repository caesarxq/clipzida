"""RED: ingest must drop clips whose score is below the configured threshold."""
import os
import tempfile

from clipping_tools.cli import _persist_candidates
from clipping_tools.models import ClipCandidate, Platform
from datetime import datetime, timezone


def test_persist_candidates_drops_low_score_and_keeps_high_score():
    clips = [
        ClipCandidate(source_platform=Platform.TWITCH, external_id="low", url="u1",
                      title="low", view_count=100, duration=20, language="en",
                      created_at=datetime.now(timezone.utc)),
        ClipCandidate(source_platform=Platform.TWITCH, external_id="high", url="u2",
                      title="high", view_count=50000, duration=20, language="en",
                      created_at=datetime.now(timezone.utc)),
    ]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "state.db")
        kept = _persist_candidates(path, clips, threshold=0.35)
        assert kept == 1
