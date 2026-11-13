from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Team(BaseModel):
    name: str | None = None
    gold: float | None = None
    kills: float | None = None
    towers: float | None = None
    dragons: float | None = None
    barons: float | None = None
    inhibitors: float | None = None


class Player(BaseModel):
    side: Literal['blue', 'red']
    role: str | None = None
    name: str | None = None
    champion: str | None = None
    gold: float | None = None
    cs: float | None = None
    level: float | None = None
    kills: float | None = None
    deaths: float | None = None
    assists: float | None = None
    items: list[int | str] | None = None
    championIconUrl: str | None = None
    championDamageShare: float | None = None
    currentHealth: float | None = None
    maxHealth: float | None = None


class Factor(BaseModel):
    name: str
    difference: float
    normalized: float
    weight: float


class Advantage(BaseModel):
    score: float | None = None
    direction: Literal['blue', 'red', 'even', 'unknown'] = 'unknown'
    confidence: Literal['high', 'medium', 'low', 'unknown'] = 'unknown'
    factors: list[Factor] = Field(default_factory=list)
    note: str = '启发式优势分，不代表获胜概率'


class Lane(BaseModel):
    role: str
    blue: Player | None = None
    red: Player | None = None
    differences: dict[str, float | None] = Field(default_factory=dict)
    advantage: Advantage = Field(default_factory=Advantage)
    reason: str | None = None


class Snapshot(BaseModel):
    game_id: str
    source_ts: datetime | None = None
    ingest_ts: datetime
    game_time: float | None = None
    game_state: str = 'unknown'
    lag_seconds: float | None = None
    freshness: Literal['fresh', 'stale', 'unknown'] = 'unknown'
    stale_threshold_seconds: float = 120
    quality: list[str] = Field(default_factory=list)
    blue: Team
    red: Team
    players: list[Player] = Field(default_factory=list)
    advantage: Advantage = Field(default_factory=Advantage)
    lanes: list[Lane] = Field(default_factory=list)
    delayed_seconds: float | None = None
    source: Literal['cito', 'demo'] = 'cito'
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    def refreshed(self, now: datetime | None = None) -> 'Snapshot':
        result = self.model_copy(deep=True)
        if self.source_ts:
            lag = ((now or utcnow()) - self.source_ts).total_seconds()
            result.lag_seconds = round(max(0, lag), 1)
            result.freshness = ('unknown' if lag < -5 else
                                'stale' if lag > self.stale_threshold_seconds else 'fresh')
        if result.freshness != 'fresh':
            result.advantage = Advantage(note='数据过期或时间戳未知，暂停态势判断')
            for lane in result.lanes:
                lane.advantage = Advantage(note='数据过期或时间戳未知，暂停对位判断')
        return result


class MonitorStatus(BaseModel):
    state: Literal['running', 'stopped', 'paused', 'error'] = 'stopped'
    game_id: str
    match_id: str | None = None
    game_time: float | None = None
    game_state: str = 'unknown'
    reason: str | None = None
    error_code: str | None = None
    consecutive_failures: int = 0
    empty_responses: int = 0
    request_count: int = 0
    updated_at: datetime = Field(default_factory=utcnow)
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
