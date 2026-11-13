import math
from datetime import datetime, timezone
from backend.app.clients.cito import CitoError
from backend.app.models.domain import Snapshot, Team, Player, utcnow

ROLES = {'top': 'TOP', 'jungle': 'JUNGLE', 'jungler': 'JUNGLE', 'mid': 'MID',
         'middle': 'MID', 'bot': 'BOT', 'bottom': 'BOT', 'adc': 'BOT',
         'support': 'SUPPORT', 'sup': 'SUPPORT'}
ENDED = {'completed', 'finished', 'ended', 'game_over', 'gameover'}


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except ValueError:
        return None


def text(value):
    return value[:160] if isinstance(value, str) else None


def normalize(payload: dict, game_id: str, stale_threshold: float, *, now=None, source='cito') -> Snapshot | None:
    data = payload.get('data')
    if data is None or data == {} or data == []:
        return None
    postgame = False
    if isinstance(data, list) and data and all(isinstance(p, dict) and p.get('final') is True for p in data):
        if payload.get('coverage', {}).get('numeric_live_state') is False:
            postgame = True
            data = {'gameId': payload.get('gameId'), 'state': 'finished',
                    'players': [{**p, 'summonerName': p.get('playerName'),
                                 'championId': p.get('championName'), 'totalGold': p.get('gold'),
                                 'creepScore': p.get('cs')} for p in data],
                    **{side + 'Team': {'name': next((p.get('teamName') for p in data if p.get('side') == side), None)}
                       for side in ('blue', 'red')}}
    if not postgame and isinstance(payload.get('coverage'), dict) and payload['coverage'].get('numeric_live_state') is False:
        raise CitoError('no_coverage', '该小局没有活动的数值实时覆盖')
    if not isinstance(data, dict):
        raise CitoError('schema', 'stats.data 结构不符合官方 scoreboard 契约')
    if str(data.get('gameId')).removeprefix('lol-game-') != game_id.removeprefix('lol-game-'):
        raise CitoError('schema', '响应 gameId 缺失或与请求不一致，已拒绝此数据')
    quality = ['postgame_final_only'] if postgame else []
    source_ts = timestamp(payload.get('frameTimestamp'))
    if source_ts is None:
        quality.append('missing_source_timestamp')
    teams = []
    for side in ('blue', 'red'):
        raw = data.get(side + 'Team')
        raw = raw if isinstance(raw, dict) else {}
        dragons = raw.get('dragons')
        values = {k: number(raw.get(v)) for k, v in {
            'gold': 'totalGold', 'kills': 'totalKills', 'towers': 'towers',
            'barons': 'barons', 'inhibitors': 'inhibitors'}.items()}
        values['dragons'] = len(dragons) if isinstance(dragons, list) else number(dragons)
        quality.extend(f'{side}.{k}.unknown' for k, v in values.items() if v is None)
        teams.append(Team(name=text(raw.get('name')), **values))
    players = []
    for raw in data.get('players', []) if isinstance(data.get('players'), list) else []:
        if not isinstance(raw, dict) or raw.get('side') not in ('blue', 'red'):
            quality.append('player_side_unknown')
            continue
        role = ROLES.get(str(raw.get('role', '')).lower())
        if role is None:
            quality.append('player_role_unknown')
        items = raw.get('items')
        players.append(Player(side=raw['side'], role=role, name=text(raw.get('summonerName')),
                              champion=text(raw.get('championId')), gold=number(raw.get('totalGold')),
                              cs=number(raw.get('creepScore')), level=number(raw.get('level')),
                              kills=number(raw.get('kills')), deaths=number(raw.get('deaths')),
                              assists=number(raw.get('assists')),
                              championIconUrl=text(raw.get('championIconUrl')),
                              championDamageShare=number(raw.get('championDamageShare')),
                              currentHealth=number(raw.get('currentHealth')),
                              maxHealth=number(raw.get('maxHealth')),
                              items=[i for i in items if type(i) in (int, str)] if isinstance(items, list) else None))
    game_time = number(data.get('gameTime'))
    if game_time is None:
        quality.append('game_time_unknown')
    delayed = payload.get('delayed')
    delay = number(delayed.get('delay_seconds')) if isinstance(delayed, dict) else None
    if delay:
        quality.append('plan_delayed')
    snapshot = Snapshot(game_id=game_id, source_ts=source_ts, ingest_ts=now or utcnow(),
                        game_time=game_time, game_state=text(data.get('state')) or 'unknown',
                        blue=teams[0], red=teams[1], players=players, quality=sorted(set(quality)),
                        delayed_seconds=delay, stale_threshold_seconds=stale_threshold, raw=payload, source=source)
    snapshot = snapshot.refreshed(now)
    if snapshot.freshness == 'unknown' and source_ts:
        snapshot.quality.append('future_source_timestamp')
    return snapshot
