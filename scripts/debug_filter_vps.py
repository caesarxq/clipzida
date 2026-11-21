import sys
sys.path.insert(0, "/home/clipzida/clipping_tools/src")
from clipping_tools.review.render import (
    init_db_for_path, source_clip_for_post,
    download_clip, extract_wav, transcribe, energy_peaks,
    select_hook_moment, make_enhanced_ass, build_enhanced_filter,
    ffmpeg_bin
)
from clipping_tools.db import init_db
from pathlib import Path

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

vf, af = build_enhanced_filter(ass, hook,
                               str(music) if music.exists() else None,
                               sfx_events, meme_events)

print("=== VF (last 200 chars) ===")
print(vf[-200:])
print()
print("=== AF ===")
print(af)
print()
print("=== FULL_FILTER (last 200 chars) ===")
full_filter = vf.rstrip(";")
if af:
    full_filter += ";" + af
print(full_filter[-200:])
print()
print("Has double semicolon:", ";;[1:a]" in full_filter or ";;[2:a]" in full_filter or ";;[0:a]" in full_filter)
