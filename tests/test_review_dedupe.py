"""RED: a post already posted to Discord must not be re-published after restart."""
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

from clipping_tools.db import init_db
from clipping_tools.review.publisher import publish_pending_reviews


def _seed():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "state.db")
    conn = init_db(db)  # migration adds review_message_id
    conn.execute("INSERT INTO posts(id,render_id,caption,status) VALUES(1,NULL,'HOOK','pending')")
    conn.commit(); conn.close()
    return db


def test_publish_skips_posts_with_existing_review_message():
    db = _seed()
    conn = init_db(db)
    conn.execute("UPDATE posts SET review_message_id='12345' WHERE id=1")
    conn.commit(); conn.close()
    channel = MagicMock(); channel.send = AsyncMock()
    client = MagicMock(); client.get_channel = MagicMock(return_value=channel)
    import asyncio
    sent = asyncio.run(publish_pending_reviews(client, db, "123", "reviewer-role"))
    assert sent == 0
    channel.send.assert_not_awaited()


def test_publish_records_message_id_after_posting():
    db = _seed()
    conn = init_db(db)
    conn.commit(); conn.close()
    channel = MagicMock()
    async def _send(**kwargs):
        m = MagicMock(); m.id = 99999; return m
    channel.send = AsyncMock(side_effect=_send)
    client = MagicMock(); client.get_channel = MagicMock(return_value=channel)
    import asyncio
    assert asyncio.run(publish_pending_reviews(client, db, "123", "reviewer-role")) == 1
    check = init_db(db)
    assert check.execute("SELECT review_message_id FROM posts WHERE id=1").fetchone()[0] == "99999"
