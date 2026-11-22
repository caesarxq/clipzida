"""News ingest from free sources (Google News RSS for GTA 6, Reddit r/GTA6)."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from clipping_tools.ingest.news import fetch_news_items, init_post


RSS = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
  <title>Google News: GTA 6</title>
  <item>
    <title>GTA 6 Coming November 19</title>
    <link>https://news.google.com/rss/articles/abc1</link>
    <guid>https://news.google.com/rss/articles/abc1</guid>
    <source>BBC News</source>
    <pubDate>Mon, 22 Nov 2026 10:00:00 GMT</pubDate>
  </item>
  <item>
    <title>PC Requirements Announced</title>
    <link>https://news.google.com/rss/articles/def2</link>
    <guid>https://news.google.com/rss/articles/def2</guid>
    <source>Bloomberg</source>
  </item>
</channel>
</rss>"""


REDDIT_JSON = """{
  "data": {
    "children": [
      {
        "data": {
          "id": "t3_xyz1",
          "title": "GTA 6 trailer breakdown",
          "url": "https://reddit.com/r/GTA6/comments/xyz1",
          "selftext": "Great breakdown of the trailer"
        }
      },
      {
        "data": {
          "id": "t3_xyz2",
          "title": "PC requirements leak",
          "url": "https://reddit.com/r/GTA6/comments/xyz2",
          "selftext": ""
        }
      }
    ]
  }
}"""


class FakeResp:
    status_code = 200

    def __init__(self, content: str):
        self.content = content.encode()

    def raise_for_status(self):
        pass


def test_fetch_news_items_parses_rss(monkeypatch):
    called = {"urls": []}

    def fake_get(url, headers=None, timeout=None):
        called["urls"].append(url)
        if "news.google.com" in url:
            return FakeResp(RSS)
        return FakeResp(REDDIT_JSON)

    items = fetch_news_items(http_get=fake_get)
    assert called["urls"][0] == (
        "https://news.google.com/rss/search?q=GTA+6&hl=en-US&gl=US&ceid=US:en"
    )
    assert "https://www.reddit.com/r/GTA6/new.json?limit=10" in called["urls"]
    assert len(items) == 4  # 2 RSS + 2 Reddit
    assert items[0]["external_id"] == "https://news.google.com/rss/articles/abc1"
    assert items[0]["title"] == "GTA 6 Coming November 19"
    assert items[0]["url"] == "https://news.google.com/rss/articles/abc1"
    assert items[0]["source"] == "BBC News"
    assert items[2]["source"] == "reddit_gta6"
    assert items[2]["external_id"] == "reddit:t3_xyz1"
    assert items[2]["title"] == "GTA 6 trailer breakdown"


def test_fetch_news_items_skips_bad_source(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        if "news.google.com" in url:
            raise Exception("network down")
        return FakeResp(REDDIT_JSON)

    items = fetch_news_items(http_get=fake_get)
    assert len(items) == 2
    assert all(i["source"] == "reddit_gta6" for i in items)
    assert items[0]["title"] == "GTA 6 trailer breakdown"


def test_fetch_news_items_dedupe_by_external_id(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return FakeResp(RSS)

    items = fetch_news_items(http_get=fake_get)
    ids = [i["external_id"] for i in items]
    assert len(ids) == len(set(ids))


def test_init_post_creates_draft(tmp_path):
    from clipping_tools.db import init_db

    db = str(tmp_path / "state.db")
    conn = init_db(db)
    conn.execute(
        "INSERT INTO posts(id, caption, status, angle, platform, idempotency_key) "
        "VALUES(1, 'existing', 'pending', 'news', 'x', 'news:existing')"
    )
    conn.commit()
    conn.close()

    item = {
        "external_id": "news:ext-1",
        "title": "News headline",
        "url": "https://example.com/news/1",
        "posted_at": "Mon, 22 Nov 2026 10:00:00 GMT",
        "source": "BBC News",
    }
    post_id = init_post(init_db(db), item)
    assert post_id > 1  # new row

    conn = init_db(db)
    row = conn.execute(
        "SELECT caption, status, angle, platform, idempotency_key FROM posts WHERE id=?",
        (post_id,),
    ).fetchone()
    conn.close()
    assert row["status"] == "pending"
    assert row["angle"] == "news"
    assert row["platform"] == "x"
    assert row["idempotency_key"] == "news:news:ext-1"
    assert "News headline" in row["caption"]
    assert "🎥 @RockstarGames" in row["caption"]


def test_init_post_dedupe(tmp_path):
    from clipping_tools.db import init_db

    db = str(tmp_path / "state.db")
    conn = init_db(db)
    conn.execute(
        "INSERT INTO posts(id, caption, status, angle, platform, idempotency_key) "
        "VALUES(1, 'existing', 'pending', 'news', 'x', 'news:dup-1')"
    )
    conn.commit()
    conn.close()

    item = {
        "external_id": "dup-1",
        "title": "Duplicate headline",
        "url": "https://example.com/news/dup",
        "posted_at": "",
        "source": "BBC News",
    }
    post_id = init_post(init_db(db), item)
    assert post_id == 1  # existing row returned, no duplicate
