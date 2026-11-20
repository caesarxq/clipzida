"""Fresh-account warm-up ramp + per-platform quota gates (plan §5B, §12)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..db import get_quota, incr_quota


def _cfg() -> dict:
    root = Path(__file__).resolve().parents[3]
    return yaml.safe_load((root / "config/platforms.yaml").read_text())


def account_age_days(created_at: str) -> int:
    then = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    return max((datetime.now(timezone.utc) - then).days, 0)


def warmup_stage(age_days: int) -> int:
    """0 = week 1, 1 = week 2, 2 = week 3+."""
    return min(max(age_days // 7, 0), 2)


def daily_cap(platform_cfg: dict, age_days: int) -> int:
    ramp = platform_cfg.get("warmup", [1, 1, 1])
    return int(ramp[warmup_stage(age_days)])


def posts_today(conn: sqlite3.Connection, platform: str, account: str | None = None) -> int:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE platform=? AND status='published' "
        "AND substr(published_at,1,10)=?", (platform, day)
    ).fetchone()
    return int(row[0])


def can_publish(conn: sqlite3.Connection, platform: str, account: str | None = None,
                cfg: dict | None = None) -> tuple[bool, str]:
    """Gate: account warm-up daily cap AND platform API quota. Fail closed."""
    cfg = cfg or _cfg()
    pcfg = cfg.get(platform, {})
    row = conn.execute("SELECT created_at, status FROM accounts WHERE platform=? AND handle=?",
                       (platform, account)).fetchone() if account else None
    if row and row["status"] != "active":
        return False, f"account {account} not active"
    if row:
        cap = daily_cap(pcfg, account_age_days(row["created_at"]))
        used = posts_today(conn, platform)
        if used >= cap:
            return False, f"warmup cap reached ({used}/{cap})"
    # Hard per-day upload count (protects fresh channels regardless of unit math)
    max_uploads = pcfg.get("max_uploads_per_day")
    if max_uploads and platform == "youtube":
        if posts_today(conn, platform) >= int(max_uploads):
            return False, f"daily upload cap reached ({max_uploads})"
    # YouTube API unit budget (uploads cost 1600; pause at threshold to leave headroom)
    if platform == "youtube":
        units = pcfg.get("daily_quota_units", 10000)
        cost = pcfg.get("upload_cost", 1600)
        pause = pcfg.get("upload_pause_at_units", 8400)
        used_units = get_quota(conn, "youtube")
        if used_units >= pause or used_units + cost > units:
            return False, f"youtube quota pause ({used_units}/{units})"
    return True, "ok"


def record_publish(conn: sqlite3.Connection, platform: str, account: str | None = None) -> None:
    """Count the publish against both the daily cap and platform API units."""
    cfg = _cfg()
    pcfg = cfg.get(platform, {})
    if platform == "youtube":
        incr_quota(conn, "youtube", int(pcfg.get("upload_cost", 1600)))
