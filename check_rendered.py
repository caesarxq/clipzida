from clipping_tools.db import init_db
c = init_db("data/state.db")
rows = c.execute(
    """SELECT p.id, p.caption, p.platform, r.path
       FROM posts p
       JOIN renders r ON r.id = p.render_id
       WHERE p.status='rendered' AND p.platform IS NULL
       LIMIT 3"""
).fetchall()
for r in rows:
    print(dict(r))
c.close()
