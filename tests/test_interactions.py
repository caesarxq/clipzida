"""RED: component interactions are handled even without a registered view."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from clipping_tools.review.bot import handle_component, parse_component


def test_parse_component_accepts_known_actions():
    assert parse_component("clipzida:approve:16") == ("approve", 16)
    assert parse_component("clipzida:reject:7") == ("reject", 7)
    assert parse_component("clipzida:edit:3") == ("edit", 3)


def test_parse_component_rejects_unknown():
    assert parse_component("other:approve:1") is None
    assert parse_component("clipzida:approve") is None
    assert parse_component("") is None


def test_handle_component_records_approval_for_reviewer(tmp_path):
    db = tmp_path / "state.db"
    from clipping_tools.db import init_db
    conn = init_db(db)
    conn.execute("INSERT INTO sources(id,platform,external_id,name) VALUES(1,'twitch','s','s')")
    conn.execute("INSERT INTO clips_raw(id,source_id,external_id,url,title,created_at,status) "
                 "VALUES(16,1,'c','u','H','2026-01-01T00:00:00+00:00','new')")
    conn.execute("INSERT INTO posts(id,render_id,caption,status,idempotency_key) "
                 "VALUES(16,NULL,'H','pending','clip-16')")
    conn.commit(); conn.close()

    interaction = MagicMock()
    interaction.user = MagicMock()
    interaction.user.roles = [MagicMock(id="reviewer-role")]
    interaction.user.id = "u1"
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    handled = asyncio.run(handle_component(interaction, "clipzida:approve:16",
                                            str(db), "reviewer-role"))
    assert handled is True
    check = init_db(db)
    assert check.execute("SELECT status FROM posts WHERE id=16").fetchone()[0] == "approved"
    interaction.response.send_message.assert_awaited_once()


def test_handle_component_ignores_unknown_custom_id():
    interaction = MagicMock()
    assert asyncio.run(handle_component(interaction, "nope:1", ":memory:", "r")) is False
