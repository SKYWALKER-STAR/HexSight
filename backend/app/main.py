import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.app.config import Settings
from backend.app.clients.cito import CitoClient
from backend.app.clients.demo import DemoClient
from backend.app.storage.repository import Repository
from backend.app.services.events import EventBus
from backend.app.services.monitor import MonitorManager
from backend.app.api.routes import router
from backend.app.services.schedule import ScheduleService


def create_app(settings: Settings | None = None, *, client=None, repository=None):
    settings = settings or Settings()
    # Own the application namespace without changing Uvicorn/httpx log levels.
    app_logger = logging.getLogger('backend.app')
    app_logger.setLevel(settings.log_level)
    app_logger.propagate = False
    if not any(getattr(handler, '_hexsight', False) for handler in app_logger.handlers):
        handler = logging.StreamHandler()
        handler._hexsight = True
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
        app_logger.addHandler(handler)

    @asynccontextmanager
    async def lifespan(app):
        if int(os.getenv('WEB_CONCURRENCY', '1')) != 1:
            raise RuntimeError('HexSight requires one collection worker')
        # Advisory lock also catches uvicorn --workers N on the same host.
        import fcntl
        from pathlib import Path
        lock = (Path('/tmp') / 'hexsight-collector.lock').open('w')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise RuntimeError('Another HexSight collector is running; use one worker') from None
        app.state.settings = settings
        app.state.client = client or (DemoClient() if settings.demo_mode else CitoClient(settings))
        app.state.schedule = ScheduleService(app.state.client)
        app.state.repo = repository or Repository(settings)
        app.state.events = EventBus()
        app.state.manager = MonitorManager(settings, app.state.client, app.state.repo, app.state.events)
        try:
            await app.state.repo.initialize()
            yield
        finally:
            await app.state.manager.close()
            await app.state.repo.close()
            await app.state.client.close()
            lock.close()

    app = FastAPI(title='HexSight', version='0.1.0', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=['GET', 'POST', 'DELETE'], allow_headers=['Content-Type'])
    app.include_router(router)

    @app.get('/health')
    async def health():
        return {'status': 'ok'}

    @app.get('/ready')
    async def ready():
        deps = await app.state.repo.health()
        configured = settings.demo_mode or bool(settings.cito_api_key.get_secret_value())
        ready = configured and all(v != 'degraded' for v in deps.values())
        return JSONResponse({'status': 'ready' if ready else 'degraded', 'dependencies': deps,
                             'cito_configured': configured, 'demo_mode': settings.demo_mode,
                             'note': '配置就绪不等于已验证套餐权限或比赛覆盖'}, status_code=200 if ready else 503)

    return app


app = create_app()
