"""RED: transcription falls back to segment-level when word alignment crashes."""
import sys
import types
from pathlib import Path

import clipping_tools.review.render as render_mod


class _FakeSeg:
    def __init__(self, text, start, end, words=None):
        self.text, self.start, self.end, self.words = text, start, end, words


class _FakeModel:
    def transcribe(self, wav, **kwargs):
        if kwargs.get("word_timestamps"):
            def boom():
                raise IndexError("boolean index did not match")
            return boom(), None  # generator fails on iteration
        return [_FakeSeg("hello world", 0.0, 2.5)], None


def test_transcribe_falls_back_to_segments(monkeypatch):
    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = lambda *a, **k: _FakeModel()
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    words = render_mod.transcribe(Path("/tmp/nonexistent.wav"))
    assert words and words[0]["word"] == "hello world"
    assert words[0]["start"] == 0.0 and words[0]["end"] == 2.5
