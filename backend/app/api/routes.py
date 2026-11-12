import asyncio
import re
from typing import Annotated
from fastapi import APIRouter, HTTPException, Path, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from backend.app.clients.cito import CitoError

router = APIRouter()
ID_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'
GameId = Annotated[str, Path(pattern=ID_PATTERN, max_length=64)]


class StartRequest(BaseModel):
    gameId: str = Field(pattern=ID_PATTERN, max_length=64)
    matchId: str | None = Field(default=None, pattern=ID_PATTERN, max_length=64)


@router.post('/api/monitors', status_code=202)
async def start(body: StartRequest, request: Request):
    try:
        return await request.app.state.manager.start(body.gameId, body.matchId)
    except CitoError as e:
        raise HTTPException(409, detail={'code': e.code, 'message': str(e)}) from None


@router.delete('/api/monitors/{game_id}')
async def stop(game_id: GameId, request: Request):
    return await request.app.state.manager.stop(game_id)


@router.get('/api/monitors')
async def monitors(request: Request):
    state = request.app.state
    return {'items': list(state.repo.statuses.values()), 'requests_used': state.client.budget.used,
            'request_budget': state.client.budget.limit, 'demo_mode': state.settings.demo_mode,
            'warnings': list(state.repo.warnings.values())}


@router.get('/api/games/{game_id}/latest')
async def latest(game_id: GameId, request: Request):
    value = await request.app.state.repo.get_latest(game_id)
    if value is None:
        raise HTTPException(404, '尚无快照，请先开始监控并等待采集')
    return value


@router.get('/api/games/{game_id}/history')
async def history(game_id: GameId, request: Request, minutes: int = Query(30, ge=1, le=1440)):
    repo = request.app.state.repo
    items = await repo.history(game_id, minutes)
    return {'items': items, 'storage': 'clickhouse+memory' if repo.ch else 'memory',
            'warnings': list(repo.warnings.values())}


@router.websocket('/ws/games/{game_id}')
async def websocket(websocket: WebSocket, game_id: str):
    state = websocket.app.state
    origin = websocket.headers.get('origin')
    if not re.fullmatch(ID_PATTERN, game_id) or (origin and origin not in state.settings.cors_origins):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    queue = state.events.subscribe(game_id)

    async def sender():
        status = state.repo.statuses.get(game_id)
        if status:
            await websocket.send_json({'type': 'status', 'data': status.model_dump(mode='json')})
        snapshot = await state.repo.get_latest(game_id)
        if snapshot:
            await websocket.send_json({'type': 'snapshot', 'data': snapshot.model_dump(mode='json')})
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), 15)
            except asyncio.TimeoutError:
                event = {'type': 'heartbeat', 'data': {'warnings': list(state.repo.warnings.values())}}
            await websocket.send_json(event)

    async def receiver():
        while True:
            await websocket.receive_text()

    tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        state.events.unsubscribe(game_id, queue)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
