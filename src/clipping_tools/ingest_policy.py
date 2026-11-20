"""Source-rights gate for ingest: only campaign-licensed broadcasters qualify."""
from __future__ import annotations


def licensed_source_weight(broadcaster: str, licensed: set[str]) -> float:
    """Return 1.0 for a licensed broadcaster, 0.0 otherwise (fail closed)."""
    name = str(broadcaster).strip().lower().lstrip("@")
    return 1.0 if name in licensed else 0.0


def licensed_from_campaigns(campaigns: list[dict]) -> set[str]:
    """Extract the broadcaster handles named in the seeded campaign registry."""
    out: set[str] = set()
    for c in campaigns:
        if c.get("status") not in (None, "accepting"):
            continue
        for handle in c.get("broadcaster_handles", []):
            out.add(str(handle).strip().lower().lstrip("@"))
    return out
