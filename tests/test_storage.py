import asyncio
import json
from unittest.mock import AsyncMock
import httpx
from backend.app.services.normalizer import normalize
from backend.app.services.advantage import calculate
from backend.app.storage.repository import Repository
from backend.app.models.domain import MonitorStatus


async def test_redis_failure_falls_back_and_recovers(settings, payload):
    repo = Repository(settings)
    repo.redis = AsyncMock()
    repo.redis.set.side_effect = ConnectionError('private')
    snapshot = calculate(normalize(payload, 'test-1', 120), settings)
    repo.save(snapshot)
    await repo.persist(snapshot)
    assert 'redis' in repo.warnings
    assert (await repo.get_latest('test-1')).blue.gold == 40000
    repo.redis.set.side_effect = None
    await repo.persist(snapshot)
    assert 'redis' not in repo.warnings


async def test_clickhouse_write_retries_bounded_without_blocking_latest(settings, payload):
    repo = Repository(settings)
    repo.ch = AsyncMock()
    repo.ch_ready = True
    repo.query = AsyncMock(side_effect=RuntimeError('secret'))
    snapshot = calculate(normalize(payload, 'test-1', 120), settings)
    repo.save(snapshot)
    assert (await repo.get_latest('test-1')).blue.gold == 40000
    await repo.persist(snapshot)
    assert repo.query.await_count == 2
    assert 'clickhouse' in repo.warnings
    assert 'secret' not in str(repo.warnings)


async def test_history_merges_and_deduplicates(settings, payload):
    snapshot = calculate(normalize(payload, 'test-1', 120), settings)
    repo = Repository(settings)
    repo.ch = AsyncMock()
    repo.query = AsyncMock(return_value=httpx.Response(200, text=json.dumps({'snapshot_json': snapshot.model_dump_json()})+'\n'))
    repo.save(snapshot)
    values = await repo.history('test-1', 30)
    assert len(values) == 1
    assert 'FINAL' in repo.query.call_args.args[0]
    assert repo.query.call_args.kwargs['params']['param_id'] == 'test-1'


async def test_restart_resets_redis_tasks(settings):
    repo = Repository(settings)
    repo.redis = AsyncMock()
    async def scan(*args, **kwargs):
        yield b'hexsight:game:test-1:status'
    repo.redis.scan_iter = scan
    repo.redis.get.return_value = MonitorStatus(game_id='test-1', state='running').model_dump_json()
    await repo.initialize()
    assert repo.statuses['test-1'].state == 'stopped'
    assert '重启' in repo.statuses['test-1'].reason
    await repo.close()


async def test_bounded_event_queue():
    from backend.app.services.events import EventBus
    bus = EventBus(); q = bus.subscribe('game')
    for i in range(100): bus.publish('game', 'snapshot', {'i':i})
    assert q.qsize() == 32
    for _ in range(31): await q.get()
    assert (await q.get())['data']['i'] == 99
    bus.unsubscribe('game', q)
    assert not bus.subscribers
