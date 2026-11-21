"""Monitoring & alerting for the CLIPZIDA pipeline (Phase 7).

Health checks for Twitch, YouTube, Discord, ffmpeg, and the SQLite DB.
Posts alerts to Discord when any check fails. Provides the `monitor`
CLI command and a systemd timer unit for periodic runs.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

import httpx

from . import db
from .review.render import get_avg_retention, init_db_for_path
from .sources.twitch import TwitchClient

ROOT = Path(__file__).resolve().parents[2]

ALERTS_KIND_HEALTH = "health"
ALERTS_KIND_RETENTION = "retention"
ALERTS_KIND_CYCLE = "cycle"


# ── Component health checks ────────────────────────────────────────────────

async def check_twitch_health() -> tuple[bool, str]:
    """Twitch app-token auth is valid."""
    try:
        client = TwitchClient()
        ok = await client.health()
        return (ok, "ok" if ok else "app-token auth failed")
    except Exception as e:  # noqa: BLE001
        return (False, f"error: {e}")


def check_youtube_health() -> tuple[bool, str]:
    """YouTube OAuth refresh token is present and can be exchanged."""
    try:
        conn = init_db_for_path(ROOT / "data" / "state.db")
        row = conn.execute(
            "SELECT refresh_token FROM tokens WHERE service='youtube'"
        ).fetchone()
        conn.close()
        if not row or not row["refresh_token"]:
            return (False, "no refresh token — authorise via Google OAuth first")
        return (True, "ok")
    except Exception as e:  # noqa: BLE001
        return (False, f"error: {e}")


def check_discord_health() -> tuple[bool, str]:
    """Discord bot process is running (checked via pgrep)."""
    try:
        out = subprocess.run(
            ["pgrep", "-f", "clipping-tools review-bot"],
            capture_output=True, text=True, timeout=10,
        )
        ok = out.returncode == 0 and bool(out.stdout.strip())
        return (ok, "ok" if ok else "bot process not running")
    except Exception as e:  # noqa: BLE001
        return (False, f"error: {e}")


def check_ffmpeg_health() -> tuple[bool, str]:
    """ffmpeg binary exists and runs `-version` successfully."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return (False, "binary not found on PATH")
    try:
        out = subprocess.run(
            [ffmpeg, "-version"], capture_output=True, text=True, timeout=15
        )
        ok = out.returncode == 0
        detail = out.stdout.splitlines()[0][:60] if out.stdout else ""
        return (ok, detail or "ok")
    except Exception as e:  # noqa: BLE001
        return (False, f"error: {e}")


def check_db_health(db_path: str | Path) -> tuple[bool, str]:
    """SQLite DB is connectable and queryable."""
    try:
        conn = db.init_db(db_path)
        conn.execute("SELECT 1")
        conn.close()
        return (True, "ok")
    except Exception as e:  # noqa: BLE001
        return (False, f"error: {e}")


# ── Retention / kill checks ────────────────────────────────────────────────

def check_low_retention_posts(
    db_path: str | Path,
    threshold: float = 30.0,
    min_views: int = 50,
) -> list[dict[str, Any]]:
    """Return posts whose retention is below `threshold` and views >= `min_views`.

    Retention = approved_views / views * 100. Uses the same kill logic as
    should_kill_underperformer (Phase 6).
    """
    conn = init_db_for_path(db_path)
    try:
        rows = conn.execute(
            """
            SELECT p.id AS post_id, p.caption, p.angle,
                   SUM(m.views) AS total_views,
                   SUM(m.approved_views) AS total_approved
            FROM posts p
            JOIN metrics m ON m.post_id = p.id
            GROUP BY p.id
            HAVING total_views >= ?
               AND (SUM(m.approved_views) * 100.0 / total_views) < ?
            ORDER BY (SUM(m.approved_views) * 1.0 / total_views) ASC
            """,
            (min_views, threshold),
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "post_id": r["post_id"],
            "caption": r["caption"],
            "angle": r["angle"],
            "views": r["total_views"],
            "retention_pct": round(
                (r["total_approved"] or 0) / r["total_views"] * 100.0, 2
            ),
        }
        for r in rows
    ]


# ── Aggregate ──────────────────────────────────────────────────────────────

