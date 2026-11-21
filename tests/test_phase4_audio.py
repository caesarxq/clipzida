"""RED: Phase 4 — Music & Audio Design.
Audio ducking, voice EQ, angle-specific music beds, SFX layering.
"""
from __future__ import annotations

from clipping_tools.review.render import (
    audio_duck_filter,
    voice_eq_filter,
    music_bed_for_angle,
    build_enhanced_filter,
)


# ── Audio ducking ──────────────────────────────────────────────────────────

def test_audio_duck_filter_lowers_music_when_voice_present():
    """Sidechain compressor ducks music bed when voice (0:a) is loud."""
    af = audio_duck_filter(
        voice_input="[0:a]",
        music_input="[music_bed]",
        output="[music_ducked]",
        threshold=-30,      # dB — voice above this triggers duck
        ratio=4,            # 4:1 compression
        attack=0.01,        # fast attack
        release=0.2,        # smooth release
    )
    # Should contain sidechaincompressor with voice as sidechain input
    assert "sidechaincompressor" in af
    assert "[0:a]" in af
    assert "[music_bed]" in af
    assert "[music_ducked]" in af
    assert "threshold=-30" in af
    assert "ratio=4" in af


def test_audio_duck_filter_default_values():
    """Defaults: threshold=-30dB, ratio=4, attack=0.01s, release=0.2s."""
    af = audio_duck_filter("[0:a]", "[music_bed]", "[ducked]")
    assert "threshold=-30" in af
    assert "ratio=4" in af
    assert "attack=0.01" in af
    assert "release=0.2" in af


def test_audio_duck_filter_no_voice_passthrough():
    """When voice_input is None, music passes through unchanged."""
    af = audio_duck_filter(None, "[music_bed]", "[music_bed]")
    assert af == "[music_bed]"


# ── Voice EQ ───────────────────────────────────────────────────────────────

def test_voice_eq_filter_boosts_presence_and_cuts_rumble():
    """EQ: high-pass below 80Hz, presence boost around 2-5kHz for clarity."""
    af = voice_eq_filter("[0:a]", "[voice_eq]")
    assert "highpass=f=80" in af
    assert "equalizer" in af or "equalizer=" in af
    assert "[0:a]" in af
    assert "[voice_eq]" in af


def test_voice_eq_filter_presence_boost_frequencies():
    """Presence boost at 2kHz, 3kHz, 5kHz for speech intelligibility."""
    af = voice_eq_filter("[0:a]", "[voice_eq]")
    # Multiple equalizer stages for presence
    assert "equalizer=f=2000" in af or "equalizer=f=3000" in af or "equalizer=f=5000" in af


# ── Angle-specific music beds ──────────────────────────────────────────────

def test_music_bed_for_angle_funny(tmp_path):
    """Funny angle → upbeat/lo-fi music bed."""
    (tmp_path / "audio").mkdir(parents=True)
    (tmp_path / "audio" / "music_funny.mp3").write_bytes(b"")
    path = music_bed_for_angle("funny", assets_dir=str(tmp_path))
    assert path is not None
    assert path.endswith(".mp3")
    assert "music_funny" in path


def test_music_bed_for_angle_hype(tmp_path):
    """Hype angle → phonky/high-energy music bed."""
    (tmp_path / "audio").mkdir(parents=True)
    (tmp_path / "audio" / "music_hype.mp3").write_bytes(b"")
    path = music_bed_for_angle("hype", assets_dir=str(tmp_path))
    assert path is not None
    assert path.endswith(".mp3")
    assert "music_hype" in path


def test_music_bed_for_angle_news(tmp_path):
    """News angle → ambient/cinematic music bed."""
    (tmp_path / "audio").mkdir(parents=True)
    (tmp_path / "audio" / "music_news.mp3").write_bytes(b"")
    path = music_bed_for_angle("news", assets_dir=str(tmp_path))
    assert path is not None
    assert path.endswith(".mp3")
    assert "music_news" in path


def test_music_bed_for_angle_unknown_defaults(tmp_path):
    """Unknown angle → default music bed."""
    (tmp_path / "audio").mkdir(parents=True)
    (tmp_path / "audio" / "music_bed.mp3").write_bytes(b"")
    path = music_bed_for_angle("unknown_angle", assets_dir=str(tmp_path))
    assert path is not None
    assert path.endswith(".mp3")
    assert "music_bed" in path


def test_music_bed_for_angle_none():
    """None angle → no music (None)."""
    assert music_bed_for_angle(None) is None


# ── build_enhanced_filter integrates ducking + EQ ──────────────────────────

def test_build_enhanced_filter_includes_ducking_when_angle_provided():
    """When angle is provided, music bed is ducked via sidechain compressor."""
    vf, af = build_enhanced_filter(
        ass_path="/tmp/c.ass",
        hook="TEST HOOK",
        angle="funny",
        music_path="/tmp/music_funny.mp3",
    )
    assert "sidechaincompressor" in af
    assert "[music_ducked]" in af
    assert "amix" in af
    assert "[music_ducked]" in af  # ducked music goes into amix


def test_build_enhanced_filter_includes_voice_eq():
    """Voice (0:a) always gets EQ applied before amix."""
    vf, af = build_enhanced_filter(
        ass_path="/tmp/c.ass",
        hook="TEST HOOK",
    )
    assert "highpass=f=80" in af
    assert "[voice_eq]" in af


def test_build_enhanced_filter_no_music_no_ducking():
    """No music path → no ducking, just voice EQ + amix."""
    vf, af = build_enhanced_filter(
        ass_path="/tmp/c.ass",
        hook="TEST HOOK",
        music_path=None,
    )
    assert "sidechaincompressor" not in af
    assert "highpass=f=80" in af
    assert "amix" in af


def test_build_enhanced_filter_angle_unknown_uses_default_music():
    """Unknown angle falls back to default music bed path."""
    vf, af = build_enhanced_filter(
        ass_path="/tmp/c.ass",
        hook="TEST HOOK",
        angle="unknown",
        music_path="/tmp/default.mp3",
    )
    # Should still use the provided music_path since it exists
    assert "sidechaincompressor" in af


# ── SFX layering ───────────────────────────────────────────────────────────

def test_build_enhanced_filter_sfx_at_peaks_with_delay():
    """SFX events get adelay to align with their timestamps."""
    vf, af = build_enhanced_filter(
        ass_path="/tmp/c.ass",
        hook="TEST",
        sfx_events=[{"t": 2.5, "file": "/tmp/boom.mp3"}],
    )
    assert "adelay" in af
    assert "2500" in af  # 2.5s → 2500ms delay
    assert "[sfx0]" in af
    assert "amix" in af
