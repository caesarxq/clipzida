from clipping_tools.db import init_db
c = init_db("data/state.db")
rows = c.execute(
    "SELECT id, external_post_id, platform, caption FROM posts WHERE status='published' AND external_post_id IS NOT NULL AND platform IS NOT NULL"
).fetchall()
for r in rows:
    print(dict(r))
c.close()
