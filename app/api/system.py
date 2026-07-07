"""系统状态 / 源管理 / 手动任务 / 进化 API。"""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm.analyst import analyze_pending
from app.llm.evolver import apply_suggestion, run_evolution
from app.log import log_event, now_iso
from app.models import (Analysis, EvolutionRun, FetchLog, Item, LlmUsage,
                        Source, Suggestion)

router = APIRouter(tags=["system"])


@router.get("/system/status")
def system_status(db: Session = Depends(get_db)):
    from app.scheduler import job_overview  # 延迟导入避免环
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    month_utc = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00Z")
    items_total = db.query(func.count(Item.id)).scalar() or 0
    by_status = dict(db.query(Item.status, func.count()).group_by(Item.status).all())
    by_tier = dict(db.query(Analysis.tier, func.count()).group_by(Analysis.tier).all())
    new_today = db.query(func.count(Item.id)).filter(Item.fetched_at >= today_utc).scalar() or 0
    usage_today = db.query(func.coalesce(func.sum(LlmUsage.cost_est), 0.0)).filter(LlmUsage.ts >= today_utc).scalar()
    usage_month = db.query(func.coalesce(func.sum(LlmUsage.cost_est), 0.0)).filter(LlmUsage.ts >= month_utc).scalar()
    calls_month = db.query(func.count(LlmUsage.id)).filter(LlmUsage.ts >= month_utc).scalar() or 0
    sources = db.query(Source).all()
    health = {"ok": 0, "degraded": 0, "down": 0, "disabled": 0, "unknown": 0}
    for s in sources:
        health[s.health if s.health in health else "unknown"] += 1
    return {
        "version": "1.0",
        "items": {"total": items_total, "by_status": by_status, "by_tier": by_tier,
                  "new_today": new_today},
        "sources": health,
        "llm": {"cost_today": round(usage_today or 0, 4), "cost_month": round(usage_month or 0, 4),
                "calls_month": calls_month, "currency": "CNY(估算)"},
        "scheduler": job_overview(),
        "server_time_utc": now_iso(),
    }


@router.get("/system/sources")
def list_sources(db: Session = Depends(get_db)):
    rows = db.query(Source).order_by(Source.tier, Source.id).all()
    counts = dict(db.query(Item.source_id, func.count()).group_by(Item.source_id).all())
    last_logs = {}
    for lg in db.query(FetchLog).order_by(FetchLog.id.desc()).limit(300):
        last_logs.setdefault(lg.source_id, {"ok": lg.ok, "found": lg.found, "new": lg.new,
                                            "error": lg.error, "ts": lg.ts, "ms": lg.ms})
    return {"sources": [{
        "id": s.id, "name": s.name, "tier": s.tier, "kind": s.kind, "url": s.url,
        "enabled": s.enabled, "health": s.health, "note": s.note,
        "last_fetch_at": s.last_fetch_at, "last_success_at": s.last_success_at,
        "consecutive_failures": s.consecutive_failures,
        "item_count": counts.get(s.id, 0), "last_run": last_logs.get(s.id),
        "schedule_minutes": (s.config or {}).get("schedule_minutes", 240),
    } for s in rows]}


@router.post("/system/sources/{source_id}/fetch")
def fetch_source(source_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    from app.ingest.pipeline import run_source
    src = db.get(Source, source_id)
    if src is None:
        raise HTTPException(404, "源不存在")
    result = run_source(source_id)
    if result.get("new"):
        background.add_task(analyze_pending)
    return result


@router.post("/system/ingest")
def ingest_all(background: BackgroundTasks):
    """手动全量抓取（忽略调度间隔），随后后台补分析。"""
    from app.ingest.pipeline import run_all
    results = run_all(only_due=False)
    background.add_task(analyze_pending)
    return {"results": results, "analyzing": True}


@router.post("/system/analyze")
def analyze_now():
    return analyze_pending()


@router.get("/evolution/log")
def evolution_log(db: Session = Depends(get_db)):
    runs = db.query(EvolutionRun).order_by(EvolutionRun.id.desc()).limit(10).all()
    out = []
    for r in runs:
        sugs = db.query(Suggestion).filter(Suggestion.run_id == r.id).order_by(Suggestion.id).all()
        out.append({"id": r.id, "ran_at": r.ran_at, "status": r.status, "report_md": r.report_md,
                    "suggestions": [{"id": s.id, "kind": s.kind, "payload": s.payload,
                                     "reason": s.reason, "status": s.status} for s in sugs]})
    return {"runs": out}


@router.post("/evolution/run")
def evolution_run():
    return run_evolution()


@router.post("/evolution/suggestions/{sug_id}/{decision}")
def decide_suggestion(sug_id: int, decision: str, db: Session = Depends(get_db)):
    if decision not in ("accept", "reject"):
        raise HTTPException(400, "decision 必须是 accept 或 reject")
    sug = db.get(Suggestion, sug_id)
    if sug is None:
        raise HTTPException(404, "建议不存在")
    if sug.status != "pending":
        raise HTTPException(409, f"建议已处理（{sug.status}）")
    detail = ""
    if decision == "accept":
        detail = apply_suggestion(db, sug)
        sug.status = "accepted"
    else:
        sug.status = "rejected"
    sug.decided_at = now_iso()
    db.commit()
    log_event("evolve.decided", suggestion=sug_id, decision=decision)
    return {"ok": True, "detail": detail}
