"""RED: render_post produces a review proxy when the master is over the ceiling."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import clipping_tools.review.render as render_mod


def _seed():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "state.db")
    from clipping_tools.db import init_db
    conn = init_db(db)
    conn.execute("INSERT INTO sources(id,platform,external_id,name) VALUES(1,'twitch','s','s')")
    conn.execute("INSERT INTO clips_raw(id,source_id,external_id,url,title,duration,created_at,status) "
                 "VALUES(16,1,'c','https://clips.twitch.tv/c','HOOK',25,'2026-01-01T00:00:00+00:00','new')")
    conn.execute("INSERT INTO posts(id,render_id,caption,status,idempotency_key) "
                 "VALUES(16,NULL,'HOOK','approved','clip-16')")
    conn.commit(); conn.close()
    return db, d


def test_render_post_creates_proxy(monkeypatch, tmp_path):
    db, d = _seed()
    master = Path(d) / "master.mp4"
    master.write_bytes(b"x" * 20_000_000)  # force proxy path

    monkeypatch.setattr(render_mod, "download_clip", lambda url, dest: Path(dest).write_bytes(b"x" * 10))
    monkeypatch.setattr(render_mod, "extract_wav", lambda src, wav: None)
    monkeypatch.setattr(render_mod, "transcribe", lambda wav: [{"word": "hook", "start": 0.0, "end": 1.0}])
    monkeypatch.setattr(render_mod, "energy_peaks", lambda wav: [])
    monkeypatch.setattr(render_mod, "render", lambda src, out, ass, hook: {"streams": []})
    monkeypatch.setattr(render_mod, "make_ass", lambda words, p: Path(p).write_text("ass"))
    monkeypatch.setattr(render_mod, "WORK", Path(d))

    with patch.object(render_mod, "make_proxy",
                      return_value=Path(d) / "clipzida_16_review.mp4"):
        result = render_mod.render_post(16, db)
        assert result["proxy_path"].endswith("_review.mp4")
