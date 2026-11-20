"""Twitch Helix ingest: app token, category lookup, Get Clips with pagination + rate guard."""
from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from datetime import datetime, timezone

import httpx

from ..models import ClipCandidate, Platform
from .base import SourceProvider

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX = "https://api.twitch.tv/helix"


class RateLimiter:
    """Sliding-window request cap (Twitch Clips endpoint: 100 req/min; we stay at 90)."""

    def __init__(self, max_per_minute: int = 90):
        self.max = max_per_minute
        self._stamps: deque[float] = deque()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            while self._stamps and now - self._stamps[0] > 60:
                self._stamps.popleft()
            if len(self._stamps) < self.max:
                self._stamps.append(now)
                return
            await asyncio.sleep(60 - (now - self._stamps[0]) + 0.1)


class TwitchClient(SourceProvider):
    name = "twitch"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None,
                 client: httpx.AsyncClient | None = None):
        self.client_id = client_id or os.environ.get("TWITCH_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("TWITCH_CLIENT_SECRET", "")
        self._client = client
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._limiter = RateLimiter()
        self._game_id: str | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    async def app_token(self) -> str:
        if self._token and time.time() < self._token_exp - 300:
            return self._token
        if not self.client_id or not self.client_secret:
            raise RuntimeError("TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET not set (register app at dev.twitch.tv/console)")
        http = await self._http()
        r = await http.post(TOKEN_URL, params={
            "client_id": self.client_id, "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        })
        r.raise_for_status()
        data = r.json()
        token = str(data["access_token"])
        self._token = token
        self._token_exp = time.time() + int(data.get("expires_in", 3600))
        return token

    async def _headers(self) -> dict[str, str]:
        return {"Client-Id": self.client_id, "Authorization": f"Bearer {await self.app_token()}"}

    async def game_id_for(self, query: str = "Grand Theft Auto VI") -> str:
        if self._game_id:
            return self._game_id
        http = await self._http()
        r = await http.get(f"{HELIX}/search/categories", params={"query": query},
                           headers=await self._headers())
        r.raise_for_status()
        for cat in r.json().get("data", []):
            if query.lower() in cat.get("name", "").lower():
                gid = str(cat["id"])
                self._game_id = gid
                return gid
        raise RuntimeError(f"Twitch category not found for {query!r}")

    async def get_clips(self, game_id: str, started_at: datetime,
                        ended_at: datetime | None = None, max_pages: int = 5) -> list[dict]:
        http = await self._http()
        params: dict = {"game_id": game_id, "first": 100,
                        "started_at": started_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        if ended_at:
            params["ended_at"] = ended_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out: list[dict] = []
        for _ in range(max_pages):
            await self._limiter.acquire()
            r = await http.get(f"{HELIX}/clips", params=params, headers=await self._headers())
            r.raise_for_status()
            body = r.json()
            out.extend(body.get("data", []))
            cursor = body.get("pagination", {}).get("cursor")
            if not cursor or not body.get("data"):
                break
            params["after"] = cursor
        return out

    @staticmethod
    def to_candidate(raw: dict) -> ClipCandidate:
        return ClipCandidate(
            source_platform=Platform.TWITCH,
            external_id=raw["id"],
            url=raw.get("url", ""),
            title=raw.get("title", ""),
            broadcaster_id=raw.get("broadcaster_id", ""),
            broadcaster_name=raw.get("broadcaster_name", ""),
            creator_name=raw.get("creator_name", ""),
            view_count=int(raw.get("view_count", 0)),
            duration=float(raw.get("duration", 0)),
            language=raw.get("language", ""),
            created_at=datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00")),
            thumbnail_url=raw.get("thumbnail_url", ""),
            video_id=raw.get("video_id", ""),
            vod_offset=raw.get("vod_offset"),
        )

    async def fetch_candidates(self, since: datetime, until: datetime | None = None) -> list[ClipCandidate]:
        gid = await self.game_id_for()
        raws = await self.get_clips(gid, since, until)
        return [self.to_candidate(r) for r in raws]

    async def health(self) -> bool:
        try:
            await self.app_token()
            return True
        except Exception:
            return False