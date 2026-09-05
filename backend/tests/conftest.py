import os
import uuid

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tasks:tasks@localhost:5502/tasks_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6440/1")
os.environ.setdefault("SEED_SYNTHETIC_DATA", "false")
os.environ.setdefault("MODEL_ARTIFACT_DIR", "./tests/_artifacts")

import pytest
import redis as redis_lib
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.core.db import Base
from app.main import app


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(get_settings().database_url, future=True)
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def _clean_db(engine):
    yield
    with engine.begin() as conn:
        for table in ("interactions", "sync_cursors", "tasks", "refresh_tokens", "users"):
            conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))


@pytest.fixture(autouse=True)
def _clean_redis():
    yield
    client = redis_lib.Redis.from_url(get_settings().redis_url, decode_responses=True)
    client.flushdb()
    client.close()


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="session", autouse=True)
def _pretrained_model():
    """Train the ranker once per test session (writes to MODEL_ARTIFACT_DIR) so the app's
    startup lifespan finds an existing artifact and skips retraining on every TestClient
    construction."""
    from pathlib import Path

    from app.ml.train import train_and_evaluate

    artifact_dir = Path(get_settings().model_artifact_dir)
    if not (artifact_dir / "ranker.joblib").exists():
        # use the same defaults as production startup training so the ranker is exercised the
        # same way in tests as it is in the running app (a smaller/noisier one occasionally
        # mis-ranks a single hand-picked pair in test_recommendations_api.py)
        train_and_evaluate()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def registered_user(client):
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    password = "supersecret1"
    resp = client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    tokens = resp.json()
    return {"email": email, "password": password, **tokens}


@pytest.fixture()
def auth_headers(registered_user):
    return {"Authorization": f"Bearer {registered_user['access_token']}"}
