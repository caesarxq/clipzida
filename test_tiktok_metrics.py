import asyncio
import os
from clipping_tools.metrics.collect import fetch_tiktok_metrics

# Load env manually
env_path = "/home/clipzida/clipping_tools/.env"
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

# Test TikTok metrics for each published TikTok post
publish_ids = [
    "v_inbox_file~v2.7711060123250165778",
    "v_inbox_file~v2.7711061145414649908",
    "v_pub_file~v2-1.7711020950019934216",
    "v_pub_file~v2-1.7711017210559285256",
]

for pid in publish_ids:
    result = fetch_tiktok_metrics(pid)
    print(f"{pid}: {result}")
