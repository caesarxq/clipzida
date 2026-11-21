"""RED: Phase 5 — Format Variants.
1:1 square output for Facebook/IG feed, loop-friendly seamless rendering.
"""
from __future__ import annotations

from pathlib import Path
import json

from clipping_tools.review.render import (
    build_square_filter,
    build_loop_filter,
    render_variant,
)


# ── Square filter ──────────────────────────────────────────────────────────

def test_build_square_filter_crops_to_1_1():
    """Square filter: scale to fit, crop center to 1080x1080."""
    vf = build_square_filter("/tmp/c.ass", "TEST HOOK", font_path="/tmp/font.ttf")
    assert "scale=1080:1080" in vf or "force_original_aspect_ratio=decrease" in vf
    assert "crop=1080:1080" in vf
    assert "subtitles=" in vf
    assert "drawtext=" in vf


def test_build_square_filter_has_1080x1080_output():
    """Final output must be 1080x1080."""
    vf = build_square_filter("/tmp/c.ass", "TEST", font_path="/tmp/font.ttf")
    assert "1080:1080" in vf


# ── Loop-friendly filter ───────────────────────────────────────────────────

def test_build_loop_filter_matches_end_to_start():
    """Loop filter: crossfade last 0.5s into first 0.5s for seamless loop."""
    vf, af = build_loop_filter(
        segs=[{"start": 0.0, "end": 5.0, "type": "normal"}],
        ass_path="/tmp/c.ass",
        hook="TEST",
        font_path="/tmp/font.ttf",
        loop_duration=0.5,
    )
    # Should contain xfade or similar crossfade filter
    assert "xfade" in vf or "overlay" in vf
    assert "[out]" in vf


def test_build_loop_filter_single_segment():
    """Loop with single segment still produces valid filtergraph."""
    vf, af = build_loop_filter(
        segs=[{"start": 0.0, "end": 3.0, "type": "normal"}],
        ass_path="/tmp/c.ass",
        hook="TEST",
        font_path="/tmp/font.ttf",
        loop_duration=0.3,
    )
    assert "1080:1920" in vf or "1080:1080" in vf


# ── render_variant ─────────────────────────────────────────────────────────

def test_render_variant_square(monkeypatch, tmp_path):
    """render_variant with variant='square' produces 1080x1080 output."""
    import clipping_tools.review.render as render_mod
    from clipping_tools.db import init_db
    import os
    from unittest.mock import patch as mock_patch
    import subprocess

    d = tmp_path
    db = os.path.join(d, "state.db")
    conn = init_db(db)
    conn.execute("INSERT INTO sources(id,platform,external_id,name) VALUES(1,'twitch','s','s')")
    conn.execute(
        "INSERT INTO clips_raw(id,source_id,external_id,url,title,duration,created_at,status) "
        "VALUES(16,1,'c','https://clips.twitch.tv/c','HOOK',25,'2026-01-01T00:00:00+00:00','new')"
    )
    conn.execute(
        "INSERT INTO posts(id,render_id,caption,status,idempotency_key,angle) "
        "VALUES(16,NULL,'HOOK','approved','clip-16','funny')"
    )
    conn.commit()
    conn.close()

    # Create dummy source file so ffmpeg command can reference it
    (Path(d) / "source_16.mp4").write_bytes(b"\x00" * 100)

    captured = {}

    def fake_render(src, out, ass, hook, **kwargs):
        captured["out"] = str(out)
        captured["kwargs"] = kwargs
        return {"streams": [{"codec_name": "h264", "width": 1080, "height": 1080}]}

    monkeypatch.setattr(render_mod, "download_clip", lambda url, dest: Path(dest).write_bytes(b"\x00" * 100))
    monkeypatch.setattr(render_mod, "extract_wav", lambda src, wav: None)
    monkeypatch.setattr(render_mod, "transcribe", lambda wav: [
        {"word": "hey", "start": 0.0, "end": 0.5},
        {"word": "you", "start": 0.5, "end": 1.0},
    ])
    monkeypatch.setattr(render_mod, "energy_peaks", lambda wav: [])
    monkeypatch.setattr(render_mod, "render", fake_render)
    monkeypatch.setattr(render_mod, "make_enhanced_ass", lambda *a, **k: None)
    monkeypatch.setattr(render_mod, "WORK", Path(d))
    monkeypatch.setattr(render_mod, "make_proxy", lambda out: None)

    # Mock subprocess.run to avoid actual ffmpeg execution
    def fake_subprocess_run(*args, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = ""
            stderr = ""
        # ffprobe call returns JSON
        args_list = list(args[0]) if args else []
        if "ffprobe" in str(args_list) or any("ffprobe" in str(a) for a in args_list):
            FakeResult.stdout = json.dumps({
                "streams": [
                    {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1080},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": "25.0", "size": "1000000"},
            })
        return FakeResult()

    with mock_patch.object(subprocess, "run", side_effect=fake_subprocess_run):
        result = render_mod.render_variant(16, db, variant="square")

    assert result["variant"] == "square"
    assert result["width"] == 1080
    assert result["height"] == 1080
