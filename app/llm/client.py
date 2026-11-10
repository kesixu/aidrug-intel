"""DeepSeek 客户端（OpenAI 兼容）：JSON 模式、纯文本、异步流式；重试 + 用量记账 + 总时限。

总时限：DeepSeek 排队时会一直回空行/保活注释（2026-10-15 现场：4 个分析请求各挂满 900s 后回 200 空内容），
httpx 的 timeout 只管单次读、挡不住，所以所有调用都边读边对表。
"""
import asyncio
import json
import time

import httpx

from app.config import settings
from app.db import session_scope
from app.log import log_event
from app.models import LlmUsage


class LlmError(Exception):
    """传输层/服务端错误（可重试后仍失败），或拿不到可用回答（超时、空内容、截断）。"""


class LlmBadOutput(Exception):
    """模型输出不符合约定（JSON 解析失败等）。"""


class _DeadlineExceeded(Exception):
    pass


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json"}


def _url() -> str:
    return f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"


def _record_usage(model: str, purpose: str, usage: dict) -> None:
    pt = int(usage.get("prompt_tokens") or 0)
    ct = int(usage.get("completion_tokens") or 0)
    if "flash" in model:
        cost = pt / 1e6 * settings.price_flash_in + ct / 1e6 * settings.price_flash_out
    else:
        cost = pt / 1e6 * settings.price_pro_in + ct / 1e6 * settings.price_pro_out
    try:
        with session_scope() as db:
            db.add(LlmUsage(model=model, purpose=purpose,
                            prompt_tokens=pt, completion_tokens=ct, cost_est=round(cost, 6)))
    except Exception:
        pass  # 记账失败不影响业务


def _stream_post(body: dict, deadline: float) -> tuple[int, str]:
    remaining = max(1.0, deadline - time.monotonic())
    timeout = httpx.Timeout(remaining, connect=min(15.0, remaining))
    with httpx.stream("POST", _url(), headers=_headers(), json=body, timeout=timeout) as r:
        buf = bytearray()
        for chunk in r.iter_bytes():
            buf += chunk
            if time.monotonic() > deadline:
                raise _DeadlineExceeded()
        return r.status_code, buf.decode("utf-8", "replace")


def _post_chat(body: dict, purpose: str, retries: int = 2, deadline_s: float = 180.0) -> dict:
    """deadline_s 是含重试在内的总时限。"""
    deadline = time.monotonic() + deadline_s
    last_err = ""
    for attempt in range(retries + 1):
        if attempt:
            pause = 2.0 * attempt
            if deadline - time.monotonic() < pause + 5:
                break
            time.sleep(pause)
        try:
            status, text = _stream_post(body, deadline)
        except _DeadlineExceeded:
            last_err = f"超过总时限 {deadline_s:.0f}s（服务端排队）"
            break
        except httpx.HTTPError as e:
            last_err = f"{type(e).__name__}: {e}"
            continue
        if status == 429 or status >= 500:
            last_err = f"HTTP {status}: {text[:200]}"
            continue
        if status != 200:
            raise LlmError(f"HTTP {status}: {text[:300]}")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            last_err = f"响应不是 JSON: {text.strip()[:200]}"
            continue
        _record_usage(body["model"], purpose, data.get("usage") or {})
        return data
    log_event("llm.failed", purpose=purpose, model=body.get("model"), error=last_err or "超过总时限")
    raise LlmError(last_err or f"超过总时限 {deadline_s:.0f}s")


def _first_choice(data: dict) -> tuple[str, str]:
    choice = (data.get("choices") or [{}])[0]
    return choice.get("finish_reason") or "", (choice.get("message") or {}).get("content") or ""


def chat_json(messages: list[dict], model: str | None = None, purpose: str = "analyze",
              temperature: float = 0.2, max_tokens: int = 8000, deadline_s: float = 180.0) -> dict:
    """JSON 模式：返回解析后的 dict；输出不合约定抛 LlmBadOutput。开思考 + 最高档（批处理不赶时间）；思考 token 计入 max_tokens。"""
    body = {
        "model": model or settings.deepseek_model_flash,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "enabled"},
        "reasoning_effort": "max",
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = _post_chat(body, purpose, deadline_s=deadline_s)
    finish, content = _first_choice(data)
    if finish == "length":
        raise LlmBadOutput(f"输出在 {max_tokens} tokens 处被截断，请调大 max_tokens")
    if not content.strip():
        if not (data.get("usage") or {}).get("completion_tokens"):
            raise LlmError("服务端返回空内容且未计 token（多为排队后放弃）")
        raise LlmBadOutput("模型返回空内容")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise LlmBadOutput(f"JSON 解析失败: {e}; head={content[:200]}") from e
    if not isinstance(parsed, dict):
        raise LlmBadOutput(f"JSON 顶层不是对象: {type(parsed).__name__}")
    return parsed


