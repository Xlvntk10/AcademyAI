from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app.main import create_app
from app.database.db import make_engine
from app.web import mount_frontend


def test_production_refuses_ephemeral_sqlite(monkeypatch):
    monkeypatch.setenv('ACADEMY_ENV', 'production')
    engine = make_engine('sqlite://')
    with pytest.raises(RuntimeError, match='PostgreSQL'):
        create_app(engine)
    engine.dispose()


def test_production_requires_database_tls(monkeypatch):
    monkeypatch.setenv('ACADEMY_ENV', 'production')
    engine = make_engine('postgresql://runtime:unused@127.0.0.1/test')
    with pytest.raises(RuntimeError, match='TLS'):
        create_app(engine)
    engine.dispose()


def test_shell_routes_worker_cache_and_private_paths(tmp_path):
    directory = tmp_path/'dist'
    directory.mkdir()
    (directory/'index.html').write_text('<main>Academy AI</main>')
    (directory/'sw.js').write_text('// worker')
    (directory/'assets').mkdir()
    (directory/'assets'/'index-hash.js').write_text('// application')
    (tmp_path/'secret.txt').write_text('private')
    app = FastAPI()
    mount_frontend(app, directory)
    with TestClient(app) as client:
        callback = client.get('/auth/callback?code=short-lived-test-code')
        assert callback.status_code == 200
        assert callback.headers['cache-control'] == 'no-store'
        for route in ('/', '/today', '/learn', '/plan', '/progress'):
            response = client.get(route)
            assert response.status_code == 200
            assert 'Academy AI' in response.text
            assert response.headers['cache-control'] == 'no-cache'
        assert client.get('/sw.js').headers['service-worker-allowed'] == '/'
        assert 'immutable' in client.get('/assets/index-hash.js').headers['cache-control']
        for path in ('/api/missing', '/assets/missing.js', '/%2e%2e/secret.txt', '/database.db'):
            assert client.get(path).status_code == 404
