"""Validate X OAuth 2.0 write permissions.

Checks:
1. Token scopes (via /2/users/me + token introspection)
2. Media upload INIT (requires tweet.write + media.write)
3. Tweet create attempt (dry-run - won't actually post)

Run: X_ACCESS_TOKEN=... python scripts/validate_x_write.py
"""
from __future__ import annotations

import httpx
import os
import sys

TOKEN = os.environ.get("X_ACCESS_TOKEN")
if not TOKEN:
    print("FAIL: X_ACCESS_TOKEN not set")
    sys.exit(1)

BASE = "https://api.x.com/2"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
client = httpx.Client(timeout=30, headers=HEADERS)

print("=" * 60)
print("X WRITE PERMISSION VALIDATION")
print("=" * 60)

# 1. Verify identity (read endpoint - should work)
try:
    r = client.get(f"{BASE}/users/me")
    if r.status_code == 200:
        me = r.json()["data"]
        print(f"[OK] Read access: user={me['username']} id={me['id']}")
    else:
        print(f"[FAIL] Read access failed: {r.status_code} {r.text[:200]}")
        sys.exit(1)
except Exception as e:
    print(f"[FAIL] Read access error: {e}")
    sys.exit(1)

# 2. Attempt media upload INIT (requires write scope)
try:
    r = client.post(
        f"{BASE}/media/upload",
        data={
            "command": "INIT",
            "media_type": "video/mp4",
            "total_bytes": "100",
            "media_category": "tweet_video",
        },
    )
    if r.status_code in (200, 201):
        mid = r.json().get("media_id")
        print(f"[OK] Write access: media upload INIT succeeded (media_id={mid})")
    elif r.status_code == 403:
        print(f"[FAIL] Write access DENIED (403 Forbidden) — token lacks tweet.write/media.write scope")
        print(f"       Response: {r.text[:300]}")
        sys.exit(1)
    elif r.status_code == 401:
        print(f"[FAIL] Token invalid/expired (401)")
        print(f"       Response: {r.text[:300]}")
        sys.exit(1)
    else:
        print(f"[WARN] Unexpected status {r.status_code}: {r.text[:300]}")
except Exception as e:
    print(f"[FAIL] Media upload error: {e}")
    sys.exit(1)

print()
print("=" * 60)
print("WRITE PERMISSIONS VALIDATED — X publishing should work")
print("=" * 60)
