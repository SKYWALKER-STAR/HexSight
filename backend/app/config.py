from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = 'INFO'

    @field_validator('log_level', mode='before')
    @classmethod
    def normalize_log_level(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    cito_api_key: SecretStr = SecretStr('')
    cito_base_url: str = 'https://api.citoapi.com/api/v1'
    cito_webhook_secret: SecretStr = SecretStr('')
    poll_interval_seconds: float = Field(30, ge=1)
    connect_timeout: float = Field(5, gt=0)
    read_timeout: float = Field(10, gt=0)
    max_retry_backoff: float = Field(30, ge=1)
    max_consecutive_failures: int = Field(5, ge=1)
    max_empty_responses: int = Field(3, ge=1)
    stale_threshold_seconds: float = Field(120, gt=0)
    request_budget: int = Field(500, ge=0)
    max_monitors: int = Field(10, ge=1, le=100)
    history_window_minutes: int = Field(30, ge=1, le=1440)
    history_max_points: int = Field(1800, ge=1, le=10000)
    cors_origins: list[str] = ['http://localhost:5173', 'http://127.0.0.1:5173',
                               'http://localhost:8080', 'http://127.0.0.1:8080']
    redis_url: SecretStr = SecretStr('')
    redis_ttl_seconds: int = Field(86400, ge=60)
    clickhouse_url: str = ''
    clickhouse_user: str = 'default'
    clickhouse_password: SecretStr = SecretStr('')
    clickhouse_database: str = 'hexsight'
    demo_mode: bool = False
    gold_weight: float = Field(.60, ge=0)
    objective_weight: float = Field(.25, ge=0)
    tower_weight: float = Field(.15, ge=0)
    gold_scale_min: float = Field(3000, gt=0)
    gold_scale_per_minute: float = Field(300, gt=0)
    tower_scale: float = Field(5, gt=0)
    dragon_scale: float = Field(3, gt=0)
    baron_scale: float = Field(2, gt=0)
    inhibitor_scale: float = Field(3, gt=0)
    even_threshold: float = Field(10, ge=0, le=100)
    lane_gold_weight: float = Field(.65, ge=0)
    lane_cs_weight: float = Field(.25, ge=0)
    lane_level_weight: float = Field(.10, ge=0)
    lane_gold_scale: float = Field(2000, gt=0)
    lane_cs_scale: float = Field(50, gt=0)
    lane_level_scale: float = Field(3, gt=0)

    @field_validator('clickhouse_database')
    @classmethod
    def database_identifier(cls, value: str) -> str:
        import re
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', value):
            raise ValueError('Invalid ClickHouse database identifier')
        return value
