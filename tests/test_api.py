import pytest
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.clients.demo import DemoClient


def test_api_lifecycle_ws_history_and_secret(settings):
    settings.demo_mode = True
    app = create_app(settings, client=DemoClient())
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/ready').status_code == 200
        assert client.post('/api/monitors', json={'gameId':'../secret'}).status_code == 422
        assert client.post('/api/monitors', json={'gameId':'x'*65}).status_code == 422
        assert client.get('/api/games/test-1/latest').status_code == 404
        with client.websocket_connect('/ws/games/test-1') as ws:
            result = client.post('/api/monitors', json={'gameId':'test-1'})
            assert result.status_code == 202
            events=[]
            for _ in range(5):
                event=ws.receive_json(); events.append(event['type'])
                if event['type']=='snapshot': break
            assert 'snapshot' in events and 'status' in events
            latest = client.get('/api/games/test-1/latest')
            assert latest.status_code == 200 and latest.json()['source'] == 'demo'
            assert 'test-key-not-real' not in latest.text and '"raw"' not in latest.text
            assert client.get('/api/games/test-1/history').json()['items']
            assert client.get('/api/games/test-1/history?minutes=99999').status_code == 422
            assert client.delete('/api/monitors/test-1').json()['state'] == 'stopped'
        assert client.get('/api/monitors').json()['items'][0]['state'] == 'stopped'
    assert not app.state.manager.tasks


def test_ws_origin_denied(settings):
    from starlette.websockets import WebSocketDisconnect
    with TestClient(create_app(settings, client=DemoClient())) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/ws/games/test-1', headers={'origin':'https://untrusted.example'}): pass


def test_no_key_readiness_and_cors(settings):
    from pydantic import SecretStr
    settings.cito_api_key = SecretStr('')
    with TestClient(create_app(settings)) as client:
        assert client.get('/ready').status_code == 503
        allowed = client.options('/api/monitors',headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'POST'})
        assert allowed.headers['access-control-allow-origin'] == 'http://localhost:5173'
        denied = client.options('/api/monitors',headers={'Origin':'https://untrusted.example','Access-Control-Request-Method':'POST'})
        assert 'access-control-allow-origin' not in denied.headers
