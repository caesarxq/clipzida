"""RED: caption lines must wrap so they never flood the frame."""
import re
from pathlib import Path

from clipping_tools.review.render import make_enhanced_ass


def _dialogue_lines(path: Path) -> list[str]:
    return [l for l in path.read_text().splitlines() if l.startswith("Dialogue:")]


def _visible(line: str) -> str:
    text = line.split(",", 9)[-1]  # ASS Dialogue: Text is the 10th field
    return re.sub(r"\{[^}]*\}", "", text)


def test_long_segment_is_wrapped_into_short_lines(tmp_path):
    words = [{"word": "this is a very long sentence that should wrap onto several lines",
              "start": 1.0, "end": 3.0}]
    ass = tmp_path / "c.ass"
    make_enhanced_ass(words, ass, "TEST HOOK")
    lines = _dialogue_lines(ass)
    assert len(lines) > 1
    for line in lines:
        assert len(_visible(line)) <= 30, line


def test_short_word_stays_single_line(tmp_path):
    words = [{"word": "hello", "start": 0.0, "end": 0.5}]
    ass = tmp_path / "c.ass"
    make_enhanced_ass(words, ass, "TEST HOOK")
    assert len(_dialogue_lines(ass)) == 1


def test_caption_font_is_reduced_from_68(tmp_path):
    words = [{"word": "hi", "start": 0.0, "end": 0.5}]
    ass = tmp_path / "c.ass"
    make_enhanced_ass(words, ass, "TEST HOOK")
    style = [l for l in ass.read_text().splitlines() if l.startswith("Style:")][0]
    assert ",50," in style and ",68," not in style
