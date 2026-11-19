# clipping_tools

Autonomous pipeline for clipping, posting, and managing GTA 6 content across
multiple platforms (TikTok, YouTube Shorts, Instagram Reels, X).

**Status:** planning — research complete, implementation plan in `docs/`.

## Concept

Free streaming-service APIs (Twitch Helix, Kick public API, YouTube Data API)
as content sources → local AI clipping on Apple Silicon (yt-dlp + whisper +
ffmpeg) → compliance/permission gates → multi-platform publishing adapters →
analytics feedback loop.

## Layout (planned)

```
clipping_tools/
├── docs/            # research, implementation plan, API notes
├── src/clipping_tools/
│   ├── sources/     # Twitch / Kick / YouTube ingest
│   ├── analysis/    # transcription, moment scoring
│   ├── render/      # 9:16 vertical rendering + captions
│   ├── compliance/  # rights, spoiler, policy gates
│   ├── publish/     # per-platform adapters + scheduler
│   └── analytics/   # metrics pull + feedback loop
├── tests/
└── data/            # SQLite state, clip artifacts (gitignored)
```

## Environment

- MacBook Air M2, 8 GB — local-first rendering (VideoToolbox HW encode)
- Python 3.11+ via `uv`, ffmpeg, yt-dlp
- $0 API budget: free tiers only

## Docs

- `docs/RESEARCH.md` — grounded research findings with citations
- `docs/PLAN.md` — granular implementation plan