"""Typer CLI: doctor, ingest, campaigns."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

from . import db
import clipping_tools.monitor as monitor_mod

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
    xk = bool(os.environ.get("X_CLIENT_ID") and os.environ.get("X_CLIENT_SECRET"))
    xa = bool(os.environ.get("X_ACCESS_TOKEN") and os.environ.get("X_ACCESS_TOKEN_SECRET"))
    checks.append(("X credentials (env)", xk and xa,
                   "set" if xk and xa else "not set — need X_CLIENT_ID/X_CLIENT_SECRET + X_ACCESS_TOKEN"))
    for name, passed, detail in checks:
        mark = "OK " if passed else "!! "
        typer.echo(f"[{mark}] {name:28s} {detail}")
    raise typer.Exit(0 if ok else 1)


def _persist_candidates(db_path, clips, threshold: float, dry_run: bool = False,
                        licensed: set[str] | None = None) -> int:
    """Apply rights gate + score threshold and persist. Returns kept count."""
    from .prefilter import passes_gates, score
    licensed = licensed or set()
    conn = db.init_db(db_path)
    kept = 0
    for c in clips:
        if not passes_gates(c):
            continue
        from .ingest_policy import licensed_source_weight
        weight = licensed_source_weight(c.broadcaster_name, licensed)
        if licensed and weight == 0.0:
            continue  # rights gate: unlicensed streamer
        c.score = score(c, source_weight=weight)
        if c.score < threshold:
            continue
        if dry_run:
            typer.echo(f"  [dry] {c.external_id[:24]:24s} {c.broadcaster_name:16s} "
                       f"views={c.view_count:<8d} score={c.score:.4f}")
        else:
            db.upsert_clip(conn, c)
        kept += 1
    conn.close()
    return kept


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
        import yaml
        cfg = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
        threshold = float(cfg.get("prefilter", {}).get("score_threshold", 0.35))
        camp = yaml.safe_load((ROOT / "config/campaigns.yaml").read_text())
        from .ingest_policy import licensed_from_campaigns
        licensed = licensed_from_campaigns(camp.get("campaigns", []))
        typer.echo(f"licensed broadcasters: {', '.join(sorted(licensed))}")
        kept = _persist_candidates(ROOT / "data/state.db", clips, threshold,
                                   dry_run=dry_run, licensed=licensed)
        typer.echo(f"{kept} passed prefilter (threshold={threshold}, dry_run={dry_run})")

    asyncio.run(_run())


@app.command()
def campaigns() -> None:
    """List the seeded campaign registry."""
    import yaml
    data = yaml.safe_load((ROOT / "config/campaigns.yaml").read_text())
    for c in data.get("campaigns", []):
        typer.echo(f"{c['status']:10s} {c['name']:38s} {c.get('pay_summary','')}")


@app.command()
def review_bot() -> None:
    """Run the Discord review bot (foreground; systemd runs it as a service)."""
    from .review.bot import run
    run()


@app.command()
def review_selftest() -> None:
    """Post a test embed to #clip-review and verify a reviewer decision round-trip."""
    from .review.bot import decide
    from .db import init_db
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        conn = init_db(os.path.join(d, "state.db"))
        conn.execute("INSERT INTO sources(id,platform,external_id,name) VALUES(1,'twitch','s','s')")
        conn.execute("INSERT INTO clips_raw(id,source_id,external_id,url,title,created_at,status) "
                     "VALUES(1,1,'c','u','t','2026-01-01T00:00:00+00:00','new')")
        conn.execute("INSERT INTO renders(id,clip_id,variant,path) VALUES(1,1,'v','v.mp4')")
        conn.execute("INSERT INTO posts(id,render_id,caption,status) VALUES(1,1,'SELFTEST','pending')")
        conn.commit()
        assert decide(["reviewer-role"], "reviewer-role", "approve", 1, "selftest", conn=conn) == "approved"
        assert conn.execute("SELECT status FROM posts WHERE id=1").fetchone()[0] == "approved"
    typer.echo("REVIEW_SELFTEST_OK")


@app.command()
def render(post_id: int) -> None:
    """Render an approved post into a captioned 1080x1920 vertical mp4."""
    from .review.render import render_post
    result = render_post(post_id, ROOT / "data/state.db")
    typer.echo(f"RENDER_OK post={result['post_id']} render={result['render_id']} path={result['path']}")


@app.command()
def review_publish() -> None:
    """Post pending drafts to Discord #clip-review as embeds with buttons."""
    import asyncio
    import discord
    from .db import init_db
    from .review.publisher import publish_pending_reviews
    from .review.pipeline import create_drafts_for_pending_clips, pending_posts

    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    channel_id = os.environ.get("DISCORD_REVIEW_CHANNEL_ID", "")
    role = os.environ.get("DISCORD_REVIEWER_ROLE_ID", "")
    if not (token and channel_id):
        raise typer.Exit("DISCORD_BOT_TOKEN / DISCORD_REVIEW_CHANNEL_ID not set")
    conn = init_db(ROOT / "data/state.db")
    n = create_drafts_for_pending_clips(conn)
    posts = pending_posts(conn)
    conn.close()
    typer.echo(f"created {n} draft(s), {len(posts)} pending")

    async def _send() -> None:
        async with discord.Client(intents=discord.Intents.default()) as client:
            await client.login(token)
            await publish_pending_reviews(client, ROOT / "data/state.db", channel_id, role)
    asyncio.run(_send())
    typer.echo("REVIEW_PUBLISH_DONE")


