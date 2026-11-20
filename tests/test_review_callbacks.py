"""RED: button callbacks must actually apply a reviewer's decision."""
import os
import tempfile

import discord

from clipping_tools.db import init_db
from clipping_tools.review.bot import ReviewView


class _Resp:
    def __init__(self): self.message = None
    async def send_message(self, msg, **kw): self.message = msg


class _User:
    def __init__(self, roles, uid="u1"):
        self.roles = roles
        self.id = uid


class _Role:
    def __init__(self, rid): self.id = rid


class _Interaction:
    def __init__(self, roles):
        self.user = _User([_Role(r) for r in roles])
        self.response = _Resp()


def test_approve_button_applies_decision_for_reviewer():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "state.db")
        conn = init_db(db)
        conn.execute("INSERT INTO sources(id,platform,external_id,name) VALUES(1,'twitch','s','s')")
        conn.execute("INSERT INTO clips_raw(id,source_id,external_id,url,title,created_at,status) "
                     "VALUES(1,1,'c','u','t','2026-01-01T00:00:00+00:00','new')")
        conn.execute("INSERT INTO renders(id,clip_id,variant,path) VALUES(1,1,'v','/tmp/a.mp4')")
        conn.execute("INSERT INTO posts(id,render_id,caption,status) VALUES(1,1,'HOOK','pending')")
        conn.commit(); conn.close()

        view = ReviewView(1, "reviewer-role", db)
        interaction = _Interaction(["reviewer-role"])
        import asyncio
        asyncio.run(view.approve.callback(interaction))

        assert interaction.response.message == "Post #1: approved."
        check = init_db(db)
        assert check.execute("SELECT status FROM posts WHERE id=1").fetchone()[0] == "approved"
        check.close()


def test_approve_button_ignores_non_reviewer():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "state.db")
        view = ReviewView(1, "reviewer-role", db)
        interaction = _Interaction(["someone-else"])
        import asyncio
        asyncio.run(view.approve.callback(interaction))
        assert interaction.response.message == "Reviewer role required."
