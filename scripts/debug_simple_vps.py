import sys
sys.path.insert(0, "/home/clipzida/clipping_tools/src")
from pathlib import Path
from clipping_tools.review.render import (
    ffmpeg_bin, init_db_for_path, source_clip_for_post,
    download_clip, extract_wav, transcribe, energy_peaks,
    select_hook_moment, make_enhanced_ass, build_enhanced_filter,
    render as render_fn,
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
out = WORK / f"clipzida_24_test.mp4"

# Download if needed
if not src.exists():
    download_clip(clip["url"], src)
extract_wav(src, wav)
words = transcribe(wav)
peaks = energy_peaks(wav)
moment = select_hook_moment(words, peaks)
hook = (words[0]["word"] if words else clip["title"] or "GTA 6 MOMENT")[:24].upper()
make_enhanced_ass(words, ass, hook)

# Build filter with NO sfx, NO memes
vf, af = build_enhanced_filter(ass, hook, None, [], [])
full_filter = vf.rstrip(";")
if af:
    full_filter += ";" + af

print("=== VDF (last 150 chars) ===")
print(vf[-150:])
print()
print("=== AF ===")
print(af[:100] if af else "(none)")
print()
print("=== FULL_FILTER (last 150 chars) ===")
print(full_filter[-150:])
print()
print("Has double semicolon:", ";" + ";" in full_filter)

cmd = [ffmpeg_bin(), "-y", "-i", str(src), "-filter_complex", full_filter,
       "-map", "[out]", "-map", "[out_a]",
       "-c:v", "libx264", "-preset", "veryfast", "-b:v", "6M",
       "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
       "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
       "-movflags", "+faststart", str(out)]

print("\nRunning ffmpeg (no sfx/memes)...")
result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
print("Return code:", result.returncode)
print("STDERR (last 1000 chars):")
print(result.stderr[-1000:] if result.stderr else "none")
