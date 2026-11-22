from clipping_tools.db import init_db
c = init_db("data/state.db")
print("pending news:", c.execute("SELECT count(*) FROM posts WHERE status='pending' AND angle='news'").fetchone()[0])
print("pending clips:", c.execute("SELECT count(*) FROM posts WHERE status='pending' AND render_id IS NOT NULL").fetchone()[0])
print("pending total:", c.execute("SELECT count(*) FROM posts WHERE status='pending'").fetchone()[0])
print("pending with review_message_id:", c.execute("SELECT count(*) FROM posts WHERE status='pending' AND review_message_id IS NOT NULL").fetchone()[0])
c.close()
