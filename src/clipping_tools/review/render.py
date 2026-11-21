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
        "SELECT c.id, c.url, c.title, c.duration, c.broadcaster FROM posts p "
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

    start = max(0.0, best_start)
    end = min(start + duration, words[-1]["end"])
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
                          end: float | None = None
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

    # Audio chain: voice + music bed + SFX
    af_parts = []
    amix_inputs = "[0:a]"
    amix_count = 1

    if music_path:
        af_parts.append(f"[1:a]volume=0.15[music_bed];")
        amix_inputs += "[music_bed]"
        amix_count += 1

    sfx_idx = 2
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

    if af_parts:
        af_parts.append(f"{amix_inputs}amix=inputs={amix_count}:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[out_a]")
        af = "".join(af_parts)
    else:
        af = ""

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
           end: float | None = None) -> dict:
    """Full enhanced render for an approved post.

    Adds:
    - Background music bed at ~15% volume under voice
    - SFX overlays at event timestamps
    - Meme/reaction PNG overlays at event timestamps
    - Dynamic emphasis via ASS captions
    """
    vf, af = build_enhanced_filter(ass_path, hook, music_path, sfx_events, meme_events, start=start, end=end)

    # Build input list
    inputs = ["-i", str(src)]

    if music_path and Path(music_path).exists():
        inputs.extend(["-i", str(music_path)])

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
    # Collect asset paths
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
                  music_path=str(music) if music.exists() else None,
                  sfx_events=[e for e in sfx_events if Path(e.get("file", "")).exists()],
                  meme_events=[e for e in meme_events if Path(e.get("file", "")).exists()],
                  start=moment["start"], end=moment["end"])
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
