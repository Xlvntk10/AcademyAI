import pytest
from fastapi.testclient import TestClient
from app.database.db import make_engine
from app.main import create_app
from scripts.prepare_db import migrate


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "test.db"
    migrate(path)
    return path


@pytest.fixture
def client(database):
    engine = make_engine("sqlite:///" + database.as_posix())
    with TestClient(create_app(engine)) as result:
        yield result
    engine.dispose()
