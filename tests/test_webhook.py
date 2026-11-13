import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from backend.app.api.routes import router


def test_signed_webhook_dedup_and_rejection(settings):
    settings.cito_webhook_secret = SecretStr('test-secret')
    app = FastAPI()
    app.include_router(router)
    manager = Mock()
    manager.request_refresh.return_value = 1
    app.state.settings = settings
    app.state.manager = manager
    raw = json.dumps({'id': 'one', 'event': 'lol.live.state', 'data': {'gameId': 'test-1'}}).encode()
    sig = hmac.new(b'test-secret', raw, hashlib.sha256).hexdigest()
    with TestClient(app) as client:
        assert client.post('/api/webhooks/cito', content=raw).status_code == 401
        headers = {'x-cito-signature': sig}
        assert client.post('/api/webhooks/cito', content=raw, headers=headers).json()['status'] == 'accepted'
        assert client.post('/api/webhooks/cito', content=raw, headers=headers).json()['status'] == 'duplicate'
        assert client.post('/api/webhooks/cito', content=raw + b' ', headers=headers).status_code == 401
        manager.request_refresh.assert_called_once_with({'gameId': 'test-1'})
