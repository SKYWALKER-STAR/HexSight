"""Make one coverage request (optional) and one stats request. Never print credentials."""
import argparse
import asyncio
import json
from pathlib import Path
from backend.app.config import Settings
from backend.app.clients.cito import CitoClient, CitoError
from backend.app.services.normalizer import normalize
from backend.app.models.domain import utcnow
from backend.app.api.routes import StartRequest


def redact(value):
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()
                if k.lower().replace('_', '').replace('-', '') not in
                {'apikey', 'authorization', 'token', 'realname', 'email', 'imageurl', 'teamlogourl', 'logourl'}}
    if isinstance(value, list): return [redact(v) for v in value]
    return value


async def main():
    parser = argparse.ArgumentParser(description='验证 Cito LOL 数据权限与 schema（最多两次请求）')
    parser.add_argument('game_id')
    parser.add_argument('--match-id')
    parser.add_argument('--output', default='docs/verification/probe.json')
    args = parser.parse_args()
    validated = StartRequest(gameId=args.game_id, matchId=args.match_id)
    settings = Settings()
    client = CitoClient(settings)
    report = {'checked_at': utcnow().isoformat(), 'game_id': args.game_id, 'match_id': args.match_id}
    try:
        if validated.matchId:
            report['coverage'] = redact(await client.get(f'lol/matches/{validated.matchId}/coverage'))
        body = await client.stats(validated.gameId)
        report['stats'] = redact(body)
        snapshot = normalize(body, validated.gameId, settings.stale_threshold_seconds)
        report['result'] = {'state': snapshot.game_state, 'source_ts': snapshot.source_ts.isoformat() if snapshot.source_ts else None,
                            'freshness': snapshot.freshness, 'lag_seconds': snapshot.lag_seconds,
                            'players': len(snapshot.players), 'quality': snapshot.quality} if snapshot else {'state':'empty'}
        print(json.dumps(report['result'], ensure_ascii=False, indent=2))
    except CitoError as error:
        report['error'] = {'code': error.code, 'message': str(error)}
        print(json.dumps(report['error'], ensure_ascii=False))
    finally:
        await client.close()
        path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
        safe = json.dumps(report, ensure_ascii=False, indent=2)
        key = settings.cito_api_key.get_secret_value()
        path.write_text(safe.replace(key, '[REDACTED]') if key else safe)
        print(f'验证记录已保存：{path}')
    return 1 if 'error' in report else 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
