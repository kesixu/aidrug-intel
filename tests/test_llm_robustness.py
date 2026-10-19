"""LLM 调用失败路径回归（2026-10-17 复盘）：总时限、截断/空稿、坏输出重试、批次互斥、晨报兜底、调度时区。

全部本地造响应，不出网。"""
import asyncio
import json
import socket
import threading
import time
import uuid

import pytest

from app.llm import analyst, briefing
from app.llm import client as llm
from app.llm.client import LlmBadOutput, LlmError
from app.log import now_iso
from app.models import Analysis, Brief, Item
from app.textutil import beijing_today


def _serve(steps, content_type=b"application/json"):
    """一次性本地 HTTP 服务：读完请求后按 steps=[(延迟秒, 字节)] 逐段回写，然后关连接。"""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def run():
        conn, _ = srv.accept()
        try:
            data = b""
            while b"\r\n\r\n" not in data:
                data += conn.recv(65536)
            head, _, body = data.partition(b"\r\n\r\n")
            n = next((int(l.split(b":")[1]) for l in head.split(b"\r\n")
                      if l.lower().startswith(b"content-length:")), 0)
            while len(body) < n:
                body += conn.recv(65536)
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: " + content_type
                         + b"\r\nConnection: close\r\n\r\n")
            for delay, chunk in steps:
                time.sleep(delay)
                conn.sendall(chunk)
        except OSError:
            pass  # 客户端到点主动断开
        finally:
            conn.close()
            srv.close()

    threading.Thread(target=run, daemon=True).start()
    return f"http://127.0.0.1:{port}"


def _completion(content, finish="stop", completion_tokens=10):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 5, "completion_tokens": completion_tokens}}


def _sse(obj) -> bytes:
    return b"data: " + json.dumps(obj, ensure_ascii=False).encode() + b"\n\n"


# ---- 总时限 ----

def test_post_chat_total_deadline_beats_keepalive_stall(client, monkeypatch):
    """DeepSeek 排队时持续回空行：单次读超时永远不触发，必须按总时限断开。"""
    monkeypatch.setattr(llm.settings, "deepseek_base_url", _serve([(0.2, b"\n")] * 60))
    t0 = time.monotonic()
    with pytest.raises(LlmError):
        llm._post_chat({"model": "deepseek-flash", "messages": []}, "test", deadline_s=1.5)
    assert time.monotonic() - t0 < 3.5


def test_post_chat_tolerates_keepalive_blank_lines(client, monkeypatch):
    body = json.dumps(_completion("{}")).encode()
    monkeypatch.setattr(llm.settings, "deepseek_base_url", _serve([(0.05, b"\n"), (0.05, b"\n"), (0.05, body)]))
    data = llm._post_chat({"model": "deepseek-flash", "messages": []}, "test", deadline_s=5)
    assert data["choices"][0]["message"]["content"] == "{}"


# ---- 截断 / 空内容 ----

def test_chat_text_rejects_truncated_and_empty(monkeypatch):
    for data in (_completion("半截", finish="length"), _completion(""), _completion("  \n")):
        monkeypatch.setattr(llm, "_post_chat", lambda *a, _d=data, **k: _d)
        with pytest.raises(LlmError):
            llm.chat_text([{"role": "user", "content": "x"}])


def test_chat_json_empty_and_non_object(monkeypatch):
    monkeypatch.setattr(llm, "_post_chat", lambda *a, **k: _completion("", completion_tokens=0))
    with pytest.raises(LlmError):  # 0 token 空内容 = 服务端放弃，算传输失败、条目下轮重试
        llm.chat_json([{"role": "user", "content": "x"}])
    for content in ("", "[1, 2]"):
        monkeypatch.setattr(llm, "_post_chat", lambda *a, _c=content, **k: _completion(_c))
        with pytest.raises(LlmBadOutput):
            llm.chat_json([{"role": "user", "content": "x"}])


# ---- 流式 ----

def _collect_stream(monkeypatch, steps, **kw):
    monkeypatch.setattr(llm.settings, "deepseek_base_url", _serve(steps, b"text/event-stream"))

    async def go():
        return [x async for x in llm.chat_stream([{"role": "user", "content": "q"}], **kw)]
    return asyncio.run(go())


