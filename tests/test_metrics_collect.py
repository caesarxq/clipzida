"""RED: Platform metrics collection from YouTube + X public APIs.
Tests use stubbed HTTP transport — no network calls.
"""
from __future__ import annotations

import json
import os

from clipping_tools.metrics.collect import (
    fetch_x_metrics,
    fetch_youtube_metrics,
    collect_for_post,
    collect_all,
)


class FakeResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status = status
    def json(self):
        return self._data
    def raise_for_status(self):
        if self.status >= 400:
            raise Exception(f"HTTP {self.status}")


# ── YouTube ──────────────────────────────────────────────────────────────

def test_fetch_youtube_metrics_returns_stats(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-key")

    def http_get(url):
        assert "part=statistics" in url
        assert "id=ytvid123" in url
        assert "key=yt-key" in url
        return {"items": [{"statistics": {
            "viewCount": "12345",
            "likeCount": "890",
            "commentCount": "42",
        }}]}

    m = fetch_youtube_metrics("ytvid123", transport=http_get)
    assert m["views"] == 12345
    assert m["likes"] == 890
    assert m["comments"] == 42
    assert m["shares"] == 0
    assert m["approved_views"] is None
    assert "error" not in m


def test_fetch_youtube_metrics_missing_key(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    m = fetch_youtube_metrics("ytvid123")
    assert m["error"] == "no api key or oauth token"


def test_fetch_youtube_metrics_empty_items(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-key")

    def http_get(url):
        return {"items": []}

    m = fetch_youtube_metrics("ytvid123", transport=http_get)
    assert m["views"] == 0
    assert m["likes"] == 0
    assert m["comments"] == 0


# ── X (Twitter) ──────────────────────────────────────────────────────────

def test_fetch_x_metrics_returns_public_metrics(monkeypatch):
    monkeypatch.setenv("X_ACCESS_TOKEN", "x-bearer")

    def http_get(url):
        assert "tweet.fields=public_metrics" in url
        assert "tweets/xpost456" in url
        return {"data": {"public_metrics": {
            "impression_count": 50000,
            "like_count": 1200,
            "reply_count": 80,
            "retweet_count": 200,
        }}}

    m = fetch_x_metrics("xpost456", transport=http_get)
    assert m["views"] == 50000   # impression_count
    assert m["likes"] == 1200    # like_count
    assert m["comments"] == 80   # reply_count
    assert m["shares"] == 200    # retweet_count
    assert m["approved_views"] is None


def test_fetch_x_metrics_missing_token(monkeypatch):
    monkeypatch.delenv("X_ACCESS_TOKEN", raising=False)
    m = fetch_x_metrics("xpost456")
    assert m["error"] == "no bearer token"


# ── Collect for post ─────────────────────────────────────────────────────

def test_collect_for_post_youtube_writes_metrics(tmp_path, monkeypatch):
    from clipping_tools.db import init_db

    db = os.path.join(tmp_path, "state.db")
    conn = init_db(db)
    conn.execute(
        "INSERT INTO posts(id, caption, status, platform, external_post_id) "
        "VALUES(1, 'hook', 'published', 'youtube', 'ytvid123')"
    )
    conn.commit(); conn.close()

    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-key")

    def http_get(url):
        return {"items": [{"statistics": {
            "viewCount": "777",
            "likeCount": "50",
            "commentCount": "5",
        }}]}

    result = collect_for_post(
        {"id": 1, "platform": "youtube", "external_post_id": "ytvid123"},
        db,
        transport=http_get,
    )
    assert result is not None
    assert result["post_id"] == 1
    assert result["platform"] == "youtube"
    assert result["metrics"]["views"] == 777

    # Verify written to DB
    conn = init_db(db)
    row = conn.execute(
        "SELECT views, likes, comments, shares FROM metrics WHERE post_id=1"
    ).fetchone()
    assert row["views"] == 777
    assert row["likes"] == 50
    assert row["comments"] == 5
    assert row["shares"] == 0
    conn.close()


def test_collect_for_post_x_writes_metrics(tmp_path, monkeypatch):
    from clipping_tools.db import init_db

    db = os.path.join(tmp_path, "state.db")
    conn = init_db(db)
    conn.execute(
        "INSERT INTO posts(id, caption, status, platform, external_post_id) "
        "VALUES(2, 'hook', 'published', 'x', 'xpost456')"
    )
    conn.commit(); conn.close()

    monkeypatch.setenv("X_ACCESS_TOKEN", "x-bearer")

    def http_get(url):
        return {"data": {"public_metrics": {
            "impression_count": 3000,
            "like_count": 300,
            "reply_count": 30,
            "retweet_count": 75,
        }}}

    result = collect_for_post(
        {"id": 2, "platform": "x", "external_post_id": "xpost456"},
        db,
        transport=http_get,
    )
    assert result is not None
    assert result["metrics"]["views"] == 3000
    assert result["metrics"]["likes"] == 300
    assert result["metrics"]["comments"] == 30
    assert result["metrics"]["shares"] == 75

    conn = init_db(db)
    row = conn.execute(
        "SELECT views, likes, comments, shares FROM metrics WHERE post_id=2"
    ).fetchone()
    assert row["views"] == 3000
    assert row["likes"] == 300
    assert row["comments"] == 30
    assert row["shares"] == 75
    conn.close()


def test_collect_for_post_unsupported_platform_returns_none(tmp_path, monkeypatch):
    from clipping_tools.db import init_db

    db = os.path.join(tmp_path, "state.db")
    conn = init_db(db)
    conn.execute(
        "INSERT INTO posts(id, caption, status, platform, external_post_id) "
        "VALUES(3, 'hook', 'published', 'tiktok', 'ttvid789')"
    )
    conn.commit(); conn.close()

    result = collect_for_post(
        {"id": 3, "platform": "tiktok", "external_post_id": "ttvid789"},
        db,
    )
    assert result is None


def test_collect_for_post_http_failure_returns_none(tmp_path, monkeypatch):
    from clipping_tools.db import init_db

    db = os.path.join(tmp_path, "state.db")
    conn = init_db(db)
    conn.execute(
        "INSERT INTO posts(id, caption, status, platform, external_post_id) "
        "VALUES(4, 'hook', 'published', 'youtube', 'ytbad')"
    )
    conn.commit(); conn.close()

    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-key")

    def http_get(url):
        raise Exception("network down")

    result = collect_for_post(
        {"id": 4, "platform": "youtube", "external_post_id": "ytbad"},
        db,
        transport=http_get,
    )
    assert result is None


# ── Collect all ──────────────────────────────────────────────────────────

def test_collect_all_filters_by_platform(tmp_path, monkeypatch):
    from clipping_tools.db import init_db

    db = os.path.join(tmp_path, "state.db")
    conn = init_db(db)
    conn.execute(
        "INSERT INTO posts(id, caption, status, platform, external_post_id) "
        "VALUES(1, 'h1', 'published', 'youtube', 'yt1')"
    )
    conn.execute(
        "INSERT INTO posts(id, caption, status, platform, external_post_id) "
        "VALUES(2, 'h2', 'published', 'x', 'x1')"
    )
    conn.execute(
        "INSERT INTO posts(id, caption, status, platform, external_post_id) "
        "VALUES(3, 'h3', 'published', 'youtube', 'yt2')"
    )
    conn.commit(); conn.close()

    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-key")
    monkeypatch.setenv("X_ACCESS_TOKEN", "x-bearer")

    youtube_calls = []
    x_calls = []

    def http_get(url):
        if "youtube/v3/videos" in url:
            youtube_calls.append(url)
            return {"items": [{"statistics": {"viewCount": "100", "likeCount": "10", "commentCount": "1"}}]}
        if "api.x.com/2/tweets" in url:
            x_calls.append(url)
            return {"data": {"public_metrics": {"impression_count": "200", "like_count": "20", "reply_count": "2", "retweet_count": "5"}}}
        raise Exception("unexpected url")

    results = collect_all(platform="youtube", db_path=db, transport=http_get)
    assert len(results) == 2  # only youtube posts
    assert len(youtube_calls) == 2
    assert len(x_calls) == 0
