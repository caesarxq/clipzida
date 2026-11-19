# GTA 6 Clipping Pipeline — Research Dossier

**Date:** 2026-11-20 · **Project:** `clipping_tools` · **Status:** research complete, 94 sources logged
**Method:** live web research; every factual claim carries an inline citation resolved in the Sources block.

---

## 1. Market timing — the wave is happening right now

- GTA 6 launched **November 19, 2026** on PS5 and Xbox Series X|S, at midnight local time rolling across time zones.[1][2][72]
- Launch day set all-time livestreaming records: **7.91M peak concurrent viewers** and **125.47M hours watched in the first 24 hours** (Streams Charts data).[86] Variety reported nearly 8M livestream views across Twitch/YouTube in the first hours.[83]
- The Twitch GTA VI category showed **2.5M viewers** on its clips directory at research time; Kai Cenat alone was streaming GTA 6 to 42K concurrent viewers.[21]
- **No PC version announced.** Rockstar/Take-Two list only PS5 and Xbox Series X|S; PC is rumored for early 2027 but unconfirmed.[25][41][26] All v1 content therefore originates from console streamers — no local PC gameplay capture is possible yet.
- Implication: a launch-week clipping operation enters the largest content wave in gaming history with maximum clip supply and maximum audience demand. Campaign budgets are being deployed *now* (Section 5).

## 2. Content sources — free streaming APIs

### 2.1 Twitch (primary source)

- **Get Clips** (`GET https://api.twitch.tv/helix/clips`) works with a free **app access token** (client-credentials OAuth); it can query by `game_id`, `broadcaster_id`, or up to 100 clip IDs, with `started_at`/`ended_at` UTC date ranges and cursor pagination.[3][4]
- Clip objects include `view_count`, `duration`, `created_at`, `broadcaster_name`, `creator_name`, `thumbnail_url`, `video_id`, `vod_offset`, `language` — everything needed for pre-filtering and attribution.[4]
- The GTA VI `game_id` is resolved at runtime via **Search Categories** (`GET /helix/search/categories?query=...`); never hardcode it.[4]
- Rate limits: the Clips endpoint is capped at **100 requests/minute**; the Helix API overall uses an **800-points-per-minute** budget per client ID.[3][5] A 10-minute polling cadence consumes a negligible fraction.
- **Create Clip** (`POST /helix/clips?broadcaster_id=...`) requires a *user* token with `clips:edit`; it captures ~90s (≈85s before the call, ≈5s after), is asynchronous (poll Get Clips ≤15s), and only works while the broadcaster is live with clips enabled (not follower/sub-only unless you qualify).[4][81] This enables v2 "live moment capture" driven by chat spikes.
- Clip media downloads via **yt-dlp** (supports Twitch clips/VODs; sub-only VODs require lawful authenticated access).[47][48][49]
- Broadcaster-side clip settings (follower-only/sub-only clips) can block capture — handle download failures gracefully and skip.[4]

### 2.2 Kick (secondary source, v2)

