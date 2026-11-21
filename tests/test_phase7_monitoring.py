"""RED: Phase 7 — Monitoring & Alerting.
Health checks for Twitch/YouTube/Discord/ffmpeg/DB, alert posting to Discord,
and a `clipping-tools monitor` CLI command.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

import clipping_tools.monitor as monitor_mod


# ── Health checks ──────────────────────────────────────────────────────────

def test_check_twitch_health_true(monkeypatch):
    """Twitch health passes when app token succeeds."""
    async def fake_health(self):
        return True
    monkeypatch.setattr(monitor_mod.TwitchClient, "health", fake_health)
    ok, detail = asyncio.run(monitor_mod.check_twitch_health())
    assert ok is True
    assert "ok" in detail.lower()


def test_check_twitch_health_false(monkeypatch):
    """Twitch health fails when app token fails."""
    async def fake_health(self):
        return False
    monkeypatch.setattr(monitor_mod.TwitchClient, "health", fake_health)
    ok, detail = asyncio.run(monitor_mod.check_twitch_health())
    assert ok is False
    assert "fail" in detail.lower() or "error" in detail.lower()


def test_check_ffmpeg_health_true(monkeypatch):
    """ffmpeg health passes when binary exists and runs."""
    monkeypatch.setattr(monitor_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    class FakeResult:
        returncode = 0
        stdout = "ffmpeg version 6.1.1"

    monkeypatch.setattr(monitor_mod.subprocess, "run", lambda *a, **k: FakeResult())
    ok, detail = monitor_mod.check_ffmpeg_health()
    assert ok is True


def test_check_ffmpeg_health_missing(monkeypatch):
    """ffmpeg health fails when binary missing."""
    monkeypatch.setattr(monitor_mod.shutil, "which", lambda name: None)
    ok, detail = monitor_mod.check_ffmpeg_health()
    assert ok is False


def test_check_db_health_true(tmp_path):
    """DB health passes when DB is queryable."""
    import clipping_tools.db as db_mod
    db_path = os.path.join(tmp_path, "state.db")
    conn = db_mod.init_db(db_path)
    conn.execute("SELECT 1")
    conn.close()
    ok, detail = monitor_mod.check_db_health(db_path)
    assert ok is True


def test_check_db_health_false():
    """DB health fails when path is invalid."""
    ok, detail = monitor_mod.check_db_health("/nonexistent/path/state.db")
    assert ok is False


# ── Retention / kill checks ────────────────────────────────────────────────

def test_check_low_retention_posts(tmp_path):
    """Identifies posts with retention below kill threshold."""
    import clipping_tools.db as db_mod
    db_path = os.path.join(tmp_path, "state.db")
    conn = db_mod.init_db(db_path)
    conn.execute("INSERT INTO posts(id, caption, status) VALUES(1, 'a', 'published')")
    conn.execute("INSERT INTO posts(id, caption, status) VALUES(2, 'b', 'published')")
    conn.execute("INSERT INTO metrics(post_id, fetched_at, views, likes, comments, shares, approved_views, payout) "
                 "VALUES(1, 't1', 1000, 0, 0, 0, 200, 0.0), (2, 't1', 1000, 0, 0, 0, 800, 0.0)")
    conn.commit()
    conn.close()

    low = monitor_mod.check_low_retention_posts(db_path, threshold=30.0, min_views=50)
    # Post 1: 200/1000 = 20% < 30% → low. Post 2: 800/1000 = 80% → not low.
    assert len(low) == 1
    assert low[0]["post_id"] == 1


# ── All-health aggregate ───────────────────────────────────────────────────

def test_run_all_health_checks_returns_dict(tmp_path, monkeypatch):
    """run_all_health_checks returns a dict with per-check results."""
    import clipping_tools.db as db_mod
    db_path = os.path.join(tmp_path, "state.db")
    conn = db_mod.init_db(db_path)
    conn.execute("SELECT 1")
    conn.close()

    with patch.object(monitor_mod, "check_twitch_health", return_value=(True, "ok")), \
         patch.object(monitor_mod, "check_youtube_health", return_value=(True, "ok")), \
         patch.object(monitor_mod, "check_discord_health", return_value=(True, "ok")), \
         patch.object(monitor_mod, "check_ffmpeg_health", return_value=(True, "ok")), \
         patch.object(monitor_mod, "check_db_health", return_value=(True, "ok")):
        results = asyncio.run(monitor_mod.run_all_health_checks(db_path))
    assert isinstance(results, dict)
    assert all("ok" in v and "detail" in v for v in results.values())
    assert all(v["ok"] for v in results.values())


# ── Alert posting ──────────────────────────────────────────────────────────

def test_post_alerts_to_discord_skips_when_all_ok(monkeypatch):
    """No alerts posted when all checks pass."""
    posted = []
    monkeypatch.setattr(monitor_mod, "post_alert_to_discord", lambda *a, **k: posted.append(1) or True)
    results = {"twitch": {"ok": True, "detail": "ok"}, "youtube": {"ok": True, "detail": "ok"}}
    count = monitor_mod.post_alerts_to_discord(results, "123456789", "token")
    assert count == 0
    assert posted == []


def test_post_alerts_to_discord_posts_on_failure(monkeypatch):
    """Posts alert when a check fails."""
    posted = []
    monkeypatch.setattr(monitor_mod, "post_alert_to_discord", lambda kind, detail, channel, token: posted.append((kind, detail)) or True)
    results = {"twitch": {"ok": False, "detail": "auth failed"}, "youtube": {"ok": True, "detail": "ok"}}
    count = monitor_mod.post_alerts_to_discord(results, "123456789", "token")
    assert count == 1
    assert posted[0][0] == "twitch"


# ── CLI command ────────────────────────────────────────────────────────────

def test_monitor_command_outputs_summary(monkeypatch, capsys):
    """`clipping-tools monitor` prints a summary line."""
    import clipping_tools.cli as cli_mod
    import typer

    async def fake_health(db):
        return {"twitch": {"ok": True, "detail": "ok"}, "youtube": {"ok": False, "detail": "token expired"}}

    monkeypatch.setattr(cli_mod.monitor_mod, "run_all_health_checks", fake_health)
    monkeypatch.setattr(cli_mod.monitor_mod, "post_alerts_to_discord", lambda *a, **k: 1)
    with pytest.raises(typer.Exit):
        cli_mod.monitor(db_path="/tmp/x.db")
    out = capsys.readouterr().out
    assert "twitch" in out.lower() and "youtube" in out.lower()
