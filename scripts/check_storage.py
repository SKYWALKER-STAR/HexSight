"""Opt-in persistence smoke check; use an isolated test database and Redis DB."""
import asyncio
import os
import uuid
from backend.app.config import Settings
from backend.app.clients.demo import DemoClient
from backend.app.models.domain import MonitorStatus
from backend.app.services.normalizer import normalize
from backend.app.services.advantage import calculate
from backend.app.storage.repository import Repository


async def main():
    settings = Settings(_env_file=None, redis_url=os.environ['TEST_REDIS_URL'],
                        clickhouse_url=os.environ['TEST_CLICKHOUSE_URL'],
                        clickhouse_database='hexsight_test_' + uuid.uuid4().hex[:12],
                        clickhouse_user=os.environ.get('TEST_CLICKHOUSE_USER', 'default'),
                        clickhouse_password=os.environ.get('TEST_CLICKHOUSE_PASSWORD', ''))
    game = 'storage-' + uuid.uuid4().hex[:12]
    first = Repository(settings)
    second = None
    try:
        await first.initialize()
        assert not first.warnings, first.warnings
        payload = await DemoClient().stats(game)
        snapshot = calculate(normalize(payload, game, 120, source='demo'), settings)
        await first.save_status(MonitorStatus(game_id=game, state='running'))
        first.save(snapshot)
        await asyncio.wait_for(first.queue.join(), 15)
        assert not first.warnings, first.warnings
        await first.persist(snapshot)  # deliberate retry/duplicate
        second = Repository(settings)
        await second.initialize()
        assert second.statuses[game].state == 'stopped'
        assert (await second.get_latest(game)).game_id == game
        assert len(await second.history(game, 30)) == 1
        # Prove latest can also recover directly from ClickHouse without the cache.
        await second.redis.delete(f'hexsight:game:{game}:latest')
        second.latest.clear()
        assert (await second.get_latest(game)).blue.gold == snapshot.blue.gold
        print('PASS: Redis latest/status, restart-to-stopped, ClickHouse persistence/history/dedup/cache fallback')
    finally:
        if first.ch:
            try: await first.query(f'DROP DATABASE IF EXISTS {settings.clickhouse_database}')
            except Exception: pass
        if first.redis:
            await first.redis.delete(f'hexsight:game:{game}:latest', f'hexsight:game:{game}:status')
        await first.close()
        if second: await second.close()


if __name__ == '__main__':
    asyncio.run(main())
