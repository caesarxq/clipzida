import sys
sys.path.insert(0, "/home/clipzida/clipping_tools/src")
from clipping_tools.review.render import render_post
import traceback

try:
    r = render_post(24, "/home/clipzida/clipping_tools/data/state.db")
    print("RENDER_OK", r)
except Exception as e:
    print(f"RENDER_FAILED: {e}")
    traceback.print_exc()
