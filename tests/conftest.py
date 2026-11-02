import os

os.environ["DATABASE_URL"] = "sqlite:///./test_safeone.db"
os.environ["SEED_ON_STARTUP"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import reset_and_seed  # noqa: E402

AGENT = {"X-API-Key": "dev-agent-key"}
ANALYST = {"X-API-Key": "dev-analyst-key"}


@pytest.fixture()
def client():
    with SessionLocal() as db:
        reset_and_seed(db)
    with TestClient(app) as c:
        yield c


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()  # no Windows o SQLite fica travado enquanto há conexões abertas
    if os.path.exists("test_safeone.db"):
        os.remove("test_safeone.db")
