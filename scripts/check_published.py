import os, httpx
from clipping_tools.db import init_db
from clipping_tools.publish.youtube import _refresh_token

c = init_db("/home/clipzida/clipping_tools/data/state.db")
tok = _refresh_token(c, os.environ["GOOGLE_CLIENT_ID"], os.environ["GOOGLE_CLIENT_SECRET"])
rows = c.execute("SELECT id, external_post_id, url FROM posts WHERE status='published'").fetchall()
print([tuple(r) for r in rows])
ids = [r[1] for r in rows]
r = httpx.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "snippet,status", "id": ",".join(ids)}, headers={"Authorization": "Bearer " + tok}, timeout=30)
for it in r.json().get("items", []):
    print(it["id"], "|", it["snippet"]["title"][:45], "|", it["status"]["privacyStatus"])
