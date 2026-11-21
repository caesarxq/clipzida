"""RED: Edit-caption submits a new caption and updates the embed in place."""
from unittest.mock import AsyncMock, MagicMock

from clipping_tools.db import init_db
from clipping_tools.review.bot import handle_component, EditCaptionModal


class _Msg:
    def __init__(self):
        self.edit = AsyncMock()
        self.embeds = []
        self.components = []


class _Resp:
    def __init__(self):
        self.messages = []

    async def send_message(self, msg, **kw):
        self.messages.append((msg, kw))
        m = MagicMock()
        m.message = msg
        return m

    async def send_modal(self, modal):
        self.messages.append(("modal", modal))
        return MagicMock()


def test_edit_caption_sends_modal():
    interaction = MagicMock()
    interaction.user = MagicMock()
    interaction.user.roles = [MagicMock(id="reviewer-role")]
    interaction.user.id = "reviewer-1"
    interaction.response = _Resp()
    interaction.message = _Msg()

    import asyncio
    result = asyncio.run(
        handle_component(interaction, "clipzida:edit:99", "/tmp/x.db", "reviewer-role")
    )
    assert result is True
    assert interaction.response.messages
    kind, modal = interaction.response.messages[-1]
    assert kind == "modal"
    assert isinstance(modal, EditCaptionModal)
    assert modal.post_id == 99


def test_edit_caption_on_submit_updates_message(tmp_path):
    db = tmp_path / "state.db"
    conn = init_db(db)
    conn.execute("INSERT INTO sources(id,platform,external_id,name) VALUES(1,'twitch','s','s')")
    conn.execute("INSERT INTO clips_raw(id,source_id,external_id,url,title,duration,created_at,status) "
                 "VALUES(99,1,'c','u','old caption',20,'2026-01-01T00:00:00+00:00','new')")
    conn.execute("INSERT INTO posts(id,render_id,caption,status,idempotency_key) "
                 "VALUES(99,NULL,'old caption','pending','clip-99')")
    conn.commit(); conn.close()

    interaction = MagicMock()
    interaction.user = MagicMock()
    interaction.user.roles = [MagicMock(id="reviewer-role")]
    interaction.user.id = "reviewer-1"
    interaction.response = _Resp()
    interaction.message = _Msg()

    modal = EditCaptionModal(99, "reviewer-role", str(db))
    modal.caption._value = "new caption text"
    
    import asyncio
    result = asyncio.run(modal.on_submit(interaction))
    assert result is None  # on_submit returns None (discord pattern)

    interaction.message.edit.assert_awaited_once()
    call_kw = interaction.message.edit.call_args.kwargs
    assert call_kw["view"] is None
    embeds = call_kw["embeds"]
    assert len(embeds) == 1
    title = str(embeds[0].title).upper()
    assert "APPROVED" in title
    assert "EDITED" in title
    assert "new caption text" in str(embeds[0].description)

    # Verify DB persisted
    check = init_db(db)
    caption_row = check.execute("SELECT caption, status FROM posts WHERE id=99").fetchone()
    decision_row = check.execute("SELECT decision FROM approvals WHERE post_id=99 ORDER BY id DESC LIMIT 1").fetchone()
    print("DB row:", tuple(caption_row) if caption_row else None, "|", tuple(decision_row) if decision_row else None)
    print("ALL APPROVALS:", check.execute("SELECT * FROM approvals").fetchall())
    print("ALL POSTS:", check.execute("SELECT id, caption, status FROM posts").fetchall())
    assert caption_row[0] == "new caption text"
    assert caption_row[1] == "approved"
    assert decision_row[0] == "approve"
