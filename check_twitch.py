import asyncio
from clipping_tools.sources.twitch import TwitchClient

async def main():
    c = TwitchClient()
    print("health:", await c.health())

asyncio.run(main())
