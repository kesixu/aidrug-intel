"""测试环境：独立临时 DB，禁调度器。必须在导入 app 前设置环境变量。"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="aidrug-test-")
os.environ["AIDRUG_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["AIDRUG_SCHEDULER_ENABLED"] = "false"
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-used")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    from app.db import migrate, SessionLocal
    migrate()
    s = SessionLocal()
    try:
        yield s
        s.commit()
    finally:
        s.close()