def test_chat_stream_signals_thinking_then_content(client, monkeypatch):
    out = _collect_stream(monkeypatch, [
        (0, _sse({"choices": [{"delta": {"reasoning_content": "想"}}]})),
        (0, _sse({"choices": [{"delta": {"content": "答"}}]})),
        (0, _sse({"choices": [{"delta": {}, "finish_reason": "stop"}],
                  "usage": {"prompt_tokens": 1, "completion_tokens": 2}})),
        (0, b"data: [DONE]\n\n"),
    ])
    assert out[0][0] == "thinking" and ("delta", "答") in out and ("truncated", "") not in out


def test_chat_stream_first_output_deadline(client, monkeypatch):
    t0 = time.monotonic()
    with pytest.raises(LlmError):
        _collect_stream(monkeypatch, [(0.2, b": keep-alive\n\n")] * 30, first_output_s=1.0)
    assert time.monotonic() - t0 < 3


def test_chat_stream_length_flags(client, monkeypatch):
    out = _collect_stream(monkeypatch, [
        (0, _sse({"choices": [{"delta": {"content": "前半"}}]})),
        (0, _sse({"choices": [{"delta": {}, "finish_reason": "length"}]})),
    ])
    assert out[-1] == ("truncated", "")
    with pytest.raises(LlmError):  # 思考吃光预算、一个字没写
        _collect_stream(monkeypatch, [
            (0, _sse({"choices": [{"delta": {"reasoning_content": "想"}}]})),
            (0, _sse({"choices": [{"delta": {}, "finish_reason": "length"}]})),
        ])


# ---- 条目分析：坏输出重试、批次互斥、连续传输失败收工 ----

CANNED = {"summary": "两句话摘要。细节。", "category": "资金申报", "event_type": "资金申报",
          "importance": 70, "lens_scores": [], "entities": [], "action_hint": "",
          "deadline": None, "signal": "强", "policy_family": "", "policy_stage": ""}


def _new_item(db, title):
    it = Item(uid=f"uid-{uuid.uuid4().hex}", source_id="most_tztg", url="https://x.cn/t",
              title=title, published_at="2026-10-17", fetched_at=now_iso(), excerpt="e",
              content="正文", status="new")
    db.add(it)
    db.commit()
    return it


def test_bad_output_retried_once_before_failed(client, db, monkeypatch):
    good, bad = _new_item(db, "好条目"), _new_item(db, "坏条目")
    calls = {"好条目": 0, "坏条目": 0}

    def fake(messages, **k):
        key = "好条目" if "好条目" in messages[1]["content"] else "坏条目"
        calls[key] += 1
        if key == "坏条目" or calls[key] == 1:
            raise LlmBadOutput("JSON 解析失败")
        return CANNED
    monkeypatch.setattr(analyst, "chat_json", fake)
    assert analyst.analyze_item(good.id) is True
    assert analyst.analyze_item(bad.id) is False
    assert calls == {"好条目": 2, "坏条目": 2}
    db.expire_all()
    assert db.get(Item, good.id).status == "analyzed"
    assert db.get(Item, bad.id).status == "failed"


def test_normalize_survives_malformed_fields():
    a = analyst._normalize({"importance": "高", "lens_scores": ["x", {"lens_id": "a", "score": "九十"}],
                            "entities": "北京"}, [])
    assert a["importance"] == 0 and a["lens_scores"] == [] and a["entities"] == []


def test_analyze_pending_is_mutually_exclusive(client):
    assert analyst._batch_lock.acquire(blocking=False)
    try:
        assert analyst.analyze_pending()["busy"] is True
        t0 = time.monotonic()
        assert analyst.analyze_pending(wait=0.2)["busy"] is True
        assert time.monotonic() - t0 >= 0.15
    finally:
        analyst._batch_lock.release()


