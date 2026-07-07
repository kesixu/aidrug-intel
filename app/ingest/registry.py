"""sources.yml ←→ DB 同步：YAML 是定义的权威，DB 保存运行状态。"""
import yaml
from sqlalchemy.orm import Session

from app.config import settings
from app.log import log_event
from app.models import Source

PROTECTED_IDS = {"legacy"}  # 非注册表管理的内部源


def load_registry() -> list[dict]:
    with open(settings.sources_file, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("sources") or []


def sync_sources(db: Session) -> None:
    defs = load_registry()
    seen = set()
    for d in defs:
        sid = d["id"]
        seen.add(sid)
        row = db.get(Source, sid)
        if row is None:
            row = Source(id=sid)
            db.add(row)
        row.name = d.get("name", sid)
        row.tier = int(d.get("tier", 3))
        row.kind = d.get("kind", "html")
        row.url = d.get("url", "")
        row.enabled = bool(d.get("enabled", True))
        cfg = dict(d.get("config") or {})
        cfg["schedule_minutes"] = int(d.get("schedule_minutes", 240))
        row.config = cfg
        if d.get("note"):
            row.note = d["note"]
        if not row.enabled:
            row.health = "disabled"
        elif row.health == "disabled":
            row.health = "unknown"
    # 注册表里删掉的源：停用但保留历史
    for row in db.query(Source).all():
        if row.id not in seen and row.id not in PROTECTED_IDS:
            row.enabled = False
            row.health = "disabled"
            row.note = row.note or "已从注册表移除"
    log_event("registry.synced", count=len(seen))
