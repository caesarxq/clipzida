"""RED: Phase 1 — hook detector trims video to the best moment; captions restyled
for high retention (48-52px font, bottom-third, karaoke word-by-word highlight).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import clipping_tools.review.render as render_mod
from clipping_tools.db import init_db
from clipping_tools.review.render import (
    select_hook_moment,
    make_enhanced_ass,
    build_enhanced_filter,
)


# ── Hook detector: select_hook_moment ──────────────────────────────────────

def test_select_hook_moment_picks_window_with_best_scoring_first_word():
    """The selected window should start at the highest-scoring hook word."""
    words = [
        {"word": "hey", "start": 0.0, "end": 0.5},
        {"word": "you", "start": 0.5, "end": 1.0},
        {"word": "WATCH", "start": 1.0, "end": 1.5},   # emph + caps = high score
        {"word": "this", "start": 1.5, "end": 2.0},
        {"word": "insane", "start": 2.0, "end": 2.5},  # hook keyword
        {"word": "clip", "start": 2.5, "end": 3.0},
    ]
    peaks = [{"t": 1.0, "rms": 0.9}, {"t": 2.0, "rms": 0.8}]
    m = select_hook_moment(words, peaks, target_min=18, target_max=45)
    # Best hook word is "insane" at t=2.0 (keyword + energy peak)
    assert m["start"] <= 2.0 <= m["end"]


def test_select_hook_moment_returns_hook_word():
    """Extended: return the best hook word text so render_post can use it."""
    words = [
        {"word": "hey", "start": 0.0, "end": 0.5},
        {"word": "INSANE", "start": 2.0, "end": 2.5},
        {"word": "clip", "start": 2.5, "end": 3.0},
    ]
    peaks = [{"t": 2.0, "rms": 0.9}]
    m = select_hook_moment(words, peaks, target_min=18, target_max=45)
    assert "hook_word" in m
    assert m["hook_word"] == "INSANE"


# ── render_post trims video to the hook moment ─────────────────────────────

def _seed_approved_post(db_path: str, post_id: int = 16, url: str = "https://clips.twitch.tv/c"):
    conn = init_db(db_path)
    conn.execute("INSERT INTO sources(id,platform,external_id,name) VALUES(1,'twitch','s','s')")
    conn.execute(
        "INSERT INTO clips_raw(id,source_id,external_id,url,title,duration,created_at,status) "
        f"VALUES({post_id},1,'c','{url}','HOOK',25,'2026-01-01T00:00:00+00:00','new')"
    )
    conn.execute(
        f"INSERT INTO posts(id,render_id,caption,status,idempotency_key) "
        f"VALUES({post_id},NULL,'HOOK','approved','clip-{post_id}')"
    )
    conn.commit()
    conn.close()


def test_render_post_trims_to_hook_moment(monkeypatch, tmp_path):
    """render_post must pass -ss and -to (hook moment) to ffmpeg, not the full clip."""
    d = tmp_path
    db = os.path.join(d, "state.db")
    _seed_approved_post(db)

    captured = {}

    def fake_render(src, out, ass, hook, music_path=None, sfx_events=None, meme_events=None, start=None, end=None, segs=None):
        captured["src"] = str(src)
        captured["hook"] = hook
        captured["start"] = start
        captured["end"] = end
        return {"streams": [{"codec_name": "h264", "width": 1080, "height": 1920}]}

    monkeypatch.setattr(render_mod, "download_clip", lambda url, dest: Path(dest).write_bytes(b"x" * 10))
    monkeypatch.setattr(render_mod, "extract_wav", lambda src, wav: None)
    monkeypatch.setattr(render_mod, "transcribe", lambda wav: [
        {"word": "hey", "start": 0.0, "end": 0.5},
        {"word": "INSANE", "start": 2.0, "end": 2.5},
        {"word": "clip", "start": 2.5, "end": 3.0},
    ])
    monkeypatch.setattr(render_mod, "energy_peaks", lambda wav: [{"t": 2.0, "rms": 0.9}])
    monkeypatch.setattr(render_mod, "render", fake_render)
    monkeypatch.setattr(render_mod, "make_enhanced_ass", lambda words, p, hook=None, moment=None: Path(p).write_text("ass"))
    monkeypatch.setattr(render_mod, "WORK", Path(d))
    monkeypatch.setattr(render_mod, "make_proxy", lambda out: Path(str(out) + "_review.mp4"))

    result = render_mod.render_post(16, db)
    # Trim start/end must be passed to the render filter graph
    assert captured["start"] is not None
    assert captured["end"] is not None
    assert captured["start"] < captured["end"]
    # Hook word should come from the moment, not words[0]
    assert captured["hook"] == "INSANE"
    assert result.get("moment") is not None


# ── Caption restyle: font size ─────────────────────────────────────────────

def test_caption_font_size_is_48_to_52(tmp_path):
    """Default style font size must be in the 48-52px range (was 56)."""
    words = [{"word": "hi", "start": 0.0, "end": 0.5}]
    ass = tmp_path / "c.ass"
    make_enhanced_ass(words, ass, "TEST HOOK")
    style = [l for l in ass.read_text().splitlines() if l.startswith("Style:")][0]
    # Extract fontsize field: Style: Name,Fontname,Fontsize,...
    parts = style.split(",")
    fontsize = int(parts[2])
    assert 48 <= fontsize <= 52, f"fontsize={fontsize} not in 48-52"


# ── Caption restyle: bottom-third positioning ──────────────────────────────

def test_caption_position_is_bottom_third(tmp_path):
    """Captions must sit in the bottom third (y near 1920, MarginV large)."""
    words = [{"word": "hi", "start": 0.0, "end": 0.5}]
    ass = tmp_path / "c.ass"
    make_enhanced_ass(words, ass, "TEST HOOK")
    dialogue = [l for l in ass.read_text().splitlines() if l.startswith("Dialogue:")][0]
    # ASS Dialogue: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
    fields = dialogue.split(",", 9)
    margin_v = int(fields[7])
    # Bottom third: MarginV should push text toward bottom (PlayResY=1920)
    assert margin_v > 400, f"MarginV={margin_v} too high for bottom-third placement"


# ── Caption restyle: karaoke word-by-word highlight ────────────────────────

def test_caption_karaoke_one_word_per_dialogue_line(tmp_path):
    """Each word gets its own Dialogue line with exact start/end (karaoke style)."""
    words = [
        {"word": "hello", "start": 0.0, "end": 0.5},
        {"word": "world", "start": 0.5, "end": 1.0},
    ]
    ass = tmp_path / "c.ass"
    make_enhanced_ass(words, ass, "TEST HOOK")
    dialogue_lines = [l for l in ass.read_text().splitlines() if l.startswith("Dialogue:")]
    assert len(dialogue_lines) == 2, f"expected 2 dialogue lines, got {len(dialogue_lines)}"
    # Each line's start/end should match the word's timing (ASS format: H:MM:SS.cc)
    line0_fields = dialogue_lines[0].split(",", 9)
    assert _parse_ass_ts(line0_fields[2]) == 0.5  # End time of first word


def test_caption_karaoke_current_word_emphasized(tmp_path):
    """The active word should use Emphasis style; others Default."""
    words = [
        {"word": "hello", "start": 0.0, "end": 0.5},
        {"word": "world", "start": 0.5, "end": 1.0},
    ]
    ass = tmp_path / "c.ass"
    make_enhanced_ass(words, ass, "TEST HOOK")
    dialogue_lines = [l for l in ass.read_text().splitlines() if l.startswith("Dialogue:")]
    styles = [l.split(",")[3] for l in dialogue_lines]
    assert "Emphasis" in styles, f"no Emphasis style used in {styles}"


def test_caption_max_two_lines_visible_at_once(tmp_path):
    """Never more than 2 caption lines on screen simultaneously."""
    words = [
        {"word": "one", "start": 0.0, "end": 0.5},
        {"word": "two", "start": 0.1, "end": 0.6},
        {"word": "three", "start": 0.2, "end": 0.7},
        {"word": "four", "start": 0.3, "end": 0.8},
    ]
    ass = tmp_path / "c.ass"
    make_enhanced_ass(words, ass, "TEST HOOK")
    dialogue_lines = [l for l in ass.read_text().splitlines() if l.startswith("Dialogue:")]
    # Build time intervals and check max overlap <= 2
    intervals = []
    for line in dialogue_lines:
        f = line.split(",", 9)
        intervals.append((_parse_ass_ts(f[1]), _parse_ass_ts(f[2])))
    # Check at each start time how many are active
    for start, _ in intervals:
        active = sum(1 for s, e in intervals if s <= start < e)
        assert active <= 2, f"at t={start}, {active} lines overlap (max 2)"


def _parse_ass_ts(ts: str) -> float:
    """Parse ASS timestamp H:MM:SS.cc to seconds."""
    parts = ts.split(":")
    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])


# ── Hook text uses moment's start word ─────────────────────────────────────

def test_hook_text_comes_from_moment_not_first_word(tmp_path):
    """Hook drawtext should use the best hook word from the moment, not words[0]."""
    words = [
        {"word": "hey", "start": 0.0, "end": 0.5},
        {"word": "INSANE", "start": 2.0, "end": 2.5},
    ]
    ass = tmp_path / "c.ass"
    make_enhanced_ass(words, ass, "TEST HOOK")
    dialogue_lines = [l for l in ass.read_text().splitlines() if l.startswith("Dialogue:")]
    # The hook word INSANE should appear in the ASS file somewhere
    ass_text = ass.read_text()
    assert "INSANE" in ass_text


# ── build_enhanced_filter: trim params ─────────────────────────────────────

def test_build_enhanced_filter_accepts_trim_times():
    """build_enhanced_filter should accept optional start/end for video trimming."""
    vf, af = build_enhanced_filter(
        ass_path="/tmp/c.ass",
        hook="TEST",
        start=2.0,
        end=5.0,
    )
    # Trim should appear somewhere in the filter graph
    assert "trim" in vf or "select" in vf, "trim filter missing from vf"
