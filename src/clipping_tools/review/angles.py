"""Angle tagging for clips/drafts: funny | hype | news, else None (human review)."""
from __future__ import annotations

# Priority order matches config/pipeline.yaml `angles: [funny, hype, news]`.
PRIORITY = ("funny", "hype", "news")
_KEYWORDS = {
    "funny": ["funny", "fail", "failed", "lmao", "lol", "caught", "creeping", "crying",
              "bruh", "whiff", "died", "clown", "oops", "troll", "meme", "😅", "😂", "💀"],
    "hype": ["insane", "crazy", "unbelievable", "4k", "kill", "streak", "clutch",
             "historic", "first", "world record", "unreal", "fire", "goated"],
    "news": ["rockstar", "release", "confirmed", "patch", "update", "leak", "trailer",
             "announce", "official", "news", "gta 6"],
}


def classify_angle(title: str = "", words: list[str] | None = None) -> str | None:
    """Return the highest-priority angle with a keyword hit, or None if unclear."""
    text = (title or "").lower()
    word_text = " ".join(words or []).lower()
    scores = {angle: 0 for angle in PRIORITY}
    for angle, kws in _KEYWORDS.items():
        for kw in kws:
            if kw.lower() in text:
                scores[angle] += 1
            if kw.lower() in word_text:
                scores[angle] += 1
    best = max(PRIORITY, key=lambda a: scores[a])
    return best if scores[best] > 0 else None
