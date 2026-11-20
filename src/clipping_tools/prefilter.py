"""Prefilter gates + candidate scoring (plan P2.3)."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from .models import ClipCandidate


def passes_gates(clip: ClipCandidate, min_duration: float = 8.0,
                 max_duration: float = 60.0, languages: tuple[str, ...] = ("en",)) -> bool:
    if not (min_duration <= clip.duration <= max_duration):
        return False
    if languages and clip.language not in languages:
        return False
    return True


def score(clip: ClipCandidate, source_weight: float = 0.0,
          now: datetime | None = None) -> float:
    """0.5*views_norm + 0.3*velocity_norm + 0.2*source_weight (plan §7)."""
    now = now or datetime.now(timezone.utc)
    age_h = max((now - clip.created_at).total_seconds() / 3600.0, 1.0)
    velocity = clip.view_count / age_h
    velocity_norm = min(velocity / 10_000.0, 1.0)
    views_norm = min(math.log10(clip.view_count + 1) / 6.0, 1.0)
    return round(0.5 * views_norm + 0.3 * velocity_norm + 0.2 * source_weight, 4)