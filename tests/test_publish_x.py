"""RED: X (Twitter) publish adapter.
OAuth 2.0 with PKCE + hybrid media upload (v2 media upload -> v2 POST /2/tweets).
Follows the same pattern as publish/youtube.py and publish/tiktok.py.
"""
from __future__ import annotations

import json
import os

from clipping_tools.publish.x import (
    build_post_metadata,
    init_media_upload,
    append_media_chunk,
    finalize_media,
    create_post,
    publish_to_x,
)


# ── Metadata ──────────────────────────────────────────────────────────

def test_build_post_metadata_truncates_and_adds_hashtags():
    md = build_post_metadata({"caption": "HE LOOKED AT ME", "angle": "funny", "hashtags": "#gta6 #clips"})
    assert md["text"].startswith("HE LOOKED AT ME")
    assert "#gta6 #clips" in md["text"]
    assert len(md["text"]) <= 280


def test_build_post_metadata_empty_caption():
    md = build_post_metadata({"caption": "", "angle": "news"})
    assert md["text"] == "GTA 6 moment"


# ── Media upload: INIT ───────────────────────────────────────────────

def test_init_media_upload_returns_media_id(monkeypatch):
    class FakeResp:
        status_code = 200
        def __init__(self, text):
            self._text = text
        def json(self):
            return json.loads(self._text)
        def raise_for_status(self):
            pass

    monkeypatch.setenv("X_CLIENT_ID", "cid")
    monkeypatch.setenv("X_CLIENT_SECRET", "csec")

    called = {}
    def fake_post(url, *, data=None, headers=None, auth=None, timeout=None):
        called["url"] = url
        called["has_media_category"] = data.get("media_category") == "tweet_video"
        called["has_total_bytes"] = data.get("total_bytes") == "11372195"
        called["has_bearer"] = headers.get("Authorization", "").startswith("Bearer ")
        return FakeResp('{"media_id": "1638400000000000000", "media_id_string": "1638400000000000000", "size": 11372195, "expires_after_secs": 86400}')

    media_id = init_media_upload("/tmp/v.mp4", 11372195, "at", transport=fake_post)
    assert media_id == "1638400000000000000"
    assert called["has_media_category"]
    assert called["has_total_bytes"]
    assert called["has_bearer"]


# ── Media upload: APPEND ─────────────────────────────────────────────

def test_append_media_chunk_uses_media_id_and_segment(monkeypatch):
    class FakeResp:
        status_code = 200
        text = "ok"
        def raise_for_status(self):
            pass

    monkeypatch.setenv("X_CLIENT_ID", "cid")
    monkeypatch.setenv("X_CLIENT_SECRET", "csec")

    captured = {}
    def fake_post(url, *, data=None, files=None, headers=None, auth=None, timeout=None):
        captured["url"] = url
        captured["has_media_id"] = data.get("media_id") == "1638400000000000000"
        captured["has_segment"] = data.get("segment_index") == "0"
        captured["has_command"] = data.get("command") == "APPEND"
        return FakeResp()

    open("/tmp/v.mp4", "wb").write(b"\x00" * 1000)
    append_media_chunk("/tmp/v.mp4", "1638400000000000000", 0, access_token="at",
                       transport=fake_post)
    assert captured["has_media_id"]
    assert captured["has_segment"]
    assert captured["has_command"]


# ── Media upload: FINALIZE ───────────────────────────────────────────

def test_finalize_media_returns_media_id(monkeypatch):
    class FakeResp:
        status_code = 200
        def __init__(self, text):
            self._text = text
        def json(self):
            return json.loads(self._text)
        def raise_for_status(self):
            pass

    monkeypatch.setenv("X_CLIENT_ID", "cid")
    monkeypatch.setenv("X_CLIENT_SECRET", "csec")

    monkeypatch.setattr("clipping_tools.publish.x.time.sleep", lambda s: None)

    def fake_post(url, *, data=None, headers=None, auth=None, timeout=None):
        return FakeResp('{"media_id": "1638400000000000000", "media_id_string": "1638400000000000000", "processing_info": {"state": "succeeded"}}')

    mid = finalize_media("1638400000000000000", "at", transport=fake_post)
    assert mid == "1638400000000000000"


# ── Create post ──────────────────────────────────────────────────────

