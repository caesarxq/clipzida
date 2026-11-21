"""RED: Phase 3 — impact flashes at energy spikes + speed ramps.
"""
from __future__ import annotations

from clipping_tools.review.render import (
    detect_segments,
    build_segment_filter,
    build_paced_filter,
    flash_overlays,
    speed_ramp_factor,
)


# ── Flash overlays ──────────────────────────────────────────────────────────

def test_flash_overlays_creates_white_flash_at_high_energy_peaks():
    """Each energy peak with RMS > 0.7 gets a 1-frame flash at its timestamp."""
    peaks = [
        {"t": 2.0, "rms": 0.8},   # high energy → flash
        {"t": 5.0, "rms": 0.3},   # low energy → no flash
        {"t": 9.0, "rms": 0.9},   # high energy → flash
    ]
    flashes = flash_overlays(peaks, threshold=0.7)
    assert len(flashes) == 2
    assert flashes[0]["t"] == 2.0
    assert flashes[1]["t"] == 9.0
    assert all(f["duration"] <= 0.05 for f in flashes)


def test_flash_overlays_empty_when_no_high_energy():
    """No peaks above threshold → no flashes."""
    peaks = [{"t": 1.0, "rms": 0.4}, {"t": 3.0, "rms": 0.5}]
    assert flash_overlays(peaks, threshold=0.7) == []


def test_build_segment_filter_flash_has_overlay():
    """Flash segment: adds white flash overlay at segment start."""
    seg = {"start": 5.0, "end": 5.05, "type": "flash"}
    vf = build_segment_filter(seg, 2)
    joined = ";".join(vf)
    assert "color" in joined and "overlay" in joined


# ── Speed ramps ─────────────────────────────────────────────────────────────

def test_speed_ramp_factor_high_energy_slow_mo():
    """Very high energy → 0.5x slow motion."""
    factor = speed_ramp_factor({"t": 2.0, "rms": 0.9})
    assert factor == 0.5


def test_speed_ramp_factor_medium_energy_normal():
    """Medium energy → 1.0x normal speed."""
    factor = speed_ramp_factor({"t": 2.0, "rms": 0.5})
    assert factor == 1.0


def test_speed_ramp_factor_low_energy_fast_forward():
    """Low energy → 1.5x fast forward."""
    factor = speed_ramp_factor({"t": 2.0, "rms": 0.1})
    assert factor == 1.5


def test_speed_ramp_factor_boundary_0_7():
    """RMS exactly 0.7 → 1.0x (not slow-mo, not fast)."""
    factor = speed_ramp_factor({"t": 2.0, "rms": 0.7})
    assert factor == 1.0


def test_detect_segments_marks_high_energy_as_zoom_with_speed_ramp():
    """Segments with high energy peaks get type='zoom' with speed_ramp=0.5."""
    words = [
        {"word": "hey", "start": 0.0, "end": 0.5},
        {"word": "INSANE", "start": 2.0, "end": 2.5},
        {"word": "clip", "start": 2.6, "end": 3.0},
    ]
    peaks = [{"t": 2.0, "rms": 0.9}]   # very high energy
    segs = detect_segments(words, peaks, 25.0)
    zoom_segs = [s for s in segs if s.get("type") == "zoom"]
    assert len(zoom_segs) >= 1
    assert any(s.get("speed_ramp") == 0.5 for s in zoom_segs)


def test_detect_segments_low_energy_gets_speed_ramp_1_5():
    """Segments with only low energy get speed_ramp=1.5 (fast forward)."""
    words = [
        {"word": "hey", "start": 0.0, "end": 0.5},
        {"word": "you", "start": 0.6, "end": 1.0},
        {"word": "walking", "start": 1.1, "end": 2.0},
    ]
    peaks = [{"t": 1.0, "rms": 0.1}]   # low energy
    segs = detect_segments(words, peaks, 25.0)
    normal_segs = [s for s in segs if s.get("type") == "normal"]
    assert len(normal_segs) >= 1
    assert any(s.get("speed_ramp") == 1.5 for s in normal_segs)


# ── build_paced_filter applies speed ramps ──────────────────────────────────

def test_build_paced_filter_applies_speed_ramp(monkeypatch, tmp_path):
    """Segments with speed_ramp != 1.0 get setpts adjustment."""
    from clipping_tools.review.render import font_path
    segs = [
        {"start": 0.0, "end": 1.0, "type": "normal", "speed_ramp": 0.5},
        {"start": 1.0, "end": 2.0, "type": "normal", "speed_ramp": 1.0},
    ]
    font = font_path()
    hook_esc = "TEST"
    vf, af = build_paced_filter(
        segs, ass_path="/tmp/c.ass", hook="TEST", font=font, hook_esc=hook_esc
    )
    # Slow-mo segment: setpts multiplied by 2 (PTS-STARTPTS*2)
    assert "setpts=(PTS-STARTPTS)*2.0" in vf
    # Normal segment: setpts = PTS-STARTPTS (factor 1.0)
    assert "setpts=PTS-STARTPTS" in vf
