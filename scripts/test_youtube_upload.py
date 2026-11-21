import os
from pathlib import Path

# Load .env
env_path = Path("/home/clipzida/clipping_tools/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip()

from clipping_tools.db import init_db
from clipping_tools.publish.youtube import upload_to_youtube

conn = init_db("/home/clipzida/clipping_tools/data/state.db")

# Try uploading post 24
print("Attempting YouTube upload for post 24...")
try:
    result = upload_to_youtube(24, "/home/clipzida/clipping_tools/data/state.db", "/home/clipzida/clipping_tools/data/renders/clipzida_24.mp4")
    print("Upload result:", result)
except Exception as e:
    print(f"Upload error: {type(e).__name__}")
    # Try to get response body
    if hasattr(e, 'response'):
        print(f"Status: {e.response.status_code}")
        print(f"Response body: {e.response.text[:1000]}")
    print(f"Error message: {str(e)[:1000]}")

conn.close()
