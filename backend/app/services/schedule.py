import asyncio
import time
from datetime import datetime, timezone
from backend.app.clients.cito import CitoError


class ScheduleService:
    """Shared cache prevents each browser from spending an upstream request."""
    def __init__(self, client):
        self.client = client
        self.lock = asyncio.Lock()
        self.cached = None
        self.expires = 0

    async def get(self):
        async with self.lock:
            if self.cached is not None and time.monotonic() < self.expires:
                return self.cached
            body = await self.client.upcoming()
            rows = body.get('data')
            if not isinstance(rows, list):
                raise CitoError('schema', '赛程响应结构异常')
            items = []
            for row in rows:
                if not isinstance(row, dict) or not row.get('matchId'):
                    continue
                if str(row.get('state', 'unstarted')).lower() not in ('unstarted', 'upcoming', 'scheduled'):
                    continue
                item = {k: row.get(k) for k in ('matchId', 'gameId', 'startTime', 'leagueName', 'leagueSlug', 'tournamentName', 'blockName', 'strategy')}
                for key in ('team1', 'team2'):
                    team = row.get(key) or {}
                    item[key] = {k: team.get(k) for k in ('name', 'code', 'slug')}
                items.append(item)
            items.sort(key=lambda item: item.get('startTime') or '9999')
            self.cached = {'items': items, 'fetchedAt': datetime.now(timezone.utc).isoformat(),
                           'refreshSeconds': 60, 'hours': 336}
            self.expires = time.monotonic() + 60
            return self.cached
