"""采集编排：抓取 → 解析 → 门控 → 去重 → 入库。单源失败完全隔离。

LLM 分析不在此处（见 llm/analyst.py）：条目先以 status=new 入库，
分析异步补跑，LLM 故障不阻塞采集。
"""
import time
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db import fts_upsert, session_scope
from app.ingest.fetcher import fetch
from app.ingest.parsers import pick_parser
from app.log import log_event, now_iso
from app.models import FetchLog, Item, Profile, Source
from app.textutil import (beijing_today, canonical_url, extract_main_text,
                          jaccard, simhash64, title_tokens, uid_for)

DEDUP_WINDOW_DAYS = 14
DUP_JACCARD = 0.7   # 实义词重合率 ≥ 此值视为同一事件（实测同事件≥0.85、模板相似不同事件≤0.35）
DETAIL_FETCH_PAUSE_S = 0.4


def _gate_pass(title: str, excerpt: str, keywords: list[str]) -> bool:
    text = f"{title} {excerpt}".lower()
    return any(k.lower() in text for k in keywords)


def _recent_titles(db) -> list[tuple[int, frozenset]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DEDUP_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = db.query(Item.id, Item.title).filter(Item.fetched_at >= cutoff).all()
    return [(int(i), title_tokens(t or "")) for i, t in rows]


def run_source(source_id: str) -> dict:
    """抓取单个源。独立事务，异常不外溢。"""
    result = {"source": source_id, "ok": False, "found": 0, "new": 0, "gated": 0, "error": ""}
    try:
        with session_scope() as db:
            src = db.get(Source, source_id)
            if src is None or not src.enabled:
                result["error"] = "源不存在或已禁用"
                return result
            cfg = src.config or {}
            res = fetch(src.url, src.etag, src.last_modified, verify=cfg.get("verify", True))
            src.last_fetch_at = now_iso()

            if res.not_modified:
                src.consecutive_failures, src.health, src.last_success_at = 0, "ok", now_iso()
                db.add(FetchLog(source_id=source_id, ok=True, http_status=304, ms=res.ms))
                result.update(ok=True)
                return result

            if not res.ok:
                src.consecutive_failures += 1
                src.health = "down" if src.consecutive_failures >= 3 else "degraded"
                err = res.error or f"HTTP {res.status}"
                db.add(FetchLog(source_id=source_id, ok=False, http_status=res.status, error=err, ms=res.ms))
                log_event("ingest.fetch_failed", source=source_id, status=res.status, error=err)
                result["error"] = err
                return result

            src.etag, src.last_modified = res.etag, res.last_modified
            try:
                raws = pick_parser(src.kind, cfg)(res.content, src.url, cfg)
            except Exception as e:  # 解析崩溃视为源故障（多半是改版）
                src.consecutive_failures += 1
                src.health = "degraded"
                err = f"parse: {type(e).__name__}: {e}"
                db.add(FetchLog(source_id=source_id, ok=False, http_status=res.status, error=err[:500], ms=res.ms))
                log_event("ingest.parse_failed", source=source_id, error=err[:300])
                result["error"] = err
                return result

            keywords = (db.get(Profile, 1).keywords or []) if cfg.get("gate") else []
            recent = _recent_titles(db)
            found, new, gated = len(raws), 0, 0

            for raw in raws[: settings.fetch_max_per_source]:
                uid = uid_for(raw.url)
                if db.query(Item.id).filter(Item.uid == uid).first():
                    continue
                if cfg.get("gate") and not _gate_pass(raw.title, raw.excerpt, keywords):
                    gated += 1
                    continue
                toks = title_tokens(raw.title)
                cluster = next((rid for rid, rt in recent if jaccard(toks, rt) >= DUP_JACCARD), None)
                content = raw.excerpt
                if cfg.get("fetch_detail") and cluster is None:
                    detail = fetch(raw.url, verify=cfg.get("verify", True), retries=1)
                    if detail.ok and detail.content:
                        content = extract_main_text(detail.content) or raw.excerpt
                    time.sleep(DETAIL_FETCH_PAUSE_S)
                item = Item(
                    uid=uid, source_id=source_id, url=canonical_url(raw.url), title=raw.title,
                    published_at=raw.published or beijing_today(), fetched_at=now_iso(),
                    excerpt=raw.excerpt, content=content or raw.excerpt,
                    status="new", simhash=str(simhash64(raw.title)), cluster_of=cluster,
                )
                db.add(item)
                db.flush()
                fts_upsert(db, item.id, item.title, "", item.content)
                recent.append((item.id, toks))
                new += 1

            src.consecutive_failures, src.health, src.last_success_at = 0, "ok", now_iso()
            db.add(FetchLog(source_id=source_id, ok=True, http_status=res.status,
                            found=found, new=new, ms=res.ms))
            log_event("ingest.source_done", source=source_id, found=found, new=new, gated=gated, ms=res.ms)
            result.update(ok=True, found=found, new=new, gated=gated)
            return result
    except Exception as e:  # 兜底：单源任何异常不影响其他源
        log_event("ingest.source_crashed", source=source_id, error=f"{type(e).__name__}: {e}")
        result["error"] = str(e)
        return result


def _is_due(last_fetch_at: str, schedule_minutes: int) -> bool:
    if not last_fetch_at:
        return True
    try:
        last = datetime.strptime(last_fetch_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - last >= timedelta(minutes=schedule_minutes)


def run_all(only_due: bool = True) -> list[dict]:
    with session_scope() as db:
        rows = db.query(Source).filter(Source.enabled.is_(True)).all()
        todo = [s.id for s in rows
                if not only_due or _is_due(s.last_fetch_at, int((s.config or {}).get("schedule_minutes", 240)))]
    results = [run_source(sid) for sid in todo]
    log_event("ingest.run_all", sources=len(todo),
              new=sum(r["new"] for r in results), failed=sum(1 for r in results if not r["ok"]))
    return results


if __name__ == "__main__":
    import argparse
    import json

    from app.db import migrate
    from app.seeds import run_seeds
    from app.ingest.registry import sync_sources

    ap = argparse.ArgumentParser(description="手动采集")
    ap.add_argument("--source", help="只跑指定源 id")
    ap.add_argument("--all", action="store_true", help="跑全部启用源（忽略调度间隔）")
    args = ap.parse_args()

    migrate()
    run_seeds()
    with session_scope() as db:
        sync_sources(db)
    if args.source:
        out = [run_source(args.source)]
    else:
        out = run_all(only_due=not args.all)
    print(json.dumps(out, ensure_ascii=False, indent=2))
