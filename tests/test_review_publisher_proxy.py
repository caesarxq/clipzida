"""Tests for Discord review publisher with clip preview proxies."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from clipping_tools.review.publisher import publish_pending_reviews


class FakeFile:
    def __init__(self, path: str):
        self.path = path


class FakeMessage:
    def __init__(self, message_id: int = 1000):
        self.id = message_id


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return FakeMessage()


class FakeClient:
    def __init__(self, channel):
        self.channel = channel

    def get_channel(self, channel_id):
        return self.channel

    async def fetch_channel(self, channel_id):
        return self.channel


def _run(coro):
    return asyncio.run(coro)


def test_publish_pending_reviews_attaches_proxy_for_clip(tmp_path):
    """Clip posts should get a proxy MP4 attached to the Discord message."""
    from clipping_tools.db import init_db

    db = str(tmp_path / "state.db")
    conn = init_db(db)

    conn.execute(
        "INSERT INTO sources(id, platform, external_id, name) VALUES(1,'twitch','s','s')"
    )
    conn.execute(
        "INSERT INTO clips_raw(id, source_id, external_id, url, title, broadcaster, "
        "duration, view_count, created_at, status) "
        "VALUES(1,1,'c','u','Clip title','streamerx',30.0,1000,'2026-01-01T00:00:00+00:00','new')"
    )
    conn.execute(
        "INSERT INTO renders(id, clip_id, variant, path) VALUES(1,1,'vertical','/tmp/master.mp4')"
    )
    conn.execute(
        "INSERT INTO posts(id, render_id, caption, status, angle, platform, "
        "idempotency_key) VALUES(1,1,'Clip caption','pending','funny','x','clip-1')"
    )
    conn.commit()
    conn.close()

    fake_proxy = str(tmp_path / "proxy.mp4")
    Path(fake_proxy).write_text("fake video bytes")

    channel = FakeChannel()
    client = FakeClient(channel)

    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "clipping_tools.review.publisher.make_proxy", return_value=fake_proxy
    ):
        n = _run(publish_pending_reviews(client, db, "123456789", "reviewer-role"))

    assert n == 1
    assert len(channel.sent) == 1
    kwargs = channel.sent[0]
    assert "embed" in kwargs
    assert "view" in kwargs
    assert "file" in kwargs
    assert kwargs["file"] is not None

    conn = init_db(db)
    row = conn.execute(
        "SELECT review_proxy_path FROM posts WHERE id=1"
    ).fetchone()
    conn.close()
    assert row["review_proxy_path"] == fake_proxy


def test_publish_pending_reviews_no_video_for_news(tmp_path):
    """News posts (render_id None) should not get a video attachment."""
    from clipping_tools.db import init_db

    db = str(tmp_path / "state.db")
    conn = init_db(db)

    conn.execute(
        "INSERT INTO posts(id, render_id, caption, status, angle, platform, "
        "idempotency_key) VALUES(1,NULL,'News headline','pending','news','x','news:abc')"
    )
    conn.commit()
    conn.close()

    channel = FakeChannel()
    client = FakeClient(channel)

    n = _run(publish_pending_reviews(client, db, "123456789", "reviewer-role"))

    assert n == 1
    kwargs = channel.sent[0]
    assert "file" not in kwargs or kwargs["file"] is None