def chat_text(messages: list[dict], model: str | None = None, purpose: str = "brief",
              temperature: float = 0.5, max_tokens: int = 8000, deadline_s: float = 180.0) -> str:
    """纯文本。截断或空内容抛 LlmError：调用方走兜底，绝不把半截稿、空稿当成功。"""
    body = {
        "model": model or settings.deepseek_model_pro,
        "messages": messages,
        "thinking": {"type": "enabled"},
        "reasoning_effort": "max",
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = _post_chat(body, purpose, deadline_s=deadline_s)
    finish, content = _first_choice(data)
    if finish == "length":
        raise LlmError(f"输出在 {max_tokens} tokens 处被截断（思考 token 也计入）")
    if not content.strip():
        raise LlmError("模型返回空内容")
    return content


async def chat_stream(messages: list[dict], model: str | None = None, purpose: str = "chat",
                      temperature: float = 0.5, max_tokens: int = 8000,
                      first_output_s: float = 40.0, total_s: float = 240.0):
    """异步生成器，yield (kind, value)：
    - ("thinking", 已用秒数)：思考中，至多每 2 秒一次——前端显示"思考中"，也让 nginx 的 60s 读超时不断流；
    - ("delta", 文本增量)；
    - ("truncated", "")：回答写到 max_tokens 被截断。
    交互式聊天：开思考，档位用默认（高），避免首字等太久。首个输出须在 first_output_s 内（nginx 60s 前），
    全程不超过 total_s；超时、传输错误、空回答一律抛 LlmError。
    """
    body = {
        "model": model or settings.deepseek_model_pro,
        "messages": messages,
        "thinking": {"type": "enabled"},
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    used_model = body["model"]
    loop = asyncio.get_running_loop()
    start = loop.time()
    got_output = got_content = False
    last_tick = start - 2.0
    finish = ""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(total_s, connect=15.0)) as client:
            async with client.stream("POST", _url(), headers=_headers(), json=body) as resp:
                if resp.status_code != 200:
                    detail = (await resp.aread()).decode("utf-8", "replace")[:300]
                    raise LlmError(f"HTTP {resp.status_code}: {detail}")
                lines = resp.aiter_lines()
                while True:
                    budget = start + (total_s if got_output else first_output_s) - loop.time()
                    if budget <= 0:
                        raise asyncio.TimeoutError
                    try:
                        line = await asyncio.wait_for(lines.__anext__(), budget)
                    except StopAsyncIteration:
                        break
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("usage"):
                        _record_usage(used_model, purpose, chunk["usage"])
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    finish = choices[0].get("finish_reason") or finish
                    delta = choices[0].get("delta") or {}
                    if delta.get("reasoning_content"):
                        got_output = True
                        now = loop.time()
                        if now - last_tick >= 2.0:
                            last_tick = now
                            yield "thinking", int(now - start)
                    if delta.get("content"):
                        got_output = got_content = True
                        yield "delta", delta["content"]
    except asyncio.TimeoutError:
        what = f"回答超过 {total_s:.0f}s" if got_output else f"{first_output_s:.0f}s 内没有任何输出"
        log_event("llm.failed", purpose=purpose, model=used_model, error=f"stream timeout: {what}")
        raise LlmError(f"{what}，模型可能在排队，请稍后再试") from None
    except httpx.HTTPError as e:
        log_event("llm.failed", purpose=purpose, model=used_model, error=f"{type(e).__name__}: {e}")
        raise LlmError(f"{type(e).__name__}: {e}") from e
    if finish == "length":
        if not got_content:
            raise LlmError(f"思考用尽 {max_tokens} tokens 仍未开始回答")
        yield "truncated", ""
    elif not got_content:
        raise LlmError("模型没有给出回答")
