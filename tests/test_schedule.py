import asyncio
from unittest.mock import AsyncMock
import pytest
from backend.app.services.schedule import ScheduleService
from backend.app.clients.cito import CitoError, CitoClient
import httpx


async def test_cache_sort_filter_and_unknown_game():
    client = AsyncMock()
    client.upcoming.return_value = {'data': [
        {'matchId': 'later', 'startTime': '2026-11-15T12:00:00Z'},
        {'matchId': 'done', 'state': 'completed'},
        {'matchId': 'first', 'startTime': '2026-11-14T12:00:00Z'},
    ]}
    service = ScheduleService(client)
    results = await asyncio.gather(*(service.get() for _ in range(5)))
    assert [m['matchId'] for m in results[0]['items']] == ['first', 'later']
    assert results[0]['items'][0]['gameId'] is None
    client.upcoming.assert_awaited_once()


async def test_schema_failure_is_not_cached():
    client = AsyncMock()
    client.upcoming.side_effect = [{'data': {}}, {'data': []}]
    service = ScheduleService(client)
    with pytest.raises(CitoError):
        await service.get()
    assert (await service.get())['items'] == []


async def test_upcoming_request(settings):
    def handler(request):
        assert request.url.path.endswith('/lol/matches/upcoming')
        assert request.url.params['hours'] == '336'
        return httpx.Response(200, json={'data': []})
    client = CitoClient(settings, transport=httpx.MockTransport(handler))
    assert await client.upcoming() == {'data': []}
    assert client.budget.used == 1
    await client.close()
