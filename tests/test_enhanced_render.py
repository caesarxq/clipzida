"""RED: enhanced render stage — hooks, captions, sound design, meme overlays."""
from clipping_tools.review.render import (
    select_hook_moment,
    wrap_emphasis,
    build_enhanced_filter,
    map_emoji,
)


def test_select_hook_moment_prefers_hook_keywords():
    words = [
        {"word": "hey", "start": 0.0, "end": 0.5},
        {"word": "you", "start": 0.5, "end": 1.0},
        {"word": "WATCH", "start": 1.0, "end": 1.5},
        {"word": "this", "start": 1.5, "end": 2.0},
        {"word": "insane", "start": 2.0, "end": 2.5},
        {"word": "clip", "start": 2.5, "end": 3.0},
    ]
    peaks = [{"t": 1.0, "rms": 0.9}, {"t": 2.0, "rms": 0.8}]
    m = select_hook_moment(words, peaks, target_min=18, target_max=45)
    # Hook word "insane" at t=2.0 should be inside the selected window
    assert m["start"] <= 2.0 <= m["end"]
    assert m["end"] - m["start"] == 3.0  # clipped to clip length


def test_select_hook_moment_empty_words():
    m = select_hook_moment([], [], target_min=18, target_max=45)
    assert m["start"] == 0.0


def test_wrap_emphasis_marks_caps_and_exclamations():
    units = [{"word": "OMG", "start": 0.0, "end": 0.5},
             {"word": "this", "start": 0.5, "end": 1.0},
             {"word": "is", "start": 1.0, "end": 1.5},
             {"word": "crazy!", "start": 1.5, "end": 2.0}]
    wrapped = wrap_emphasis(units)
    assert any(u.get("emph") is True for u in wrapped)
    assert wrapped[0]["word"] == "OMG" and wrapped[0].get("emph") is True


def test_map_emoji_returns_emoji_for_known_words():
    assert map_emoji("OMG") == "😱"
    assert map_emoji("bruh") == "🤦‍♂️"
    assert map_emoji("fire") == "🔥"
    assert map_emoji("laugh") == "😂"
    assert map_emoji("unknown") == ""


def test_build_enhanced_filter_includes_music_and_sfx():
    vf, af = build_enhanced_filter(
        ass_path="/tmp/c.ass",
        hook="TEST HOOK",
        music_path="/tmp/music.mp3",
        sfx_events=[{"t": 2.0, "file": "/tmp/boom.mp3"}],
        meme_events=[{"t": 3.0, "file": "/tmp/meme.png"}],
    )
    assert "amix" in af
    assert "overlay" in vf
    assert "subtitles=" in vf
    assert "drawtext=" in vf
