from backend.app.config import Settings
from backend.app.models.domain import Advantage, Factor, Lane, Snapshot


def difference(a, b):
    return a - b if a is not None and b is not None else None


def clamp(value):
    return max(-1, min(1, value))


def score(parts, settings: Settings, *, coverage=1.0, note=None):
    parts = [p for p in parts if p[1] is not None and p[3] > 0]
    total = sum(p[3] for p in parts)
    if not total:
        return Advantage()
    factors = [Factor(name=name, difference=round(diff, 3), normalized=round(clamp(diff / scale), 6),
                      weight=weight / total) for name, diff, scale, weight in parts]
    value = round(sum(f.normalized * f.weight for f in factors) * 100, 1)
    return Advantage(score=value, direction='even' if abs(value) < settings.even_threshold else 'blue' if value > 0 else 'red',
                     confidence='high' if coverage >= .9 else 'medium' if coverage >= .5 else 'low',
                     factors=factors, **({'note': note} if note else {}))


def calculate(snapshot: Snapshot, settings: Settings) -> Snapshot:
    b, r = snapshot.blue, snapshot.red
    objectives = [(name, difference(getattr(b, name), getattr(r, name)), scale)
                  for name, scale in [('dragons', settings.dragon_scale), ('barons', settings.baron_scale),
                                      ('inhibitors', settings.inhibitor_scale)]]
    available = [(n, d, scale) for n, d, scale in objectives if d is not None]
    # Split the objective allocation among observed components; do not treat absent fields as zero.
    parts = [('gold', difference(b.gold, r.gold), max(settings.gold_scale_min,
              (snapshot.game_seconds or 0) / 60 * settings.gold_scale_per_minute), settings.gold_weight),
             ('towers', difference(b.towers, r.towers), settings.tower_scale, settings.tower_weight)]
    parts += [(n, d, scale, settings.objective_weight / len(available)) for n, d, scale in available]
    total_weight = settings.gold_weight + settings.objective_weight + settings.tower_weight
    observed_weight = (settings.gold_weight if b.gold is not None and r.gold is not None else 0)
    observed_weight += settings.tower_weight if b.towers is not None and r.towers is not None else 0
    observed_weight += settings.objective_weight * len(available) / 3
    coverage = observed_weight / total_weight if total_weight else 0
    if snapshot.game_seconds is None:
        coverage *= .7
    snapshot.advantage = score(parts, settings, coverage=coverage)
    for role in ('TOP', 'JUNGLE', 'MID', 'BOT', 'SUPPORT'):
        blue = [p for p in snapshot.players if p.side == 'blue' and p.role == role]
        red = [p for p in snapshot.players if p.side == 'red' and p.role == role]
        lane = Lane(role=role, blue=blue[0] if len(blue) == 1 else None,
                    red=red[0] if len(red) == 1 else None)
        if len(blue) != 1 or len(red) != 1:
            lane.reason = '角色缺失或重复，无法可靠匹配'
        else:
            lane.differences = {k: difference(getattr(blue[0], k), getattr(red[0], k))
                                for k in ('gold', 'cs', 'level', 'kills', 'deaths', 'assists')}
            if role in ('JUNGLE', 'SUPPORT'):
                lane.reason = '基础发育差异；打野与辅助暂不做综合对位评分'
            else:
                weights = [('gold', settings.lane_gold_scale, settings.lane_gold_weight),
                           ('cs', settings.lane_cs_scale, settings.lane_cs_weight),
                           ('level', settings.lane_level_scale, settings.lane_level_weight)]
                count = sum(lane.differences[k] is not None for k, _, _ in weights)
                cov = count / 3 * (1 if lane.differences['gold'] is not None else .5)
                lane.advantage = score([(k, lane.differences[k], scale, w) for k, scale, w in weights],
                                       settings, coverage=cov, note='基础发育优势；KDA 与装备仅供解释')
        snapshot.lanes.append(lane)
    return snapshot.refreshed(snapshot.ingest_ts)
