import asyncio
import time
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ValidationError
from backend.app.clients.cito import CitoError


class RankedPlayer(BaseModel):
    rank: int = Field(ge=1)
    playerId: str
    playerName: str
    nationality: str | None = None
    role: str | None = None
    currentTeam: str | None = None
    value: float = Field(ge=0, le=100)
    gamesPlayed: int = Field(ge=0)


class WinrateService:
    """One shared hourly snapshot; failed refreshes back off for all browsers."""
    def __init__(self, client, demo=False):
        self.client, self.demo = client, demo
        self.lock = asyncio.Lock()
        self.cached = None
        self.expires = 0
        self.error = None

    async def get(self):
        async with self.lock:
            if self.demo:
                return {'items': [], 'fetchedAt': None, 'stale': False, 'demo_mode': True}
            if time.monotonic() < self.expires:
                if self.cached is not None:
                    return {**self.cached, 'stale': self.error is not None}
                raise self.error
            try:
                body = await self.client.get('lol/leaderboards/winrate', allow_list=True)
                rows = body.get('data') if isinstance(body, dict) else body
                if not isinstance(rows, list):
                    raise CitoError('schema', 'Invalid winrate leaderboard')
                try:
                    items = [RankedPlayer.model_validate(row).model_dump() for row in rows]
                except ValidationError:
                    raise CitoError('schema', 'Invalid winrate leaderboard rows') from None
                items.sort(key=lambda p: p['rank'])
                self.cached = {'items': items, 'fetchedAt': datetime.now(timezone.utc).isoformat(),
                               'refreshSeconds': 3600, 'demo_mode': False}
                self.error = None
                self.expires = time.monotonic() + 3600
            except CitoError as error:
                self.error = error
                self.expires = time.monotonic() + max(300, error.retry_after or 0)
                if self.cached is None:
                    raise
            return {**self.cached, 'stale': self.error is not None}