def test_batch_stops_after_consecutive_transport_failures(client, db, monkeypatch):
    items = [_new_item(db, f"传输失败{i}") for i in range(5)]
    calls = []

    def down(*a, **k):
        calls.append(1)
        raise LlmError("down")
    monkeypatch.setattr(analyst, "chat_json", down)
    try:
        analyst.analyze_pending()
        assert len(calls) == analyst._MAX_TRANSPORT_FAILS
        db.expire_all()
        assert all(db.get(Item, it.id).status == "new" for it in items)
    finally:
        for it in items:
            db.delete(db.get(Item, it.id))
        db.commit()


# ---- 晨报 ----

def _brief_material(db, title="晨报素材条目"):
    it = Item(uid=f"uid-{uuid.uuid4().hex}", source_id="most_tztg", url="https://x.cn/b", title=title,
              published_at="2026-10-17", fetched_at=now_iso(), status="analyzed")
    db.add(it)
    db.flush()
    db.add(Analysis(item_id=it.id, summary="摘要", category="资金申报", importance=100,
                    final_score=100, tier="red", model="test"))
    db.commit()
    return it


def test_brief_failure_falls_back_to_item_list(client, db, monkeypatch):
    _brief_material(db)

    def boom(*a, **k):
        raise LlmError("输出在 16000 tokens 处被截断")
    monkeypatch.setattr(briefing, "chat_text", boom)
    r = briefing.generate_brief(force=True)
    db.expire_all()
    b = db.get(Brief, r["id"])
    assert b.model == "fallback" and "晨报素材条目" in b.content_md and "生成失败" in b.content_md
    assert "无达到关注阈值" not in b.content_md


def test_empty_brief_counts_as_missing(client, db, monkeypatch):
    _brief_material(db)
    date = beijing_today()
    b = db.query(Brief).filter(Brief.date == date).first() or Brief(date=date)
    b.content_md, b.model = "", "deepseek-v4-pro"
    db.add(b)
    db.commit()
    monkeypatch.setattr(briefing, "chat_text", lambda *a, **k: "# 见微晨报\n\n正文")
    assert briefing.generate_brief(force=False)["created"] is True
    db.expire_all()
    assert db.query(Brief).filter(Brief.date == date).one().content_md.startswith("# 见微晨报")
    assert briefing.generate_brief(force=False)["created"] is False


def test_brief_generate_api_runs_in_background(client, db, monkeypatch):
    _brief_material(db)
    monkeypatch.setattr(briefing, "chat_text", lambda *a, **k: "# 见微晨报\n\n后台生成")
    assert "running" in client.post("/api/v1/brief/generate").json()
    s = client.get("/api/v1/brief/generate/status").json()
    assert s["running"] is False and s["error"] is None and s["result"]["created"] is True


def test_system_analyze_api_returns_immediately(client, monkeypatch):
    monkeypatch.setattr(analyst, "chat_json", lambda *a, **k: (_ for _ in ()).throw(LlmError("down")))
    assert set(client.post("/api/v1/system/analyze").json()) == {"pending", "queued"}


# ---- 对话 SSE ----

def test_chat_sse_thinking_truncation_and_empty(client, monkeypatch):
    async def fake_stream(*a, **k):
        yield "thinking", 3
        yield "delta", "结论"
        yield "truncated", ""
    monkeypatch.setattr("app.api.chat.chat_stream", fake_stream)
    t = client.post("/api/v1/chat/stream", json={"message": "测试"}).text
    assert "event: thinking" in t and "截断" in t and "event: done" in t

    async def empty_stream(*a, **k):
        raise LlmError("模型没有给出回答")
        yield  # noqa: unreachable — 让它成为异步生成器
    monkeypatch.setattr("app.api.chat.chat_stream", empty_stream)
    t = client.post("/api/v1/chat/stream", json={"message": "测试二"}).text
    assert "event: error" in t and "event: done" not in t


# ---- 调度时区 ----

def test_cron_jobs_use_beijing_time():
    from app import scheduler
    scheduler.start_scheduler()
    try:
        for jid in ("brief", "evolve"):
            assert str(scheduler._scheduler.get_job(jid).trigger.timezone) == "Asia/Shanghai"
    finally:
        scheduler.stop_scheduler()
