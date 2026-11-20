"""Tracer bullet: real GTA 6 Twitch clip -> captioned 1080x1920 vertical render.

Proves the core loop: download (done via yt-dlp) -> transcribe -> energy ->
moment -> ASS captions -> gaming-split render (VideoToolbox) -> verify.
Local test only; nothing is published.
"""
from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = str(ROOT / "bin/ffmpeg") if (ROOT / "bin/ffmpeg").exists() else "ffmpeg"
FFPROBE = str(ROOT / "bin/ffprobe") if (ROOT / "bin/ffprobe").exists() else "ffprobe"
SRC = ROOT / "data/source/dinah_tracer.mp4"
WORK = ROOT / "data/renders"
WORK.mkdir(parents=True, exist_ok=True)
WAV = WORK / "tracer_16k.wav"
ASS = WORK / "tracer_captions.ass"
OUT = WORK / "tracer_vertical.mp4"
META = WORK / "tracer_vertical.metadata.txt"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    if cmd[0] == "ffmpeg":
        cmd = [FFMPEG, *cmd[1:]]
    elif cmd[0] == "ffprobe":
        cmd = [FFPROBE, *cmd[1:]]
    print("+", " ".join(cmd[:6]), "...")
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def extract_wav() -> None:
    run(["ffmpeg", "-y", "-i", str(SRC), "-ac", "1", "-ar", "16000", str(WAV)])


def transcribe() -> list[dict]:
    from faster_whisper import WhisperModel

    model = None
    for size in ("small", "tiny"):
        try:
            model = WhisperModel(size, device="cpu", compute_type="int8")
            break
        except Exception as e:  # model download failure -> smaller fallback
            print(f"model {size} failed: {e}")
    if model is None:
        raise RuntimeError("no whisper model available")
    segments, info = model.transcribe(str(WAV), word_timestamps=True, language="en")
    words = []
    for seg in segments:
        for w in seg.words or []:
            words.append({"word": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)})
    print(f"transcribed {len(words)} words, lang={info.language} p={info.language_probability:.2f}")
    (WORK / "tracer_words.json").write_text(json.dumps(words, indent=1))
    return words


def energy_peaks() -> list[dict]:
    with wave.open(str(WAV)) as wf:
        x = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    hop = 8000  # 0.5s @16k
    rms = [float(np.sqrt(np.mean(x[i : i + hop] ** 2) + 1e-12)) for i in range(0, len(x) - hop, hop)]
    peaks = sorted(range(len(rms)), key=lambda i: rms[i], reverse=True)[:5]
    out = [{"t": round(i * 0.5, 1), "rms": round(rms[i], 4)} for i in sorted(peaks)]
    print("energy peaks:", out)
    (WORK / "tracer_energy.json").write_text(json.dumps(out, indent=1))
    return out


def make_ass(words: list[dict]) -> None:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,68,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,60,60,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def ts(t: float) -> str:
        h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    lines = []
    # group into lines of <=4 words
    groups = [words[i : i + 4] for i in range(0, len(words), 4)]
    for g in groups:
        for idx, w in enumerate(g):
            parts = []
            for j, gw in enumerate(g):
                txt = gw["word"].replace("{", "").replace("}", "")
                if j == idx:
                    parts.append("{\\c&H0000FFFF&}" + txt.upper() + "{\\c&H00FFFFFF&}")
                else:
                    parts.append(txt)
            start, end = w["start"], max(w["end"], w["start"] + 0.08)
            lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Default,,0,0,0,,{' '.join(parts)}")
    ASS.write_text(header + "\n".join(lines) + "\n")
    print(f"ASS written: {len(lines)} events")


def hook_title(words: list[dict]) -> str:
    out = ""
    for w in words:
        candidate = (out + " " + w["word"]).strip()
        if len(candidate) > 24 and out:
            break
        out = candidate
    return (out[:24] or "GTA 6 MOMENT").upper().rstrip(".,")


def render(hook: str) -> None:
    font = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    hook_esc = hook.replace("'", "\u2019").replace(":", "\\:")
    vf = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "boxblur=20:5,eq=brightness=-0.06[bg];"
        "[0:v]scale=1080:-2[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[base]subtitles={ASS}[cap];"
        f"[cap]drawtext=fontfile='{font}':text='{hook_esc}':fontsize=58:fontcolor=white:"
        "borderw=5:bordercolor=black:x=(w-text_w)/2:y=320:enable='lt(t,2)'[out]"
    )
    run([
        "ffmpeg", "-y", "-i", str(SRC),
        "-filter_complex", vf, "-map", "[out]", "-map", "0:a",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:v", "h264_videotoolbox", "-b:v", "6M", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
        "-movflags", "+faststart", str(OUT),
    ])


def verify() -> dict:
    p = run(["ffprobe", "-v", "error", "-show_entries",
             "format=duration,size:stream=codec_name,width,height,r_frame_rate",
             "-of", "json", str(OUT)])
    info = json.loads(p.stdout)
    print(json.dumps(info, indent=1))
    assert any(s.get("width") == 1080 and s.get("height") == 1920 for s in info["streams"]), "not 1080x1920"
    return info


def main() -> None:
    extract_wav()
    words = transcribe()
    energy_peaks()
    make_ass(words)
    hook = hook_title(words)
    render(hook)
    info = verify()
    META.write_text(
        f"hook_title: {hook}\nsource: dinah / Twitch clip InventiveStylishSwanTBCheesePull (LOCAL TEST ONLY)\n"
        f"angle: funny\nlayout: gaming-split\ncaptions: word-level ASS, MarginV=560\n"
        f"loudnorm: I=-14 TP=-1.5 LRA=11\nprobe: {json.dumps(info)}\n"
    )
    print("TRACER OK ->", OUT)


if __name__ == "__main__":
    sys.exit(main())