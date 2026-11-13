import asyncio
from asyncio.log import logger
import math
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import httpx
from backend.app.config import Settings
import logging as lo
logger = lo.getLogger(__name__)


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
        self.http = httpx.AsyncClient(
            base_url=settings.cito_base_url.rstrip('/') + '/',
            headers={'x-api-key': settings.cito_api_key.get_secret_value(), 'accept': 'application/json'},
            timeout=httpx.Timeout(settings.read_timeout, connect=settings.connect_timeout),
            transport=transport, follow_redirects=False,
        )

    async def get(self, path: str) -> dict:
        if not self.settings.cito_api_key.get_secret_value():
            raise CitoError('missing_key', '服务端未配置 CITO_API_KEY')
        await self.budget.consume()
        try:
            response = await self.http.get(path.lstrip('/'))
        except httpx.TimeoutException:
            raise CitoError('timeout', 'Cito 请求超时', retryable=True) from None
        except httpx.RequestError:
            raise CitoError('network', 'Cito 网络连接失败', retryable=True) from None
        code = response.status_code
        if code in (401, 403):
            logger.info(response.text)
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
            raise CitoError('schema', 'Cito 未返回有效 JSON') from None
        if not isinstance(data, dict):
            raise CitoError('schema', 'Cito 响应结构不符合预期')
        if data.get('success') is False:
            raise CitoError('api_error', 'Cito 返回失败状态，请检查比赛覆盖与套餐权限')
        return data

    async def stats(self, game_id: str) -> dict:
        return await self.get(f'lol/live/{game_id}/stats')

    async def upcoming(self):
        return await self.get('lol/matches/upcoming?hours=336')

    async def coverage(self, match_id: str):
        body = await self.get(f'lol/matches/{match_id}/coverage')
        data = body.get('data', body)
        coverage = data.get('coverage') if isinstance(data, dict) else None
        if not isinstance(coverage, dict) or coverage.get('numeric_live_state') is not True:
            raise CitoError('no_coverage', '该比赛尚未确认 numeric_live_state 数值实时覆盖')

    async def close(self):
        await self.http.aclose()
