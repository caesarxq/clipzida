from clipping_tools.db import init_db
c = init_db("data/state.db")
for t in ("posts", "clips_raw", "sources"):
    print(t)
    for r in c.execute("PRAGMA table_info(" + t + ")"):
        print("   ", r[1], r[2])
c.close()
