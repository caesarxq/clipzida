import os
from datetime import datetime, timezone

env_path = "/home/clipzida/clipping_tools/.env"
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

from clipping_tools.db import init_db
c = init_db("data/state.db")
row = c.execute("SELECT access_token, refresh_token, expires_at FROM tokens WHERE service='youtube'").fetchone()
print(f"access_token present: {bool(row['access_token'])}")
print(f"refresh_token present: {bool(row['refresh_token'])}")
print(f"expires_at: {row['expires_at']}")

expires = datetime.fromisoformat(row["expires_at"])
print(f"expires tzinfo: {expires.tzinfo}")
print(f"now: {datetime.now(timezone.utc)}")
print(f"expired: {datetime.now(timezone.utc) >= expires}")

if datetime.now(timezone.utc) >= expires and row["refresh_token"]:
    import httpx
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
            "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
            "refresh_token": row["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    print(f"refresh status: {resp.status_code}")
    print(f"refresh body: {resp.text[:200]}")
c.close()
