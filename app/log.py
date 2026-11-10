"""JSONL 结构化日志（workspace/logs/YYYY-MM-DD.jsonl）+ stdout（journald 收集）。"""
import json
import sys
import threading
from datetime import datetime, timezone

from app.config import settings

_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_event(event: str, **fields) -> None:
    rec = {"ts": now_iso(), "event": event, **fields}
    line = json.dumps(rec, ensure_ascii=False, default=str)
    print(line, file=sys.stdout, flush=True)
    try:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        path = settings.log_dir / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
        with _lock, open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # 日志落盘失败不影响业务
