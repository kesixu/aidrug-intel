"""DeepSeek 客户端（OpenAI 兼容）：JSON 模式、纯文本、异步流式；重试 + 用量记账。"""
import json
import time

import httpx

from app.config import settings
from app.db import session_scope
from app.log import log_event
from app.models import LlmUsage


class LlmError(Exception):
    """传输层/服务端错误（可重试后仍失败）。"""


class LlmBadOutput(Exception):
    """模型输出不符合约定（JSON 解析失败等）。"""


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


def _post_chat(body: dict, purpose: str, retries: int = 2, timeout: float = 180.0) -> dict:
    last_err = ""
    for attempt in range(retries + 1):
        try:
            r = httpx.post(_url(), headers=_headers(), json=body, timeout=timeout)
            if r.status_code in (429,) or r.status_code >= 500:
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                time.sleep(2.0 * (attempt + 1))
                continue
            if r.status_code != 200:
                raise LlmError(f"HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            _record_usage(body["model"], purpose, data.get("usage") or {})
            return data
        except httpx.HTTPError as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(2.0 * (attempt + 1))
    log_event("llm.failed", purpose=purpose, model=body.get("model"), error=last_err)
    raise LlmError(last_err)


def chat_json(messages: list[dict], model: str | None = None, purpose: str = "analyze",
              temperature: float = 0.2, max_tokens: int = 2000) -> dict:
    """JSON 模式：返回解析后的 dict；解析失败抛 LlmBadOutput。"""
    body = {
        "model": model or settings.deepseek_model_flash,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = _post_chat(body, purpose)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise LlmBadOutput(f"JSON 解析失败: {e}; head={content[:200]}") from e


def chat_text(messages: list[dict], model: str | None = None, purpose: str = "brief",
              temperature: float = 0.5, max_tokens: int = 3500) -> str:
    body = {
        "model": model or settings.deepseek_model_pro,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = _post_chat(body, purpose)
    return (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""


async def chat_stream(messages: list[dict], model: str | None = None, purpose: str = "chat",
                      temperature: float = 0.5, max_tokens: int = 2500):
    """异步生成器，逐段 yield 文本增量。"""
    body = {
        "model": model or settings.deepseek_model_pro,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    used_model = body["model"]
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=15.0)) as client:
        async with client.stream("POST", _url(), headers=_headers(), json=body) as resp:
            if resp.status_code != 200:
                detail = (await resp.aread()).decode("utf-8", "replace")[:300]
                raise LlmError(f"HTTP {resp.status_code}: {detail}")
            async for line in resp.aiter_lines():
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
                if choices:
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        yield delta
