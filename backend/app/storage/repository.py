import asyncio
import json
import logging
import re
import time
from collections import defaultdict, deque
from datetime import timedelta
import httpx
from redis.asyncio import Redis
from backend.app.config import Settings
from backend.app.models.domain import MonitorStatus, Snapshot, utcnow

logger = logging.getLogger(__name__)

DDL = '''CREATE TABLE IF NOT EXISTS {db}.game_snapshots (
 game_id String, frame_ts DateTime64(3, 'UTC'), ingest_ts DateTime64(3, 'UTC'),
 raw_json String, blue_gold Nullable(Int64), red_gold Nullable(Int64),
 overall_score Nullable(Float64), quality String, snapshot_json String
) ENGINE = ReplacingMergeTree(ingest_ts) ORDER BY (game_id, frame_ts)'''


class Repository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.latest: dict[str, Snapshot] = {}
        self.statuses: dict[str, MonitorStatus] = {}
        self.frames = defaultdict(lambda: deque(maxlen=settings.history_max_points))
        self.warnings: dict[str, str] = {}
        self.redis = Redis.from_url(settings.redis_url.get_secret_value(), socket_timeout=2,
                                    socket_connect_timeout=2) if settings.redis_url.get_secret_value() else None
        self.ch = httpx.AsyncClient(base_url=settings.clickhouse_url,
                                    auth=(settings.clickhouse_user, settings.clickhouse_password.get_secret_value()),
                                    timeout=3) if settings.clickhouse_url else None
        self.ch_ready = False
        self.queue: asyncio.Queue[Snapshot] = asyncio.Queue(maxsize=256)
        self.writer: asyncio.Task | None = None

    async def initialize(self):
        logger.debug('Storage initialized redis_enabled=%s clickhouse_enabled=%s database=%s',
                     bool(self.redis), bool(self.ch), self.settings.clickhouse_database)
        if self.redis:
            try:
                await self.redis.ping()
                async for key in self.redis.scan_iter('hexsight:game:*:status', count=100):
                    raw = await self.redis.get(key)
                    if raw:
                        status = MonitorStatus.model_validate_json(raw)
                        status.state, status.reason = 'stopped', '服务已重启，请手动开始监控'
                        status.next_retry_at = None
                        self.statuses[status.game_id] = status
                        await self.save_status(status)
            except Exception:
                self.warnings['redis'] = 'Redis 不可用，已降级到进程内存'
        if self.ch:
            await self.ensure_ch()
        self.writer = asyncio.create_task(self._writer(), name='storage-writer')

    async def ensure_ch(self):
        try:
            await self.query(f'CREATE DATABASE IF NOT EXISTS {self.settings.clickhouse_database}')
            await self.query(DDL.format(db=self.settings.clickhouse_database))
            self.ch_ready = True
            self.warnings.pop('clickhouse', None)
        except Exception:
            self.ch_ready = False
            self.warnings['clickhouse'] = 'ClickHouse 不可用，历史暂存内存；本次写入最多重试两次'

    async def query(self, sql: str, *, params=None, content=None):
        started = time.monotonic()
        operation = ' '.join(sql.split()[:2]) if sql.startswith('CREATE') else sql.split()[0]
        try:
            response = await self.ch.post('/', params={'query': sql, **(params or {})}, content=content)
            response.raise_for_status()
            return response
        except Exception as exc:
            # Never log request URLs, SQL parameters, payloads or raw exception text:
            # those can contain credentials and match data.
            status = None
            code = None
            reason = type(exc).__name__
            if isinstance(exc, httpx.HTTPStatusError):
                status = exc.response.status_code
                match = re.search(r'Code:\s*(\d+)\.', exc.response.text[:4096])
                code = match.group(1) if match else None
                reason = {401: 'authentication_failed', 403: 'access_denied',
                          404: 'http_endpoint_not_found'}.get(status, 'server_rejected_query')
            elif isinstance(exc, httpx.TimeoutException):
                reason = 'timeout'
            elif isinstance(exc, httpx.ConnectError):
                reason = 'connection_failed_check_dns_port_tls'
            url = httpx.URL(self.settings.clickhouse_url)
            logger.warning(
                'ClickHouse request failed operation=%s host=%s port=%s database=%s '
                'error_type=%s reason=%s http_status=%s clickhouse_code=%s elapsed_ms=%.0f',
                operation, url.host, url.port, self.settings.clickhouse_database,
                type(exc).__name__, reason, status, code, (time.monotonic() - started) * 1000,
            )
            raise

    async def save_status(self, status: MonitorStatus):
        self.statuses[status.game_id] = status
        if self.redis:
            try:
                await self.redis.set(f'hexsight:game:{status.game_id}:status', status.model_dump_json(),
                                     ex=self.settings.redis_ttl_seconds)
                self.warnings.pop('redis', None)
            except Exception:
                self.warnings['redis'] = 'Redis 不可用，已降级到进程内存'

    def save(self, snapshot: Snapshot):
        logger.debug('Snapshot saved to memory game_id=%s source_ts=%s', snapshot.game_id, snapshot.source_ts)
        self.latest[snapshot.game_id] = snapshot
        frames = self.frames[snapshot.game_id]
        frames.append(snapshot)
        cutoff = utcnow() - timedelta(minutes=self.settings.history_window_minutes)
        while frames and (frames[0].source_ts or frames[0].ingest_ts) < cutoff:
            frames.popleft()
        if self.redis or self.ch:
            try:
                self.queue.put_nowait(snapshot)
                logger.debug('Snapshot queued game_id=%s queue_size=%d writer_running=%s',
                             snapshot.game_id, self.queue.qsize(), bool(self.writer and not self.writer.done()))
            except asyncio.QueueFull:
                logger.debug('Snapshot persistence skipped game_id=%s reason=queue_full', snapshot.game_id)
                self.warnings['storage_queue'] = '存储队列已满，部分历史未持久化；最新态势仍可用'

        else:
            logger.debug('Snapshot memory_only game_id=%s reason=no_storage_configured', snapshot.game_id)

    async def _writer(self):
        while True:
            snapshot = await self.queue.get()
            try:
                await self.persist(snapshot)
            finally:
                self.queue.task_done()

    async def persist(self, snapshot: Snapshot):
        if self.redis:
            try:
                await self.redis.set(f'hexsight:game:{snapshot.game_id}:latest', snapshot.model_dump_json(),
                                     ex=self.settings.redis_ttl_seconds)
                self.warnings.pop('redis', None)
            except Exception:
                self.warnings['redis'] = 'Redis 不可用，已降级到进程内存'
        if not self.ch:
            logger.debug('ClickHouse insert skipped game_id=%s reason=not_configured', snapshot.game_id)
            return
        if snapshot.source_ts is None:
            logger.debug('ClickHouse insert skipped game_id=%s reason=missing_source_timestamp', snapshot.game_id)
            self.warnings['timestamp'] = '缺少数据源时间戳的快照仅保留在内存/Redis，未写入 ClickHouse'
            return
        row = dict(game_id=snapshot.game_id, frame_ts=snapshot.source_ts.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                   ingest_ts=snapshot.ingest_ts.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3], raw_json=json.dumps(snapshot.raw, ensure_ascii=False),
                   blue_gold=int(snapshot.blue.gold) if snapshot.blue.gold is not None else None,
                   red_gold=int(snapshot.red.gold) if snapshot.red.gold is not None else None,
                   overall_score=snapshot.advantage.score, quality=json.dumps(snapshot.quality),
                   snapshot_json=snapshot.model_dump_json())
        for attempt in range(2):
            logger.debug('ClickHouse insert attempt game_id=%s attempt=%d table=%s.game_snapshots',
                         snapshot.game_id, attempt + 1, self.settings.clickhouse_database)
            try:
                if not self.ch_ready:
                    await self.ensure_ch()
                if not self.ch_ready:
                    raise RuntimeError('storage_unavailable')
                await self.query(f'INSERT INTO {self.settings.clickhouse_database}.game_snapshots FORMAT JSONEachRow',
                                 params={'async_insert': 0}, content=(json.dumps(row) + '\n').encode())
                self.warnings.pop('clickhouse', None)
                logger.debug('ClickHouse insert succeeded game_id=%s source_ts=%s', snapshot.game_id, snapshot.source_ts)
                return
            except Exception:
                self.warnings['clickhouse'] = 'ClickHouse 写入失败，部分历史未持久化；最新态势仍可用'
                if attempt == 0:
                    await asyncio.sleep(.5)

    async def get_latest(self, game_id: str) -> Snapshot | None:
        if game_id in self.latest:
            return self.latest[game_id].refreshed()
        if self.redis:
            try:
                raw = await self.redis.get(f'hexsight:game:{game_id}:latest')
                if raw:
                    value = Snapshot.model_validate_json(raw)
                    self.latest[game_id] = value
                    logger.debug('Loaded latest snapshot from Redis for game_id=%s,value=%s', game_id, value)
                    return value.refreshed()
            except Exception:
                self.warnings['redis'] = 'Redis 不可用，已降级到进程内存'
        if self.ch:
            try:
                r = await self.query(f'SELECT snapshot_json FROM {self.settings.clickhouse_database}.game_snapshots FINAL '
                                     'WHERE game_id = {id:String} ORDER BY frame_ts DESC LIMIT 1 FORMAT JSONEachRow',
                                     params={'param_id': game_id})
                if r.text.strip():
                    value = Snapshot.model_validate_json(json.loads(r.text)['snapshot_json'])
                    self.latest[game_id] = value
                    logger.debug('Loaded latest snapshot from ClickHouse for game_id=%s,value=%s', game_id, value)
                    return value.refreshed()
            except Exception:
                self.warnings['clickhouse'] = 'ClickHouse 查询失败，使用内存历史'
        return None

    async def history(self, game_id: str, minutes: int):
        cutoff = utcnow() - timedelta(minutes=minutes)
        memory = [s for s in self.frames[game_id] if (s.source_ts or s.ingest_ts) >= cutoff]
        stored = []
        if self.ch:
            try:
                r = await self.query(f'SELECT snapshot_json FROM {self.settings.clickhouse_database}.game_snapshots FINAL '
                                     'WHERE game_id = {id:String} AND frame_ts >= fromUnixTimestamp64Milli({since:Int64}) '
                                     'ORDER BY frame_ts DESC LIMIT {limit:UInt32} FORMAT JSONEachRow',
                                     params={'param_id': game_id, 'param_since': int(cutoff.timestamp() * 1000),
                                             'param_limit': self.settings.history_max_points})
                stored = [Snapshot.model_validate_json(json.loads(line)['snapshot_json'])
                          for line in r.text.splitlines() if line]
                self.warnings.pop('clickhouse', None)
            except Exception:
                self.warnings['clickhouse'] = 'ClickHouse 查询失败，使用内存历史'
        merged = {s.source_ts or s.ingest_ts: s for s in stored + memory}
        return [merged[k] for k in sorted(merged)][-self.settings.history_max_points:]

    async def health(self):
        deps = {'redis': 'disabled', 'clickhouse': 'disabled'}
        if self.redis:
            try:
                await self.redis.ping()
                deps['redis'] = 'ready'
            except Exception:
                deps['redis'] = 'degraded'
        if self.ch:
            try:
                await self.query('SELECT 1')
                deps['clickhouse'] = 'ready' if self.ch_ready else 'degraded'
            except Exception:
                deps['clickhouse'] = 'degraded'
        return deps

    async def close(self):
        if self.writer:
            try:
                await asyncio.wait_for(self.queue.join(), timeout=5)
            except asyncio.TimeoutError:
                pass
            self.writer.cancel()
            await asyncio.gather(self.writer, return_exceptions=True)
        if self.redis:
            await self.redis.aclose()
        if self.ch:
            await self.ch.aclose()
