import asyncio
import copy
from datetime import timedelta
import pytest
from backend.app.clients.cito import CitoError, RequestBudget
from backend.app.services.events import EventBus
from backend.app.services.monitor import MonitorManager
from backend.app.storage.repository import Repository
from backend.app.models.domain import utcnow


class SequenceClient:
    def __init__(self, items):
        self.items = iter(items)
        self.budget = RequestBudget(100)
        self.entered = asyncio.Event()
        self.cancelled = False

    async def stats(self, game_id):
        await self.budget.consume()
        self.entered.set()
        item = next(self.items, 'block')
        if item == 'block':
            try: await asyncio.Event().wait()
            except asyncio.CancelledError: self.cancelled = True; raise
        if isinstance(item, Exception): raise item
        return copy.deepcopy(item)

    async def coverage(self, match_id):
        await self.budget.consume()


@pytest.fixture
def fast_sleep(monkeypatch):
    delays = []
    original = asyncio.sleep
    async def sleep(delay):
        delays.append(delay)
        await original(0)
    monkeypatch.setattr('backend.app.services.monitor.asyncio.sleep', sleep)
    return delays


def setup(settings, items):
    client = SequenceClient(items)
    repo = Repository(settings)
    manager = MonitorManager(settings, client, repo, EventBus())
    return manager, client, repo


async def test_duplicate_start_and_cancel(settings, payload):
    manager, client, repo = setup(settings, ['block'])
    results = await asyncio.gather(*(manager.start('test-1') for _ in range(20)))
    assert all(r is results[0] for r in results)
    assert len(manager.tasks) == 1
    await client.entered.wait()
    await manager.stop('test-1')
    assert client.cancelled and not manager.tasks
    assert repo.statuses['test-1'].state == 'stopped'


async def test_retry_after_then_recover(settings, payload, fast_sleep):
    ended = copy.deepcopy(payload); ended['data']['state'] = 'finished'
    manager, client, repo = setup(settings, [CitoError('rate_limited','limited',retryable=True,retry_after=75), ended])
    await manager.start('test-1')
    await asyncio.wait_for(manager.tasks['test-1'], 2)
    assert fast_sleep == [75]
    assert repo.statuses['test-1'].state == 'stopped'
    assert repo.statuses['test-1'].consecutive_failures == 0
    assert repo.statuses['test-1'].request_count == 2


async def test_failure_threshold_and_backoff(settings, fast_sleep):
    settings.max_consecutive_failures = 4
    errors = [CitoError('upstream','unavailable',retryable=True) for _ in range(8)]
    manager, client, repo = setup(settings, errors)
    await manager.start('test-1'); await asyncio.wait_for(manager.tasks['test-1'], 2)
    assert repo.statuses['test-1'].state == 'error'
    assert client.budget.used == 4
    assert len(fast_sleep) == 3
    assert 2 <= fast_sleep[0] <= 3 and 4 <= fast_sleep[1] <= 5 and 8 <= fast_sleep[2] <= 9


async def test_permission_no_retry(settings, fast_sleep):
    manager, client, repo = setup(settings, [CitoError('permission','denied')])
    await manager.start('test-1'); await asyncio.wait_for(manager.tasks['test-1'], 2)
    assert repo.statuses['test-1'].state == 'error'
    assert client.budget.used == 1 and not fast_sleep


async def test_empty_stops(settings, fast_sleep):
    manager, client, repo = setup(settings, [{}, {}, {}, {}])
    await manager.start('test-1'); await asyncio.wait_for(manager.tasks['test-1'], 2)
    assert repo.statuses['test-1'].state == 'stopped'
    assert repo.statuses['test-1'].empty_responses == 3
    assert client.budget.used == 3


async def test_duplicate_and_old_frames_ignored(settings, payload, fast_sleep):
    old = copy.deepcopy(payload); old['frameTimestamp'] = (utcnow() - timedelta(seconds=60)).isoformat()
    old['data']['blueTeam']['totalGold'] = 1
    old['data']['state'] = 'finished'
    ended = copy.deepcopy(payload); ended['frameTimestamp'] = (utcnow() + timedelta(seconds=1)).isoformat()
    ended['data']['state'] = 'finished'
    manager, client, repo = setup(settings, [payload, payload, old, ended])
    await manager.start('test-1'); await asyncio.wait_for(manager.tasks['test-1'], 2)
    assert len(repo.frames['test-1']) == 2
    assert repo.latest['test-1'].blue.gold == 40000
    assert client.budget.used == 4


