import sys
sys.path.insert(0, "/home/clipzida/clipping_tools/src")
from clipping_tools.review.render import build_enhanced_filter
from pathlib import Path

vf, af = build_enhanced_filter(
    "/home/clipzida/clipping_tools/data/renders/caption_24.ass",
    "TEST HOOK",
    music_path="/home/clipzida/clipping_tools/assets/audio/music_bed.mp3",
    sfx_events=[{"t": 2.0, "file": "/home/clipzida/clipping_tools/assets/audio/boom.mp3"}],
    meme_events=[{"t": 3.0, "file": "/home/clipzida/clipping_tools/assets/memes/reaction.png"}],
)
print("VF:", vf)
print()
print("AF:", af)
