from clipping_tools.db import init_db
c = init_db("data/state.db")
rows = c.execute("SELECT post_id, fetched_at, views, likes, comments, shares FROM metrics ORDER BY fetched_at").fetchall()
for r in rows:
    print(dict(r))
print(f"Total metrics rows: {c.execute('SELECT count(*) FROM metrics').fetchone()[0]}")
c.close()
