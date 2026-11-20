import sys
sys.path.insert(0, "/home/clipzida/clipping_tools/src")
from clipping_tools.db import init_db
c = init_db("/home/clipzida/clipping_tools/data/state.db")
print("=== ALL APPROVALS ===")
rows = c.execute("SELECT id, post_id, decision, reviewer, decided_at, edits_json FROM approvals ORDER BY id DESC").fetchall()
print("count:", len(rows))
for r in rows:
    print(dict(r))
print()
print("=== ALL POSTS ===")
rows = c.execute("SELECT id, caption, status, platform, external_post_id, review_message_id, angle FROM posts ORDER BY id DESC").fetchall()
print("count:", len(rows))
for r in rows:
    print(dict(r))