async def test_unknown_timestamp_dedup_and_no_score(settings, payload, fast_sleep):
    payload.pop('frameTimestamp')
    manager, client, repo = setup(settings, [payload, payload, CitoError('permission','stop')])
    await manager.start('test-1'); await asyncio.wait_for(manager.tasks['test-1'], 2)
    assert len(repo.frames['test-1']) == 1
    assert repo.latest['test-1'].advantage.score is None


async def test_cancel_during_backoff(settings):
    manager, client, repo = setup(settings, [CitoError('rate_limited','wait',retryable=True,retry_after=3600)])
    await manager.start('test-1')
    for _ in range(30):
        if repo.statuses['test-1'].next_retry_at: break
        await asyncio.sleep(.01)
    await asyncio.wait_for(manager.stop('test-1'), .5)
    assert not manager.tasks and repo.statuses['test-1'].next_retry_at is None


async def test_unhandled_exception_isolated(settings):
    manager, client, repo = setup(settings, [ValueError('do not expose sensitive response')])
    await manager.start('test-1'); await asyncio.wait_for(manager.tasks['test-1'], 2)
    assert repo.statuses['test-1'].error_code == 'internal'
    assert 'sensitive' not in repo.statuses['test-1'].reason


async def test_monitor_limit_and_shutdown(settings):
    settings.max_monitors = 1
    manager, client, repo = setup(settings, ['block'])
    await manager.start('test-1')
    with pytest.raises(CitoError): await manager.start('test-2')
    await manager.close()
    with pytest.raises(CitoError): await manager.start('test-1')


async def test_no_numeric_coverage_is_explicit(settings, payload):
    payload['data']['blueTeam'] = {}; payload['data']['redTeam'] = {}; payload['data']['players'] = []
    manager, client, repo = setup(settings, [payload])
    await manager.start('test-1'); await asyncio.wait_for(manager.tasks['test-1'], 2)
    assert repo.statuses['test-1'].error_code == 'no_numeric_state'


async def test_completed_real_fixture_stops_once(settings):
    import json
    from pathlib import Path
    body = json.loads((Path(__file__).parent / 'fixtures/cito_completed.json').read_text())
    manager, client, repo = setup(settings, [body])
    game_id = 'lol-game-117393592614464355'
    await manager.start(game_id); await asyncio.wait_for(manager.tasks[game_id], 2)
    assert repo.statuses[game_id].state == 'stopped'
    assert repo.statuses[game_id].reason == '比赛已结束'
    assert client.budget.used == 1


async def test_postgame_after_timestamped_frame_still_stops(settings, payload, fast_sleep):
    import json
    from pathlib import Path
    body = json.loads((Path(__file__).parent / 'fixtures/cito_completed.json').read_text())
    game_id = body['gameId']
    payload['data']['gameId'] = game_id
    manager, client, repo = setup(settings, [payload, body])
    await manager.start(game_id); await asyncio.wait_for(manager.tasks[game_id], 2)
    assert repo.statuses[game_id].state == 'stopped'
    assert repo.statuses[game_id].reason == '比赛已结束'
    assert repo.latest[game_id].source_ts is not None
    assert client.budget.used == 2


async def test_future_frame_does_not_poison_watermark(settings, payload, fast_sleep):
    future = copy.deepcopy(payload)
    future['frameTimestamp'] = (utcnow() + timedelta(hours=1)).isoformat()
    payload['data']['state'] = 'finished'
    manager, client, repo = setup(settings, [future, payload])
    await manager.start('test-1'); await asyncio.wait_for(manager.tasks['test-1'], 2)
    assert len(repo.frames['test-1']) == 1
    assert repo.latest['test-1'].source_ts < utcnow() + timedelta(seconds=5)
    assert repo.statuses['test-1'].state == 'stopped'
