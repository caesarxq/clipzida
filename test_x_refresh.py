import base64
import httpx
import os

# Load env manually
env_path = "/home/clipzida/clipping_tools/.env"
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

client_id = os.environ["X_CLIENT_ID"]
client_secret = os.environ["X_CLIENT_SECRET"]
refresh_token = os.environ["X_ACCESS_TOKEN_SECRET"]

print(f"client_id: {client_id[:8]}...")
print(f"refresh_token len: {len(refresh_token)}")

TOKEN_URL = "https://api.x.com/2/oauth2/token"
data = {
    "grant_type": "refresh_token",
    "refresh_token": refresh_token,
    "client_id": client_id,
}
basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
resp = httpx.post(TOKEN_URL, data=data, headers={
    "Authorization": f"Basic {basic}",
    "Content-Type": "application/x-www-form-urlencoded",
}, timeout=30)
print(f"status: {resp.status_code}")
print(f"body: {resp.text[:500]}")
