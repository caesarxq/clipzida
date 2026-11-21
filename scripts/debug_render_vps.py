import sys
sys.path.insert(0, "/home/clipzida/clipping_tools/src")
from pathlib import Path
from clipping_tools.review.render import (
    ffmpeg_bin, init_db_for_path, source_clip_for_post,
    download_clip, extract_wav, transcribe, energy_peaks,
    select_hook_moment, make_enhanced_ass, build_enhanced_filter,
)
from clipping_tools.db import init_db
import subprocess

conn = init_db_for_path("/home/clipzida/clipping_tools/data/state.db")
clip = source_clip_for_post(conn, 24)
print("Clip:", clip["title"])

WORK = Path("/home/clipzida/clipping_tools/data/renders")
src = WORK / f"source_{24}.mp4"
wav = WORK / f"audio_{24}.wav"
ass = WORK / f"caption_{24}.ass"
out = WORK / f"clipzida_{24}.mp4"

download_clip(clip["url"], src)
extract_wav(src, wav)
words = transcribe(wav)
peaks = energy_peaks(wav)
moment = select_hook_moment(words, peaks)
hook = (words[0]["word"] if words else clip["title"] or "GTA 6 MOMENT")[:24].upper()
make_enhanced_ass(words, ass, hook)

ASSETS_DIR = Path("/home/clipzida/clipping_tools/assets")
music = ASSETS_DIR / "audio/music_bed.mp3"
sfx_events = []
meme_events = []
if ASSETS_DIR.exists():
    for p in peaks[:3]:
        sfx_file = ASSETS_DIR / "audio/boom.mp3"
        if Path(sfx_file).exists():
            sfx_events.append({"t": p["t"], "file": str(sfx_file)})
    t = 2.0
    while t < moment["end"]:
        meme_file = ASSETS_DIR / "memes/reaction.png"
        if Path(meme_file).exists():
            meme_events.append({"t": t, "file": str(meme_file)})
        t += 4.0

vf, af = build_enhanced_filter(ass, hook, str(music) if music.exists() else None,
                               sfx_events, meme_events)

inputs = ["-i", str(src)]
if music and Path(music).exists():
    inputs.extend(["-i", str(music)])

sfx_idx = 2
if sfx_events:
    for i, ev in enumerate(sfx_events):
        sfx_file = ev.get("file", "")
        if sfx_file and Path(sfx_file).exists():
            inputs.extend(["-i", sfx_file])
            sfx_idx += 1

if meme_events:
    for i, ev in enumerate(meme_events):
        meme_file = ev.get("file", "")
        if meme_file and Path(meme_file).exists():
            inputs.extend(["-i", meme_file])
            sfx_idx += 1

full_filter = ";".join(p for p in [vf, af] if p)

cmd = [ffmpeg_bin(), "-y"] + inputs + ["-filter_complex", full_filter,
       "-map", "[out]", "-map", "[out_a]",
       "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
       "-c:v", "libx264", "-preset", "veryfast", "-b:v", "6M",
       "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
       "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
       "-movflags", "+faststart", str(out)]

print("Running ffmpeg...")
result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
print("Return code:", result.returncode)
print("STDERR (last 2000 chars):")
print(result.stderr[-2000:] if result.stderr else "none")
