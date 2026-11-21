"""RED: Phase 2 — pacing & transitions.
Jump-cut silence gaps, zoom emphasis on high-energy words,
impact flashes at audio spikes, and speed ramps.
"""
from __future__ import annotations

from clipping_tools.review.render import (
    detect_segments,
    build_segment_filter,
    build_paced_filter,
    _word_score,
    font_path,
)


# ── Segment detection ──────────────────────────────────────────────────────

def test_detect_segments_removes_silence_gaps():
    """Gaps > 0.4s between words are cut out (jump-cut)."""
    words = [
        {"word": "hey", "start": 0.0, "end": 0.5},
        {"word": "you", "start": 1.0, "end": 1.5},   # 0.5s gap after "hey"
        {"word": "WATCH", "start": 1.6, "end": 2.0},
    ]
    segs = detect_segments(words, [], 25.0)
    # Two segments: [0.0-0.5] and [1.0-2.0], gap removed
    assert len(segs) == 2
    assert segs[0]["start"] == 0.0 and segs[0]["end"] == 0.5
    assert segs[1]["start"] == 1.0 and segs[1]["end"] == 2.0


def test_detect_segments_keeps_small_gaps():
    """Gaps <= 0.4s are NOT cut (words flow together)."""
    words = [
        {"word": "hey", "start": 0.0, "end": 0.5},
        {"word": "you", "start": 0.6, "end": 1.0},   # 0.1s gap — kept
    ]
    segs = detect_segments(words, [], 25.0)
    assert len(segs) == 1
    assert segs[0]["start"] == 0.0 and segs[0]["end"] == 1.0


def test_detect_segments_marks_high_energy_zoom():
    """Segments containing high energy peaks get type='zoom'."""
    words = [
        {"word": "hey", "start": 0.0, "end": 0.5},
        {"word": "INSANE", "start": 2.0, "end": 2.5},
        {"word": "clip", "start": 2.6, "end": 3.0},
    ]
    peaks = [{"t": 2.0, "rms": 0.9}]   # high energy at t=2.0
    segs = detect_segments(words, peaks, 25.0)
    zoom_segs = [s for s in segs if s.get("type") == "zoom"]
    assert len(zoom_segs) >= 1
    assert any(s["start"] <= 2.0 <= s["end"] for s in zoom_segs)


def test_detect_segments_max_duration():
    """No segment exceeds max_seg duration."""
    words = [
        {"word": "a", "start": 0.0, "end": 0.5},
        {"word": "b", "start": 0.6, "end": 1.0},
        {"word": "c", "start": 1.1, "end": 1.5},
        {"word": "d", "start": 1.6, "end": 2.0},
    ]
    segs = detect_segments(words, [], 25.0, max_seg=1.0)
    for s in segs:
        assert s["end"] - s["start"] <= 1.0 + 1e-6


def test_detect_segments_empty_words():
    """No words → single segment covering the whole clip."""
    segs = detect_segments([], [], 30.0)
    assert len(segs) == 1
    assert segs[0]["start"] == 0.0
    assert segs[0]["end"] == 30.0


def test_detect_segments_preserves_entire_clip_without_gaps():
    """Continuous speech → one segment (no unnecessary cuts)."""
    words = [
        {"word": "hey", "start": 0.0, "end": 0.5},
        {"word": "you", "start": 0.5, "end": 1.0},
        {"word": "WATCH", "start": 1.0, "end": 1.5},
    ]
    segs = detect_segments(words, [], 25.0)
    assert len(segs) == 1
    assert segs[0]["start"] == 0.0
    assert segs[0]["end"] == 1.5


# ── Segment filter ─────────────────────────────────────────────────────────

def test_build_segment_filter_normal():
    """Normal segment: trim + setpts only."""
    seg = {"start": 0.0, "end": 1.0, "type": "normal"}
    vf = build_segment_filter(seg, 0)
    # build_segment_filter returns a list now
    assert any("trim=start=0.0:end=1.0" in f for f in vf)
    assert any("setpts=PTS-STARTPTS" in f for f in vf)


def test_build_segment_filter_zoom():
    """Zoom segment: adds zoompan filter."""
    seg = {"start": 2.0, "end": 2.5, "type": "zoom"}
    vf = build_segment_filter(seg, 1)
    assert any("zoompan" in f for f in vf)


def test_build_segment_filter_flash():
    """Flash segment: adds white flash overlay."""
    seg = {"start": 5.0, "end": 5.05, "type": "flash"}
    vf = build_segment_filter(seg, 2)
    joined = ";".join(vf)
    assert "color" in joined or "flash" in joined


# ── Paced filter graph ─────────────────────────────────────────────────────

def test_build_paced_filter_concats_segments():
    """Multiple segments are concatenated with concat filter."""
    segs = [
        {"start": 0.0, "end": 0.5, "type": "normal"},
        {"start": 1.0, "end": 1.5, "type": "normal"},
    ]
    font = font_path()
    hook_esc = "TEST"
    vf, af = build_paced_filter(segs, ass_path="/tmp/c.ass", hook="TEST",
                                font=font, hook_esc=hook_esc)
    assert "concat" in vf


def test_build_paced_filter_single_segment():
    """Single segment: no concat needed."""
    segs = [{"start": 0.0, "end": 1.0, "type": "normal"}]
    font = font_path()
    hook_esc = "TEST"
    vf, af = build_paced_filter(segs, ass_path="/tmp/c.ass", hook="TEST",
                                font=font, hook_esc=hook_esc)
    assert "concat" not in vf


# ── Word scoring ───────────────────────────────────────────────────────────

def test_word_score_high_for_all_caps_hook_word():
    """ALL-CAPS hook word scores highest."""
    w = {"word": "INSANE", "start": 2.0, "end": 2.5}
    peaks = [{"t": 2.0, "rms": 0.9}]
    s = _word_score(w, peaks)
    assert s > 3.0, f"score={s} too low for caps+keyword+energy"


def test_word_score_low_for_normal_word():
    """Normal word scores low."""
    w = {"word": "the", "start": 2.0, "end": 2.5}
    peaks = [{"t": 10.0, "rms": 0.1}]   # energy far away
    s = _word_score(w, peaks)
    assert s < 1.0, f"score={s} too high for normal word"
