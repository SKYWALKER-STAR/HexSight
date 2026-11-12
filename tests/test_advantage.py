from datetime import timedelta
import pytest
from backend.app.models.domain import utcnow
from backend.app.services.normalizer import normalize
from backend.app.services.advantage import calculate
from backend.app.clients.cito import CitoError


def calc(payload, settings):
    return calculate(normalize(payload, 'test-1', 120), settings)


def test_blue_red_even_and_bounded(payload, settings):
    blue = calc(payload, settings)
    assert 10 < blue.advantage.score <= 100
    assert blue.advantage.direction == 'blue'
    payload['data']['blueTeam'], payload['data']['redTeam'] = payload['data']['redTeam'], payload['data']['blueTeam']
    red = calc(payload, settings)
    assert red.advantage.score == -blue.advantage.score
    assert red.advantage.direction == 'red'
    payload['data']['blueTeam'] = payload['data']['redTeam'].copy()
    assert calc(payload, settings).advantage.direction == 'even'
    payload['data']['blueTeam']['totalGold'] = 10**12
    assert calc(payload, settings).advantage.score <= 100


def test_missing_fields_reweight_not_zero(payload, settings):
    payload['data']['redTeam'] = {'totalGold': 35000}
    result = calc(payload, settings)
    assert result.red.towers is None
    assert [f.name for f in result.advantage.factors] == ['gold']
    assert result.advantage.factors[0].weight == 1
    assert result.advantage.score == pytest.approx(83.3)
    payload['data']['redTeam'] = {}
    result = calc(payload, settings)
    assert result.advantage.score is None
    assert result.advantage.direction == 'unknown'


def test_kills_not_double_counted(payload, settings):
    first = calc(payload, settings).advantage.score
    payload['data']['blueTeam']['totalKills'] = 100
    assert calc(payload, settings).advantage.score == first


def test_lane_mapping_not_position_and_duplicate_disabled(payload, settings):
    payload['data']['players'].reverse()
    result = calc(payload, settings)
    assert result.lanes[0].blue.role == 'TOP'
    assert result.lanes[0].advantage.score > 0
    assert result.lanes[1].advantage.score is None
    assert result.lanes[-1].advantage.score is None
    payload['data']['players'].append(next(p for p in payload['data']['players'] if p['role'] == 'top' and p['side'] == 'blue').copy())
    top = calc(payload, settings).lanes[0]
    assert top.blue is None and top.advantage.score is None
    assert '重复' in top.reason


def test_missing_personal_gold_lowers_confidence(payload, settings):
    for p in payload['data']['players']:
        p.pop('totalGold')
    top = calc(payload, settings).lanes[0]
    assert top.advantage.score > 0
    assert top.advantage.confidence == 'low'


@pytest.mark.parametrize('offset', [-121, 30])
def test_stale_and_future_disable_score(payload, settings, offset):
    payload['frameTimestamp'] = (utcnow() + timedelta(seconds=offset)).isoformat()
    result = calc(payload, settings)
    assert result.advantage.score is None
    assert all(l.advantage.score is None for l in result.lanes)


def test_missing_timestamp_and_game_time(payload, settings):
    payload.pop('frameTimestamp')
    payload['data'].pop('gameTimeSeconds')
    result = calc(payload, settings)
    assert result.freshness == 'unknown' and result.advantage.score is None
    assert result.game_seconds is None
    assert 'missing_source_timestamp' in result.quality


def test_freshness_rechecked_without_new_frame(payload, settings):
    result = calc(payload, settings)
    assert result.advantage.score is not None
    old = result.refreshed(utcnow() + timedelta(seconds=121))
    assert old.freshness == 'stale' and old.advantage.score is None
    assert result.advantage.score is not None


def test_invalid_values_and_id_mismatch(payload, settings):
    payload['data']['blueTeam'].update(totalGold='NaN', towers=False, barons=-1)
    result = calc(payload, settings)
    assert result.blue.gold is None and result.blue.towers is None and result.blue.barons is None
    payload['data']['gameId'] = 'other'
    with pytest.raises(CitoError, match='gameId'):
        calc(payload, settings)


def test_raw_not_returned_to_browser(payload, settings):
    result = calc(payload, settings)
    assert result.raw == payload
    assert 'raw' not in result.model_dump(mode='json')


def test_verified_postgame_response(settings):
    import json
    from pathlib import Path
    body = json.loads((Path(__file__).parent / 'fixtures/cito_completed.json').read_text())
    result = calculate(normalize(body, 'lol-game-117393592614464355', 120), settings)
    assert result.game_state == 'finished'
    assert len(result.players) == 10
    assert result.source_ts is None and result.advantage.score is None
    assert result.lanes[0].blue.champion == 'Olaf'
    assert result.blue.gold is None  # Never invent team totals from incomplete data.
    assert 'postgame_final_only' in result.quality


def test_explicit_no_numeric_coverage_rejected(payload, settings):
    payload['coverage'] = {'numeric_live_state': False}
    with pytest.raises(CitoError) as error:
        calc(payload, settings)
    assert error.value.code == 'no_coverage'
