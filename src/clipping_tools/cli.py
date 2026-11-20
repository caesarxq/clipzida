"""Typer CLI: doctor, ingest, campaigns."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

import typer

from . import db

app = typer.Typer(help="clipping_tools — autonomous GTA 6 clipping pipeline")
ROOT = Path(__file__).resolve().parents[2]


def _bin(name: str) -> str | None:
    local = ROOT / "bin" / name
    if local.exists():
        return str(local)
    return shutil.which(name)


@app.command()
def doctor() -> None:
    """Check environment readiness."""
    ok = True
    checks: list[tuple[str, bool, str]] = []
    checks.append(("python>=3.11", sys.version_info >= (3, 11), sys.version.split()[0]))
    for tool in ("ffmpeg", "ffprobe", "yt-dlp"):
        p = _bin(tool)
        detail = ""
        if p:
            try:
                flag = "--version" if tool == "yt-dlp" else "-version"
                out = subprocess.run([p, flag], capture_output=True, text=True, timeout=15)
                detail = out.stdout.splitlines()[0][:60] if out.stdout else ""
            except Exception as e:
                detail = str(e)
        checks.append((tool, bool(p), detail or "MISSING"))
        ok = ok and bool(p)
    try:
        conn = db.init_db(ROOT / "data/state.db")
        conn.execute("SELECT 1")
        checks.append(("sqlite state.db", True, str(ROOT / "data/state.db")))
    except Exception as e:
        checks.append(("sqlite state.db", False, str(e)))
        ok = False
    for cfg in ("pipeline.yaml", "platforms.yaml", "campaigns.yaml"):
        p = ROOT / "config" / cfg
        checks.append((f"config/{cfg}", p.exists(), "" if p.exists() else "MISSING"))
        ok = ok and p.exists()
    tw = bool(os.environ.get("TWITCH_CLIENT_ID") and os.environ.get("TWITCH_CLIENT_SECRET"))
    checks.append(("twitch credentials (env)", tw, "set" if tw else "not set — needed for live ingest"))
    for name, passed, detail in checks:
        mark = "OK " if passed else "!! "
        typer.echo(f"[{mark}] {name:28s} {detail}")
    raise typer.Exit(0 if ok else 1)


@app.command()
def ingest(hours: float = 24.0, dry_run: bool = True) -> None:
    """Poll Twitch GTA VI clips (requires TWITCH_CLIENT_ID/SECRET)."""
    from datetime import datetime, timedelta, timezone

    from .sources.twitch import TwitchClient

    async def _run() -> None:
        client = TwitchClient()
        if not await client.health():
            typer.echo("Twitch auth failed — set TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET (dev.twitch.tv/console).")
            raise typer.Exit(1)
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        clips = await client.fetch_candidates(since)
        typer.echo(f"fetched {len(clips)} clips since {since.isoformat()}")
        conn = db.init_db(ROOT / "data/state.db")
        from .prefilter import passes_gates, score
        kept = 0
        for c in clips:
            if not passes_gates(c):
                continue
            c.score = score(c, source_weight=0.0)
            if dry_run:
                typer.echo(f"  [dry] {c.external_id[:24]:24s} {c.broadcaster_name:16s} views={c.view_count:<8d} score={c.score}")
            else:
                db.upsert_clip(conn, c)
            kept += 1
        typer.echo(f"{kept} passed prefilter (dry_run={dry_run})")

    asyncio.run(_run())


@app.command()
def campaigns() -> None:
    """List the seeded campaign registry."""
    import yaml
    data = yaml.safe_load((ROOT / "config/campaigns.yaml").read_text())
    for c in data.get("campaigns", []):
        typer.echo(f"{c['status']:10s} {c['name']:38s} {c.get('pay_summary','')}")


if __name__ == "__main__":
    app()