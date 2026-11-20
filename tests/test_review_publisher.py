"""RED: publish_pending_reviews posts an embed+view per pending post."""
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

from clipping_tools.db import init_db
from clipping_tools.review.publisher import publish_pending_reviews


def _seed():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "state.db")
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id,render_id,caption,status) VALUES(1,NULL,'HOOK','pending')")
    conn.commit(); conn.close()
    return db


def test_publish_pending_reviews_sends_one_message_per_post():
    db = _seed()
    channel = MagicMock()
    channel.send = AsyncMock()
    client = MagicMock()
    client.get_channel = MagicMock(return_value=channel)
    import asyncio
    sent = asyncio.run(publish_pending_reviews(client, db, "123", "reviewer-role"))
    assert sent == 1
    assert channel.send.await_count == 1
    kwargs = channel.send.await_args.kwargs
    assert kwargs["embed"].title == "HOOK"
    assert kwargs["view"].post_id == 1