def test_create_post_attaches_media(monkeypatch):
    class FakeResp:
        status_code = 200
        def __init__(self, text):
            self._text = text
        def json(self):
            return json.loads(self._text)
        def raise_for_status(self):
            pass

    monkeypatch.setenv("X_CLIENT_ID", "cid")
    monkeypatch.setenv("X_CLIENT_SECRET", "csec")

    captured = {}
    def fake_post(url, *, json=None, headers=None, auth=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResp('{"data": {"id": "1876543210987654321", "text": "HE LOOKED AT ME #gta6 #shorts"}}')

    result = create_post("HE LOOKED AT ME #gta6 #shorts", ["1638400000000000000"], "at", transport=fake_post)
    assert result["id"] == "1876543210987654321"
    assert captured["json"]["media"]["media_ids"] == ["1638400000000000000"]
    assert captured["json"]["text"] == "HE LOOKED AT ME #gta6 #shorts"


# ── Full flow ────────────────────────────────────────────────────────

def test_publish_to_x_writes_back_external_id_and_url(monkeypatch, tmp_path):
    import clipping_tools.publish.x as xmod
    from clipping_tools.db import init_db

    d = tmp_path
    db = os.path.join(d, "state.db")
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id,render_id,caption,status,angle) "
                 "VALUES(16,1,'HE LOOKED AT ME','rendered','funny')")
    conn.execute("INSERT INTO renders(id,clip_id,path) VALUES(1,16,?)", (os.path.join(d, "v.mp4"),))
    # X credentials come from env vars (set via monkeypatch below), not DB
    conn.commit(); conn.close()
    open(os.path.join(d, "v.mp4"), "wb").write(b"\x00" * 100)

    class FakeResp:
        status_code = 200
        def __init__(self, text):
            self._text = text
        def json(self):
            return json.loads(self._text)
        def raise_for_status(self):
            pass

    def fake_post(url, *, data=None, files=None, json=None, headers=None, auth=None, timeout=None):
        # INIT
        if data is not None and data.get("command") == "INIT":
            return FakeResp('{"media_id": "1638400000000000000", "media_id_string": "1638400000000000000", "size": 100, "expires_after_secs": 86400}')
        # APPEND
        if data is not None and data.get("command") == "APPEND":
            return FakeResp("ok")
        # FINALIZE
        if data is not None and data.get("command") == "FINALIZE":
            return FakeResp('{"media_id": "1638400000000000000", "processing_info": {"state": "succeeded"}}')
        # POST /2/tweets
        return FakeResp('{"data": {"id": "1876543210987654321", "text": "HE LOOKED AT ME #gta6 #shorts"}}')

    monkeypatch.setenv("X_CLIENT_ID", "cid")
    monkeypatch.setenv("X_CLIENT_SECRET", "csec")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", "ats")

    monkeypatch.setattr(xmod.time, "sleep", lambda s: None)
    result = publish_to_x(16, db, os.path.join(d, "v.mp4"), transport=fake_post)
    assert result["external_id"] == "1876543210987654321"
    assert result["url"].endswith("1876543210987654321")
    assert result["platform"] == "x"

    conn = init_db(db)
    row = conn.execute("SELECT external_post_id, url, status, platform FROM posts WHERE id=16").fetchone()
    assert row["external_post_id"] == "1876543210987654321"
    assert row["status"] == "published"
    assert row["platform"] == "x"


def test_publish_to_x_raises_when_no_client_id(monkeypatch, tmp_path):
    import clipping_tools.publish.x as xmod
    from clipping_tools.db import init_db

    monkeypatch.delenv("X_CLIENT_ID", raising=False)
    monkeypatch.delenv("X_CLIENT_SECRET", raising=False)

    db = os.path.join(tmp_path, "state.db")
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id,render_id,caption,status) VALUES(16,1,'x','rendered')")
    conn.commit(); conn.close()

    try:
        publish_to_x(16, db, "/tmp/v.mp4")
        assert False, "should have raised"
    except RuntimeError as e:
        assert "credential" in str(e).lower() or "client" in str(e).lower()


def test_publish_to_x_raises_when_no_access_token(monkeypatch, tmp_path):
    import clipping_tools.publish.x as xmod
    from clipping_tools.db import init_db

    monkeypatch.setenv("X_CLIENT_ID", "cid")
    monkeypatch.setenv("X_CLIENT_SECRET", "csec")
    monkeypatch.delenv("X_ACCESS_TOKEN", raising=False)

    db = os.path.join(tmp_path, "state.db")
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id,render_id,caption,status) VALUES(16,1,'x','rendered')")
    conn.commit(); conn.close()

    try:
        publish_to_x(16, db, "/tmp/v.mp4")
        assert False, "should have raised"
    except RuntimeError as e:
        assert "token" in str(e).lower() or "authorization" in str(e).lower()
