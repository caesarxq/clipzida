from clipping_tools.db import init_db
c = init_db("data/state.db")
print("news pending:", c.execute("SELECT count(*) FROM posts WHERE angle='news' AND status='pending'").fetchone()[0])
print("news total:", c.execute("SELECT count(*) FROM posts WHERE angle='news'").fetchone()[0])
row = c.execute("SELECT id, caption, platform, render_id, status FROM posts WHERE angle='news' LIMIT 1").fetchone()
print(dict(row))
c.close()
