"""界面依赖的启动与 SSE 契约。不改 API 形状，只锁住别被缓冲或环境变量卡住。"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_chat_stream_is_not_gzipped(client, monkeypatch):
    async def fake_stream(*_a, **_k):
        yield "delta", "你好"

    monkeypatch.setattr("app.api.chat.chat_stream", fake_stream)
    r = client.post(
        "/api/v1/chat/stream",
        json={"message": "缓冲测试"},
        headers={"Accept-Encoding": "gzip, deflate"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers.get("x-accel-buffering") == "no"
    assert "gzip" not in (r.headers.get("content-encoding") or "").lower()
    assert "event: delta" in r.text and "你好" in r.text


def test_boots_with_key_only_env(tmp_path):
    """生产 .env 只有 DEEPSEEK_API_KEY。调度保持默认开启，健康检查仍要立刻可用。"""
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("AIDRUG_") or key.startswith("DEEPSEEK_"):
            env.pop(key)
    env["DEEPSEEK_API_KEY"] = "sk-test-only"
    env["AIDRUG_DB_PATH"] = str(tmp_path / "boot.db")
    env["AIDRUG_LOG_DIR"] = str(tmp_path / "logs")
    port = str(_free_port())
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        last = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as resp:
                    body = json.loads(resp.read().decode())
                assert body["status"] == "ok"
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/system/status", timeout=2) as resp:
                    status = json.loads(resp.read().decode())
                assert status["scheduler"], "默认应启动进程内调度"
                return
            except Exception as exc:  # 端口还没起来
                last = exc
                time.sleep(0.25)
        out = ""
        if proc.stdout:
            proc.terminate()
            out = proc.stdout.read()[-2000:]
        raise AssertionError(f"startup failed: {last}\n{out}")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
