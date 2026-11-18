import asyncio
import logging
import time
from urllib.parse import urlsplit
import math
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import httpx
from backend.app.config import Settings
logger = logging.getLogger(__name__)


class CitoError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False,
                 retry_after: float | None = None):
        super().__init__(message)
        self.code, self.retryable, self.retry_after = code, retryable, retry_after


class RequestBudget:
    """One process-wide quota including coverage checks and failed attempts."""
    def __init__(self, limit: int):
        self.limit, self.used = limit, 0
        self.lock = asyncio.Lock()
        self.by_task = defaultdict(int)

    async def consume(self):
        async with self.lock:
            if self.limit and self.used >= self.limit:
                raise CitoError('budget_exhausted', '本进程请求预算已耗尽，请检查配置和套餐额度')
            self.used += 1
            self.by_task[asyncio.current_task().get_name()] += 1


def retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else None
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


class CitoClient:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.budget = RequestBudget(settings.request_budget)
        self._champions = {}
        self._champions_refresh_at = 0.0
        self._champions_lock = asyncio.Lock()
        self._items = {}
        self._items_refresh_at = 0.0
        self._items_lock = asyncio.Lock()
        self.http = httpx.AsyncClient(
            base_url=settings.cito_base_url.rstrip('/') + '/',
            headers={'x-api-key': settings.cito_api_key.get_secret_value(), 'accept': 'application/json'},
            timeout=httpx.Timeout(settings.read_timeout, connect=settings.connect_timeout),
            transport=transport, follow_redirects=False,
        )

    async def get(self, path: str, *, allow_list: bool = False) -> dict | list:
        # Omit query values, headers and raw bodies: they can contain credentials.
        endpoint = urlsplit(path).path
        logger.debug('Cito GET path=%s', endpoint)
        key = self.settings.cito_api_key.get_secret_value()
        if key:
            endpoint = endpoint.replace(key, '[REDACTED]')
        endpoint = endpoint[:256].replace('\r', '').replace('\n', '')
        if not self.settings.cito_api_key.get_secret_value():
            logger.debug('Cito GET path=%s skipped: missing_key', endpoint)
            raise CitoError('missing_key', '服务端未配置 CITO_API_KEY')
        try:
            await self.budget.consume()
        except CitoError:
            logger.debug('Cito GET path=%s skipped: budget_exhausted used=%d limit=%d',
                         endpoint, self.budget.used, self.budget.limit)
            raise
        started = time.perf_counter()
        logger.debug('Cito GET path=%s started budget_used=%d budget_limit=%d',
                     endpoint, self.budget.used, self.budget.limit)
        try:
            response = await self.http.get(path.lstrip('/'))
        except httpx.TimeoutException:
            logger.debug('Cito GET path=%s failed: timeout elapsed_ms=%.1f', endpoint,
                         (time.perf_counter() - started) * 1000)
            raise CitoError('timeout', 'Cito 请求超时', retryable=True) from None
        except httpx.RequestError:
            logger.debug('Cito GET path=%s failed: network elapsed_ms=%.1f', endpoint,
                         (time.perf_counter() - started) * 1000)
            raise CitoError('network', 'Cito 网络连接失败', retryable=True) from None
        except asyncio.CancelledError:
            logger.debug('Cito GET path=%s cancelled elapsed_ms=%.1f', endpoint,
                         (time.perf_counter() - started) * 1000)
            raise
        code = response.status_code
        logger.debug('Cito GET path=%s status=%d elapsed_ms=%.1f response_bytes=%d retry_after_seconds=%s',
                     endpoint, code, (time.perf_counter() - started) * 1000, len(response.content),
                     retry_after_seconds(response.headers.get('retry-after')))
        logger.debug('Cito GET path=%s response=%d', endpoint, code)
        if code in (401, 403):
            raise CitoError('permission', f'Cito HTTP {code}：密钥或套餐无权访问该实时数据')
        if code == 404:
            raise CitoError('not_found', 'Cito HTTP 404：比赛不存在或没有实时数据覆盖')
        if code == 429:
            raise CitoError('rate_limited', 'Cito 请求受限，等待 Retry-After 后重试',
                            retryable=True, retry_after=retry_after_seconds(response.headers.get('retry-after')))
        if code >= 500:
            raise CitoError('upstream', f'Cito HTTP {code}：上游暂时不可用', retryable=True)
        if code == 204:
            return {}
        if code >= 300:
            raise CitoError('http_error', f'Cito HTTP {code}：请求失败')
        try:
            data = response.json()
        except ValueError:
            logger.debug('Cito GET path=%s invalid_json', endpoint)
            raise CitoError('schema', 'Cito 未返回有效 JSON') from None
        if allow_list and isinstance(data, list):
            logger.debug('Cito GET path=%s parsed root_type=list entries=%d', endpoint, len(data))
            return data
        if not isinstance(data, dict):
            logger.debug('Cito GET path=%s invalid_schema root_type=%s', endpoint, type(data).__name__)
            raise CitoError('schema', 'Cito 响应结构不符合预期')
        if data.get('success') is False:
            logger.debug('Cito GET path=%s api_error success=false', endpoint)
            raise CitoError('api_error', 'Cito 返回失败状态，请检查比赛覆盖与套餐权限')
        payload = data.get('data')
        logger.debug('Cito GET path=%s parsed data_type=%s data_size=%s', endpoint,
                     type(payload).__name__, len(payload) if isinstance(payload, (dict, list)) else None)
        return data

    async def item_catalog(self):
        """One full catalog per day, shared across games and concurrent requests."""
        async with self._items_lock:
            if time.monotonic() < self._items_refresh_at:
                return self._items
            try:
                body = await self.get('lol/static/items', allow_list=True)
                rows = body.get('data', body) if isinstance(body, dict) else body
                if isinstance(rows, dict) and 'items' in rows:
                    rows = rows['items']
                catalog = {}
                entries = rows.items() if isinstance(rows, dict) else enumerate(rows) if isinstance(rows, list) else []
                for key, value in entries:
                    if isinstance(value, dict):
                        item_id = value.get('id', value.get('itemId', key if isinstance(rows, dict) else None))
                        if item_id is not None:
                            catalog[str(item_id)] = value
                if not catalog:
                    raise CitoError('schema',
                                    f'Invalid static item catalog: rows_type={type(rows).__name__}, '
                                    f'rows_count={len(rows) if isinstance(rows, (dict, list)) else 0}')
                self._items = catalog
                self._items_refresh_at = time.monotonic() + 86400
            except CitoError as error:
                self._items_refresh_at = time.monotonic() + max(300, error.retry_after or 0)
                logger.warning('Item catalog unavailable code=%s reason=%s', error.code, str(error))
            return self._items

    async def champion_catalog(self):
        """One full catalog per day, shared across games and concurrent requests."""
        async with self._champions_lock:
            if time.monotonic() < self._champions_refresh_at:
                return self._champions
            try:
                body = await self.get('lol/static/champions', allow_list=True)
                rows = body.get('data', body) if isinstance(body, dict) else body
                if isinstance(rows, dict) and 'champions' in rows:
                    rows = rows['champions']
                catalog = {}
                entries = rows.items() if isinstance(rows, dict) else enumerate(rows) if isinstance(rows, list) else []
                for key, value in entries:
                    if isinstance(value, dict):
                        aliases = [value.get(field) for field in ('championId', 'id', 'key', 'name')]
                        if isinstance(rows, dict):
                            aliases.append(key)
                        for alias in aliases:
                            if type(alias) in (int, str) and str(alias).strip():
                                catalog[str(alias).strip().casefold()] = value
                if not catalog:
                    raise CitoError('schema',
                                    f'Invalid static champion catalog: rows_type={type(rows).__name__}, '
                                    f'rows_count={len(rows) if isinstance(rows, (dict, list)) else 0}')
                self._champions = catalog
                self._champions_refresh_at = time.monotonic() + 86400
            except CitoError as error:
                self._champions_refresh_at = time.monotonic() + max(300, error.retry_after or 0)
                logger.warning('Champion catalog unavailable code=%s reason=%s', error.code, str(error))
            return self._champions

    async def stats(self, game_id: str) -> dict:
        logger.debug('Stats fetch started game_id=%s', game_id)
        try:
            body = await self.get(f'lol/live/{game_id}/stats')
        except CitoError as error:
            logger.debug('Stats fetch failed game_id=%s code=%s retryable=%s',
                         game_id, error.code, error.retryable)
            raise
        data = body.get('data')
        players = data.get('players', []) if isinstance(data, dict) else data if isinstance(data, list) else []
        players = [p for p in players if isinstance(p, dict)] if isinstance(players, list) else []
        if any(isinstance(p.get('items'), list) and any(type(i) in (int, str) and str(i) not in ('0', '') for i in p['items']) for p in players):
            catalog = await self.item_catalog()
            for player in players:
                if isinstance(player.get('items'), list):
                    player['itemDetails'] = [catalog.get(str(i)) for i in player['items'] if type(i) in (int, str)]
        if any(p.get('championId') or p.get('championName') for p in players):
            champions = await self.champion_catalog()
            for player in players:
                identifiers = (player.get('championId'), player.get('championName'))
                details = next((champions[str(i).strip().casefold()] for i in identifiers
                                if i is not None and str(i).strip().casefold() in champions), None)
                player['championDetails'] = details
                if details and not player.get('championIconUrl'):
                    player['championIconUrl'] = details.get('imageUrl')
        logger.debug('Stats fetched game_id=%s data_type=%s entries=%s has_frame_timestamp=%s',
                     game_id, type(data).__name__, len(data) if isinstance(data, (dict, list)) else None,
                     bool(body.get('frameTimestamp')))
        return body

    async def upcoming(self):
        return await self.get('lol/schedule/upcoming')

    async def coverage(self, match_id: str):
        body = await self.get(f'lol/matches/{match_id}/coverage')
        data = body.get('data', body)
        coverage = data.get('coverage') if isinstance(data, dict) else None
        if not isinstance(coverage, dict) or coverage.get('numeric_live_state') is not True:
            raise CitoError('no_coverage', '该比赛尚未确认 numeric_live_state 数值实时覆盖')

    async def close(self):
        await self.http.aclose()
