"""Enhanced render stage: hook-first selection, emphasis captions,
sound design (music + SFX), meme/reaction overlays, dynamic emphasis.

Built from research on high-conversion short-form video:
- Hook in first 1-3 seconds (curiosity gap, pattern interrupt, bold claim)
- Fast cuts + zoom-ins on key words
- Meme/reaction inserts every 3-5 seconds
- Sound effects synced to visual beats
- Music bed at 15-25% under voice
- Captions with emphasis pops on key words
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import wave
from pathlib import Path

import numpy as np

from ..db import utcnow
from .proxy import make_proxy

WORK = Path(os.environ.get("CLIPZIDA_RENDER_DIR", "data/renders"))
WORK.mkdir(parents=True, exist_ok=True)
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
ASSETS_DIR = Path(os.environ.get("CLIPZIDA_ASSETS_DIR", "assets"))

# Emoji keyword mapping for emphasis captions
EMOJI_MAP = {
    "omg": "😱", "oh my god": "😱", "ohmygod": "😱",
    "bruh": "🤦‍♂️", "bro": "🤦‍♂️",
    "fire": "🔥", "lit": "🔥",
    "laugh": "😂", "haha": "😂", "lol": "😂", "funny": "😂",
    "crazy": "🤪", "insane": "🤯", "mind": "🤯",
    "love": "❤️", "heart": "❤️",
    "shock": "😳", "wow": "😳", "shocked": "😳",
    "laughing": "🤣", "dead": "💀",
    "fire": "🔥", "hot": "🔥",
}

# Hook keywords that signal a strong opener
HOOK_KEYWORDS = {
    "omg", "wow", "crazy", "insane", "bruh", "wait", "stop", "look",
    "this", "that", "you", "need", "must", "never", "always", "secret",
    "truth", "lie", "fake", "real", "best", "worst", "top", "first",
    "last", "only", "one", "two", "three", "how", "why", "what",
    "who", "where", "when", "mind", "blown", "game", "changer",
    "epic", "fail", "win", "clutch", "god", "savage",
}

EMPHASIS_COLOR = "&H0000FFFF&"  # yellow
NORMAL_COLOR = "&H00FFFFFF&"    # white


def source_clip_for_post(conn: sqlite3.Connection, post_id: int) -> dict | None:
    row = conn.execute(
        "SELECT c.id, c.url, c.title, c.duration, c.broadcaster, p.angle FROM posts p "
        "JOIN clips_raw c ON c.id = CAST(SUBSTR(p.idempotency_key, 6) AS INTEGER) "
        "WHERE p.id=? AND p.status IN ('approved','rendered') AND p.idempotency_key LIKE 'clip-%'",
        (post_id,),
    ).fetchone()
    return dict(row) if row else None


def ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def font_path() -> str:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    raise RuntimeError("no usable bold font for drawtext")


def download_clip(url: str, dest: Path) -> None:
    candidates = [shutil.which("yt-dlp"),
                  str(Path.home() / ".local/bin/yt-dlp"),
                  "/home/clipzida/.local/bin/yt-dlp"]
    ytdlp = next((c for c in candidates if c and Path(c).exists()), None)
    if not ytdlp:
        raise RuntimeError("yt-dlp not found on PATH or ~/.local/bin")
    subprocess.run([ytdlp, "-f", "best[ext=mp4]/best", "-o", str(dest), url],
                   check=True, capture_output=True, text=True, timeout=300)


def extract_wav(src: Path, wav: Path) -> None:
    subprocess.run([ffmpeg_bin(), "-y", "-i", str(src), "-ac", "1", "-ar", "16000", str(wav)],
                   check=True, capture_output=True, text=True)


def transcribe(wav: Path) -> list[dict]:
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    for word_timestamps in (True, False):
        try:
            segments, _ = model.transcribe(str(wav), word_timestamps=word_timestamps, language="en")
            segments = list(segments)
            words: list[dict] = []
            for seg in segments:
                if word_timestamps and seg.words:
                    for w in seg.words:
                        words.append({"word": w.word.strip(), "start": round(w.start, 2),
                                      "end": round(w.end, 2)})
                elif seg.text and seg.text.strip():
                    words.append({"word": seg.text.strip(), "start": round(seg.start, 2),
                                  "end": round(seg.end, 2)})
            if words:
                return words
        except (IndexError, ValueError, RuntimeError):
            continue
    return []


def energy_peaks(wav: Path) -> list[dict]:
    with wave.open(str(wav)) as wf:
        x = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    hop = 8000
    rms = [float(np.sqrt(np.mean(x[i:i+hop] ** 2) + 1e-12)) for i in range(0, len(x) - hop, hop)]
    peaks = sorted(range(len(rms)), key=lambda i: rms[i], reverse=True)[:8]
    return [{"t": round(i * 0.5, 1), "rms": round(rms[i], 4)} for i in sorted(peaks)]


def _word_score(word: dict, peaks: list[dict]) -> float:
    """Score a word by energy + hook keywords + emphasis markers."""
    text = str(word.get("word", "")).strip().lower()
    score = 0.0
    # Hook keyword match
    for kw in HOOK_KEYWORDS:
        if kw in text:
            score += 2.0
            break
    # All-caps emphasis
    w = str(word.get("word", "")).strip()
    if w.isupper() and len(w) > 1:
        score += 1.5
    # Exclamation emphasis
    if "!" in w:
        score += 1.0
    # Energy peak proximity
    t = float(word.get("start", 0))
    for p in peaks:
        if abs(t - p["t"]) < 0.75:
            score += p["rms"] * 2.0
            break
    return score


def detect_segments(words: list[dict], peaks: list[dict],
                    clip_duration: float, min_seg: float = 0.5,
                    max_seg: float = 3.0) -> list[dict]:
    """Detect jump-cut segments from transcript gaps + energy peaks.

    Cuts out silence gaps (> 0.4 seconds between words) and caps segment
    length at max_seg. Segments containing high energy peaks are marked
    'zoom'. Returns list of {start, end, type}.
    """
    if not words:
        return [{"start": 0.0, "end": float(clip_duration), "type": "normal"}]

    sorted_words = sorted(words, key=lambda w: float(w.get("start", 0)))

    # Build cut points: start, then gap boundaries, then end of last word
    cut_points = [float(sorted_words[0]["start"])]
    for i in range(len(sorted_words) - 1):
        gap = float(sorted_words[i + 1]["start"]) - float(sorted_words[i]["end"])
        if gap > 0.4:  # silence gap = jump-cut point
            cut_points.append(float(sorted_words[i]["end"]))
            cut_points.append(float(sorted_words[i + 1]["start"]))
    cut_points.append(float(sorted_words[-1]["end"]))

    # Build segments from cut points, capping each at max_seg.
    # Skip segments that contain no words (pure silence between cuts).
    segments = []
    for i in range(len(cut_points) - 1):
        seg_start = cut_points[i]
        seg_end = cut_points[i + 1]
        if seg_end - seg_start < 0.1:
            continue
        # Check if any word falls within this segment
        has_word = any(
            seg_start <= float(w.get("start", 0)) < seg_end
            for w in sorted_words
        )
        if not has_word:
            continue
        while seg_start < seg_end:
            piece_end = min(seg_start + max_seg, seg_end)
            # Check if any word falls within this piece
            piece_has_word = any(
                seg_start <= float(w.get("start", 0)) < piece_end
                for w in sorted_words
            )
            if not piece_has_word:
                seg_start = piece_end
                continue
            seg_type = "normal"
            speed_ramp = 1.0
            for p in peaks:
                if seg_start <= float(p["t"]) <= piece_end:
                    rms = float(p["rms"])
                    if rms > 0.7:
                        seg_type = "zoom"
                        speed_ramp = 0.5
                        break  # dramatic moment takes priority
                    elif rms < 0.4:
                        speed_ramp = 1.5
            segments.append({
                "start": round(seg_start, 2),
                "end": round(piece_end, 2),
                "type": seg_type,
                "speed_ramp": speed_ramp,
            })
            seg_start = piece_end

    return segments


def flash_overlays(peaks: list[dict], threshold: float = 0.7) -> list[dict]:
    """Return flash events for energy peaks above threshold.

    Each flash is a 1-frame (0.03s) white overlay at the peak timestamp.
    Used for impact emphasis on kills, crashes, and other dramatic moments.
    """
    flashes = []
    for p in peaks:
        if float(p["rms"]) > threshold:
            flashes.append({
                "t": float(p["t"]),
                "duration": 0.03,
                "type": "flash",
            })
    return flashes


def speed_ramp_factor(peak: dict) -> float:
    """Return speed multiplier based on energy peak RMS.

    > 0.7  → 0.5x slow motion  (dramatic kill/fail moment)
    0.4-0.7 → 1.0x normal speed
    < 0.4  → 1.5x fast forward (travel/montage, low energy)
    """
    rms = float(peak["rms"])
    if rms > 0.7:
        return 0.5
    elif rms >= 0.4:
        return 1.0
    else:
        return 1.5


def audio_duck_filter(voice_input: str | None,
                      music_input: str,
                      output: str,
                      threshold: float = -30,
                      ratio: float = 4,
                      attack: float = 0.01,
                      release: float = 0.2) -> str:
    """Sidechain compressor that ducks music when voice is present.

    Uses ffmpeg's sidechaincompressor: music is the main input, voice is
    the sidechain. When voice exceeds threshold, music volume is reduced.
    """
    if voice_input is None:
        return music_input
    return (
        f"{music_input}{voice_input}sidechaincompressor="
        f"threshold={threshold}:ratio={ratio}:attack={attack}:"
        f"release={release}[{output.strip('[]')}]"
    )


def voice_eq_filter(input_label: str, output_label: str) -> str:
    """EQ chain for voice clarity: high-pass rumble, presence boost.

    - High-pass at 80Hz to cut low-frequency rumble
    - Presence boost at 2kHz, 3kHz, 5kHz for speech intelligibility
    """
    return (
        f"{input_label}highpass=f=80,"
        f"equalizer=f=2000:t=h:w=200:g=3,"
        f"equalizer=f=3000:t=h:w=300:g=2,"
        f"equalizer=f=5000:t=h:w=400:g=1{output_label}"
    )


def music_bed_for_angle(angle: str | None,
                        assets_dir: str | None = None) -> str | None:
    """Return the music bed path for a given angle.

    - funny → lo-fi/upbeat
    - hype → phonky/high-energy
    - news → ambient/cinematic
    - None → no music
    - unknown → default music_bed.mp3
    """
    if angle is None:
        return None

    if assets_dir is None:
        assets_dir = str(ASSETS_DIR)

    mapping = {
        "funny": "audio/music_funny.mp3",
        "hype": "audio/music_hype.mp3",
        "news": "audio/music_news.mp3",
    }

    rel = mapping.get(angle, "audio/music_bed.mp3")
    path = str(Path(assets_dir) / rel)
    return path if Path(path).exists() else str(Path(assets_dir) / "audio/music_bed.mp3")


def build_segment_filter(seg: dict, seg_idx: int) -> list[str]:
    """Build ffmpeg filter fragments for one segment from [0:v].

    Returns a list of filter-chain strings (joined by ';' by caller).
    Each chain ends with [fv{N}_bg] and [fv{N}_fg] labels via split=2.
    Applies speed ramp via setpts when speed_ramp != 1.0.
    """
    start = seg["start"]
    end = seg["end"]
    seg_type = seg.get("type", "normal")
    speed_ramp = seg.get("speed_ramp", 1.0)

    # Speed ramp: setpts multiplier = 1 / speed_ramp
    #   speed_ramp=0.5 (slow mo) → *2   (takes 2x longer)
    #   speed_ramp=1.5 (fast fwd)  → /1.5 (takes 0.67x the time)
    if speed_ramp == 1.0:
        pts_expr = "PTS-STARTPTS"
    elif speed_ramp < 1.0:
        pts_expr = f"(PTS-STARTPTS)*{1.0 / speed_ramp}"
    else:
        pts_expr = f"(PTS-STARTPTS)/{speed_ramp}"

    # Base trim chain, ends with a pre-split label
    pre = f"[fv{seg_idx}_pre]"
    base = f"[0:v]trim=start={start}:end={end},setpts={pts_expr}{pre}"

    if seg_type == "zoom":
        # Zoom in during the segment: 1.0x -> 1.3x
        zoom = f"{pre}zoompan=z='min(zoom+0.01,1.3)':d=25[fv{seg_idx}_zoomed]"
        split = f"[fv{seg_idx}_zoomed]split=2[fv{seg_idx}_bg][fv{seg_idx}_fg]"
        return [base, zoom, split]
    elif seg_type == "flash":
        # White flash overlay at segment start
        flash = (
            f"color=c=white:s=1080x1920:d=0.05[fv{seg_idx}_flash];"
            f"{pre}[fv{seg_idx}_flash]overlay=enable='eq(t,{start})'"
            f"[fv{seg_idx}_merged]"
        )
        split = f"[fv{seg_idx}_merged]split=2[fv{seg_idx}_bg][fv{seg_idx}_fg]"
        return [base, flash, split]
    else:
        # Normal segment: just split
        split = f"{pre}split=2[fv{seg_idx}_bg][fv{seg_idx}_fg]"
        return [base, split]


def build_paced_filter(segs: list[dict], ass_path: str, hook: str,
                       font: str, hook_esc: str,
                       flashes: list[dict] | None = None) -> tuple[str, str]:
    """Build complete filtergraph from segments: trim + effects + concat + captions.

    Returns (video_filter, audio_filter).
    """
    af = ""

    if len(segs) == 1:
        seg = segs[0]
        seg_fragments = build_segment_filter(seg, 0)
        vf = (
            ";".join(seg_fragments) + ";"
            f"[fv0_bg]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,boxblur=20:5,eq=brightness=-0.06[bg];"
            f"[fv0_fg]scale=1080:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
            f"[base]subtitles={ass_path}[cap];"
            f"[cap]drawtext=fontfile='{font}':text='{hook_esc}':fontsize=50:"
            f"fontcolor=white:borderw=5:bordercolor=black:"
            f"x=(w-text_w)/2:y=320:enable='lt(t,2)'[cap_out]"
        )
        # Apply flash overlays after captions (single segment path)
        if flashes:
            vf = _apply_flash_overlays(vf, "cap_out", flashes)
            # Rename final output label to [out]
            vf = vf.replace("[cap_out]", "[out]", 1)
        else:
            vf = vf.replace("[cap_out]", "[out]", 1)
    else:
        all_fragments = []
        for i, seg in enumerate(segs):
            all_fragments.extend(build_segment_filter(seg, i))
        bg_inputs = "".join([f"[fv{i}_bg]" for i in range(len(segs))])
        fg_inputs = "".join([f"[fv{i}_fg]" for i in range(len(segs))])
        vf = ";".join(all_fragments)
        # Concat once for background (blurred + scaled), once for foreground
        vf += (
            f";{bg_inputs}concat=n={len(segs)}:v=1:a=0,"
            f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,boxblur=20:5,eq=brightness=-0.06[bg];"
            f"{fg_inputs}concat=n={len(segs)}:v=1:a=0,scale=1080:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
            f"[base]subtitles={ass_path}[cap];"
            f"[cap]drawtext=fontfile='{font}':text='{hook_esc}':fontsize=50:"
            f"fontcolor=white:borderw=5:bordercolor=black:"
            f"x=(w-text_w)/2:y=320:enable='lt(t,2)'[cap_out]"
        )
        # Apply flash overlays after captions (multi segment path)
        if flashes:
            vf = _apply_flash_overlays(vf, "cap_out", flashes)
            vf = vf.replace("[cap_out]", "[out]", 1)
        else:
            vf = vf.replace("[cap_out]", "[out]", 1)

    return vf, af


def _apply_flash_overlays(vf: str, start_label: str, flashes: list[dict]) -> str:
    """Chain flash overlays after the given label in the filtergraph.

    Each flash is a 1-frame white screen overlaid at its timestamp.
    Returns the filtergraph string with the final label renamed to [flash_out{N}].
    """
    current_label = start_label
    for i, flash in enumerate(flashes):
        t = flash["t"]
        flash_label = f"[flash{i}]"
        out_label = f"[flash_out{i}]" if i < len(flashes) - 1 else "[out]"
        vf += (
            f";{current_label}color=c=white:s=1080x1920:d={flash['duration']}"
            f"{flash_label};"
            f"{current_label}{flash_label}overlay=enable='eq(t,{t})'{out_label}"
        )
        current_label = out_label
    return vf


def select_hook_moment(words: list[dict], peaks: list[dict],
                       target_min: float = 18, target_max: float = 45) -> dict:
    """Select a moment window that STARTS near a high-scoring hook word.

    Research: hooks must land in the first 1-3 seconds. We slide a window
    across the clip and pick the one whose first word has the highest score
    (energy + hook keywords + emphasis).
    """
    if not words:
        return {"start": 0.0, "end": min(target_max, 30.0)}

    total_duration = words[-1]["end"] - words[0]["start"]
    duration = min(target_max, max(target_min, total_duration))

    best_start = 0.0
    best_score = -1.0
    step = 0.5  # slide in 0.5s increments

    t = words[0]["start"]
    while t + duration <= words[-1]["end"] + 0.5:
        # Score words in the first 2 seconds of this window
        window_words = [w for w in words
                        if t <= float(w.get("start", 0)) <= t + 2.0]
        score = sum(_word_score(w, peaks) for w in window_words)
        if score > best_score:
            best_score = score
            best_start = t
        t += step

    start = float(max(0.0, best_start))
    end = float(min(start + duration, words[-1]["end"]))
    # Identify the best hook word within the window (highest _word_score)
    hook_word = ""
    hook_word_score = -1.0
    for w in words:
        wt = float(w.get("start", 0))
        if start <= wt <= end:
            ws = _word_score(w, peaks)
            if ws > hook_word_score:
                hook_word_score = ws
                hook_word = str(w.get("word", ""))
    return {"start": round(start, 2), "end": round(end, 2), "hook_word": hook_word}


def _wrap_word(word: str, start: float, end: float, max_chars: int = 24) -> list[dict]:
    """Split an over-long caption unit into chunks so it never floods the frame."""
    text = str(word).strip()
    if len(text) <= max_chars:
        return [{"word": text, "start": start, "end": end}]
    words = text.split()
    chunks, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) > max_chars and cur:
            chunks.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        chunks.append(cur)
    span = max(end - start, 0.08)
    step = span / len(chunks)
    return [{"word": c, "start": round(start + i * step, 2),
             "end": round(start + (i + 1) * step, 2)} for i, c in enumerate(chunks)]


def map_emoji(word: str) -> str:
    """Return an emoji for a keyword, or empty string."""
    text = str(word).strip().lower().rstrip("!.,?")
    return EMOJI_MAP.get(text, "")


def wrap_emphasis(units: list[dict]) -> list[dict]:
    """Mark emphasis words (all-caps, exclamation) with emph=True."""
    out = []
    for u in units:
        w = str(u.get("word", "")).strip()
        emph = w.isupper() and len(w) > 1 or "!" in w
        out.append({**u, "emph": emph})
    return out


def _ass_style(name: str, fontsize: int, primary: str, secondary: str,
               bold: int = -1) -> str:
    return (f"Style: {name},Arial,{fontsize},{primary},{secondary},"
            f"&H00000000,&H80000000,{bold},0,0,0,100,100,0,0,1,4,0,2,60,60,560,1")


def make_enhanced_ass(words: list[dict], ass_path: Path, hook: str,
                      moment: dict | None = None) -> None:
    """ASS captions with karaoke word-by-word highlight, bottom-third placement.

    Each word gets its own Dialogue line with exact start/end timing.
    The active word uses Emphasis style; only max 2 lines visible at once.
    Filtered to the hook moment window when provided.
    """
    # Filter words to hook moment window if provided
    if moment:
        ws = float(moment.get("start", 0))
        we = float(moment.get("end", 0))
        words = [w for w in words
                 if ws <= float(w.get("start", 0)) < we]

    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, "
        "SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{_ass_style('Default', 50, NORMAL_COLOR, EMPHASIS_COLOR)}\n"
        f"{_ass_style('Emphasis', 52, EMPHASIS_COLOR, NORMAL_COLOR, bold=1)}\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )

    def ts(t: float) -> str:
        h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    units = []
    for w in words:
        units.extend(_wrap_word(w.get("word", ""),
                                float(w.get("start", 0)),
                                float(w.get("end", 0))))

    # Apply emphasis markers
    units = wrap_emphasis(units)

    # Prevent overlap: trim each word's end to the next word's start
    # so max 1 caption line is visible at a time (well under the 2-line cap)
    for i in range(len(units) - 1):
        next_start = units[i + 1]["start"]
        if units[i]["end"] > next_start:
            units[i]["end"] = next_start

    # Build karaoke dialogue: one line per word, exact timing.
    # Every word uses Emphasis style — it's the "active" word during its window.
    lines = []
    for u in units:
        w = u["word"].replace("{", "").replace("}", "")
        emoji = map_emoji(w)
        display = w + (" " + emoji if emoji else "")
        # Karaoke: each word is emphasized during its own time window
        lines.append(
            f"Dialogue: 0,{ts(u['start'])},{ts(u['end'])},"
            f"Emphasis,,0,0,700,,{display}"
        )

    ass_path.write_text(header + "\n".join(lines) + "\n")

def build_enhanced_filter(ass_path: Path, hook: str,
                          music_path: str | None = None,
                          sfx_events: list[dict] | None = None,
                          meme_events: list[dict] | None = None,
                          start: float | None = None,
                          end: float | None = None,
                          angle: str | None = None
                          ) -> tuple[str, str]:
    """Build video + audio filtergraphs.

    Returns (video_filter, audio_filter).
    """
    font = font_path()
    hook_esc = hook.replace("'", "\\u2019").replace(":", "\\:")

    # Optional trim to hook moment window
    trim = ""
    if start is not None and end is not None:
        trim = f"trim=start={start}:end={end},setpts=PTS-STARTPTS,"

    # Video chain: gaming-split layout
    vf = (
        f"[0:v]{trim}scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "boxblur=20:5,eq=brightness=-0.06[bg];"
        "[0:v]scale=1080:-2[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[base]subtitles={ass_path}[cap];"
        f"[cap]drawtext=fontfile='{font}':text='{hook_esc}':fontsize=58:"
        "fontcolor=white:borderw=5:bordercolor=black:x=(w-text_w)/2:y=320:"
        "enable='lt(t,2)'[out]"
    )

    # Audio chain: voice EQ + music bed (with ducking when angle provided) + SFX
    af_parts = []

    # Always apply EQ to voice
    af_parts.append(voice_eq_filter("[0:a]", "[voice_eq]"))

    # Resolve music path from angle if not explicitly provided
    resolved_music = music_path
    if resolved_music is None and angle is not None:
        resolved_music = music_bed_for_angle(angle)

    if resolved_music:
        if angle:
            # Duck music when voice is present (sidechain compression)
            # Music is input 1 ([1:a]), voice EQ output is [voice_eq]
            af_parts.append(
                f"[1:a][voice_eq]sidechaincompressor="
                f"threshold=-30:ratio=4:attack=0.01:release=0.2[music_ducked];"
            )
            amix_inputs = "[voice_eq][music_ducked]"
            amix_count = 2
        else:
            # Simple volume duck (no sidechain)
            af_parts.append(f"[1:a]volume=0.15[music_bed];")
            amix_inputs = "[voice_eq][music_bed]"
            amix_count = 2

        sfx_idx = 2
    else:
        amix_inputs = "[voice_eq]"
        amix_count = 1
        sfx_idx = 1

    if sfx_events:
        for i, ev in enumerate(sfx_events):
            sfx_file = ev.get("file", "")
            if sfx_file:
                af_parts.append(
                    f"[{sfx_idx}:a]adelay={int(float(ev.get('t', 0))*1000)}|"
                    f"{int(float(ev.get('t', 0))*1000)}[sfx{i}];"
                )
                amix_inputs += f"[sfx{i}]"
                amix_count += 1
                sfx_idx += 1

    af_parts.append(
        f"{amix_inputs}amix=inputs={amix_count}:normalize=0,"
        f"loudnorm=I=-14:TP=-1.5:LRA=11[out_a]"
    )
    af = "".join(af_parts)

    # Meme/reaction image overlays: chain after [out]
    if meme_events:
        meme_parts = []
        prev_label = "[out]"
        for i, ev in enumerate(meme_events):
            meme_file = ev.get("file", "")
            if not meme_file:
                continue
            t = float(ev.get("t", 0))
            dur = float(ev.get("duration", 1.0))
            out_label = f"[meme_out{i}]" if i < len(meme_events) - 1 else "[out]"
            meme_parts.append(
                f"[{sfx_idx + i}:v]scale=300:300:"
                f"force_original_aspect_ratio=decrease,"
                f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2[meme_scaled{i}];"
                f"[meme_scaled{i}][{prev_label.strip('[]')}]overlay="
                f"(W-w)/2:(H-h)/2:"
                f"enable='between(t\\,{t:.1f}\\,{t+dur:.1f})'{out_label};"
            )
            prev_label = out_label
        if meme_parts:
            vf = vf + ";" + "".join(meme_parts)

    return vf, af


def _flash_filter(durations: list[float]) -> str:
    """Generate a white flash filter at given timestamps."""
    parts = []
    for i, t in enumerate(durations):
        parts.append(
            f"[out{i}]color=c=white:s=1080x1920:d=0.05:f=30[flash{i}];"
            f"[prev{i}][flash{i}]overlay=enable='eq(t\\,{t})'[out{i+1}];"
        )
    return "".join(parts)


def render(src: Path, out: Path, ass_path: Path, hook: str,
           music_path: str | None = None,
           sfx_events: list[dict] | None = None,
           meme_events: list[dict] | None = None,
           start: float | None = None,
           end: float | None = None,
           segs: list[dict] | None = None,
           flashes: list[dict] | None = None,
           angle: str | None = None) -> dict:
    """Full enhanced render for an approved post.

    Adds:
    - Background music bed at ~15% volume under voice
    - SFX overlays at event timestamps
    - Meme/reaction PNG overlays at event timestamps
    - Dynamic emphasis via ASS captions
    - Jump-cut pacing via segments (when segs provided)
    - Impact flashes at high energy peaks (when flashes provided)
    - Angle-specific music bed with voice ducking (when angle provided)
    """
    font = font_path()
    hook_esc = hook.replace("'", "\\u2019").replace(":", "\\:")

    # Resolve music path from angle if not explicitly provided
    resolved_music = music_path
    if resolved_music is None and angle is not None:
        resolved_music = music_bed_for_angle(angle)

    # Use segment-based pacing when segs provided
    if segs:
        vf, af = build_paced_filter(segs, str(ass_path), hook, font, hook_esc,
                                    flashes=flashes)
        # Paced path: source video only (no music/SFX/memes yet)
        inputs = ["-i", str(src)]
        full_filter = vf.rstrip(";")
        # Map video from concat output, copy audio from source
        cmd = [
            ffmpeg_bin(), "-y",
        ]
        cmd.extend(inputs)
        cmd.extend(["-filter_complex", full_filter])
        cmd.extend(["-map", "[out]", "-map", "0:a?"])
        cmd.extend([
            "-c:v", "libx264", "-preset", "veryfast", "-b:v", "6M",
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
            "-movflags", "+faststart", str(out),
        ])
    else:
        vf, af = build_enhanced_filter(ass_path, hook, resolved_music, sfx_events,
                                       meme_events, start=start, end=end,
                                       angle=angle)

        # Build input list
        inputs = ["-i", str(src)]

        if resolved_music and Path(resolved_music).exists():
            inputs.extend(["-i", str(resolved_music)])

        sfx_idx = 2
        if sfx_events:
            for i, ev in enumerate(sfx_events):
                sfx_file = ev.get("file", "")
                if sfx_file and Path(sfx_file).exists():
                    inputs.extend(["-i", sfx_file])
                    sfx_idx += 1

        meme_idx = sfx_idx
        if meme_events:
            for i, ev in enumerate(meme_events):
                meme_file = ev.get("file", "")
                if meme_file and Path(meme_file).exists():
                    inputs.extend(["-i", meme_file])
                    sfx_idx += 1

        # Build full filter_complex string (video + audio)
        full_filter = vf.rstrip(";")
        if af:
            full_filter += ";" + af

        cmd = [
            ffmpeg_bin(), "-y",
        ]
        # Add inputs
        cmd.extend(inputs)
        # Filter complex
        cmd.extend(["-filter_complex", full_filter])
        # Map video
        cmd.extend(["-map", "[out]"])
        # Map audio (amix output always exists since build_enhanced_filter includes amix)
        cmd.extend(["-map", "[out_a]"])
        cmd.extend([
            "-c:v", "libx264", "-preset", "veryfast", "-b:v", "6M",
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
            "-movflags", "+faststart", str(out),
        ])

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=900)
    except subprocess.CalledProcessError as e:
        import sys as _sys
        _sys.stderr.write(f"FFMPEG_STDERR:\n{e.stderr}\n")
        raise

    p = subprocess.run([ffprobe_bin(), "-v", "error", "-show_entries",
                        "format=duration,size:stream=codec_name,width,height",
                        "-of", "json", str(out)], check=True,
                       capture_output=True, text=True)
    info = json.loads(p.stdout)
    assert any(s.get("width") == 1080 and s.get("height") == 1920
               for s in info["streams"]), "not 1080x1920"
    return info


def _replace_render(conn: sqlite3.Connection, clip_id: int, variant: str,
                    path: str) -> int:
    conn.execute("DELETE FROM renders WHERE clip_id=? AND variant=?",
                 (clip_id, variant))
    cur = conn.execute(
        "INSERT INTO renders(clip_id, variant, path) VALUES(?,?,?)",
        (clip_id, variant, path))
    return int(cur.lastrowid or 0)


def render_post(post_id: int, db_path: str | Path) -> dict:
    conn = init_db_for_path(db_path)
    clip = source_clip_for_post(conn, post_id)
    if not clip:
        raise RuntimeError(f"post {post_id} has no approved source clip")
    src = WORK / f"source_{post_id}.mp4"
    wav = WORK / f"audio_{post_id}.wav"
    ass = WORK / f"caption_{post_id}.ass"
    out = WORK / f"clipzida_{post_id}.mp4"
    download_clip(clip["url"], src)
    extract_wav(src, wav)
    words = transcribe(wav)
    peaks = energy_peaks(wav)
    moment = select_hook_moment(words, peaks)
    hook = (moment.get("hook_word") or clip["title"] or "GTA 6 MOMENT")[:24].upper()
    make_enhanced_ass(words, ass, hook, moment=moment)
    # Detect jump-cut segments for pacing
    clip_duration = words[-1]["end"] if words else 30.0
    segs = detect_segments(words, peaks, clip_duration)
    # Detect impact flashes at high energy peaks
    flashes = flash_overlays(peaks, threshold=0.7)
    # Collect asset paths (only used in non-paced path)
    assets = ASSETS_DIR
    music = assets / "audio" / "music_bed.mp3"
    sfx_events = []
    meme_events = []
    if assets.exists():
        # SFX events at energy peaks (top 3)
        for p in peaks[:3]:
            sfx_file = assets / "audio" / "boom.mp3"
            if sfx_file.exists():
                sfx_events.append({"t": p["t"], "file": str(sfx_file)})
        # Meme events every 4 seconds
        t = 2.0
        while t < moment["end"]:
            meme_file = assets / "memes" / "reaction.png"
            if meme_file.exists():
                meme_events.append({"t": t, "file": str(meme_file)})
            t += 4.0
    info = render(src, out, ass, hook,
                  # When angle is provided, let render() resolve music via music_bed_for_angle
                  music_path=None if clip.get("angle") else (str(music) if music.exists() else None),
                  sfx_events=[e for e in sfx_events if Path(e.get("file", "")).exists()],
                  meme_events=[e for e in meme_events if Path(e.get("file", "")).exists()],
                  start=moment["start"], end=moment["end"],
                  segs=segs if len(segs) > 1 else None,
                  flashes=flashes if flashes else None,
                  angle=clip.get("angle"))
    proxy_path = make_proxy(out)
    with conn:
        render_id = _replace_render(conn, clip["id"], "vertical-1080x1920", str(out))
        conn.execute(
            "UPDATE renders SET spec_json=?, checksum='', rendered_at=? WHERE id=?",
            (json.dumps({"hook": hook, "moment": moment, "peaks": peaks,
                         "sfx": sfx_events, "memes": meme_events, "probe": info}),
             utcnow(), render_id))
        conn.execute("UPDATE posts SET render_id=?, status='rendered' WHERE id=?",
                     (render_id, post_id))
    return {"post_id": post_id, "render_id": render_id, "path": str(out),
            "proxy_path": str(proxy_path) if proxy_path else None,
            "moment": moment, "probe": info}


def init_db_for_path(path: str | Path):
    from ..db import init_db
    return init_db(path)
