import sys
sys.path.insert(0, "/home/clipzida/clipping_tools/src")
from clipping_tools.review.render import render_post
import subprocess

try:
    r = render_post(24, "/home/clipzida/clipping_tools/data/state.db")
    print("RENDER_OK", r)
except Exception as e:
    print(f"RENDER_FAILED: {e}")

# Try running ffmpeg directly to see stderr
print("\n=== Direct ffmpeg test ===")
import os
os.chdir("/home/clipzida/clipping_tools")

# Build the same command as render() would
from clipping_tools.review.render import (
    ffmpeg_bin, ffprobe_bin, font_path, source_clip_for_post,
    init_db_for_path, download_clip, extract_wav, transcribe,
    energy_peaks, select_hook_moment, make_enhanced_ass,
    build_enhanced_filter
)
from clipping_tools.db import init_db

conn = init_db_for_path("/home/clipzida/clipping_tools/data/state.db")
clip = source_clip_for_post(conn, 24)
print("Clip:", clip["title"] if clip else "None")

src = "/home/clipzida/clipping_tools/data/renders/source_24.mp4"
wav = "/home/clipzida/clipping_tools/data/renders/audio_24.wav"
ass = "/home/clipzida/clipping_tools/data/renders/caption_24.ass"
out = "/home/clipzida/clipping_tools/data/renders/clipzida_24.mp4"

# Download and transcribe
download_clip(clip["url"], src)
extract_wav(src, wav)
words = transcribe(wav)
peaks = energy_peaks(wav)
moment = select_hook_moment(words, peaks)
hook = (words[0]["word"] if words else clip["title"] or "GTA 6 MOMENT")[:24].upper()
make_enhanced_ass(words, ass, hook)

# Build filter
vf, af = build_enhanced_filter(ass, hook)

print("VF:", vf[:200])
print("AF:", af)

# Build command
inputs = ["-i", str(src)]
from pathlib import Path
ASSETS_DIR = "/home/clipzida/clipping_tools/assets"
music = ASSETS_DIR + "/audio/music_bed.mp3"
sfx_events = []
meme_events = []
if Path(ASSETS_DIR).exists():
    for p in peaks[:3]:
        sfx_file = ASSETS_DIR + "/audio/boom.mp3"
        if Path(sfx_file).exists():
            sfx_events.append({"t": p["t"], "file": str(sfx_file)})
    t = 2.0
    while t < moment["end"]:
        meme_file = ASSETS_DIR + "/memes/reaction.png"
        if Path(meme_file).exists():
            meme_events.append({"t": t, "file": str(meme_file)})
        t += 4.0

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

cmd = [ffmpeg_bin(), "-y"] + inputs + ["-filter_complex", vf + ";" + af, "-map", "[out]", "-map", "[out_a]",
       "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
       "-c:v", "libx264", "-preset", "veryfast", "-b:v", "6M",
       "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
       "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
       "-movflags", "+faststart", str(out)]

print(f"\nRunning: {' '.join(cmd[:5])}...")
result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
print("Return code:", result.returncode)
print("STDERR:", result.stderr[-2000:] if result.stderr else "none")
