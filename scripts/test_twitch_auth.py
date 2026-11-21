import os
from pathlib import Path

# Load .env manually
env_path = Path("/home/clipzida/clipping_tools/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip()

print("TWITCH_CLIENT_ID set:", bool(os.environ.get("TWITCH_CLIENT_ID")))
print("TWITCH_CLIENT_SECRET set:", bool(os.environ.get("TWITCH_CLIENT_SECRET")))

# Check what's available in twitch module
import clipping_tools.sources.twitch as twitch_mod
print("Twitch module attrs:", [x for x in dir(twitch_mod) if not x.startswith("_")])

# Try to get an app token
import httpx
client_id = os.environ["TWITCH_CLIENT_ID"]
client_secret = os.environ["TWITCH_CLIENT_SECRET"]

resp = httpx.post("https://id.twitch.tv/oauth2/token", data={
    "client_id": client_id,
    "client_secret": client_secret,
    "grant_type": "client_credentials",
})
print("Token response status:", resp.status_code)
if resp.status_code == 200:
    data = resp.json()
    print("Access token obtained (length:", len(data.get("access_token", "")), ")")
else:
    print("Error:", resp.text[:500])
