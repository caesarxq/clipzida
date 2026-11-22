from clipping_tools.db import init_db
c = init_db("data/state.db")
rows = c.execute("SELECT service, access_token, refresh_token, expires_at, scopes FROM tokens").fetchall()
for r in rows:
    d = dict(r)
    print(d["service"], "| access_len=", len(d["access_token"] or ""), "| refresh_len=", len(d["refresh_token"] or ""), "| expires_at=", d["expires_at"], "| scopes=", d["scopes"])
c.close()
