import asyncio
from datetime import timedelta
from email.utils import format_datetime
import httpx
import pytest
from backend.app.clients.cito import CitoClient, CitoError, retry_after_seconds, RequestBudget
from backend.app.models.domain import utcnow


@pytest.mark.parametrize('status,code,retryable', [(401,'permission',False),(403,'permission',False),
    (404,'not_found',False),(429,'rate_limited',True),(500,'upstream',True),(503,'upstream',True),(400,'http_error',False)])
async def test_http_errors_sanitized(settings, status, code, retryable):
    client = CitoClient(settings, transport=httpx.MockTransport(lambda _: httpx.Response(status,
                        text='secret-provider-content', headers={'Retry-After':'45'})))
    try:
        with pytest.raises(CitoError) as caught:
            await client.stats('test-1')
        assert caught.value.code == code
        assert caught.value.retryable == retryable
        assert 'secret' not in str(caught.value)
        if status == 429: assert caught.value.retry_after == 45
    finally:
        await client.close()


@pytest.mark.parametrize('error,code', [(httpx.ReadTimeout('secret'), 'timeout'), (httpx.ConnectError('secret'), 'network')])
async def test_transport_errors(settings, error, code):
    def handler(_): raise error
    client = CitoClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(CitoError) as caught: await client.stats('test-1')
    assert caught.value.code == code and caught.value.retryable
    await client.close()


async def test_auth_endpoint_budget_and_coverage(settings):
    paths = []
    def handler(request):
        assert request.headers['x-api-key'] == 'test-key-not-real'
        assert 'test-key-not-real' not in str(request.url)
        paths.append(request.url.path)
        return httpx.Response(200, json={'coverage':{'numeric_live_state':True}})
    settings.request_budget = 2
    client = CitoClient(settings, transport=httpx.MockTransport(handler))
    await client.coverage('match-1'); await client.stats('test-1')
    with pytest.raises(CitoError, match='预算'): await client.stats('test-1')
    assert paths == ['/api/v1/lol/matches/match-1/coverage', '/api/v1/lol/live/test-1/stats']
    await client.close()


async def test_no_coverage_stops(settings):
    client = CitoClient(settings, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'coverage': {'numeric_live_state':False}})))
    with pytest.raises(CitoError) as caught: await client.coverage('match-1')
    assert caught.value.code == 'no_coverage' and not caught.value.retryable
    await client.close()


@pytest.mark.parametrize('body', ['not JSON', '[]', '{"success": false}'])
async def test_invalid_response(settings, body):
    client = CitoClient(settings, transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body)))
    with pytest.raises(CitoError): await client.stats('test-1')
    await client.close()


def test_retry_after_http_date_and_invalid():
    assert 58 <= retry_after_seconds(format_datetime(utcnow() + timedelta(seconds=60))) <= 60
    assert retry_after_seconds('nonsense') is None
    assert retry_after_seconds('NaN') is None
    assert retry_after_seconds('-3') == 0


async def test_budget_concurrency():
    budget = RequestBudget(3)
    results = await asyncio.gather(*(budget.consume() for _ in range(10)), return_exceptions=True)
    assert budget.used == 3
    assert sum(isinstance(r, CitoError) for r in results) == 7


async def test_http_cancellation(settings):
    entered = asyncio.Event()
    async def handler(_):
        entered.set()
        await asyncio.Event().wait()
    client = CitoClient(settings, transport=httpx.MockTransport(handler))
    task = asyncio.create_task(client.stats('test-1'))
    await entered.wait(); task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    await client.close()

async def test_items_shared_and_enriched(settings):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/static/items'):
            return httpx.Response(200, json={'data': {'1001': {'name': 'Boots', 'gold': {'total': 300}}}})
        return httpx.Response(200, json={'data': {'players': [{'items': [1001, '1001', 9999, 0]}]}})
    client = CitoClient(settings, transport=httpx.MockTransport(handler))
    results = await asyncio.gather(*(client.stats(str(i)) for i in range(5)))
    assert sum(p.endswith('/static/items') for p in calls) == 1
    assert results[0]['data']['players'][0]['itemDetails'] == [
        {'name': 'Boots', 'gold': {'total': 300}}, {'name': 'Boots', 'gold': {'total': 300}}, None, None]
    await client.close()


async def test_items_failure_cooldown(settings):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/static/items'):
            return httpx.Response(429, headers={'retry-after': '900'})
        return httpx.Response(200, json={'data': {'players': [{'items': [1001]}]}})
    client = CitoClient(settings, transport=httpx.MockTransport(handler))
    for _ in range(3):
        body = await client.stats('test')
        assert body['data']['players'][0]['itemDetails'] == [None]
    assert sum(p.endswith('/static/items') for p in calls) == 1
    await client.close()


@pytest.mark.parametrize('id_field', ['id', 'itemId'])
async def test_items_root_list_shared(settings, id_field):
    calls = []
    item = {id_field: 1001, 'name': 'Boots', 'gold': {'total': 300}}
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/static/items'):
            return httpx.Response(200, json=[item])
        return httpx.Response(200, json={'data': {'players': [{'items': [1001, '1001', 9999]}]}})
    client = CitoClient(settings, transport=httpx.MockTransport(handler))
    try:
        results = await asyncio.gather(*(client.stats(str(i)) for i in range(5)))
        assert sum(p.endswith('/static/items') for p in calls) == 1
        for result in results:
            assert result['data']['players'][0]['itemDetails'] == [item, item, None]
    finally:
        await client.close()


async def test_stats_still_rejects_root_list(settings):
    client = CitoClient(settings, transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=[])))
    try:
        with pytest.raises(CitoError) as caught:
            await client.stats('test')
        assert caught.value.code == 'schema'
    finally:
        await client.close()

async def test_champions_shared_aliases_and_details(settings):
    champion = {'championId': 103, 'id': 'Ahri', 'name': 'Ahri',
                'imageUrl': 'https://example.com/ahri.png', 'stats': {'hp': 590}}
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/static/champions'):
            return httpx.Response(200, json=[champion])
        return httpx.Response(200, json={'data': {'players': [
            {'championId': 103}, {'championId': 'ahri'},
            {'championName': 'Ahri'}, {'championId': 'unknown'}]}})
    client = CitoClient(settings, transport=httpx.MockTransport(handler))
    try:
        results = await asyncio.gather(*(client.stats(str(i)) for i in range(5)))
        assert sum(p.endswith('/static/champions') for p in calls) == 1
        for result in results:
            players = result['data']['players']
            assert all(p['championDetails'] == champion for p in players[:3])
            assert players[0]['championIconUrl'] == champion['imageUrl']
            assert players[3]['championDetails'] is None
    finally:
        await client.close()


async def test_champions_refresh_failure_retains_cache(settings):
    responses = [httpx.Response(200, json={'data': [{'key': '103', 'name': 'Ahri'}]}),
                 httpx.Response(429, headers={'retry-after': '900'})]
    client = CitoClient(settings, transport=httpx.MockTransport(lambda _: responses.pop(0)))
    try:
        first = await client.champion_catalog()
        client._champions_refresh_at = 0
        assert await client.champion_catalog() == first
        assert await client.champion_catalog() == first
        assert not responses
    finally:
        await client.close()
