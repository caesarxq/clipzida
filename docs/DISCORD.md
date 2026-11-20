# Discord integration guide — CLIPZIDA review surface

Purpose: Discord is the **human approval surface** (`D8`) and the alert/digest channel.
The pipeline renders a clip → writes a `posts` row → the bot posts an embed with the
mp4 into `#clip-review` → Mohamed taps **Approve / Reject / Edit-caption** → an
`approvals` row is written → the publish queue releases or discards the post.

Nothing in this flow requires a public inbound port. The bot connects **outbound**
over Discord's gateway WebSocket, so it works on the Contabo VPS behind NAT.

---

## 1. Human setup (you, ~10 min, in your own browser)

1. **Create the server** (or reuse one) — name it `CLIPZIDA Ops`.
2. **Create three channels** (private to you; the bot posts into them):
   - `#clip-review` — embeds + mp4 + buttons
   - `#alerts` — failures, token expiry, campaign budget <20%, strikes → auto-halt
   - `#daily` — morning digest (pending, published yesterday, views, revenue estimate)
3. **Create a Reviewer role** and assign it to yourself. The bot checks this role before
   accepting any button press — no other member can approve.
4. **Create the bot** at <https://discord.com/developers/applications>:
   - **New Application** → name `CLIPZIDA Review`
   - **Bot** → **Reset Token** (this is the bot token — it goes to the vault, never chat)
   - Under **Privileged Gateway Intents**: leave all OFF. We use slash commands + button
     components, not message-content scanning.
   - **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`;
     permissions: Send Messages, Embed Links, Attach Files, Read Message History,
     Use External Emojis (permission integer **378880**).
   - Open the generated invite URL, select `CLIPZIDA Ops`, authorize.
5. **Capture three channel IDs and your user ID**: enable Developer Mode
   (User Settings → Advanced → Developer Mode), right-click each channel/user → **Copy ID**.
6. **Give me the token + four IDs** through masked vault prompts (one value per prompt).
   They land in the VPS `.env` as:

   ```
   DISCORD_BOT_TOKEN=...
   DISCORD_REVIEW_CHANNEL_ID=...
   DISCORD_ALERTS_CHANNEL_ID=...
   DISCORD_DAILY_CHANNEL_ID=...
   DISCORD_REVIEWER_ROLE_ID=...
   ```

   File is `0600`, owned by `clipzida`, gitignored. Never in chat, never in git.

---

## 2. Bot behaviour (implementation contract, P7.3)

Stack: `discord.py` 2.x, runs as a systemd unit on the VPS (`clipzida-bot.service`),
no inbound ports. Reads/writes the same SQLite `state.db` as the pipeline (single writer
on the VPS; the bot is the only interactive writer).

### Embed posted to `#clip-review` for each pending `posts` row

Fields: hook title, streamer/broadcaster, campaign name, angle (`funny|hype|news`),
compliance gate badges (rights / Rockstar / campaign / platform), score, scheduled slot.
Attachment: the rendered mp4 (1080×1920, 30–45s, ≈5–15MB — under Discord's 25MB limit;
if a render exceeds 25MB, re-encode at a lower bitrate before attaching — never link out
to a public host).

### Components

- `Approve` — writes `approvals(decision='approve', reviewer, decided_at)`, sets
  `posts.status='approved'`, releases the publish queue.
- `Reject` — writes `decision='reject'` with an optional reason modal, sets status
  `rejected`; the render is retained for audit.
- `Edit-caption` — opens a modal with the current caption/hashtags; on submit writes
  `edits_json` and sets `decision='approve'` with `edited=1`. Graduation metric P7.4
  tracks the unchanged-approval rate; an edited approval does not count as unchanged.

All three buttons are wrapped in a **persistent** `discord.ui.View` (`timeout=None`,
stable `custom_id` containing `post_id`) so the bot survives restarts and the buttons
keep working. Every handler first checks the reviewer role and ignores other users.

### Alert rules (`#alerts`)

Adapter failures, token expiry within 7 days, campaign budget <20%, any takedown/strike.
A strike triggers **auto-halt** (`autonomy` → `queue`, publishing paused) and mentions
you by user ID. Recovery is explicit: `clipping-tools resume`.

### Digest (`#daily`)

Posted by the scheduler at 08:00 EAT: pending count, posts published yesterday,
views/revenue estimates from `metrics`, campaign runway. Mirrored by the Hermes cron
digest.

---

## 3. Build order (TDD, RED→GREEN→REFACTOR)

| Step | Test first | Then implement |
|---|---|---|
| 1 | `test_bot.py`: role gate rejects non-reviewer | `ReviewView` + role check |
| 2 | `test_approvals.py`: approve writes row + releases post | DB helpers on `approvals` |
| 3 | `test_embeds.py`: embed fields + mp4 attachment size | `build_review_embed()` |
| 4 | `test_modal.py`: edit-caption writes `edits_json` | `EditCaptionModal` |
| 5 | `test_alerts.py`: strike triggers halt + mention | alert dispatcher |
| 6 | `test_digest.py`: totals from `metrics` | digest formatter |
| 7 | integration: fake draft → button tap → status change | live bot on VPS |

Files to add: `src/clipping_tools/review/bot.py`, `review/embeds.py`, `review/views.py`,
`tests/test_review_bot.py`, `tests/test_review_store.py`, systemd unit under `deploy/`.

---

## 4. Verification checklist (before you trust it)

1. `/ping` in `#clip-review` → bot replies (slash commands registered).
2. Insert a fake `posts` row → embed with mp4 appears in `#clip-review`.
3. **Approve** from a non-reviewer account → ignored; from you → `approvals` row + status `approved`.
4. **Reject** → status `rejected`, render retained.
5. **Edit-caption** → `edits_json` populated, approval marked edited.
6. Restart the bot → old buttons still work (persistent view).
7. Simulate a strike → `#alerts` mention + `autonomy` reverted + publishing halted.
8. Confirm no inbound port opened: `ufw status` still SSH-only.

---

## 5. Security rules (non-negotiable)

- Bot token, channel IDs and reviewer role ID arrive via **vault masked prompts**, never chat.
- Bot has no message-content intent and no access to other servers; verify the invite
  server list in the Developer Portal is only `CLIPZIDA Ops`.
- Only the Reviewer role can approve. Buttons re-check the role on every interaction —
  a stale embed cannot be used by someone else.
- `#alerts` and `#daily` are private to you; the bot cannot read general chat.
- On any credential leak: **Reset Token** in the Developer Portal, update the vault entry,
  rewrite the VPS `.env`, restart the service.

---

## 6. Handoff

You do: §1 steps 1–6 (server, channels, role, bot app, invite, IDs + token via my prompts).
I do: §3 build + tests, install the systemd unit, run §4 checklist, report results.
