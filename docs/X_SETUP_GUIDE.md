# CLIPZIDA — X (Twitter) Publishing Setup Guide (OAuth 2.0)

X uses **OAuth 2.0 with PKCE**, not OAuth 1.0a. This guide walks you through
configuring the X publish adapter so the CLIPZIDA pipeline can post GTA 6 clips
to X automatically.

---

## 1. Create a X Developer Account

1. Go to https://developer.x.com/ and sign in with your X account.
2. Apply for a developer account if you don't have one.
3. Once approved, you'll access the **Developer Portal** at https://developer.x.com/en/portal.

---

## 2. Create a Project and App

X API v2 requires your app to be inside a **Project**:

1. In the Developer Portal, click **Create Project**.
2. Give it a name (e.g., "Clipzida GTA 6 Clips").
3. Select a use case (e.g., "Student / personal project").
4. Inside the project, click **Create App**.
5. Give the app a name (e.g., "clipzida-x-publisher").
6. The portal will display your **Client ID** and **Client Secret** — copy these somewhere safe.

---

## 3. Configure OAuth 2.0 Settings

In your app's settings in the Developer Portal:

| Setting | Value | Notes |
|---------|-------|-------|
| **Callback URI / Redirect URI** | `https://clipzida.com/callback/x` or `http://localhost:8765/callback/x` | Where X redirects after user authorization |
| **App type** | Web App | Required for OAuth 2.0 |
| **App permissions** | Read + Write | Needed to post tweets and upload media |
| **Enable OAuth 2.0** | Checked | Must be enabled for bearer token auth |

Save the changes. The app will generate a **Client ID** (public) and **Client Secret** (keep secret).

---

## 4. Complete OAuth 2.0 Authorization Flow

To get an initial access token + refresh token, complete the OAuth 2.0 Authorization Code Flow with PKCE:

### Step A: Generate PKCE Code Verifier & Challenge

```python
import base64, hashlib, os

code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).rstrip(b"=").decode()
```

### Step B: Direct User to Authorization URL

Open this URL in a browser (you're authorizing the CLIPZIDA X account):

```
https://twitter.com/i/oauth2/authorize
?response_type=code
&client_id=YOUR_CLIENT_ID
&redirect_uri=https://clipzida.com/callback/x
&scope=tweet.read tweet.write users.read media.write
&state=random_state_string
&code_challenge=CODE_CHALLENGE
&code_challenge_method=S256
```

### Step C: Exchange Authorization Code for Tokens

After the user authorizes, X redirects to your callback URI with a `?code=...` parameter. Exchange it:

```http
POST https://api.x.com/2/oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
code=AUTHORIZATION_CODE
redirect_uri=https://clipzida.com/callback/x
client_id=YOUR_CLIENT_ID
code_verifier=CODE_VERIFIER
```

Response includes:
- `access_token` — bearer token for API calls
- `refresh_token` — use to get new access tokens when they expire
- `expires_in` — seconds until access token expires (typically 7200 = 2 hours)

---

## 5. Set Environment Variables on the VPS

Add these to `/home/clipzida/clipping_tools/.env` on the VPS:

```bash
# X (Twitter) OAuth 2.0 credentials
X_CLIENT_ID=your_client_id_here
X_CLIENT_SECRET=your_client_secret_here
X_ACCESS_TOKEN=your_access_token_here          # initial bearer token
X_ACCESS_TOKEN_SECRET=your_refresh_token_here  # refresh token
```

You can set them via SSH:

```bash
ssh -i ~/.ssh/clipzida_vps_ed25519 clipzida@169.58.182.213
cd ~/clipping_tools

echo "X_CLIENT_ID=your_client_id_here" >> .env
echo "X_CLIENT_SECRET=your_client_secret_here" >> .env
echo "X_ACCESS_TOKEN=your_access_token_here" >> .env
echo "X_ACCESS_TOKEN_SECRET=your_refresh_token_here" >> .env
```

The adapter will:
1. Check the DB `tokens` table first for a valid (non-expired) access token
2. Auto-refresh using the refresh token when expired
3. Fall back to the `X_ACCESS_TOKEN` env var if no DB row exists

---

## 6. Add X to Publish Targets

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

## 7. Restart the Pipeline Cycle

After adding X to targets and setting env vars, restart the cycle service so it picks up the new target:

```bash
ssh -i ~/.ssh/clipzida_vps_ed25519 root@169.58.182.213 'systemctl restart clipzida-cycle.timer'
```

The pipeline will now attempt to publish each approved clip to **both YouTube and X** on every 5-minute cycle run.

---

## 8. Verify It Works

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

## 9. Token Refresh (Automatic)

Access tokens expire after ~2 hours. The adapter handles this automatically:

1. Before each publish, it checks `tokens.expires_at` in the DB
2. If expired, it calls `POST https://api.x.com/2/oauth2/token` with `grant_type=refresh_token`
3. The new access token + refresh token are stored back in the DB
4. Publishing continues with the fresh token

No manual intervention needed as long as the refresh token remains valid (X refresh tokens are long-lived but can be revoked).

---

## 10. Rate Limits & Warmup

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
| `401 Unauthorized` | Invalid client ID/secret or expired/refresh token | Regenerate keys in X Developer Portal, re-run OAuth flow |
| `403 Forbidden` | App permissions don't include `tweet.write` or `media.write` | Update app permissions in Developer Portal |
| `429 Too Many Requests` | Rate limit hit | Wait for window reset, reduce posting frequency |
| `X credentials missing` | `X_CLIENT_ID` / `X_CLIENT_SECRET` not set | Add both env vars to `.env` |
| `X access token not found` | No access token in DB or env | Complete OAuth 2.0 authorization flow first |

---

## Files Changed

- `src/clipping_tools/publish/x.py` — X publish adapter (OAuth 2.0 bearer auth + v2 media upload + v2 tweet create)
- `src/clipping_tools/cli.py` — X credentials check in `doctor` updated to OAuth 2.0 env vars
- `tests/test_publish_x.py` — 9 TDD tests (metadata, media init/append/finalize, create post, full flow, missing credentials)
- `docs/X_SETUP_GUIDE.md` — This setup guide
