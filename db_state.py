from clipping_tools.db import init_db
c = init_db("data/state.db")
for t in ("posts", "clips_raw", "renders", "approvals", "metrics", "tokens", "sources"):
    try:
        n = c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n}")
    except Exception as e:
        print(f"  {t}: ERR {e}")
print("  posts by status:")
for r in c.execute("SELECT status, count(*) FROM posts GROUP BY status"):
    print("    ", r[0], r[1])
print("  posts by platform:")
for r in c.execute("SELECT platform, count(*) FROM posts GROUP BY platform"):
    print("    ", r[0], r[1])
print("  posts by angle:")
for r in c.execute("SELECT angle, count(*) FROM posts GROUP BY angle"):
    print("    ", r[0], r[1])
print("  pending posts (first 10):")
for r in c.execute("SELECT id, caption, angle, platform, render_id, review_message_id FROM posts WHERE status='pending' ORDER BY id LIMIT 10"):
    print("    ", dict(r))
print("  recent approvals:")
for r in c.execute("SELECT post_id, decision, reviewer, decided_at FROM approvals ORDER BY decided_at DESC LIMIT 5"):
    print("    ", dict(r))
c.close()
