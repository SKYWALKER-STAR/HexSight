import asyncio
import httpx
import pytest
from backend.app.clients.cito import CitoClient, CitoError
from backend.app.services.winrate import WinrateService


ROW = {'rank': 1, 'playerId': 'test-player', 'playerName': 'Test', 'value': 85.7,
       'gamesPlayed': 28, 'role': 'Mid', 'currentTeam': None, 'nationality': None}


async def test_shared_cache_and_stale_fallback(settings):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        assert request.url.path.endswith('/lol/leaderboards/winrate')
        return httpx.Response(200, json=[ROW]) if len(calls) == 1 else httpx.Response(429, headers={'retry-after': '900'})
    client = CitoClient(settings, transport=httpx.MockTransport(handler))
    service = WinrateService(client)
    try:
        results = await asyncio.gather(*(service.get() for _ in range(8)))
        assert len(calls) == 1
        assert all(r['items'] == [ROW] and not r['stale'] for r in results)
        service.expires = 0
        stale = await service.get()
        assert stale['stale'] and stale['items'] == [ROW]
        assert (await service.get())['stale']
        assert len(calls) == 2
    finally:
        await client.close()


@pytest.mark.parametrize('body', [None, {}, [{'rank': 1}], [{**ROW, 'value': 101}]])
async def test_invalid_response_is_cooled_down(settings, body):
    client = CitoClient(settings, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)))
    service = WinrateService(client)
    try:
        for _ in range(2):
            with pytest.raises(CitoError):
                await service.get()
        assert client.budget.used == 1
    finally:
        await client.close()


async def test_demo_does_not_request():
    assert (await WinrateService(None, demo=True).get())['demo_mode']
