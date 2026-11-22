import os
import httpx
import base64

# Load env manually
env_path = "/home/clipzida/clipping_tools/.env"
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

print("=== X TOKEN REFRESH ===")
client_id = os.environ.get("X_CLIENT_ID")
client_secret = os.environ.get("X_CLIENT_SECRET")
refresh = os.environ.get("X_ACCESS_TOKEN_SECRET")
print(f"client_id: {client_id[:10] if client_id else None}...")
print(f"refresh_token len: {len(refresh) if refresh else 0}")
print(f"refresh_token prefix: {refresh[:20] if refresh else None}...")

if refresh:
    data = {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": client_id}
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = httpx.post(
        "https://api.x.com/2/oauth2/token",
        data=data,
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    print(f"X refresh status: {resp.status_code}")
    print(f"X refresh body: {resp.text[:300]}")

print()
print("=== YOUTUBE TOKEN REFRESH ===")
yt_client_id = os.environ.get("GOOGLE_CLIENT_ID")
yt_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
print(f"google_client_id: {yt_client_id[:10] if yt_client_id else None}...")

from clipping_tools.db import init_db
c = init_db("data/state.db")
row = c.execute("SELECT refresh_token, access_token, expires_at FROM tokens WHERE service='youtube'").fetchone()
if row:
    print(f"youtube refresh_token len: {len(row['refresh_token']) if row['refresh_token'] else 0}")
    print(f"youtube expires_at: {row['expires_at']}")
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": yt_client_id,
            "client_secret": yt_client_secret,
            "refresh_token": row["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    print(f"youtube refresh status: {resp.status_code}")
    print(f"youtube refresh body: {resp.text[:300]}")
else:
    print("no youtube token row in DB")
c.close()
