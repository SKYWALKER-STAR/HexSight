import math
from backend.app.clients.cito import RequestBudget
from backend.app.models.domain import utcnow


class DemoClient:
    """Explicit opt-in synthetic data, never a fallback for a failed live API."""
    def __init__(self):
        self.budget = RequestBudget(0)
        self.ticks = {}

    async def coverage(self, match_id):
        await self.budget.consume()

    async def stats(self, game_id):
        await self.budget.consume()
        tick = self.ticks.get(game_id, 0) + 1
        self.ticks[game_id] = tick
        swing = round(math.sin(tick / 5) * 2400)
        teams, players = {}, []
        for side, offset in [('blue', swing), ('red', 0)]:
            teams[side + 'Team'] = {'name': f'DEMO {side.upper()}', 'totalGold': 36000 + tick * 220 + offset,
                                   'totalKills': 8 if side == 'blue' else 6, 'towers': 3, 'barons': 0,
                                   'inhibitors': 0, 'dragons': ['cloud'] if side == 'blue' else ['infernal']}
            for i, role in enumerate(['top', 'jungle', 'mid', 'bot', 'support']):
                players.append({'side': side, 'role': role, 'summonerName': f'{side}-{role}',
                                'championId': ['Gnar', 'Vi', 'Ahri', 'Jinx', 'Nautilus'][i],
                                'totalGold': 7200 + tick * 44 + offset / 5, 'creepScore': 140 + i * 10,
                                'level': 11 + i % 3, 'kills': 2, 'deaths': 1, 'assists': 3,
                                'items': [1001, 1055]})
        return {'success': True, 'frameTimestamp': utcnow().isoformat(),
                'data': {'gameId': game_id, 'state': 'in_game', 'gameTime': 1200 + tick * 30,
                         **teams, 'players': players}}

    async def close(self):
        pass

    async def upcoming(self):
        from datetime import timedelta
        return {'data': [dict(matchId=f'demo-match-{i}', gameId=f'demo-game-{i}',
                    startTime=(utcnow() + timedelta(hours=i * 3 + 1)).isoformat(),
                    leagueName='DEMO', leagueSlug='demo', tournamentName='演示邀请赛',
                    strategy='Bo3', state='unstarted',
                    team1={'name': f'DEMO BLUE {i}', 'code': f'B{i}'},
                    team2={'name': f'DEMO RED {i}', 'code': f'R{i}'}) for i in range(4)]}
