import os, httpx
from clipping_tools.db import init_db
from clipping_tools.publish.youtube import _refresh_token

c = init_db("/home/clipzida/clipping_tools/data/state.db")
tok = _refresh_token(c, os.environ["GOOGLE_CLIENT_ID"], os.environ["GOOGLE_CLIENT_SECRET"])
ids = [r[0] for r in c.execute("SELECT external_post_id FROM posts WHERE status='published'").fetchall()]

for vid in ids:
    r = httpx.post(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "status"},
        json={"id": vid, "status": {"privacyStatus": "public"}},
        headers={"Authorization": f"Bearer {tok}"},
        timeout=60,
    )
    print(vid, r.status_code, r.text[:120])
