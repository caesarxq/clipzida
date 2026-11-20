"""Discord-safe review proxy: re-encode a master render to fit upload limits."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

DISCORD_CEILING = 10_000_000  # conservative; Discord can reject 20MB+ on some servers


def needs_proxy(size_bytes: int, ceiling: int = DISCORD_CEILING) -> bool:
    return size_bytes > ceiling


def proxy_params(ceiling: int = DISCORD_CEILING) -> dict:
    return {"width": 540, "height": 960, "video_bitrate": "800k", "audio_bitrate": "96k",
            "max_bytes": ceiling}


def build_proxy_command(src: str | Path, out: str | Path) -> list[str]:
    p = proxy_params()
    return [
        shutil.which("ffmpeg") or "ffmpeg", "-y", "-i", str(src),
        "-c:v", "libx264", "-preset", "medium",
        "-b:v", p["video_bitrate"], "-maxrate", p["video_bitrate"], "-bufsize", "1600k",
        "-vf", f"scale={p['width']}:{p['height']}",
        "-c:a", "aac", "-b:a", p["audio_bitrate"], "-movflags", "+faststart", str(out),
    ]


def make_proxy(src: str | Path, out_dir: str | Path | None = None,
               ceiling: int = DISCORD_CEILING) -> Path | None:
    """Create a proxy only when the master exceeds the ceiling. Returns proxy path or None."""
    src = Path(src)
    if not needs_proxy(src.stat().st_size, ceiling):
        return None
    out_dir = Path(out_dir) if out_dir else src.parent
    out = out_dir / f"{src.stem}_review.mp4"
    subprocess.run(build_proxy_command(src, out), check=True,
                   capture_output=True, text=True, timeout=900)
    return out
