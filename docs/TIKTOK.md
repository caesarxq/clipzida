# TikTok setup guide — CLIPZIDA Content Posting

Goal: let the VPS pipeline push GTA 6 clips to TikTok. Our adapter (`publish/tiktok.py`)
uses the **Content Posting API** in **inbox mode** (scope `video.upload`) — it sends a
draft to the creator's TikTok inbox, you tap to finish in the app. That mode is the
fastest legal path for a fresh account; **Direct Post** (`video.publish`) comes later.

**Important reality check:** TikTok reviews apps. **Sandbox mode does not allow public
posting** through the Content Posting API — it is for testing with private posts. To
publish for real, the app must pass **App review** (explanation + demo video). Plan for
that; it is the gate, not a formality.

---

## 0. What our pipeline needs from you

| Item | Where | Notes |
|---|---|---|
| TikTok app with **Login Kit** + **Content Posting API** | developers.tiktok.com | products added to one app |
| Registered **redirect URI** (https) | app → Login Kit settings | must match exactly |
| Scopes | app → Scopes | `user.info.basic`, `video.upload` |
| **Access token** for the CLIPZIDA TikTok account | from the authorize step | goes to vault, never chat |
| (later) **Client key + secret** | app → Credentials | for token refresh |

---

## 1. Create the developer account + organization

1. Go to <https://developers.tiktok.com> and sign up with the **CLIPZIDA TikTok account**.
2. TikTok recommends an **organization** as the app owner (not an individual profile).
   Create one if prompted — teammates share access.

## 2. Create the app

1. Profile icon → **Manage apps** → **Connect an app**.
2. Choose the organization as owner.
3. Fill in:
   - **Icon** 1024×1024 px
   - **App name:** `CLIPZIDA`
   - **Category:** pick the closest (e.g. *Social* / *Tools*)
   - **Description:** shown on the authorization page — e.g. *"Posts licensed GTA 6 clip drafts to your TikTok inbox."*
   - **Platforms:** **Desktop** (loopback redirect, PKCE — simplest for a VPS/CLI pipeline).
     Choose Web only if you are verifying a domain.

## 3. Add products

**Products → Add products:**
- **Login Kit** — needed to authorize the account and get the access token.
- **Content Posting API** — needed to send the video draft.

### Login Kit settings
- Set a **Redirect URI**. Rules depend on the **platform type**:
  - **Desktop** (recommended for this pipeline): loopback only — `http://localhost:<port>/callback/`
    or `http://127.0.0.1:<port>/callback/`; a port is required; wildcard `*` is allowed; **`http` is fine**.
  - **Web**: absolute `https`, static, no query/fragment, and under a domain you **verify** in URL properties.
- **Use Desktop + `http://127.0.0.1:*/callback/`** unless you are registering and verifying a domain.
- Desktop **requires PKCE** — the authorize URL carries `code_challenge` + `code_challenge_method=S256`
  (hex-encoded SHA-256 of a per-attempt `code_verifier`), and the exchange sends the verifier.

## 4. Add scopes

**Scopes** — add only what we use:
- `user.info.basic` (comes with Login Kit)
- `video.upload` (inbox drafts — no Direct Post audit)
- `video.publish` (only when you want Direct Post later)

## 5. Verify URLs (required for apps created after 2024-09-09)

**URL properties** → verify a **Domain** (e.g. `clipzida.com`) or **URL prefix**
(`https://host/path/`). Also add **Terms of Service** and **Privacy Policy** URLs —
TikTok requires both for review. A simple static page each is fine.

## 6. Test in Sandbox (no review needed)

1. Switch the app to **Sandbox** at the top of the app page.
2. Add up to **10 TikTok accounts you own** as sandbox target users (include the
   CLIPZIDA account).
3. Run the authorize flow and confirm a draft lands in the TikTok **inbox**.
   Sandbox posts are private — that's expected.

## 7. Authorize the CLIPZIDA account → access token

Build the authorize URL (I can generate it once the app exists):
```
https://www.tiktok.com/v2/auth/authorize?client_key=<CLIENT_KEY>&scope=user.info.basic,video.upload&redirect_uri=<REDIRECT_URI>&response_type=code&state=clipzida
```
1. Open it **signed in as the CLIPZIDA TikTok account**.
2. Approve the requested permissions.
3. TikTok redirects to your URI with `?code=…`. **Copy the code** and give it to me
   (via masked prompt / a file — not chat if you prefer). I exchange it for the
   access token and store it on the VPS.

## 8. Submit for App review (the real gate)

**App review** → explain **how each product and scope is used** (be specific: "sends
licensed GTA 6 clip drafts to the creator's inbox via Content Posting API; Login Kit
identifies the account"), then:
- Upload **at least one demo video** (up to 5, ≤50 MB each) showing the full flow.
- **Save**, then **Submit for review**.
- Website must be fully developed with ToS + Privacy Policy links visible.

## 9. After approval

1. Switch the app to **Production**.
2. Tell me "tiktok ready" — I will:
   - write `TIKTOK_ACCESS_TOKEN` to the VPS `.env`
   - set `publish.targets: [youtube, tiktok]` in `config/pipeline.yaml`
   - the 5-minute cycle starts sending drafts to your TikTok inbox.

---

## Limits our pipeline enforces (from `config/platforms.yaml`)

- TikTok warm-up: **1/day week 1 → 2/day week 2 → 3/day week 3+** (per fresh account).
- Inbox drafts: max **5 pending per creator per 24h** (TikTok limit).
- Before Direct Post is approved: posts are **SELF_ONLY** (private).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `redirect_uri` mismatch | must match the registered URI exactly (scheme, host, path, no trailing `#`) |
| `invalid_client` | wrong client key/secret, or app not in the right mode |
| Sandbox: no public post | expected — Sandbox is private-only; submit for review |
| Review rejected | demo video must show the complete end-to-end flow; explain each scope |
| Token expired | I refresh via client key/secret; keep them in the vault |

## Handoff

- **You:** steps 1–8 (account, app, products, redirect, scopes, URL verify, sandbox test, authorize, review).
- **Me:** generate the authorize URL, exchange the code for the token, store it, flip the config, verify the first draft arrives.