- Kick has an **official public API** (`api.kick.com/public/v1` and `/public/v2`) with app tokens via `POST https://id.kick.com/oauth/token` (client credentials; tokens last **60 days**). It exposes livestreams, channels, categories, viewer counts — and official webhooks for stream start/end and metadata.[15]
- **There is no official clips endpoint.** Kick engineering has an open request (issue #424) for a Clips API + `clip.created` webhook; until it ships, clips are only reachable through undocumented website endpoints (`kick.com/api/v2/...`, no auth) or yt-dlp.[16][15][17]
- Decision: Kick is a **v2 source** — official API for discovering live GTA 6 streams, best-effort clip retrieval with graceful degradation. Do not build v1 on undocumented endpoints.

### 2.3 YouTube (tertiary source + primary publish target)

- YouTube Data API v3 `search.list` finds GTA 6 videos (100 quota units per search); default project quota is **10,000 units/day**.[11]
- Some campaigns explicitly pay for clips of a creator's **YouTube videos** (e.g., TOMO), which supplies the permission layer that YouTube's ToS otherwise lacks for downloads.[72]
- Quota conflict: uploads cost 1,600 units each (Section 3.1), so ingest-search and upload must share a carefully budgeted quota or use separate GCP projects.

## 3. Publishing platforms — API access, flows, limits

### 3.1 YouTube Shorts — easiest public API right now

- **Policy reversal (Nov 2, 2026):** videos uploaded via `videos.insert` from **unverified API projects are no longer restricted to private viewing mode** — the July 2020 audit-lock policy was reversed.[61] This removes the single biggest barrier to autonomous Shorts posting; no audit needed to publish publicly.
- Nov 16, 2026 addition: `shortsAspectRatio` property for Shorts custom thumbnails.[61]
- Quota: default **10,000 units/day**; `videos.insert` = **1,600 units** → ~5–6 uploads/day per project; `search.list` = 100 units; `videos.list` (stats) = 1 unit.[11]
- Upload flow: OAuth2 (refresh token) → resumable `videos.insert` with `status.privacyStatus`, `snippet.title/description/tags/categoryId=20 (Gaming)`; Shorts are auto-detected from vertical ≤3-min format, `#Shorts` in metadata is conventional.[62][80]
- Monetization (long game): YPP ad-revenue eligibility = **1,000 subscribers + 4,000 qualified watch hours (12 mo) OR 10M qualified Shorts views (90 days)**; no active strikes; 2FA; AdSense linked.[28] **YPP terms change Feb 1, 2027** — updated terms must be accepted in Studio by Jan 31, 2027.[28][44]
- **Reused-content risk:** YouTube monetization review explicitly scrutinizes clips/compilations; borrowed content must be significantly transformed, and mass-produced/repetitive content is ineligible ("inauthentic content" policy, renamed July 2025).[76][77] A raw-clip channel is a real YPP-rejection risk; campaign revenue does not depend on YPP.

### 3.2 TikTok — two paths, one gated

- **Direct Post** (`/v2/post/publish/video/init/`, `video.publish` scope) requires querying `creator_info` first and is gated behind **App Review/security audit**; **all content posted by unaudited clients is restricted to private viewing mode**.[6][7][37]
- **Upload-inbox path** (`video.upload` scope, push-by-file) works without audit: the video lands in the creator's TikTok inbox as a draft and the creator taps confirm in the app — a viable *semi-autonomous* v1 path (one tap per post).[71]
- Limits: **6 requests/minute per user access token**; caption ≤2,200 chars; video 3s–10min via inbox (audit accounts typically capped to 60s); ≥540px short edge, 1080×1920 recommended; mp4/mov/webm etc.; ≤4GB push-by-file.[52][71]
- Tokens: 24-hour access tokens, 365-day rolling refresh tokens — a refresh daemon is mandatory.[71]
- Monetization: Creator Rewards requires **10,000 followers + 100,000 views in 30 days**, and pays only for **original content over 1 minute** — sub-60s campaign clips do not qualify.[29][30]

### 3.3 Instagram Reels — Business account + Meta app

- Publishing requires an **Instagram professional (Business) account connected to a Facebook Page**, a Meta developer app, and `instagram_basic` + `instagram_content_publish` permissions (plus `pages_read_engagement` for the Facebook-Login flow); Advanced Access requires App Review, Standard Access works for your own accounts in development.[9][10]
- Flow: `POST /<IG_ID>/media` with `media_type=REELS` → container → poll `GET /<container>?fields=status_code` (once/min, ≤5 min) → `POST /<IG_ID>/media_publish`.[9]
- **Media must be on a publicly accessible URL** (Meta cURLs it) — *unless* you use `upload_type=resumable` + `POST https://rupload.facebook.com/ig-api-upload/<container_id>` (Facebook Login for Business), which uploads bytes directly and removes the public-hosting requirement.[9]
- Rate limit: **100 API-published posts per rolling 24h** (current docs, updated Oct 20, 2026); older samples cite 25 — enforce via `GET /<IG_ID>/content_publishing_limit` before publishing.[9][10][39]
- Reels specs: MOV/MP4, moov atom at front, no edit lists; H264/HEVC progressive, closed GOP, 4:2:0; AAC ≤48kHz mono/stereo; 23–60 FPS; ≤1920px horizontal; 9:16 recommended; VBR ≤25Mbps; audio 128kbps; **3s–15min**; ≤1GB.[10]
- Cover control: `cover_url` or `thumb_offset` (ms).[10]

### 3.4 X (Twitter) — free tier is write-only and tiny

- Free tier: **500 posts/month** (app + user level), **100 reads/month**, v2 posting + media upload access; Pro is $5K/month (out of scope).[12][58]
- Media upload v2 is chunked: INIT (`/2/media/upload/initialize`) → APPEND → FINALIZE, then attach `media_ids` to `POST /2/tweets`.[65]
- **Upload and post-attach limits are separately enforced**, and video size/duration caps follow the authenticated user's **Premium/verified status** — confirm the exact caps for the posting account during setup; a successfully finalized media_id can still be rejected at post time.[64][66][59]
- Per-user upload rate: 500/15min (not the binding constraint; the 500 posts/month cap is).[13]
- Consequence: X is a **3–5 posts/day** channel, and analytics reads must be rationed (~100/month).

### 3.5 Facebook Reels (optional v1.1)

- Reels Publishing API on Pages: initialize upload session → upload → publish via `/{page_id}/video_reels`; shares the Meta app with Instagram.[67][69]

## 4. Rights & policy — the three-layer problem

**Layer 1 — Rockstar/Take-Two (game IP).** The official policy (updated Jan 10, 2025) tolerates fan footage **only for non-commercial use that does not intentionally spoil the plot**; "non-commercial" explicitly means *not making money from the footage*. Take-Two reserves takedown rights at any time. Explicit takedown triggers:[14]
- pre-release leaked footage (incl. "early unboxing");
- **story spoilers**: endings, big reveals, edited cutscene compilations, isolated cinematics (cutscenes inside a larger play-through are OK);
- isolated in-game entertainment (TV shows, comedy performances);
- cheat/glitch/exploit promotion, mod menus, unauthorized mods/ports;
- ToS violations.
Press coverage confirms Rockstar intends to enforce spoiler takedowns **even after launch**.[23][24][54]
A monetized raw-clip channel sits outside the policy's safe harbor — this is the core legal risk of the naive approach.[22]

**Layer 2 — streamers (broadcast copyright).** The broadcaster owns their stream footage. Clipping without permission risks DMCA strikes and platform bans. The clean paths: (a) **paid clipping campaigns** where the streamer/agency explicitly licenses clipping for bounties, (b) written permission, (c) your own gameplay.[32][33]
Not every top streamer runs a program — e.g., no official Kai Cenat clipping program was verifiable, but agency-run campaigns (Reach, Clipped & Shipped) pay for his clips.[31][34][72]

**Layer 3 — platforms.** YouTube reused/inauthentic-content rules (Section 3.1), TikTok originality rules for Rewards, per-platform community guidelines, and music copyright (use only campaign-provided audio, e.g., the "Tokyo Girl" song licensed by its campaign).[76][29][72]

**Strategy implication:** campaign-licensed clipping is the only path that is simultaneously (a) permissioned by the footage owner, (b) paid from clip #1 without follower thresholds, and (c) compatible with a $0 API budget. Rockstar's non-commercial policy remains a background risk on *all* GTA footage; mitigations are spoiler/entertainment/cheat gates, attribution, and fast takedown compliance.[14][72]

## 5. Live GTA 6 clipping campaigns (market snapshot, Nov 18, 2026)

Eleven GTA 6 campaigns were open on Content Rewards: seven pay-per-view ($0.70–$1.50 per 1,000 views), four split cash pools ($5,000–$12,500).[72][74]

| Campaign | Operator | Subject | Model | Pay | Per-clip min–max | Platforms | Entry bar |
|---|---|---|---|---|---|---|---|
| Tokyo Girl | Placements | GTA 6 edits w/ "Tokyo Girl" by Passive (music promo) | per-view | $0.70/1k | $2–$35 | TikTok, IG | none; $2k budget |
| Ruckus (Dom) | Ruckus | Dasgasd3m funny moments | per-view | $1.00/1k | $10–$100 | TikTok, YT Shorts | account posts GTA 6; $1k budget |
| TOMO GTA VI | Clipping Nation | Tomo streams + YouTube videos | per-view | $1.50/1k | $3.50–$150 | TikTok, IG, YT Shorts | $1k budget |
| LACY marathon | Reach | Lacy GTA 6 marathon | pool | $12,500 split by approved-view share | share | (see rules) | **1M approved views**; caption: name + #LACY; Lacy main focus |
| Clix marathon | Reach | Clix GTA 6 marathon | pool | $5,000 split | share | TikTok, IG, YT Shorts, X | **400k approved views**; #Clix; **no AI-generated videos** |
| Kai Cenat | Clipped & Shipped | Kai Cenat GTA 6 streams | pool | $10,000 split | share | TikTok, YT Shorts, IG, X | **750k approved views**; clip needs ≥1k views to count |
| YourRAGE | Reach | YourRAGE Twitch marathon | pool | $5,000 split | share | TikTok, IG, YT Shorts | **500k approved views** |
| Lauren Hamden | Reach | Lauren Hamden Twitch streams | per-view | $1.50/1k | $15–$250 | TikTok, IG | dedicated account; $5k budget |

(8 of 11 detailed in the source; the registry-seed task pulls the full live list.)[72]

Key campaign rules: **no follower minimum** (new accounts earn); **the same final clip may not be submitted to two campaigns** — re-cut with a new hook per campaign; budgets deplete as clips get paid; Rockstar's spoiler rules still apply on top.[72] Typical Content Rewards campaign: ~$1.00/1k views with a $200 cap per clip (740-campaign live sample).[75] Pool campaigns pay out when the marathon ends — **time-sensitive**.[72]

## 6. Tooling — proven open-source building blocks

- **Gaming-Clipper** (MIT, updated Nov 14, 2026): local-first, watermark-free pipeline — yt-dlp + faster-whisper + ffmpeg; RMS audio-energy peaks + word-level timestamps; `gaming-split` 9:16 layout (blurred background + centered 16:9 gameplay, HUD preserved), optional facecam corner box, caption presets in the TikTok/Reels safe zone (`MarginV=560`), speech-start snapping, −14 LUFS loudnorm, per-clip metadata sidecar; ships as an agent SKILL.md.[19]
- **NeonClipping**: similar local engine (audio-first, YouTube captions, local LLM), ~2 min per clip.[20] **AI-Youtube-Shorts-Generator** (6.1k★, MIT) is the Opus-Clip-style alternative for long-form sources.[18]
- **Whisper on Apple Silicon:** faster-whisper is CPU-only on Mac; **whisper.cpp (CoreML)** and **mlx-whisper (Metal)** are the fast backends — mlx-whisper measured ~3× faster than whisper.cpp on M1 Max.[35][36][56] On an 8GB M2 Air, a `small`-class model is the comfortable ceiling.
- **yt-dlp** handles Twitch clips/VODs and Kick/YouTube downloads; **ffmpeg** (already installed) does extraction, filtering, and encode; `h264_videotoolbox` gives Apple hardware encoding.[49][19]
- Reference architecture pattern: Agent OS conventions (Pydantic v2 typed context, provider ABCs, SQLite state, declarative YAML stages, TDD) apply directly; `clipping_tools` stays standalone per directive.

## 7. Hardware & environment constraints (measured)

- MacBook Air **M2, 8GB RAM**, 8 cores; ffmpeg present at `/opt/homebrew/bin/ffmpeg`; **yt-dlp and uv missing**; system Python 3.9.6 (needs 3.11+ via uv).
- 8GB unified memory: whisper `small` + ffmpeg render is fine sequentially; avoid parallel render+transcribe jobs; queue renders.
- Fanless Air: sustained libx264 encodes throttle — prefer VideoToolbox HW encode; keep Mac awake (`caffeinate`/launchd) during campaign windows or accept sleep gaps.
- $0 budget: all APIs above have free tiers sufficient for 5–15 posts/day; the only optional spend is a small VPS later for 24/7 uptime.

## 8. Strategic conclusions

1. **Enter via campaigns, not raw clipping.** Permissioned, paid from clip #1, no follower thresholds, and the launch wave has 11 live GTA 6 campaigns right now.[72][75]
2. **YouTube Shorts is the v1 autonomy anchor** — the Nov 2 policy reversal makes public API uploads work without audit.[61]
   TikTok runs semi-auto (inbox draft + one tap) until its app audit clears.[71] IG needs account/app setup; X is a low-volume amplifier.[9][12]
3. **Compliance is a pipeline stage, not an afterthought** — rights gate → Rockstar spoiler/entertainment/cheat gate → campaign-rules gate → platform gate, all before render.[14][72][76]
4. **Speed wins pools.** Marathon pools close when the stream ends; ingest→post latency under ~30 minutes is the competitive edge.[72]
5. **Platform monetization is a later, riskier track** — YPP thresholds plus reused-content review gate it.[28][76]
   TikTok Rewards needs 1-min originals and 10k followers.[29][30] Pursue only after the campaign engine is profitable.

## Sources

[1] https://www.rockstargames.com/newswire/article/ak3ak31a49a221/grand-theft-auto-vi-is-now-set-to-launch-november-19-2026 — Rockstar Newswire: GTA VI launch Nov 19 2026
[2] https://www.freep.com/story/tech/gaming/2026/11/19/gta-6-live-updates--live/92811863007 — GTA 6 launch live updates Nov 19 2026
[3] https://dev.twitch.tv/docs/api/reference/clips — Twitch Helix API reference: Clips
[4] https://dev.twitch.tv/docs/api/clips — Twitch Clips guide
[5] https://www.activepieces.com/blog/twitch-api-access-tokens-and-rate-limits-2026 — Twitch API tokens and rate limits 2026
[6] https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post — TikTok Direct Post reference
[7] https://developers.tiktok.com/docs/en/content-sharing-guidelines — TikTok content sharing guidelines
[9] https://developers.facebook.com/documentation/instagram-platform/content-publishing — Meta IG content publishing
[10] https://github.com/fbsamples/reels_publishing_apis/blob/main/insta_reels_publishing_api_sample/README.md — IG Reels publishing API sample
[11] https://developers.google.com/youtube/v3/determine_quota_cost — YouTube Data API quota calculator
[12] https://developer.x.com/en/docs/x-api — X API access levels
[13] https://docs.x.com/x-api/fundamentals/rate-limits — X API rate limits
[14] https://support.rockstargames.com/articles/7bNaeoMFTV0iUDGhStTXvz/policy-on-posting-copyrighted-rockstar-games-material — Rockstar policy on posting copyrighted material
[15] https://github.com/AnisAbdellatif/kicksdk/blob/main/docs/KICK.md — Kick SDK docs: public API surfaces
[16] https://github.com/KickEngineering/KickDevDocs/issues/424 — Kick DevDocs issue: no official clips API
[17] https://github.com/3z/kick-py — kick-py unofficial client
[18] https://github.com/clipx-io/awesome-ai-clipping — awesome-ai-clipping list
[19] https://github.com/HmdNvd/Gaming-Clipper/blob/main/README.md — Gaming-Clipper local-first AI clipping pipeline
[20] https://github.com/iamajmeena/neonclipping — NeonClipping local clipping engine
[21] https://www.twitch.tv/directory/category/grand-theft-auto-vi/clips — Twitch GTA VI clips directory
[22] https://www.sove7gn.org/gta-6-monetization — GTA 6 monetization analysis
[23] https://insider-gaming.com/rockstar-might-dmca-gta-6-spoilers — Rockstar might DMCA GTA 6 spoilers
[24] https://metro.co.uk/2026/11/04/rockstar-will-take-videos-gta-6-story-spoilers-even-launch-29765723 — Metro: Rockstar spoiler takedowns
[25] https://mashable.com/entertainment/gta-6-pc-launch-date — Mashable: GTA 6 PC launch date status
[26] https://shiftdelete.net/en/gta-6-pc-release-early-2027 — GTA 6 PC reportedly early 2027
[28] https://support.google.com/youtube/answer/72851?hl=en — YouTube Partner Program eligibility
[29] https://newsroom.tiktok.com/introducing-the-new-creator-rewards-program/?lang=en — TikTok Creator Rewards Program
[30] https://blog.hootsuite.com/how-many-followers-on-tiktok-to-get-paid — Hootsuite: TikTok follower requirements 2026
[31] https://reelshift.app/streamers/kai-cenat — ReelShift: Kai Cenat clipping program status
[32] https://contentrewards.com/articles/get-paid-clip-streamers — Content Rewards: how clipping campaigns work
[33] https://www.clyper.io/clipping-programs — Clyper: streamer clipping programs 2026
[34] https://www.clyper.io/clipping-programs/kai-cenat — Clyper: Kai Cenat campaigns
[35] https://simonwillison.net/2024/Aug/13/mlx-whisper — Simon Willison: mlx-whisper speed
[36] https://github.com/Mobiss11/Whisper-Skill/blob/main/backends/mlx-whisper.md — mlx-whisper backend notes
[37] https://www.socialync.io/blog/tiktok-content-posting-api-guide-2026 — Socialync: TikTok posting API access and limits
[39] https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/content_publishing_limit — IG content_publishing_limit reference
[41] https://www.syracuse.com/us-news/2026/11/gta-6-is-finally-here-but-pc-players-are-still-waiting-for-one-big-answer.html — GTA 6 is finally here, but PC players are still waiting for one big answer
[44] https://blog.youtube/news-and-events/youtube-partner-program-updates-2027-new-opportunities-earn — New opportunities to earn and changes to the YouTube Partner Program
[47] https://yt-dlp.app/download/twitch — Twitch Video Downloader — Free, Fast & Full Quality
[48] https://yt-dlp.app/how-to-download-twitchvideosclips-videos — 3 Ways to Download Videos from Twitch Videos Clips (2026 Archival Guide)
[49] https://github.com/yt-dlp//yt-dlp — GitHub - yt-dlp/yt-dlp: A feature-rich command-line audio/video ...
[52] https://developers.tiktok.com/docs/zh-Hans/content-posting-api-reference-photo-post — Photo | TikTok for Developers
[54] https://finalboss.io/gta-6-spoiler-takedowns-what-rockstar-targets-and-safer-coverage — GTA 6 Spoiler Takedowns: What Rockstar Targets and Safer ...
[56] https://github.com/shun-liang/yt2doc/issues/15 — Less hacky integration with whisper.cpp - shun-liang/yt2doc - GitHub
[58] https://developer.x.com/en/support/x-api/v2 — X API v2 support | Twitter Developer Platform
[59] https://docs.x.com/changelog — X API changelog and release notes - X
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
[75] https://contentrewards.com/articles — Articles
[76] https://support.google.com/youtube/answer/1311392?hl=en — YouTube channel monetization policies
[77] https://support.google.com/youtube/community-guide/271248162/faq-reused-content-youtube — FAQ: Reused Content & YouTube's Partner Program - YouTube ...
[80] https://developers.google.com/youtube/v3/docs/videos/insert — YouTube videos.insert reference
[81] https://dev.twitch.tv/docs/authentication/scopes — Twitch Access Token Scopes
[83] https://variety.com/2026/gaming/news/gta-6-launch-livestream-internet-traffic-records-1236953145 — ‘GTA 6’ Launch Breaks Internet Usage Records; Livestreams Hit Nearly 8 Million Views on Tw
[86] https://labs.invenglobal.com/articles/28854/gta-vi-sets-livestreaming-records-with-791m-peak-viewers-on-launch-day — GTA VI sets livestreaming records with 7.91m peak viewers on launch day