async def run_all_health_checks(db_path: str | Path) -> dict[str, dict[str, Any]]:
    """Run every health check and return {name: {ok, detail}}.

    Includes a low-retention scan; any post below threshold counts as a
    retention alert.
    """
    twitch_ok, twitch_detail = await check_twitch_health()
    yt_ok, yt_detail = check_youtube_health()
    dc_ok, dc_detail = check_discord_health()
    ff_ok, ff_detail = check_ffmpeg_health()
    db_ok, db_detail = check_db_health(db_path)

    results: dict[str, dict[str, Any]] = {
        "twitch": {"ok": twitch_ok, "detail": twitch_detail},
        "youtube": {"ok": yt_ok, "detail": yt_detail},
        "discord": {"ok": dc_ok, "detail": dc_detail},
        "ffmpeg": {"ok": ff_ok, "detail": ff_detail},
        "database": {"ok": db_ok, "detail": db_detail},
    }

    # Retention scan — treat any low-retention post as an alert.
    try:
        low = check_low_retention_posts(db_path)
        if low:
            results["retention"] = {
                "ok": False,
                "detail": f"{len(low)} post(s) below kill threshold",
                "posts": low,
            }
        else:
            results["retention"] = {"ok": True, "detail": "all posts above threshold"}
    except Exception as e:  # noqa: BLE001
        results["retention"] = {"ok": False, "detail": f"error: {e}"}

    return results


# ── Discord alerting ───────────────────────────────────────────────────────

def _discord_api_url(channel_id: str) -> str:
    return f"https://discord.com/api/v10/channels/{channel_id}/messages"


def post_alert_to_discord(
    kind: str,
    detail: str,
    channel_id: str,
    bot_token: str,
) -> bool:
    """Post a single alert embed to a Discord channel. Returns True on success."""
    try:
        embed = {
            "title": f"ALERT — {kind.upper()}",
            "description": detail,
            "color": 0xFF0000,  # red
        }
        resp = httpx.post(
            _discord_api_url(channel_id),
            headers={"Authorization": f"Bot {bot_token}"},
            json={"embeds": [embed]},
            timeout=15,
        )
        return resp.status_code in (200, 201, 204)
    except Exception:  # noqa: BLE001
        return False


def post_alerts_to_discord(
    results: dict[str, dict[str, Any]],
    channel_id: str,
    bot_token: str,
) -> int:
    """Post an alert for every failing health check. Returns number posted."""
    posted = 0
    for name, result in results.items():
        if result.get("ok"):
            continue
        detail = result.get("detail", "no detail")
        if "posts" in result and isinstance(result["posts"], list):
            # Retention alert — summarise the worst offender.
            worst = result["posts"][0]
            detail = (
                f"post #{worst['post_id']} retention {worst['retention_pct']}% "
                f"(views={worst['views']})"
            )
        if post_alert_to_discord(name, detail, channel_id, bot_token):
            posted += 1
    return posted


# ── CLI command ────────────────────────────────────────────────────────────

def monitor(
    db_path: Optional[str | Path] = None,
    alerts_channel: str | None = None,
    post_alerts: bool = True,
) -> None:
    """Run all health checks, print a summary, and post alerts to Discord.

    Defaults:
      - db_path: CLIPZIDA_DB env var or data/state.db
      - alerts_channel: DISCORD_ALERTS_CHANNEL_ID env var
      - post_alerts: True
    """
    import typer

    from . import cli as cli_mod  # noqa: F401  (ensures typer import)

    if db_path is None:
        db_path = os.environ.get("CLIPZIDA_DB", str(Path("data") / "state.db"))
    if alerts_channel is None:
        alerts_channel = os.environ.get("DISCORD_ALERTS_CHANNEL_ID", "")
    bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")

    typer.echo("CLIPZIDA pipeline health check")
    typer.echo("=" * 40)

    results = asyncio.run(run_all_health_checks(db_path))

    all_ok = True
    for name in sorted(results):
        r = results[name]
        mark = "OK  " if r["ok"] else "!!  "
        all_ok = all_ok and r["ok"]
        typer.echo(f"[{mark}] {name:14s} {r['detail']}")

    typer.echo("=" * 40)
    typer.echo(f"Overall: {'HEALTHY' if all_ok else 'UNHEALTHY'}")

    if post_alerts and not all_ok and alerts_channel and bot_token:
        posted = post_alerts_to_discord(results, alerts_channel, bot_token)
        typer.echo(f"Posted {posted} alert(s) to Discord #{alerts_channel}")
    elif post_alerts and not all_ok:
        typer.echo("Alerts suppressed: DISCORD_ALERTS_CHANNEL_ID or DISCORD_BOT_TOKEN missing")

    raise typer.Exit(0 if all_ok else 1)
