import asyncio
from datetime import datetime, timezone

import httpx

from clipping_tools.sources.twitch import RateLimiter, TwitchClient


def _raw(i):
    return {"id": i, "url": f"https://clips.twitch.tv/{i}", "broadcaster_id": "1",
            "broadcaster_name": "dinah", "creator_name": "viewer", "view_count": 1000,
            "duration": 25.0, "language": "en", "created_at": "2026-11-19T12:00:00Z",
            "thumbnail_url": "thumb", "video_id": "v", "vod_offset": 10, "title": "LMAO"}


def _handler(request: httpx.Request) -> httpx.Response:
    p = request.url.path
    if p == "/oauth2/token":
        return httpx.Response(200, json={"access_token": "tok", "expires_in": 5000, "token_type": "bearer"})
    if p == "/helix/search/categories":
        return httpx.Response(200, json={"data": [{"id": "999", "name": "Grand Theft Auto VI"}]})
    if p == "/helix/clips":
        if request.url.params.get("after"):
            return httpx.Response(200, json={"data": [_raw("c3")], "pagination": {}})
        return httpx.Response(200, json={"data": [_raw("c1"), _raw("c2")],
                                         "pagination": {"cursor": "cur1"}})
    return httpx.Response(404)


def test_fetch_candidates_paginates():
    async def run():
        transport = httpx.MockTransport(_handler)
        async with httpx.AsyncClient(transport=transport) as hc:
            c = TwitchClient(client_id="id", client_secret="sec", client=hc)
            clips = await c.fetch_candidates(datetime(2026, 11, 19, tzinfo=timezone.utc))
            assert [x.external_id for x in clips] == ["c1", "c2", "c3"]
            assert clips[0].broadcaster_name == "dinah"
            assert clips[0].duration == 25.0
            assert await c.health()
    asyncio.run(run())


def test_missing_credentials_health_false():
    async def run():
        c = TwitchClient(client_id="", client_secret="")
        assert not await c.health()
    asyncio.run(run())


def test_rate_limiter_allows_burst_up_to_cap():
    async def run():
        rl = RateLimiter(max_per_minute=3)
        for _ in range(3):
            await rl.acquire()
        assert len(rl._stamps) == 3
    asyncio.run(run())