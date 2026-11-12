import copy
import json
from pathlib import Path
import pytest
from backend.app.config import Settings
from backend.app.models.domain import utcnow


@pytest.fixture
def settings():
    return Settings(_env_file=None, cito_api_key='test-key-not-real', request_budget=100,
                    redis_url='', clickhouse_url='', demo_mode=False)


@pytest.fixture
def payload():
    data = json.loads((Path(__file__).parent / 'fixtures/board.json').read_text())
    data['frameTimestamp'] = utcnow().isoformat()
    return copy.deepcopy(data)
