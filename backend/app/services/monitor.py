import logging
import asyncio
import hashlib
import json
import random
from collections import defaultdict
from datetime import timedelta
from backend.app.clients.cito import CitoError
from backend.app.models.domain import MonitorStatus, utcnow
from backend.app.services.normalizer import normalize, ENDED
from backend.app.services.advantage import calculate


logger = logging.getLogger(__name__)


class MonitorManager:
    def __init__(self, settings, client, repository, events):
        self.settings, self.client, self.repo, self.events = settings, client, repository, events
        self.tasks: dict[str, asyncio.Task] = {}
        self.locks = defaultdict(asyncio.Lock)
        self.admission_lock = asyncio.Lock()
        self.last_frame = {}
        self.last_hash = {}
        self.closed = False
        self.refresh_events = defaultdict(asyncio.Event)

    def request_refresh(self, data):
        ids = {str(data[k]).removeprefix('lol-game-') for k in ('gameId', 'canonicalGameId') if data.get(k)}
        count = 0
        for game_id, task in self.tasks.items():
            status = self.repo.statuses.get(game_id)
            match = not ids and status and data.get('matchId') == status.match_id
            if not task.done() and (game_id.removeprefix('lol-game-') in ids or match):
                self.refresh_events[game_id].set()
                count += 1
        return count

    async def emit_status(self, status):
        status.updated_at = utcnow()
        self.events.publish(status.game_id, 'status', status.model_dump(mode='json'))
        await self.repo.save_status(status)

    async def start(self, game_id, match_id=None):
        async with self.admission_lock, self.locks[game_id]:
            if self.closed:
                raise CitoError('shutdown', '服务正在停止')
            task = self.tasks.get(game_id)
            if task and not task.done():
                return self.repo.statuses[game_id]
            if sum(not t.done() for t in self.tasks.values()) >= self.settings.max_monitors:
                raise CitoError('monitor_limit', '同时监控数量已达上限')
            status = MonitorStatus(game_id=game_id, match_id=match_id, state='running')
            self.repo.statuses[game_id] = status
            self.events.publish(game_id, 'status', status.model_dump(mode='json'))
            self.tasks[game_id] = asyncio.create_task(self.run(status), name=f'monitor:{game_id}')
            return status

    async def stop(self, game_id):
        async with self.locks[game_id]:
            task = self.tasks.pop(game_id, None)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            status = self.repo.statuses.get(game_id, MonitorStatus(game_id=game_id))
            status.state, status.reason, status.error_code = 'stopped', '用户已停止监控', None
            status.next_retry_at = None
            await self.emit_status(status)
            return status

    async def run(self, status):
        game_id = status.game_id
        coverage_checked = not status.match_id
        try:
            await self.emit_status(status)
            previous = await self.repo.get_latest(game_id)
            if previous and previous.source_ts:
                self.last_frame[game_id] = previous.source_ts
            while True:
                delay = self.settings.poll_interval_seconds
                owner = asyncio.current_task().get_name()
                before = self.client.budget.by_task[owner]
                status.last_attempt_at = utcnow()
                try:
                    if not coverage_checked:
                        await self.client.coverage(status.match_id)
                        coverage_checked = True
                    payload = await self.client.stats(game_id)
                    snapshot = normalize(payload, game_id, self.settings.stale_threshold_seconds,
                                         source='demo' if self.settings.demo_mode else 'cito')
                    if snapshot and snapshot.source_ts and (snapshot.source_ts - snapshot.ingest_ts).total_seconds() > 5:
                        raise CitoError('clock_skew', '数据源时间戳位于未来，已忽略并等待重试', retryable=True)
                    status.consecutive_failures = 0
                    status.error_code, status.reason, status.next_retry_at = None, None, None
                    if snapshot is None:
                        logger.debug('Snapshot skipped game_id=%s reason=empty_response', game_id)
                        status.empty_responses += 1
                        status.reason = '未返回数值数据，等待下一次采集'
                        if status.empty_responses >= self.settings.max_empty_responses:
                            status.state, status.reason = 'stopped', '连续空响应达到阈值，比赛可能未开始或已无覆盖'
                    else:
                        status.empty_responses = 0
                        digest = hashlib.sha256(json.dumps(payload.get('data'), sort_keys=True).encode()).hexdigest()
                        old_ts = self.last_frame.get(game_id)
                        accept = ((old_ts is None or snapshot.source_ts > old_ts) if snapshot.source_ts
                                  else old_ts is None and digest != self.last_hash.get(game_id))
                        logger.debug('Snapshot decision game_id=%s accept=%s source_ts=%s previous_ts=%s quality=%s',
                                     game_id, accept, snapshot.source_ts, old_ts, snapshot.quality)
                        if accept:
                            snapshot = calculate(snapshot, self.settings)
                            self.repo.save(snapshot)
                            self.last_hash[game_id] = digest
                            if snapshot.source_ts:
                                self.last_frame[game_id] = snapshot.source_ts
                            self.events.publish(game_id, 'snapshot', snapshot.model_dump(mode='json'))
                        else:
                            status.reason = '重复帧或旧帧，已忽略'
                        # An out-of-order terminal frame must not stop a newer live game.
                        if snapshot.game_state.lower() in ENDED and (accept or snapshot.source_ts == old_ts or 'postgame_final_only' in snapshot.quality):
                            status.state, status.reason = 'stopped', '比赛已结束'
                        elif not any(v is not None for team in (snapshot.blue, snapshot.red)
                                     for v in (team.gold, team.kills, team.towers, team.dragons, team.barons, team.inhibitors)) and not any(
                                         value is not None for player in snapshot.players
                                         for value in (player.gold, player.cs, player.level, player.kills, player.deaths, player.assists)):
                            raise CitoError('no_numeric_state', '响应没有可用的数值实时状态，已停止监控')
                except CitoError as error:
                    logger.debug('Monitor failed game_id=%s code=%s retryable=%s', game_id, error.code, error.retryable)
                    status.consecutive_failures += 1
                    status.error_code, status.reason = error.code, str(error)
                    if not error.retryable or status.consecutive_failures >= self.settings.max_consecutive_failures:
                        status.state = 'error'
                        status.next_retry_at = None
                    else:
                        delay = error.retry_after if error.retry_after is not None else min(
                            self.settings.max_retry_backoff, 2 ** min(status.consecutive_failures, 20) + random.uniform(0, 1))
                        status.next_retry_at = utcnow() + timedelta(seconds=delay)
                    self.events.publish(game_id, 'warning', {'code': error.code, 'message': str(error)})
                finally:
                    status.request_count += self.client.budget.by_task[owner] - before
                await self.emit_status(status)
                if status.state != 'running':
                    break
                if status.consecutive_failures or not self.settings.cito_webhook_secret.get_secret_value():
                    await asyncio.sleep(delay)
                else:
                    minimum = min(5, delay)
                    await asyncio.sleep(minimum)
                    try:
                        await asyncio.wait_for(self.refresh_events[game_id].wait(), max(.001, delay - minimum))
                    except asyncio.TimeoutError:
                        pass
                self.refresh_events[game_id].clear()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.debug('Monitor internal failure game_id=%s error_type=%s', game_id, type(error).__name__)
            # Do not log provider responses, keys or arbitrary exception strings.
            status.state, status.error_code = 'error', 'internal'
            status.reason = '采集任务异常，已隔离；请检查数据结构后重新开始'
            status.next_retry_at = None
            await self.emit_status(status)
        finally:
            if self.tasks.get(game_id) is asyncio.current_task():
                self.tasks.pop(game_id, None)

    async def close(self):
        self.closed = True
        await asyncio.gather(*(self.stop(game_id) for game_id in list(self.tasks)))
