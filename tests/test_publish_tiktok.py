"""RED: TikTok Content Posting adapter (inbox draft mode, no audit required)."""
import json
import os
import tempfile
from unittest.mock import MagicMock

from clipping_tools.db import init_db
from clipping_tools.publish.tiktok import (
    build_post_info, fetch_status, init_publish, publish_to_tiktok, upload_video,
)


def _resp(payload, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


def _seed():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "state.db")
    conn = init_db(db)
    conn.execute("INSERT INTO posts(id,render_id,caption,status,angle,platform) "
                 "VALUES(7,3,'HOOK TITLE','rendered','funny','tiktok')")
    conn.execute("INSERT INTO renders(id,clip_id,path) VALUES(3,7,?)", (os.path.join(d, "v.mp4"),))
    conn.commit(); conn.close()
    return db, os.path.join(d, "v.mp4")


def test_build_post_info_uses_brand_hashtags_and_self_only():
    pi = build_post_info({"caption": "HOOK TITLE", "angle": "funny"})
    assert "HOOK TITLE" in pi["title"]
    assert "#gta6" in pi["description"] or "#gta6" in pi["title"]
    assert pi["privacy_level"] == "SELF_ONLY"


def test_build_post_info_credits_broadcaster():
    pi = build_post_info({"caption": "HOOK TITLE", "broadcaster": "streamerx"})
    assert "🎥 @streamerx" in pi["title"]


def test_init_publish_posts_to_inbox_endpoint():
    db, mp4 = _seed()
    open(mp4, "wb").write(b"x" * 100)
    transport = MagicMock()
    transport.post.return_value = _resp({"data": {"publish_id": "pub1", "upload_url": "https://up"}})
    pid, url = init_publish("tok", {"caption": "H", "angle": "funny"}, mp4, transport=transport)
    assert pid == "pub1" and url == "https://up"
    called_url = transport.post.call_args.args[0]
    assert "inbox/video/init" in called_url
    body = transport.post.call_args.kwargs["json"]
    assert body["source_info"]["source"] == "FILE_UPLOAD"


def test_upload_video_puts_bytes_to_upload_url(tmp_path):
    f = tmp_path / "x.mp4"
    f.write_bytes(b"x" * 16)
    transport = MagicMock()
    transport.put.return_value = _resp({"data": {}, "error": {"code": "ok"}})
    upload_video("https://up", str(f), transport=transport)
    assert transport.put.call_args.args[0] == "https://up"


def test_fetch_status_returns_publish_complete():
    transport = MagicMock()
    transport.post.return_value = _resp({"data": {"status": "PUBLISH_COMPLETE"}})
    assert fetch_status("tok", "pub1", transport=transport) == "PUBLISH_COMPLETE"


def test_publish_to_tiktok_writes_back_external_id():
    db, mp4 = _seed()
    open(mp4, "wb").write(b"x" * 100)
    transport = MagicMock()
    transport.post.side_effect = [
        _resp({"data": {"publish_id": "pub9", "upload_url": "https://up"}}),
        _resp({"data": {"status": "PUBLISH_COMPLETE"}}),
    ]
    transport.put.return_value = _resp({"data": {}, "error": {"code": "ok"}})
    result = publish_to_tiktok(7, db, mp4, access_token="tok", transport=transport)
    assert result["publish_id"] == "pub9"
    conn = init_db(db)
    assert conn.execute("SELECT status FROM posts WHERE id=7").fetchone()[0] == "published"


def test_upload_video_sends_content_range_header(tmp_path):
    """TikTok requires Content-Range bytes 0-N/N even for single-chunk uploads."""
    f = tmp_path / "x.mp4"
    f.write_bytes(b"x" * 100)
    transport = MagicMock()
    transport.put.return_value = _resp({"data": {}})
    upload_video("https://up", str(f), transport=transport)
    headers = transport.put.call_args.kwargs["headers"]
    assert headers["Content-Range"] == "bytes 0-99/100"
