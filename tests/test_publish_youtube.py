"""RED: YouTube Shorts uploader (OAuth, videos.insert, metadata + status writeback)."""
import json
import os
import tempfile
from unittest.mock import MagicMock

from clipping_tools.db import init_db
from clipping_tools.publish.youtube import build_upload_metadata, upload_to_youtube


def _seed(post_id=16):
    d = tempfile.mkdtemp()
    db = os.path.join(d, "state.db")
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id,render_id,caption,status,angle) "
                 "VALUES(?,1,'HOOK TITLE','rendered','funny')", (post_id,))
    conn.execute("INSERT INTO renders(id,clip_id,path) VALUES(1,16,?)", (os.path.join(d, "v.mp4"),))
    conn.execute("INSERT INTO tokens(service,access_token,refresh_token,expires_at,scopes) "
                 "VALUES('youtube','ya29.old','r1','2026-01-01T00:00:00+00:00','youtube')")
    conn.commit(); conn.close()
    return db, os.path.join(d, "v.mp4")


def test_upload_metadata_is_short_and_gaming():
    md = build_upload_metadata({"caption": "HOOK TITLE", "angle": "funny", "hashtags": "#gta6"})
    assert md["snippet"]["title"].startswith("HOOK TITLE")
    assert "Shorts" in md["snippet"]["title"]
    assert md["snippet"]["categoryId"] == "20"
    assert md["status"]["privacyStatus"] == "unlisted"
    assert "#Shorts" in md["snippet"]["description"]


def test_upload_metadata_credits_broadcaster_in_description():
    md = build_upload_metadata({"caption": "HOOK TITLE", "broadcaster": "streamerx"})
    assert "🎥 Gameplay by @streamerx" in md["snippet"]["description"]
    # credit lives in description, not the title
    assert "🎥" not in md["snippet"]["title"]


def test_upload_metadata_no_broadcaster_keeps_description_clean():
    md = build_upload_metadata({"caption": "HOOK TITLE"})
    assert "🎥" not in md["snippet"]["description"]


def test_upload_writes_back_external_id_and_url(monkeypatch):
    monkeypatch.setenv("YOUTUBE_ACCESS_TOKEN", "fake-token")
    db, mp4 = _seed()
    transport = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"id": "ytvid123", "snippet": {"title": "x"}}
    resp.raise_for_status.return_value = None
    transport.post.return_value = resp
    open(mp4, "wb").write(b"x")
    result = upload_to_youtube(16, db, mp4, transport=transport)
    assert result["external_id"] == "ytvid123"
    assert result["url"].endswith("ytvid123")
    conn = init_db(db)
    row = conn.execute("SELECT external_post_id, url FROM posts WHERE id=16").fetchone()
    assert row["external_post_id"] == "ytvid123"
    plat = conn.execute("SELECT status, platform FROM post_platforms WHERE post_id=16 AND platform='youtube'").fetchone()
    assert plat["status"] == "published"
    assert plat["platform"] == "youtube"
