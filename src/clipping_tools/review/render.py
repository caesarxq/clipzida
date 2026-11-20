"""Render stage: approved post -> captioned 1080x1920 mp4 (portable, libx264)."""
from __future__ import annotations

import json
import os
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


def source_clip_for_post(conn: sqlite3.Connection, post_id: int) -> dict | None:
    """Resolve an approved post to its source clip via idempotency_key = clip-<id>."""
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
    ytdlp = shutil.which("yt-dlp") or "yt-dlp"
    subprocess.run([ytdlp, "-f", "best[ext=mp4]/best", "-o", str(dest), url],
                   check=True, capture_output=True, text=True, timeout=300)


def extract_wav(src: Path, wav: Path) -> None:
    subprocess.run([ffmpeg_bin(), "-y", "-i", str(src), "-ac", "1", "-ar", "16000", str(wav)],
                   check=True, capture_output=True, text=True)


def transcribe(wav: Path) -> list[dict]:
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    # Word-level alignment can crash on some audio (IndexError in find_alignment).
    # Fall back to segment-level timestamps so the render never hard-fails.
    for word_timestamps in (True, False):
        try:
            segments, _ = model.transcribe(str(wav), word_timestamps=word_timestamps, language="en")
            segments = list(segments)  # materialize; alignment may fail during iteration
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
    peaks = sorted(range(len(rms)), key=lambda i: rms[i], reverse=True)[:5]
    return [{"t": round(i * 0.5, 1), "rms": round(rms[i], 4)} for i in sorted(peaks)]


def select_moment(words: list[dict], target_min: float = 18, target_max: float = 45) -> dict:
    """Pick a window around the densest speech, within target bounds."""
    if not words:
        return {"start": 0.0, "end": min(target_max, 30.0)}
    duration = min(target_max, max(target_min, words[-1]["end"] - words[0]["start"]))
    mid = (words[0]["start"] + words[-1]["end"]) / 2
    start = max(0.0, mid - duration / 2)
    return {"start": round(start, 2), "end": round(start + duration, 2)}


def make_ass(words: list[dict], ass_path: Path) -> None:
    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, "
        "Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,68,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,60,60,560,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    def ts(t: float) -> str:
        h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    lines = []
    for i in range(0, len(words), 4):
        group = words[i:i+4]
        for idx, w in enumerate(group):
            parts = []
            for j, gw in enumerate(group):
                txt = gw["word"].replace("{", "").replace("}", "")
                parts.append("{\\c&H0000FFFF&}" + txt.upper() + "{\\c&H00FFFFFF&}" if j == idx else txt)
            lines.append(f"Dialogue: 0,{ts(w['start'])},{ts(max(w['end'], w['start']+0.08))},"
                         f"Default,,0,0,0,,{' '.join(parts)}")
    ass_path.write_text(header + "\n".join(lines) + "\n")


def build_filter(ass_path: Path, hook: str) -> str:
    font = font_path()
    hook_esc = hook.replace("'", "\\u2019").replace(":", "\\:")
    return (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "boxblur=20:5,eq=brightness=-0.06[bg];"
        "[0:v]scale=1080:-2[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[base]subtitles={ass_path}[cap];"
        f"[cap]drawtext=fontfile='{font}':text='{hook_esc}':fontsize=58:fontcolor=white:"
        "borderw=5:bordercolor=black:x=(w-text_w)/2:y=320:enable='lt(t,2)'[out]"
    )


def render(src: Path, out: Path, ass_path: Path, hook: str) -> dict:
    vf = build_filter(ass_path, hook)
    subprocess.run([
        ffmpeg_bin(), "-y", "-i", str(src), "-filter_complex", vf,
        "-map", "[out]", "-map", "0:a",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", "6M", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
        "-movflags", "+faststart", str(out),
    ], check=True, capture_output=True, text=True, timeout=900)
    p = subprocess.run([ffprobe_bin(), "-v", "error", "-show_entries",
                        "format=duration,size:stream=codec_name,width,height",
                        "-of", "json", str(out)], check=True, capture_output=True, text=True)
    info = json.loads(p.stdout)
    assert any(s.get("width") == 1080 and s.get("height") == 1920 for s in info["streams"]), "not 1080x1920"
    return info


def render_post(post_id: int, db_path: str | Path) -> dict:
    """Full render for an approved post. Writes renders row + links post.render_id."""
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
    moment = select_moment(words)
    hook = (words[0]["word"] if words else clip["title"] or "GTA 6 MOMENT")[:24].upper()
    make_ass(words, ass)
    info = render(src, out, ass, hook)
    proxy_path = make_proxy(out)
    with conn:
        cur = conn.execute(
            "INSERT INTO renders(clip_id, variant, path, spec_json, checksum, rendered_at) "
            "VALUES(?,?,?,?,?,?)",
            (clip["id"], "vertical-1080x1920", str(out),
             json.dumps({"hook": hook, "moment": moment, "peaks": peaks, "probe": info}),
             "", utcnow()),
        )
        render_id = cur.lastrowid
        conn.execute("UPDATE posts SET render_id=?, status='rendered' WHERE id=?", (render_id, post_id))
    return {"post_id": post_id, "render_id": render_id, "path": str(out),
            "proxy_path": str(proxy_path) if proxy_path else None, "probe": info}


def init_db_for_path(path: str | Path):
    from ..db import init_db
    return init_db(path)
