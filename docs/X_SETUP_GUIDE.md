# CLIPZIDA — X (Twitter) Publishing Setup Guide

This guide walks you through configuring the X/Twitter publish adapter so the CLIPZIDA
pipeline can post GTA 6 clips to X automatically.

---

## 1. Create a X Developer Account

1. Go to https://developer.x.com/ and sign in with your X account.
2. Apply for a developer account if you don't have one (instant approval for most).
3. Once approved, you'll access the **Developer Portal** at https://developer.x.com/en/portal.

---

## 2. Create a Project and App

X API v2 requires your app to be inside a **Project**:

1. In the Developer Portal, click **Create Project**.
2. Give it a name (e.g., "Clipzida GTA 6 Clips").
3. Select a use case (e.g., "Student / personal project").
4. Inside the project, click **Create App**.
5. Give the app a name (e.g., "clipzida-x-publisher").
6. The portal will display your **API Key** and **API Secret** — copy these somewhere safe.

---

## 3. Generate User Access Tokens (OAuth 1.0a)

X publishing requires **user context** tokens, not app-only tokens:

1. In your app's settings, go to **Keys and Tokens**.
2. Under **Authentication tokens**, click **Create** next to **Access Token & Secret**.
3. You'll get:
   - **Access Token** (oauth_token)
   - **Access Token Secret** (oauth_token_secret)
4. Copy all four values: API Key, API Secret, Access Token, Access Token Secret.

> **Note:** Tokens do not auto-expire. They remain valid until revoked.

---

## 4. Set Environment Variables on the VPS

Add these to `/home/clipzida/clipping_tools/.env` on the VPS:

```bash
# X (Twitter) API credentials
X_API_KEY=your_api_key_here
X_API_SECRET=your_api_secret_here
X_ACCESS_TOKEN=your_access_token_here
X_ACCESS_TOKEN_SECRET=your_access_token_secret_here
```

You can set them via SSH:

```bash
ssh -i ~/.ssh/clipzida_vps_ed25519 clipzida@169.58.182.213
cd ~/clipping_tools

# Append to .env
echo "X_API_KEY=your_api_key_here" >> .env
echo "X_API_SECRET=your_api_secret_here" >> .env
echo "X_ACCESS_TOKEN=your_access_token_here" >> .env
echo "X_ACCESS_TOKEN_SECRET=your_access_token_secret_here" >> .env
```

---

## 5. Add X to Publish Targets

Edit `/home/clipzida/clipping_tools/config/pipeline.yaml` and add `x` to the publish targets:

```yaml
publish:
  targets: [youtube, x]   # add 'x' alongside youtube
  slots: {start: "12:00", end: "23:00", tz: "Africa/Nairobi"}
  jitter_minutes: 7
  launch_wave_mode: asap
```

The X platform section already exists in `config/platforms.yaml`:

```yaml
x:
  posts_per_month: 500
  reads_per_month: 100
  planned_per_day: 4
  metrics_cadence: weekly
  warmup: [2, 3, 5]
```

No changes needed there unless you want to adjust the warmup ramp.

---

## 6. Restart the Pipeline Cycle

After adding X to targets and setting env vars, restart the cycle service so it picks up the new target:

```bash
ssh -i ~/.ssh/clipzida_vps_ed25519 root@169.58.182.213 'systemctl restart clipzida-cycle.timer'
```

The pipeline will now attempt to publish each approved clip to **both YouTube and X** on every 5-minute cycle run.

---

## 7. Verify It Works

Run a manual cycle to test:

```bash
ssh -i ~/.ssh/clipzida_vps_ed25519 root@169.58.182.213 'su - clipzida -c "cd ~/clipping_tools && set -a && . .env && set +a && ~/.local/bin/uv run clipping-tools cycle"'
```

Check the output — you should see `CYCLE_OK` with published count. Then verify on X that the clip appeared.

You can also run the monitor to check health:

```bash
ssh -i ~/.ssh/clipzida_vps_ed25519 root@169.58.182.213 'su - clipzida -c "cd ~/clipping_tools && set -a && . .env && set +a && ~/.local/bin/uv run clipping-tools monitor"'
```

---

## 8. Rate Limits & Warmup

| Limit | Value |
|-------|-------|
| Posts per month (free tier) | 500 (~17/day) |
| Media uploads per 24h | 85 total |
| Posts per 15 min | 100 |

The warmup ramp in `platforms.yaml` limits fresh accounts:
- Week 1: 2 posts/day
- Week 2: 3 posts/day
- Week 3+: 5 posts/day

Start conservatively and increase `planned_per_day` as the account ages.

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `401 Unauthorized` | Invalid API key/secret or token | Regenerate keys in X Developer Portal |
| `403 Forbidden` | App not in a Project | Move app into a Project in Developer Portal |
| `429 Too Many Requests` | Rate limit hit | Wait for window reset, reduce posting frequency |
| `X credentials missing` | Env vars not set | Add all 4 X env vars to `.env` |
| Media processing failed | Invalid video format | Ensure MP4 with H.264 + AAC |

---

## Files Changed

- `src/clipping_tools/publish/x.py` — new X publish adapter (OAuth 1.0a + v1.1 media upload + v2 tweet create)
- `src/clipping_tools/cli.py` — added X to `_publish` dispatch + X credentials to `doctor` check
- `tests/test_publish_x.py` — 8 new TDD tests (metadata, media init/append/finalize, create post, full flow, missing credentials)