@app.command()
def monitor(db_path: Optional[str] = None) -> None:
    """Run pipeline health checks and post alerts to Discord."""
    monitor_mod.monitor(db_path=db_path)


@app.command()
def measure(
    subcommand: str,
    post_id: Optional[int] = None,
    views: Optional[int] = None,
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
    fetched_at: Optional[str] = None,
    approved_views: Optional[int] = None,
    payout: float = 0.0,
    retention_pct: Optional[float] = None,
    current_angle: Optional[str] = None,
) -> None:
    """Phase 6: Measurement & Optimization — record metrics, check retention,
    kill underperformers, auto-optimize default angle."""
    from datetime import datetime, timezone
    from clipping_tools.review.render import (
        record_metrics,
        get_avg_retention,
        should_kill_underperformer,
        auto_optimize_angle,
    )
    import yaml

    cfg = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text()).get(
        "measurement", {}
    )
    db_path = ROOT / "data" / "state.db"

    if subcommand == "record":
        if post_id is None or views is None:
            raise typer.Exit("measure record requires --post-id and --views")
        if fetched_at is None:
            fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record_metrics(
            str(db_path), post_id=post_id, views=views, likes=likes,
            comments=comments, shares=shares, fetched_at=fetched_at,
            approved_views=approved_views, payout=payout,
        )
        typer.echo(f"MEASURE_RECORD post={post_id} views={views} fetched_at={fetched_at}")

    elif subcommand == "retention":
        avg = get_avg_retention(str(db_path), post_id=post_id)
        scope = f"post #{post_id}" if post_id is not None else "all posts"
        typer.echo(f"MEASURE_RETENTION {scope}: {avg}%")

    elif subcommand == "kill":
        if retention_pct is None or views is None:
            raise typer.Exit("measure kill requires --retention-pct and --views")
        threshold = float(cfg.get("retention_threshold", 30.0))
        min_views = int(cfg.get("min_views_for_kill", 50))
        kill = should_kill_underperformer(retention_pct, views,
                                          retention_threshold=threshold,
                                          min_views=min_views)
        typer.echo(f"MEASURE_KILL post views={views} retention={retention_pct}% -> {'KILL' if kill else 'KEEP'}")

    elif subcommand == "optimize":
        if not cfg.get("auto_optimize", True):
            typer.echo("MEASURE_OPTIMIZE auto_optimize disabled in config")
            return
        if current_angle is None:
            raise typer.Exit("measure optimize requires --current-angle")
        min_posts = int(cfg.get("min_posts_per_angle", 1))
        min_views = int(cfg.get("min_views_per_angle", 10))
        threshold = float(cfg.get("switch_threshold", 10.0))
        new_angle = auto_optimize_angle(
            str(db_path), current_angle=current_angle,
            min_posts_per_angle=min_posts, min_views_per_angle=min_views,
            switch_threshold=threshold,
        )
        if new_angle != current_angle:
            typer.echo(f"MEASURE_OPTIMIZE switch {current_angle} -> {new_angle}")
        else:
            typer.echo(f"MEASURE_OPTIMIZE keep {current_angle}")

    else:
        raise typer.Exit(f"unknown subcommand: {subcommand}")


@app.command()
def metrics_collect(platform: Optional[str] = None) -> None:
    """Fetch engagement metrics from platform APIs and write to the DB.

    Collects views, likes, comments, shares for all published posts that have
    an external_post_id, via each platform's public API.
    """
    from clipping_tools.metrics.collect import collect_all
    results = collect_all(platform=platform,
                          db_path=str(ROOT / "data" / "state.db"))
    n_ok = sum(1 for r in results if r is not None)
    n_fail = sum(1 for r in results if r is None)
    for r in results:
        if r:
            typer.echo(
                f"  METRICS post={r['post_id']} platform={r['platform']} "
                f"views={r['metrics']['views']} likes={r['metrics']['likes']} "
                f"comments={r['metrics']['comments']} shares={r['metrics']['shares']}"
            )
    typer.echo(f"METRICS_COLLECT ok={n_ok} failed={n_fail}")


