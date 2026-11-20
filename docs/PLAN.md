# clipping_tools — Implementation Plan (v1)

**Date:** 2026-11-20 · **Owner:** Mohamed · **Executor:** chief-of-staff + coding agents
**Companion:** `docs/RESEARCH.md` (all factual claims cited there; bracketed ids below resolve to the same ledger)
**Method:** TDD (RED→GREEN→REFACTOR), Pydantic v2 typed contracts, SQLite state, declarative YAML stage config, provider ABCs.

---

## 0. Decision register — CONFIRMED by Mohamed 2026-11-20

| # | Decision | Confirmed value | Consequence |
|---|---|---|---|
| D1 | Content source | Campaign-licensed + permissioned streamer clips ONLY (no own gameplay — doesn't own the game, no time to play) | P9.4 own-gameplay track removed from roadmap |
| D2 | Platforms v1 | TikTok + YouTube Shorts + IG Reels + X | all four adapters in scope |
| D3 | Autonomy | Approval queue → graduate after clean-run criteria (P7.4) | review surface = **Hermes + Discord** (D8) |
| D4 | Goal | Campaign revenue first; audience as byproduct | per-view campaigns prioritized over pools |
| D5 | Hosting | **$30/month budget** → VPS hybrid (§13A): 24/7 pipeline on VPS, Mac = dev + review | Hetzner CPX31-class box recommended |
| D6 | Language/angle | English, **mixed angles** (funny/fail + hype edits + news/guides) | angle presets in scoring + caption writer (P3.4) |
| D7 | Volume | 6–12 posts/day at steady state — **gated by fresh-account warmup ramp (§5B)** | full volume ~week 3–4 |
| D8 | Review surface | **Hermes + Discord** (bot with approve/reject buttons, §13A) | P7.3/P7.5 updated |
| D9 | Identity | **One brand across platforms, multiple accounts** (per-platform mains + campaign-dedicated/sub-angle accounts under the brand) | accounts table + per-account token/quota isolation (§4, §5A) |
| D10 | Accounts | **ALL FRESH** — nothing exists yet | Account Factory runbook §5A is the critical path |

**Remaining decisions (small, answer in chat):**
1. **Brand name — NEEDS RE-CONFIRMATION.** Approved "Leonida Clips" is TAKEN on all 4 platforms (active GTA 6 clip squatters, incl. a TikTok "LeonidaClips" linked to @ViceCityHub); 9 alternatives also taken. **Recommendation: CLIPZIDA** (@clipzida) — coined "Clips + Leonida", verified AVAILABLE on YouTube/TikTok/IG/X + clipzida.com (2026-11-20, control-calibrated checks). Confirm to lock.
2. Brand email + phone for signups (you create the Gmail; OTPs stay on your device — secrets go to the vault, never chat).
3. Discord server: create one (or reuse existing) + invite me to set up the bot.
4. VPS provider approval: Hetzner (~$17.80/mo, card payment by you).

---

## 1. Objectives & success metrics

**Mission:** autonomous pipeline that turns live GTA 6 stream moments into compliant, captioned vertical clips and publishes them across 4 platforms, earning campaign bounties with zero policy strikes.

| Metric | Week 2 target | Week 6 target |
|---|---|---|
| Ingest→post latency (p50) | < 60 min | < 30 min |
| Approved posts/day | 3–5 | 8–12 |
| Campaign-approved views/week | 50k | 500k+ |
| Revenue/week | first $5–50 | $100–400 (pool-dependent) |
| Takedowns/strikes | 0 | 0 |
| Human touches per post | 1 approval tap | 0 (whitelisted sources) |

Pool campaigns have view-share minimums (400k–1M approved views) — v1 targets per-view campaigns for guaranteed revenue while pool clips accumulate.[72]

## 2. Architecture

```
                 ┌────────────────────────── scheduler (launchd) ─────────────────────────┐
                 │                                                                        │
 [Twitch Helix]──┤ INGEST → PREFILTER → DOWNLOAD → ANALYZE → SELECT → COMPLIANCE → RENDER │
 [Kick (v2)]─────│   │         │           │         │         │          │          │    │
 [YT Data API]───┘   ▼         ▼           ▼         ▼         ▼          ▼          ▼    │
                 clips_raw  score>τ    source.mp4  transcript moments  verdicts   variants│
                 (SQLite)   dedupe                 +energy   (LLM)    (4 gates)  (ffmpeg)│
                                                                                        │
                  ┌─────────────────────────────────────────────────────────────────────┘
                  ▼
             POST QUEUE ──► APPROVAL (CLI/dashboard) ──► PUBLISH ADAPTERS ──► platforms
                  │              │ graduation gate          │  YT / TikTok / IG / X
                  │              ▼                          ▼
                  │         audit_log                  posts table
                  └──────────────► ANALYTICS ◄───────────────┘
                                   metrics + campaign ledger → weekly report → scoring weights
```

**Stage contracts (Pydantic v2, explicit context passing — no hidden state):**

```python
ClipCandidate    # source refs, external_id, url, broadcaster, views, duration, created_at, score
AnalysisResult   # transcript segments (word timestamps), energy peaks, candidate moments
MomentSelection  # start/end, hook_title, hook_text, reason, confidence, spoiler_flags[]
ComplianceVerdict# rights: pass|fail, rockstar: pass|review|fail, campaign: pass|fail, platform: pass|fail, reasons[]
RenderSpec       # layout, style, start/end, caption tracks, loudnorm, per-platform variants
PostDraft        # render_id, campaign_id, platform, caption, hashtags, attribution, schedule_slot
PublishResult    # external_post_id, url, status, error, idempotency_key
MetricsSnapshot  # views/likes/comments/shares, approved_views, payout
```

Every stage reads/writes SQLite and appends to `audit_log`; any stage is restartable/idempotent. Pipeline stages and thresholds live in `config/pipeline.yaml` (declarative, editable without code changes).

## 3. Repo layout & stack

```
clipping_tools/
├── pyproject.toml            # uv, Python ≥3.11
├── config/
│   ├── pipeline.yaml         # stages, thresholds, cadences, autonomy mode
│   ├── campaigns.yaml        # seeded registry (§11) + rules
│   └── platforms.yaml        # per-platform caps, slots, accounts
├── src/clipping_tools/
│   ├── models.py             # stage contracts + SQLite row models
│   ├── db.py                 # schema, migrations, WAL, quota counters
│   ├── sources/              # base.py (SourceProvider ABC), twitch.py, kick.py, youtube.py
│   ├── analysis/             # transcribe.py (mlx-whisper/whisper.cpp), energy.py, select.py (LLM)
│   ├── compliance/           # rights.py, rockstar.py, campaign_rules.py, platform_rules.py
│   ├── render/               # layout.py, captions.py, encode.py, variants.py
│   ├── publish/              # base.py (PublishProvider ABC), youtube.py, tiktok.py, instagram.py, x.py
│   ├── scheduler/            # queue.py, rate_limiter.py, tokens.py, slots.py
│   ├── analytics/            # metrics.py, ledger.py, report.py, feedback.py
│   ├── review/               # cli.py (Typer), dashboard.py (FastAPI, localhost)
│   └── llm/                  # provider ABC + OpenRouter adapter (free models dev / paid prod)
├── tests/                    # mirrors src; fixtures/ = recorded API responses
├── data/                     # state.db, source/, renders/, exports/ (gitignored)
└── docs/
```

Stack: `httpx` (async), `pydantic v2`, `typer`, `uv`, `pytest`, `yt-dlp`, `ffmpeg` (VideoToolbox), `mlx-whisper` (primary) / `whisper.cpp` (fallback), `ass` captions via ffmpeg subtitles filter. LLM via OpenRouter with provider ABC (Jev/Hermes pluggable later for gating decisions — control plane vs generative plane separation).

## 4. Data model (SQLite, WAL mode)

```sql
CREATE TABLE sources(id INTEGER PRIMARY KEY, platform TEXT, external_id TEXT, name TEXT,
  permission_id INTEGER, active INTEGER DEFAULT 1, UNIQUE(platform, external_id));
CREATE TABLE permissions(id INTEGER PRIMARY KEY, source_id INTEGER,
  kind TEXT CHECK(kind IN ('campaign','written','own')), campaign_id INTEGER,
  evidence_url TEXT, granted_at TEXT, expires_at TEXT, notes TEXT);
CREATE TABLE campaigns(id INTEGER PRIMARY KEY, marketplace TEXT, external_id TEXT, name TEXT,
  subject TEXT, pay_model TEXT CHECK(pay_model IN ('per_view','pool')), rate_per_1k REAL,
  pool_total REAL, min_views INTEGER, min_payout REAL, max_payout REAL, budget_remaining REAL,
  platforms TEXT, required_tokens TEXT, rules_json TEXT, status TEXT, last_checked TEXT);
CREATE TABLE clips_raw(id INTEGER PRIMARY KEY, source_id INTEGER, external_id TEXT UNIQUE,
  url TEXT, title TEXT, broadcaster TEXT, creator TEXT, view_count INTEGER, duration REAL,
  language TEXT, created_at TEXT, fetched_at TEXT, thumbnail_url TEXT, video_id TEXT,
  vod_offset INTEGER, status TEXT);  -- new→scored→downloaded→analyzed→selected→rendered→posted|rejected
CREATE TABLE analysis(clip_id INTEGER PRIMARY KEY, transcript_json TEXT, energy_json TEXT,
  moments_json TEXT, spoiler_risk REAL, score REAL, model TEXT, analyzed_at TEXT);
CREATE TABLE renders(id INTEGER PRIMARY KEY, clip_id INTEGER, variant TEXT, path TEXT,
  spec_json TEXT, checksum TEXT, rendered_at TEXT, UNIQUE(clip_id, variant));
CREATE TABLE posts(id INTEGER PRIMARY KEY, render_id INTEGER, campaign_id INTEGER, platform TEXT,
  account TEXT, caption TEXT, hashtags TEXT, status TEXT,  -- draft→queued→approved→publishing→published|failed|dead
  scheduled_at TEXT, published_at TEXT, external_post_id TEXT, url TEXT,
  idempotency_key TEXT UNIQUE, error TEXT);
CREATE TABLE approvals(id INTEGER PRIMARY KEY, post_id INTEGER, decision TEXT, reviewer TEXT,
  edits_json TEXT, decided_at TEXT);
CREATE TABLE metrics(post_id INTEGER, fetched_at TEXT, views INTEGER, likes INTEGER,
  comments INTEGER, shares INTEGER, approved_views INTEGER, payout REAL,
  PRIMARY KEY(post_id, fetched_at));
CREATE TABLE tokens(service TEXT PRIMARY KEY, access_token TEXT, refresh_token TEXT,
  expires_at TEXT, scopes TEXT);
CREATE TABLE accounts(id INTEGER PRIMARY KEY, platform TEXT, handle TEXT, brand_role TEXT,
  -- main | campaign_dedicated | angle_sub
  campaign_id INTEGER, created_at TEXT, warmup_stage INTEGER, daily_cap INTEGER,
  token_ref TEXT, status TEXT, UNIQUE(platform, handle));
CREATE TABLE quota_usage(service TEXT, day TEXT, units INTEGER, PRIMARY KEY(service, day));
CREATE TABLE audit_log(id INTEGER PRIMARY KEY, ts TEXT, stage TEXT, entity TEXT,
  entity_id INTEGER, event TEXT, detail_json TEXT);
```

## 5. Phase 0 — Environment & accounts (Day 1–2)

**All accounts are FRESH (D10).** Execute P0.5–P0.10 in the dependency order of the Account Factory runbook (§5A); Mohamed performs identity/OTP/payment/mobile steps, the agent prepares and drives everything else. Warmup caps (§5B) apply from first post.

| Task | Description | Est | Acceptance |
|---|---|---|---|
| P0.1 | `uv init`, Python 3.11 pin, deps (httpx, pydantic, typer, pytest, yt-dlp, mlx-whisper), ruff | 1h | `uv run pytest` green on skeleton; `uv run clipping-tools doctor` passes |
| P0.2 | Install yt-dlp via uv tool; verify `yt-dlp --version`; ffmpeg HW encoder probe (`ffmpeg -encoders | grep videotoolbox`) | 0.5h | doctor reports both OK |
| P0.3 | `db.py` schema + migrations + WAL; quota counters; audit_log helpers | 2h | schema tests green; concurrent-write test passes |
| P0.4 | Config loader (YAML→Pydantic), `.env` secret handling (never committed), `doctor` CLI | 1.5h | config validation tests; missing-secret errors are actionable |
| P0.5 | **Manual (Mohamed):** register Twitch app at dev.twitch.tv/console (confidential, client-credentials) → store client_id/secret | 15m | app token fetch succeeds (P2.1 test) |
| P0.6 | **Manual:** Google Cloud project → enable YouTube Data API v3 → OAuth consent (External, testing) → Desktop OAuth client → consent flow for `youtube.upload youtube.readonly` → refresh token | 30m | token stored; `channels.list(mine)` returns channel |
| P0.7 | **Manual:** Meta app (Business type) + Facebook Login for Business; convert IG to Business, link FB Page; grant `instagram_basic instagram_content_publish pages_read_engagement`; note App Review needed only for Advanced Access | 45m | `GET /me/accounts` shows Page + IG id |
| P0.8 | **Manual:** TikTok developer app → Content Posting API → enable Direct Post config; scopes `user.info.basic video.upload` (+`video.publish` post-audit); **submit audit immediately** (long lead time: demo video + use-case writeup) | 1h | sandbox OAuth works; audit submitted (ticket id logged) |
| P0.9 | **Manual:** X developer free-tier app → OAuth2 PKCE (`tweet.write media.write users.read offline.access`) | 20m | refresh token stored; test post to self succeeds |
| P0.10 | **Manual:** Content Rewards creator account; join 2–3 per-view campaigns (TOMO, Ruckus, Lauren Hamden if dedicated account); export campaign rule pages | 30m | campaigns visible in dashboard; rules saved to `campaigns.yaml` |
| P0.11 | launchd plists + `caffeinate` wrapper for ingest/render/publish loops; log rotation | 1h | loops survive reboot; sleep gaps logged |

## 5A. Account Factory runbook (fresh accounts, one brand, multiple accounts)

**Brand kit first** (blocks every signup):
| Task | Description | Owner |
|---|---|---|
| AF.1 | Pick brand name (recommend **Leonida Clips**); availability-check handles on TikTok/IG/X/YouTube | Mohamed picks, agent checks |
| AF.2 | Generate logo + banners + bio template (consistent across platforms); store in `assets/brand/` | agent |
| AF.3 | Create brand Gmail (e.g., leonidaclips@gmail.com); all signups use it (+aliases per platform); passwords → vault, never chat | Mohamed (OTP) |
| AF.4 | Account matrix naming: `<brand>` mains per platform; campaign-dedicated accounts `<brand>.<streamer>` (Lauren Hamden requires one[72]); angle subs later | agent config |

**Signup dependency order** (agent drives browser to the OTP/credential wall; Mohamed completes identity steps):
1. **Discord** server + bot application (review surface, §13A) — no dependencies.
2. **Google**: Gmail → YouTube brand channel → Cloud project → YouTube Data API v3 → OAuth consent **External, PUBLISHED** (⚠ testing-mode refresh tokens expire in 7 days — publish the consent screen; unverified is fine for own-account use, and the Nov 2 change removed the upload lock[61]) → Desktop OAuth client → consent flow → refresh token to vault.
3. **Twitch**: dev.twitch.tv/console app registration (confidential, client-credentials) — needs only a Twitch account (fresh signup, email verify).
4. **Meta**: fresh FB profile (⚠ real-name policy — use Mohamed's real identity for the admin profile; brand lives on the Page) → warm up 2–3 days → create Brand Page → fresh IG account (mobile signup, Mohamed) → convert to Business, link Page → Meta developer app (Business) → Facebook Login for Business → `instagram_basic instagram_content_publish pages_read_engagement` → long-lived tokens. App Review only needed for Advanced Access; own accounts work on Standard.[9][10]
5. **TikTok**: fresh account (mobile signup, Mohamed) → complete profile → **3–5 days niche consumption before first post (§5B)** → developers.tiktok.com app → Content Posting API + Direct Post config → scopes `user.info.basic video.upload` → **submit audit immediately** (demo video + use-case writeup; long lead time).[6][8]
6. **X**: fresh account (web signup, OTP) → complete profile → developer.x.com free-tier app → OAuth2 PKCE (`tweet.write media.write users.read offline.access`).[12]
7. **Content Rewards**: creator signup with brand email → join per-view campaigns once posting accounts exist (Ruckus requires a GTA 6-posting account).[72]
8. **VPS**: Hetzner account (Mohamed, card) → agent provisions CPX31-class box via cloud API/SSH (§13A).

**Secrets policy:** every credential lands in the Hermes vault / `.env` (gitignored); nothing sensitive in chat or commits.

## 5B. Fresh-account warmup & trust ramp (all accounts are new — this gates volume)

New accounts get algorithmic trust constraints; rushed posting is the top shadowban trigger. Operator guidance (not published caps — treat as heuristics and watch account-status dashboards):[95][92]

| Platform | Days 1–3 | First posting week | Week 2 | Week 3+ (steady) |
|---|---|---|---|---|
| TikTok | profile complete + watch/engage GTA 6 niche only, no posts | **1 video/day, 2 max**[90] | 2/day | 3/day per account |
| IG Reels | same consumption warmup | **1 Reel/day for first 4–7 posting days**[91] | 1–2/day if reach/completion holds | 2–3/day |
| X | profile + light manual engagement | 1–2 posts/day (new accounts <30d under heightened scrutiny[93]) | 2–3/day | 3–5/day (500/mo cap[12]) |
| YouTube | channel art/about complete | 2–3 uploads/day | 3–4/day | 5/day (quota cap[11]) |

Rules: one account per device/IP during warmup; no engagement pods; consistent niche signals; check TikTok notifications / IG Account Status before assuming shadowban.[92][95]
**Enforcement:** `accounts.daily_cap` + `warmup_stage` (§4); ramp scheduler raises caps by account age; P7.4 graduation additionally requires account age ≥14 days.
**Consequence:** week 1–2 total volume ≈3–6 posts/day; steady 8–12/day from week 3–4. First campaign revenue still week 2 — per-view campaigns pay on any approved view, no follower minimum.[72]

## 6. Phase 1 — Tracer bullet (Day 1–2)

One vertical slice before any engine work: **1 Twitch clip → mp4 → transcript → moment → 1080×1920 captioned render + metadata sidecar.** Proves the core loop and surfaces integration bugs early.

| Task | Description | Est | Acceptance |
|---|---|---|---|
| P1.1 | `sources/twitch.py`: app-token fetch + Get Clips by game_id (hardcode nothing: resolve GTA VI id via Search Categories at runtime)[4] | 2h | live fetch returns ≥20 GTA VI clips; token cached with expiry |
| P1.2 | `download.py`: yt-dlp wrapper (clip URL → `data/source/<id>.mp4`, ≤720p for speed), failure taxonomy (sub-only/dead/geo) | 1.5h | 3 real clips downloaded; failures classified, not crashed |
| P1.3 | `analysis/transcribe.py`: ffmpeg 16kHz mono WAV → mlx-whisper `small` word timestamps; whisper.cpp fallback; CPU int8 last resort[35][36] | 3h | 60s clip transcribes < 90s on M2; JSON contract test |
| P1.4 | `analysis/energy.py`: RMS windows (0.5s hop) → top peaks; merge with transcript into `analysis.json` (Gaming-Clipper pattern)[19] | 1.5h | peaks align with audible hype on test clip |
| P1.5 | `render/encode.py`: gaming-split layout + ASS captions + loudnorm −14 LUFS + VideoToolbox; metadata sidecar[19] | 3h | output plays vertical, captions in safe zone, loudness measured −14±1 LUFS |
| P1.6 | End-to-end tracer test (local fixture mp4, mocked APIs) | 1h | CI green without network |

## 7. Phase 2 — Ingest engine (Day 2–4)

| Task | Description | Est | Acceptance |
|---|---|---|---|
| P2.1 | Token daemon: Twitch app token (~60d), Kick (60d), TikTok (24h access/365d refresh), Meta (60d long-lived), Google/X refresh — refresh 1h before expiry, alert on failure[15][71] | 3h | expiry simulation tests; no manual re-auth for 30d |
| P2.2 | Twitch poller: Get Clips `game_id` + `started_at/ended_at` windows, cursor pagination, `first=100`; 10-min cadence; 100 req/min endpoint cap + 800 pts/min global budget guard[3][5] | 3h | dedupe test: re-poll inserts 0; rate-guard test throttles |
| P2.3 | Prefilter + scoring: duration 8–60s; language filter (D6); `score = 0.5·log10(views+1)/6 + 0.3·velocity_norm + 0.2·source_weight` where velocity = views/hour-since-created; campaign-source boost; threshold τ in YAML | 2h | unit tests on synthetic clip set; τ tunable without code |
| P2.4 | Dedupe: clip external_id unique; cross-platform moment dedupe via transcript shingle similarity (avoid same joke twice); per-campaign re-cut requirement enforced at draft time[72] | 2h | near-duplicate fixture pair collapses to 1 |
| P2.5 | Permissions registry: every source maps to campaign or written permission; **no permission → quarantine, never render** | 2h | unpermissioned clip cannot advance (test) |
| P2.6 | Campaign registry sync: seed from §11; daily re-check of budgets/status/rules (marketplace pages; manual export fallback); alert on budget <20% or campaign closed | 3h | stale campaign auto-deactivates; alert fires in test |
| P2.7 | YouTube source adapter (campaign-licensed creators only, e.g., TOMO): search.list budgeted ≤10 searches/day; yt-dlp download[11][72] | 2h | quota counter blocks search #11 |
| P2.8 | Kick v2 adapter stub: official public API livestream discovery; clips via best-effort website endpoint behind feature flag, graceful skip[15][16] | 3h | flag off by default; on: discovers GTA 6 lives |

## 8. Phase 3 — Analysis & moment selection (Day 4–6)

| Task | Description | Est | Acceptance |
|---|---|---|---|
| P3.1 | LLM provider ABC + OpenRouter adapter; query `/v1/models` at startup (slugs volatile); `:free` models for dev/CI, cheap paid for prod | 2h | provider swap test; model-list cache test |
| P3.2 | Moment selector: input = transcript + energy peaks + clip metadata; output = typed `MomentSelection[]` (18–45s, self-contained, hook in first 2s, 3–5-word ALL-CAPS hook title); speech-start snap; JSON-schema validation with 1 repair retry[19] | 4h | schema tests; golden-fixture selection review by Mohamed |
| P3.3 | Spoiler/scene classifier: labels {none, mild, story_reveal, ending, isolated_cutscene, ingame_entertainment, cheat_glitch, leak}; cutscene-heuristic = high plot-dialogue density + low gameplay audio variance; ambiguous → human review queue (policy says email copyright@take2games.com when unsure)[14] | 3h | labeled fixture set ≥90% agreement; ending/leak always hard-fail |
| P3.4 | Hook/caption writer with **mixed-angle presets** (D6): `funny` (punchline-first), `hype` (energy-peak-first, fast cuts), `news/guide` (context card + voiceover-style captions); angle tag stored per moment; per-platform caption + hashtags + required campaign tokens (streamer name, #LACY etc.) + attribution line (streamer + clip URL) | 2h | campaign-token compliance test per campaign; one fixture per angle |
| P3.5 | Scoring feedback hook: store selection features for later weight tuning (P8.4) | 1h | features persisted |

## 9. Phase 4 — Compliance gates (Day 5–6, hard gates before render)

Gate order: **rights → Rockstar → campaign rules → platform**. Any fail = reject with reason; any `review` = approval queue regardless of autonomy mode.

| Task | Description | Est | Acceptance |
|---|---|---|---|
| P4.1 | Rights gate: active permission for source; campaign active + budget remaining; expiry check | 1.5h | expired permission blocks (test) |
| P4.2 | Rockstar gate: classifier verdicts → ending/isolated_cutscene/ingame_entertainment/cheat_glitch/leak = FAIL; story_reveal/mild = REVIEW; blocklist terms (ending names, "final mission", glitch/exploit phrases) maintained in YAML[14][23][24] | 2h | gate matrix tests; blocklist editable without code |
| P4.3 | Campaign-rules engine: per-campaign `rules_json` — platform allowlist, required caption tokens, subject-focus rule, min-view bars, per-clip caps, **no-AI-generated-video rule (Clix)** → our renders are real footage with AI-assisted editing; store rule text verbatim; flag interpretation for human sign-off once per campaign[72] | 3h | each seeded campaign has a passing + failing fixture |
| P4.4 | Platform gate: duration/aspect/size caps per platform (§12); profanity beeper option for advertiser-friendliness; music = campaign-provided audio only (Tokyo Girl)[72][76] | 2h | over-length X variant rejected pre-upload |
| P4.5 | Gate audit: every verdict + reason into audit_log; weekly compliance report | 1h | report renders from fixtures |

## 10. Phase 5 — Rendering (Day 6–8)

| Task | Description | Est | Acceptance |
|---|---|---|---|
| P5.1 | Layouts: `gaming-split` default (blurred 9:16 bg + centered 16:9 gameplay, HUD intact); `--cam-box x,y,w,h` facecam option; `center-crop` for IRL[19] | 3h | visual check on 3 fixture clips |
| P5.2 | Captions: word-level ASS, active-word highlight, presets (classic/neon/fire/clean), safe-zone MarginV=560; hook-title overlay first 2s[19] | 2.5h | captions readable at 360px preview; no safe-zone overlap |
| P5.3 | Encode spec: 1080×1920, H.264 high, yuv420p, 30fps, closed GOP, `+faststart`, moov front; `h264_videotoolbox` ~6Mbps VBR (≤25Mbps IG cap), libx264 veryfast CRF20 fallback; AAC 128k 48kHz; loudnorm I=−14:TP=−1.5:LRA=11[10][19] | 2h | ffprobe contract test on every render; IG spec check |
| P5.4 | Platform variants: TikTok/IG/Shorts ≤60s campaign cut; Shorts ≤3min hard cap; X ≤ account cap (verify at setup, §12); per-variant caption burn-in | 2h | variant matrix tests |
| P5.5 | Render queue: single concurrent job (8GB RAM), checksum dedupe, cleanup of source WAVs after render[19] | 1.5h | memory stays <6GB under load test |
| P5.6 | Metadata sidecar → PostDraft auto-creation (caption, hashtags, attribution, campaign tags, slot) | 1h | draft appears in review queue |

## 11. Phase 6 — Publishing adapters (Day 7–11)

Build order: **YouTube → X → Instagram → TikTok** (easiest autonomy first; TikTok audit runs in parallel since P0.8).

| Task | Description | Est | Acceptance |
|---|---|---|---|
| P6.1 | `PublishProvider` ABC: `publish(draft) -> PublishResult`, `health()`, `quota_left()`; idempotency keys; retry/backoff; dead-letter after 3 fails | 2h | contract tests across all adapters |
| P6.2 | **YouTube:** resumable videos.insert; privacyStatus=public (allowed unverified since Nov 2, 2026[61]); categoryId 20; #Shorts; madeForKids=false; quota guard 1600/upload; thumbnail via shortsAspectRatio[11][61][62] | 4h | real public Shorts upload from test channel; quota counter accurate |
| P6.3 | **X:** chunked media INIT/APPEND/FINALIZE (tweet_video) → POST /2/tweets with media_ids; preflight duration/size vs account caps (verify at setup[64][66]); 500 posts/month guard; separate upload-vs-attach error handling[12][65] | 3h | real video post; month-cap simulation blocks #501 |
| P6.4 | **Instagram:** container (media_type=REELS) via **resumable upload** (rupload.facebook.com — no public hosting needed[9]); poll status_code 1/min ≤5min; media_publish; content_publishing_limit precheck (100/24h[9]); cover_url/thumb_offset; EXPIRED/ERROR handling[9][10] | 4h | real Reel published to Business account; limit precheck test |
| P6.5 | **TikTok path A (v1):** upload-inbox push_by_file (video.upload) → draft in creator inbox → notification "tap confirm in TikTok"; track confirm via video.list polling[71] | 3h | draft lands in inbox; status tracked |
| P6.6 | **TikTok path B (post-audit):** Direct Post creator_info/query → /v2/post/publish/video/init/ → status poll; privacy_level from allowlist; 6 req/min token guard; feature-flagged until audit clears[6][52] | 3h | sandbox direct post; flag test |
| P6.7 | Facebook Reels (optional): upload session → /{page}/video_reels publish; shares Meta token[67][69] | 2h | real Page Reel (flag off by default) |
| P6.8 | Attribution & campaign submission: caption includes required tokens; log campaign submission ids; **never submit same final clip to two campaigns** — re-cut variant per campaign[72] | 2h | double-submission blocked (test) |

## 12. Quota & rate-limit budgets (enforced in code, not honor system)

| Service | Hard limit | Planned usage | Guard |
|---|---|---|---|
| YouTube Data API | 10,000 units/day[11] | 5 uploads (8,000) + 10 searches (1,000) + ~50 stats reads (50) + buffer 950 | quota_usage table; uploads pause at 8,400 spent; 2nd GCP project for ingest if D7 raises volume |
| Twitch Helix | 800 pts/min; Clips 100 req/min[3][5] | 1 clips poll/10min + token calls | token-bucket; 429 backoff |
| TikTok | 6 req/min per user token[52] | ≤10 posts/day + status polls | per-token bucket |
| Instagram | 100 API posts/24h[9] | ≤8/day | content_publishing_limit precheck |
| X | 500 posts/month; 100 reads/month[12][58] | 3–5 posts/day (~120/mo); reads ≤20/mo (weekly metrics only) | month counter; read rationing |
| OpenRouter | free-tier RPM varies by model | ≤20 scoring calls/hr dev | model-list cache; backoff |

## 13. Phase 7 — Scheduler, approval UX, graduation (Day 8–12)

| Task | Description | Est | Acceptance |
|---|---|---|---|
| P7.1 | Post queue: SQLite-backed, per-platform token buckets, posting slots (launch wave: ASAP; steady: 12:00–23:00 EAT overlap with US evening), jitter, idempotent resume | 3h | crash-restart test posts nothing twice |
| P7.2 | Review CLI: `clipping-tools review` — list pending (score, campaign, gate verdicts), preview path, approve/reject/edit-caption; batch approve | 2h | full approve→publish flow from terminal |
| P7.3 | **Discord review bot** (primary, D8): #clip-review embeds with mp4 preview + Approve/Reject/Edit buttons → approvals table (§13A); local FastAPI dashboard kept as fallback | 4h | approve from Discord releases the post (test) |
| P7.4 | **Graduation policy:** after ≥14 days AND ≥50 approved posts AND 0 strikes/takedowns AND ≥90% approvals unchanged → `autonomy: auto` for whitelisted campaign sources only; new sources stay queued; any strike → instant revert to full queue | 2h | policy simulation tests; kill-switch CLI |
| P7.5 | Notifications: Discord #alerts (failures, token expiry, budget <20%, strikes → auto-halt) + Hermes cron digest (pending count, revenue, campaign runway) | 1.5h | digest delivered to both surfaces |
| P7.6 | Kill switch: `clipping-tools halt` pauses all publishing; `resume` requires confirm | 0.5h | halt blocks queue (test) |

## 13A. Discord review bot + VPS topology ($30/mo confirmed)

**Discord bot** (discord.py, free; runs on VPS):
- `#clip-review`: embed per pending post — hook title, streamer, campaign, angle, gate badges, score; **mp4 attached** (Discord 25MB limit; our 1080×1920 30–45s renders ≈5–15MB fit); buttons **Approve / Reject / Edit-caption** → writes `approvals` → queue releases. Edit opens a modal.
- `#alerts`: adapter failures, token expiry warnings, campaign budget <20%, any takedown/strike → auto-halt + @Mohamed.
- `#daily`: morning digest (pending, published yesterday, views, revenue estimate) mirrored from Hermes cron.
- Bot token in vault; bot needs no public inbound port (gateway WebSocket) — works behind NAT.

**VPS topology** (D5 = $30/mo):
- Recommended: **Hetzner CPX31** — 4 vCPU AMD / 8GB RAM / 160GB NVMe, ~$17.80/mo.[87] Runs the ENTIRE pipeline 24/7: ingest, whisper-small (CPU int8), libx264 veryfast renders, scheduler, Discord bot, publishing. 160GB holds weeks of artifacts; cleanup job keeps <60%.
- Budget alternative: CX32 (~$8.20/mo, 4GB[87][89]) with renders offloaded to the Mac — rejected as default: Mac sleep breaks autonomy; CPX31 keeps the loop closed. Verify live pricing at signup.[88]
- Mac = dev machine, dashboard fallback, optional render offload during marathons.
- Provisioning: cloud-init + SSH key from vault; systemd units per worker; SQLite on the VPS (single writer); rsync artifacts to Mac on demand.
- Budget allocation: VPS $17.80 + OpenRouter scoring ~$8 + brand domain ~$1.20 + buffer ~$3 = **$30**.

## 14. Phase 8 — Analytics, campaign ledger, feedback (Day 11–14)

| Task | Description | Est | Acceptance |
|---|---|---|---|
| P8.1 | Metrics pullers: YouTube videos.list (1 unit/video, daily); IG insights; TikTok video.list; X public_metrics **weekly, rationed** (100 reads/mo)[11][12] | 3h | quota-aware scheduling tests |
| P8.2 | Campaign ledger: approved views + payouts per clip per campaign (campaign dashboard is source of truth; manual CSV import v1, scrape/API v2); pool-share estimator (your views / total approved views × pool)[72] | 3h | ledger reconciles with a manual export |
| P8.3 | Weekly report: revenue, views/clip, $/render-hour, best streamers/hooks/slots, strikes, campaign budget runway → markdown + Hermes delivery | 2h | report generates from fixtures |
| P8.4 | Feedback loop: tune prefilter weights + hook-style priors from per-source/per-hook performance; A/B hook styles on same moment (different cuts, campaign-compliant) | 3h | weights versioned in YAML; rollback test |
| P8.5 | Takedown monitor: post-publish status checks (YT privacy/status, IG media status, TikTok video.list); any removal → strike event → autonomy revert + source review | 2h | simulated removal triggers revert |

## 15. Phase 9 — Hardening & v2 roadmap (Week 3+)

- P9.1 Self-healing: health checks per adapter, circuit breakers, auto-recovery (Agent OS resilience patterns), dead-letter replay CLI.
- P9.2 **Twitch live capture:** EventSub WebSocket (stream.online/channel.update for whitelisted streamers) + chat-velocity spike detection → Create Clip (clips:edit user token, 90s window, async poll ≤15s) → same pipeline. Cuts ingest latency from ~10min to ~1min.[4][81]
- P9.3 Kick full source (official clips API if issue #424 ships; else website-endpoint adapter with ToS review).[16]
- P9.4 Own-gameplay track (if D1/Q2): PS5/Xbox capture-card or Remote Play recording ingest → `kind='own'` permission → no campaign needed; commentary layer for YPP transformation.[76]
- P9.5 Brand track: evergreen guides/news edits with original commentary → YPP application at thresholds; accept updated YPP terms before Jan 31, 2027.[28][44]
- P9.6 VPS migration option (D5): ingest/scheduler/posting on $6 VPS; Mac renders on demand; artifact sync via rsync/R2.
- P9.7 Multi-account fan pages (campaigns requiring dedicated accounts, e.g., Lauren Hamden) with per-account token isolation.[72]

## 16. Campaign registry — LIVE status 2026-11-20 (machine-readable: `config/campaigns.yaml`)

| Campaign | Model | Pay (live) | Budget left | Platforms | Status | Notes |
|---|---|---|---|---|---|---|
| Ruckus / Dasgasd3m | per-view | **$2.00/1k**, $20–150/clip | **$805** | TikTok, YTS | accepting | rate DOUBLED since Nov 18; GTA 6-specific account required |
| Lauren Hamden (Reach) | per-view | $1.50/1k, $15–250/clip | **$4,332** | TikTok, IG | accepting | **dedicated account**; rules: reachclipping.com/Sisters |
| YourRAGE pool (Reach) | pool | $5,000 | pool | all 4 | accepting | **0 clippers so far** — early-mover advantage |
| Kai Cenat pool (C&S) | pool | $10,000 | pool | all 4 | accepting | 96 clippers; clip needs ≥1k views |
| LACY pool (Reach) | pool | $12,500 | pool | all 4 | accepting | 427 clippers — crowded; caption name + #LACY |
| Clix pool (Reach) | pool | $5,000 | pool | all 4 | accepting | 340 clippers; #Clix; **no AI-generated videos** |
| TOMO (Clipping Nation) | per-view | $1.50/1k | **$0** | — | **paused/depleted** | died <48h after launch — validates daily budget sync (P2.6) |
| Tokyo Girl (Placements) | per-view | $0.70/1k | unverified | TikTok, IG | re-check | music promo ("Tokyo Girl" by Passive) |

Live source: individual contentrewards.com campaign pages, fetched 2026-11-20; launch-week snapshot context.[72][74]
Global rules: no same-clip double-submission; re-cut per campaign; budgets deplete; pools pay at marathon end; Rockstar policy applies on top.[72][14]
**Join order:** Ruckus (best rate) → Lauren Hamden (deepest budget, needs dedicated account) → YourRAGE pool (zero competition). Pools are secondary until per-view revenue flows.

## 17. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Rockstar takedown (spoiler/cutscene/entertainment) | Med | High | P4.2 hard gates; REVIEW queue for ambiguity; fast compliance on notice; email copyright@take2games.com for borderline scenes[14] |
| R2 | Streamer DMCA / no permission | Low (campaign path) | High | rights gate P4.1; only campaign/written sources; attribution always |
| R3 | TikTok audit delay/rejection | Med | Med | inbox path A works day one (one tap); audit submitted P0.8; YT/X/IG carry volume meanwhile[71] |
| R4 | YouTube quota exhaustion | Med | Med | §12 guards; 2nd GCP project split; uploads prioritized over searches |
| R5 | YPP reused-content rejection (brand track) | High | Med | campaign revenue independent of YPP; transformative commentary layer before applying[76][77] |
| R6 | Account ban (spam pattern) | Low | High | rate guards, dedupe, jitter, per-platform caps, graduation policy, kill switch |
| R7 | 8GB RAM / fanless throttle | Med | Low | single render job, whisper small, VideoToolbox, queue backpressure |
| R8 | Mac sleep misses campaign windows | Med | Med | caffeinate + launchd during marathons; VPS option P9.6 |
| R9 | Campaign budget depleted / pool bar unreachable | High | Med | daily budget sync P2.6; per-view campaigns first; pool estimator P8.2; diversify ≥3 campaigns |
| R10 | X free-tier read starvation | Certain | Low | weekly rationed reads; campaign dashboards as truth |
| R11 | Music copyright strike | Low | High | campaign-provided audio only; no trending-audio scraping |
| R12 | Policy/API drift (all platforms move fast) | Med | Med | weekly policy re-check job; revision-history watch (YT changed twice in Nov 2026[61]); feature flags |
| R13 | Same clip double-submitted → campaign ban | Low | Med | P6.8 hard block + re-cut variants |

## 18. Cost table ($30/mo ceiling — confirmed)

| Item | Cost |
|---|---|
| Hetzner CPX31 VPS (4 vCPU/8GB/160GB), 24/7 pipeline[87] | ~$17.80/mo |
| OpenRouter paid scoring (free models for dev/CI) | ~$5–8/mo |
| Brand domain (.com, link-in-bio) | ~$1.20/mo amortized |
| Twitch / Kick / YouTube / IG / X / TikTok APIs, Discord bot | $0 |
| Buffer | ~$3/mo |
| **Total** | **≤$30/mo** |

## 19. Test plan (TDD throughout)

- **Unit:** scoring formula, dedupe shingles, gate matrices, quota guards, token refresh, caption-token compliance, variant specs.
- **Contract:** every external API response parsed from recorded fixtures (no live calls in CI); LLM outputs schema-validated with repair-retry; ffprobe assertions on every render (resolution, codec, GOP, faststart, loudness).
- **Integration (sandbox accounts):** YT unlisted→public test upload; X test post; IG Reel to Business test account; TikTok inbox draft. Each adapter has a `--dry-run` mode.
- **E2E tracer:** fixture mp4 → full pipeline → 4 platform drafts → mocked publish → metrics → report; runs in CI.
- **Chaos:** token expiry mid-publish, 429 storms, crash-restart idempotency, sleep/wake, removal-event revert.
- Rule: every task lands RED→GREEN→REFACTOR; no task closes without its acceptance test green.

## 20. Timeline & milestones

| Milestone | When | Definition |
|---|---|---|
| M0: accounts + env ready | Day 1 | P0 complete; doctor green; TikTok audit submitted |
| M1: first captioned clip | Day 2 | tracer bullet renders a real GTA 6 moment |
| M2: first public post (YT Shorts) | Day 4–5 | ingest→post autonomous except approval tap |
| M3: 4-platform publishing | Day 10–11 | YT + X + IG live; TikTok inbox path live; **volumes under warmup caps (§5B)** |
| M4: first campaign revenue | Week 2 | ≥1 approved-view payout recorded in ledger |
| M5: graduation review | Week 3–4 | P7.4 criteria + account age ≥14d; auto-post for whitelisted sources; warmup ramp completes |
| M6: feedback loop live | Week 4 | weekly report + weight tuning + pool estimator |

Critical path: **P0.8 TikTok audit (external lead time)** and **P0.6/P0.7 account setup (manual)** — start both Day 1. Everything else is agent-executable.

## 21. Immediate next actions

1. **Mohamed (≈30 min spread over day 1–2):** pick brand name (recommend Leonida Clips); create brand Gmail; create Discord server; card-payment for Hetzner when provisioned. Mobile signups (IG/TikTok) + OTPs as we hit them (§5A).
2. **Agent, today:** tracer bullet (done this run — real GTA 6 clip → captioned 1080×1920 render); handle availability checks once name picked; logo/banner generation; drive desktop signups to the OTP wall.
3. **Agent, next:** P2 ingest engine as soon as the Twitch app exists; seed live campaign registry (P2.6); VPS provisioning + Discord bot skeleton in parallel.

## Sources

[3] https://dev.twitch.tv/docs/api/reference/clips — Twitch Helix API reference: Clips
[4] https://dev.twitch.tv/docs/api/clips — Twitch Clips guide
[5] https://www.activepieces.com/blog/twitch-api-access-tokens-and-rate-limits-2026 — Twitch API tokens and rate limits 2026
[6] https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post — TikTok Direct Post reference
[8] https://developers.tiktok.com/docs/en/content-posting-api-get-started — TikTok Content Posting API get started
[9] https://developers.facebook.com/documentation/instagram-platform/content-publishing — Meta IG content publishing
[10] https://github.com/fbsamples/reels_publishing_apis/blob/main/insta_reels_publishing_api_sample/README.md — IG Reels publishing API sample
[11] https://developers.google.com/youtube/v3/determine_quota_cost — YouTube Data API quota calculator
[12] https://developer.x.com/en/docs/x-api — X API access levels
[14] https://support.rockstargames.com/articles/7bNaeoMFTV0iUDGhStTXvz/policy-on-posting-copyrighted-rockstar-games-material — Rockstar policy on posting copyrighted material
[15] https://github.com/AnisAbdellatif/kicksdk/blob/main/docs/KICK.md — Kick SDK docs: public API surfaces
[16] https://github.com/KickEngineering/KickDevDocs/issues/424 — Kick DevDocs issue: no official clips API
[19] https://github.com/HmdNvd/Gaming-Clipper/blob/main/README.md — Gaming-Clipper local-first AI clipping pipeline
[23] https://insider-gaming.com/rockstar-might-dmca-gta-6-spoilers — Rockstar might DMCA GTA 6 spoilers
[24] https://metro.co.uk/2026/11/04/rockstar-will-take-videos-gta-6-story-spoilers-even-launch-29765723 — Metro: Rockstar spoiler takedowns
[28] https://support.google.com/youtube/answer/72851?hl=en — YouTube Partner Program eligibility
[35] https://simonwillison.net/2024/Aug/13/mlx-whisper — Simon Willison: mlx-whisper speed
[36] https://github.com/Mobiss11/Whisper-Skill/blob/main/backends/mlx-whisper.md — mlx-whisper backend notes
[44] https://blog.youtube/news-and-events/youtube-partner-program-updates-2027-new-opportunities-earn — New opportunities to earn and changes to the YouTube Partner Program
[52] https://developers.tiktok.com/docs/zh-Hans/content-posting-api-reference-photo-post — Photo | TikTok for Developers
[58] https://developer.x.com/en/support/x-api/v2 — X API v2 support | Twitter Developer Platform
[61] https://developers.google.com/youtube/data/revision_history — Revision History | YouTube Data API
[62] https://developers.google.com/youtube/v3/docs/videos/insert?authuser=9 — Videos: insert | YouTube Data API - Google for Developers
[64] https://docs.x.com/x-api/media/introduction — Media upload endpoints on the X API v2 - X
[65] https://docs.x.com/x-api/media/quickstart/media-upload-chunked — Chunked Media Upload - X
[66] https://docs.x.com/x-api/media/quickstart/best-practices — Best practices
[67] https://developers.facebook.com/documentation/video-api/guides/reels-publishing — Reels Publishing API | Meta for Developers - Facebook
[69] https://developers.secure.facebook.com/docs/graph-api/reference/page/video_reels — Graph API Reference v27.0: Page Video Reels
[71] https://docs.letmepost.dev/platforms/tiktok — TikTok - letmepost.dev
[72] https://contentrewards.com/articles/gta-6-clipping — How to Get Paid to Clip GTA 6 (2026)
[74] https://contentrewards.com/articles/video-game-clipping-campaigns — Video Game Clipping Campaigns: Get Paid to Clip Games
[76] https://support.google.com/youtube/answer/1311392?hl=en — YouTube channel monetization policies
[77] https://support.google.com/youtube/community-guide/271248162/faq-reused-content-youtube — FAQ: Reused Content & YouTube's Partner Program - YouTube ...
[81] https://dev.twitch.tv/docs/authentication/scopes — Twitch Access Token Scopes
[87] https://cloudmart.dev/provider/hetzner — Hetzner pricing Nov 2026 (CloudMart)
[88] https://usehcm.com/hetzner-pricing — Hetzner cloud pricing 2026
[89] https://stackrates.ai/blog/hetzner-cloud-honest-review — Hetzner review 2026 plan prices
[90] https://cut.pro/en/blog/how-to-warm-up-tiktok-account-2026 — TikTok new-account warmup 2026
[91] https://www.tokportal.com/learn/warm-up-new-instagram-tiktok-account — TokPortal: IG/TikTok warmup
[92] https://www.jem.social/blog/how-to-warm-up-tiktok-and-instagram-accounts — Jem Social: 14-day warmup plan
[93] https://socialnexis.com/guides/twitter-automation-safe-2026 — SocialNexis: X automation limits 2026
[95] https://www.tokportal.com/learn/tiktok-shadow-limits-new-accounts — TokPortal: TikTok shadow limits new accounts
