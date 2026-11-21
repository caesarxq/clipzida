from clipping_tools.db import init_db

conn = init_db("data/state.db")
rows = conn.execute("SELECT status, COUNT(*) as c FROM posts GROUP BY status").fetchall()
for r in rows:
    print(f"  {r['status']}: {r['c']}")
n_review = conn.execute("SELECT COUNT(*) FROM posts WHERE review_message_id IS NOT NULL").fetchone()[0]
print(f"  With Discord embed: {n_review}")
conn.close()
