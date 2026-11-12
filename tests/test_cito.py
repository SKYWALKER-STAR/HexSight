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
