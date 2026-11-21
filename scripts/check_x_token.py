import httpx
import os

token = os.environ.get("X_ACCESS_TOKEN")
if not token:
    print("X_ACCESS_TOKEN not set")
    exit(1)

resp = httpx.get(
    "https://api.x.com/2/users/me",
    headers={"Authorization": f"Bearer {token}"},
    timeout=30,
)
print("Status:", resp.status_code)
print("Body:", resp.text[:1000])