@app.command()
def tiktok_web(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the TikTok posting web UI (Login Kit + Direct Post posting screen)."""
    from .publish.tiktok_web import run
    run(host=host, port=port)


@app.command()
def cycle() -> None:
    """Run one autonomous pipeline pass (ingest -> review -> render -> publish)."""
    import asyncio
    from .review.orchestrator import run_cycle

    def _ingest():
        asyncio.run(_ingest_async())

    async def _ingest_async() -> None:
        from datetime import datetime, timedelta, timezone
        from .sources.twitch import TwitchClient
        client = TwitchClient()
        if not await client.health():
            raise typer.Exit("Twitch auth failed")
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        clips = await client.fetch_candidates(since)
        import yaml
        cfg = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
        threshold = float(cfg.get("prefilter", {}).get("score_threshold", 0.35))
        camp = yaml.safe_load((ROOT / "config/campaigns.yaml").read_text())
        from .ingest_policy import licensed_from_campaigns
        licensed = licensed_from_campaigns(camp.get("campaigns", []))
        _persist_candidates(ROOT / "data/state.db", clips, threshold, dry_run=False, licensed=licensed)
        typer.echo(f"ingest: {len(clips)} fetched")

    def _review_publish():
        asyncio.run(_review_publish_async())

    async def _review_publish_async() -> None:
        import discord
        from .review.publisher import publish_pending_reviews
        token = os.environ.get("DISCORD_BOT_TOKEN", "")
        channel_id = os.environ.get("DISCORD_REVIEW_CHANNEL_ID", "")
        role = os.environ.get("DISCORD_REVIEWER_ROLE_ID", "")
        if not (token and channel_id):
            return
        async with discord.Client(intents=discord.Intents.default()) as client:
            await client.login(token)
            await publish_pending_reviews(client, ROOT / "data/state.db", channel_id, role)

    def _render(post_id, db_path):
        from .review.render import render_post
        render_post(post_id, db_path)

    def _publish(post_id, db_path, path, platform):
        # Kill gate: skip publishing if retention is below threshold with enough views
        from clipping_tools.review.render import get_avg_retention, should_kill_underperformer
        import yaml
        mcfg = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text()).get(
            "measurement", {}
        )
        retention_threshold = float(mcfg.get("retention_threshold", 30.0))
        min_views_for_kill = int(mcfg.get("min_views_for_kill", 50))
        avg_ret = get_avg_retention(str(db_path), post_id=post_id)
        # Count views across all metrics rows for this post
        from ..db import init_db as _init_db
        conn = _init_db(db_path)
        vrow = conn.execute(
            "SELECT SUM(views) AS total_views FROM metrics WHERE post_id=?",
            (post_id,),
        ).fetchone()
        total_views = vrow["total_views"] or 0
        conn.close()
        if total_views >= min_views_for_kill and should_kill_underperformer(
            avg_ret, total_views, retention_threshold=retention_threshold,
            min_views=min_views_for_kill,
        ):
            typer.echo(f"  SKIP publish post {post_id} on {platform}: retention {avg_ret}% below kill threshold")
            return
        if platform == "tiktok":
            from .publish.tiktok import publish_to_tiktok
            publish_to_tiktok(post_id, db_path, path)
        elif platform == "x":
            from .publish.x import publish_to_x
            publish_to_x(post_id, db_path, path)
        else:
            from .publish.youtube import upload_to_youtube
            upload_to_youtube(post_id, db_path, path)
        from .db import init_db as _init_db2
        from .review.warmup import record_publish
        record_publish(_init_db2(db_path), platform, os.environ.get("YOUTUBE_CHANNEL_HANDLE") or None)

    def _gate(conn, platform, account):
        from .review.warmup import can_publish
        return can_publish(conn, platform, account)

    import yaml
    targets = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text()).get("publish", {}).get("targets", ["youtube"])
    result = run_cycle(ROOT / "data/state.db", ingest_fn=_ingest,
                       review_publish_fn=_review_publish, render_fn=_render,
                       publish_fn=_publish, gate_fn=_gate,
                       publish_account=os.environ.get("YOUTUBE_CHANNEL_HANDLE") or None,
                       targets=targets)
    typer.echo(f"CYCLE_OK rendered={result['rendered']} published={result['published']}")

    # Auto-optimize: switch default angle if another performs significantly better
    import yaml
    mcfg = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text()).get(
        "measurement", {}
    )
    if mcfg.get("auto_optimize", True):
        from clipping_tools.review.render import auto_optimize_angle
        current_angle = os.environ.get("CLIPZIDA_DEFAULT_ANGLE", "funny")
        min_posts = int(mcfg.get("min_posts_per_angle", 1))
        min_views = int(mcfg.get("min_views_per_angle", 10))
        threshold = float(mcfg.get("switch_threshold", 10.0))
        new_angle = auto_optimize_angle(
            str(ROOT / "data" / "state.db"), current_angle=current_angle,
            min_posts_per_angle=min_posts, min_views_per_angle=min_views,
            switch_threshold=threshold,
        )
        if new_angle != current_angle:
            typer.echo(f"MEASURE_OPTIMIZE switch {current_angle} -> {new_angle}")
        else:
            typer.echo(f"MEASURE_OPTIMIZE keep {current_angle}")


if __name__ == "__main__":
    app()
