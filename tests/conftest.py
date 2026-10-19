"""测试环境：独立临时 DB 与日志目录，禁调度器，LLM 不出网。必须在导入 app 前设置环境变量。"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="aidrug-test-")
os.environ["AIDRUG_DB_PATH"] = os.path.join(_TMP, "test.db")
# 2026-10-17：曾漏设，测试事件（收藏/取消、画像更新）写进了生产 workspace/logs
os.environ["AIDRUG_LOG_DIR"] = os.path.join(_TMP, "logs")
os.environ["AIDRUG_SCHEDULER_ENABLED"] = "false"
# 强制覆盖：shell 里导出的真 key 不能让漏 mock 的测试产生真实计费调用
os.environ["DEEPSEEK_API_KEY"] = "test-key-not-used"
os.environ["DEEPSEEK_BASE_URL"] = "http://127.0.0.1:9"

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
