import os
from pathlib import Path
from clipping_tools.metrics.collect import fetch_youtube_metrics

env_path = "/home/clipzida/clipping_tools/.env"
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

db_path = Path("/home/clipzida/clipping_tools/data/state.db")

# Test each YouTube video
for vid in ["AwRrWCvaJ9w", "5NEVrfec2eM", "QDgl3urApJo"]:
    result = fetch_youtube_metrics(vid, db_path=db_path)
    print(f"{vid}: {result}")
