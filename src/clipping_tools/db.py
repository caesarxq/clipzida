"""SQLite state: schema, WAL, quota counters, audit log."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import ClipCandidate

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY, platform TEXT, external_id TEXT, name TEXT,
  permission_id INTEGER, active INTEGER DEFAULT 1, UNIQUE(platform, external_id));
CREATE TABLE IF NOT EXISTS permissions(id INTEGER PRIMARY KEY, source_id INTEGER,
  kind TEXT CHECK(kind IN ('campaign','written','own')), campaign_id INTEGER,
  evidence_url TEXT, granted_at TEXT, expires_at TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS campaigns(id INTEGER PRIMARY KEY, marketplace TEXT, external_id TEXT, name TEXT,
  subject TEXT, pay_model TEXT CHECK(pay_model IN ('per_view','pool')), rate_per_1k REAL,
  pool_total REAL, min_views INTEGER, min_payout REAL, max_payout REAL, budget_remaining REAL,
  platforms TEXT, required_tokens TEXT, rules_json TEXT, status TEXT, last_checked TEXT);
CREATE TABLE IF NOT EXISTS clips_raw(id INTEGER PRIMARY KEY, source_id INTEGER, external_id TEXT UNIQUE,
  url TEXT, title TEXT, broadcaster TEXT, creator TEXT, view_count INTEGER, duration REAL,
  language TEXT, created_at TEXT, fetched_at TEXT, thumbnail_url TEXT, video_id TEXT,
  vod_offset INTEGER, status TEXT);
CREATE TABLE IF NOT EXISTS analysis(clip_id INTEGER PRIMARY KEY, transcript_json TEXT, energy_json TEXT,
  moments_json TEXT, spoiler_risk REAL, score REAL, model TEXT, analyzed_at TEXT);
CREATE TABLE IF NOT EXISTS renders(id INTEGER PRIMARY KEY, clip_id INTEGER, variant TEXT, path TEXT,
  spec_json TEXT, checksum TEXT, rendered_at TEXT, UNIQUE(clip_id, variant));
CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY, render_id INTEGER, campaign_id INTEGER, platform TEXT,
  account TEXT, caption TEXT, hashtags TEXT, status TEXT, angle TEXT,
  scheduled_at TEXT, published_at TEXT, external_post_id TEXT, url TEXT,
  idempotency_key TEXT UNIQUE, review_message_id TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS approvals(id INTEGER PRIMARY KEY, post_id INTEGER, decision TEXT, reviewer TEXT,
  edits_json TEXT, decided_at TEXT);
CREATE TABLE IF NOT EXISTS metrics(post_id INTEGER, fetched_at TEXT, views INTEGER, likes INTEGER,
  comments INTEGER, shares INTEGER, approved_views INTEGER, payout REAL,
  PRIMARY KEY(post_id, fetched_at));
CREATE TABLE IF NOT EXISTS tokens(service TEXT PRIMARY KEY, access_token TEXT, refresh_token TEXT,
  expires_at TEXT, scopes TEXT);
CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY, platform TEXT, handle TEXT, brand_role TEXT,
  campaign_id INTEGER, created_at TEXT, warmup_stage INTEGER, daily_cap INTEGER,
  token_ref TEXT, status TEXT, UNIQUE(platform, handle));
CREATE TABLE IF NOT EXISTS quota_usage(service TEXT, day TEXT, units INTEGER, PRIMARY KEY(service, day));
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, ts TEXT, stage TEXT, entity TEXT,
  entity_id INTEGER, event TEXT, detail_json TEXT);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    # Lightweight migration: add columns introduced after first deploy.
    existing = {r[1] for r in conn.execute("PRAGMA table_info(posts)")}
    if "review_message_id" not in existing:
        conn.execute("ALTER TABLE posts ADD COLUMN review_message_id TEXT")
    if "angle" not in existing:
        conn.execute("ALTER TABLE posts ADD COLUMN angle TEXT")
    return conn


def upsert_clip(conn: sqlite3.Connection, clip: ClipCandidate, source_id: int | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO clips_raw(source_id, external_id, url, title, broadcaster, creator,
             view_count, duration, language, created_at, fetched_at, thumbnail_url, video_id,
             vod_offset, status)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'new')
           ON CONFLICT(external_id) DO UPDATE SET
             view_count=excluded.view_count, fetched_at=excluded.fetched_at
           RETURNING id""",
        (source_id, clip.external_id, clip.url, clip.title, clip.broadcaster_name,
         clip.creator_name, clip.view_count, clip.duration, clip.language,
         clip.created_at.isoformat(), utcnow(), clip.thumbnail_url, clip.video_id,
         clip.vod_offset),
    )
    row = cur.fetchone()
    conn.commit()
    return int(row[0])


def incr_quota(conn: sqlite3.Connection, service: str, units: int, day: str | None = None) -> int:
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn.execute(
        """INSERT INTO quota_usage(service, day, units) VALUES(?,?,?)
           ON CONFLICT(service, day) DO UPDATE SET units=units+excluded.units""",
        (service, day, units),
    )
    conn.commit()
    row = conn.execute("SELECT units FROM quota_usage WHERE service=? AND day=?", (service, day)).fetchone()
    return int(row[0])


def get_quota(conn: sqlite3.Connection, service: str, day: str | None = None) -> int:
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute("SELECT units FROM quota_usage WHERE service=? AND day=?", (service, day)).fetchone()
    return int(row[0]) if row else 0


def audit(conn: sqlite3.Connection, stage: str, entity: str, entity_id: int | None,
          event: str, detail: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_log(ts, stage, entity, entity_id, event, detail_json) VALUES(?,?,?,?,?,?)",
        (utcnow(), stage, entity, entity_id, event, json.dumps(detail or {})),
    )
    conn.commit()