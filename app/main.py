"""AI for Science 大陆情报系统 — FastAPI 后端"""
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from app.models import SessionLocal, IntelEntry, engine, Base
import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="AI for Science 大陆情报系统", version="0.1.0", lifespan=lifespan)


# ─── API Routes ────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/intel")
def list_intel(
    category: str = Query(None),
    region_tier: str = Query(None),
    min_score: int = Query(None),
    search: str = Query(None),
    status: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """列出情报条目，支持过滤和搜索"""
    db = SessionLocal()
    try:
        q = db.query(IntelEntry)
        if category:
            q = q.filter(IntelEntry.category == category)
        if region_tier:
            q = q.filter(IntelEntry.region_tier == region_tier)
        if min_score is not None:
            q = q.filter(IntelEntry.relevance_score_overall >= min_score)
        if status:
            q = q.filter(IntelEntry.user_status == status)
        if search:
            like = f"%{search}%"
            q = q.filter(
                (IntelEntry.title.contains(like))
                | (IntelEntry.original_excerpt.contains(like))
                | (IntelEntry.ai_interpretation.contains(like))
                | (IntelEntry.source_department.contains(like))
            )
        total = q.count()
        entries = (
            q.order_by(IntelEntry.date_published.desc(), IntelEntry.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {"total": total, "limit": limit, "offset": offset, "data": [e.to_dict() for e in entries]}
    finally:
        db.close()


@app.get("/api/intel/{entry_id}")
def get_intel(entry_id: str):
    db = SessionLocal()
    try:
        e = db.query(IntelEntry).filter(IntelEntry.id == entry_id).first()
        if not e:
            raise HTTPException(404, "条目不存在")
        return e.to_dict()
    finally:
        db.close()


@app.post("/api/intel")
async def create_intel(request: Request):
    body = await request.json()
    db = SessionLocal()
    try:
        # Generate ID if not provided
        if "id" not in body or not body["id"]:
            now = datetime.utcnow().strftime("%Y%m%d")
            count = db.query(IntelEntry).filter(IntelEntry.id.like(f"intel_{now}_%")).count()
            body["id"] = f"intel_{now}_{count + 1:03d}"

        entry = IntelEntry(
            id=body["id"],
            date_published=body.get("date_published", datetime.utcnow().strftime("%Y-%m-%d")),
            date_captured=body.get("date_captured", datetime.utcnow().strftime("%Y-%m-%d")),
            source_department=body.get("source_department", ""),
            source_url=body.get("source_url", ""),
            title=body.get("title", ""),
            category=body.get("category", ""),
            region_tier=body.get("region_tier", ""),
            original_excerpt=body.get("original_excerpt", ""),
            ai_interpretation=body.get("ai_interpretation", ""),
            relevance_score_overall=body.get("relevance_score", {}).get("overall", 0) if isinstance(body.get("relevance_score"), dict) else 0,
            relevance_score_az=body.get("relevance_score", {}).get("az_beijing", 0) if isinstance(body.get("relevance_score"), dict) else 0,
            relevance_score_trustpathbot=body.get("relevance_score", {}).get("trustpathbot", 0) if isinstance(body.get("relevance_score"), dict) else 0,
            relevance_score_talent=body.get("relevance_score", {}).get("talent_program", 0) if isinstance(body.get("relevance_score"), dict) else 0,
            relevance_score_funding=body.get("relevance_score", {}).get("funding_opportunity", 0) if isinstance(body.get("relevance_score"), dict) else 0,
            relevance_reasoning=body.get("relevance_reasoning", ""),
            forecast=body.get("forecast", ""),
            recommended_action=body.get("recommended_action", ""),
            follow_up_flag=body.get("follow_up_flag", False),
            related_entry_ids=body.get("related_entry_ids", []),
            policy_family=body.get("policy_family", ""),
            policy_stage=body.get("policy_stage", ""),
        )
        db.add(entry)
        db.commit()
        return {"status": "created", "id": entry.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))
    finally:
        db.close()


@app.put("/api/intel/{entry_id}")
async def update_intel(entry_id: str, request: Request):
    body = await request.json()
    db = SessionLocal()
    try:
        e = db.query(IntelEntry).filter(IntelEntry.id == entry_id).first()
        if not e:
            raise HTTPException(404, "条目不存在")

        updatable = [
            "title", "category", "region_tier", "original_excerpt", "ai_interpretation",
            "relevance_reasoning", "forecast", "recommended_action",
            "source_department", "source_url", "follow_up_flag",
            "user_note", "user_status", "policy_family", "policy_stage",
        ]
        for k in updatable:
            if k in body:
                setattr(e, k, body[k])

        if "relevance_score" in body and isinstance(body["relevance_score"], dict):
            rs = body["relevance_score"]
            e.relevance_score_overall = rs.get("overall", e.relevance_score_overall)
            e.relevance_score_az = rs.get("az_beijing", e.relevance_score_az)
            e.relevance_score_trustpathbot = rs.get("trustpathbot", e.relevance_score_trustpathbot)
            e.relevance_score_talent = rs.get("talent_program", e.relevance_score_talent)
            e.relevance_score_funding = rs.get("funding_opportunity", e.relevance_score_funding)

        if "related_entry_ids" in body:
            e.related_entry_ids = body["related_entry_ids"]

        db.commit()
        return {"status": "updated", "id": entry_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))
    finally:
        db.close()


@app.delete("/api/intel/{entry_id}")
def delete_intel(entry_id: str):
    db = SessionLocal()
    try:
        e = db.query(IntelEntry).filter(IntelEntry.id == entry_id).first()
        if not e:
            raise HTTPException(404, "条目不存在")
        db.delete(e)
        db.commit()
        return {"status": "deleted", "id": entry_id}
    finally:
        db.close()


@app.get("/api/policy-lineages")
def list_lineages():
    """列出所有政策家族及其生命周期阶段"""
    db = SessionLocal()
    try:
        entries = db.query(IntelEntry).filter(IntelEntry.policy_family != "").order_by(IntelEntry.date_published.asc()).all()
        families = {}
        for e in entries:
            fam = e.policy_family
            if fam not in families:
                families[fam] = {"name": fam, "entries": [], "stages": set()}
            families[fam]["entries"].append({"id": e.id, "title": e.title, "date": e.date_published, "stage": e.policy_stage})
            if e.policy_stage:
                families[fam]["stages"].add(e.policy_stage)
        return {"data": list(families.values())}
    finally:
        db.close()


@app.get("/api/stats")
def get_stats():
    """统计概览"""
    db = SessionLocal()
    try:
        total = db.query(IntelEntry).count()
        high_priority = db.query(IntelEntry).filter(IntelEntry.relevance_score_overall >= 4).count()
        need_followup = db.query(IntelEntry).filter(
            (IntelEntry.user_status == "需跟进") | (IntelEntry.follow_up_flag == True)
        ).count()
        by_category = {}
        for row in db.query(IntelEntry.category, IntelEntry.id).all():
            by_category[row[0]] = by_category.get(row[0], 0) + 1
        by_region = {}
        for row in db.query(IntelEntry.region_tier, IntelEntry.id).all():
            by_region[row[0]] = by_region.get(row[0], 0) + 1
        return {
            "total": total,
            "high_priority": high_priority,
            "need_followup": need_followup,
            "by_category": by_category,
            "by_region": by_region,
        }
    finally:
        db.close()


# ─── Static Files ──────────────────────────────────────────

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8010, reload=True)
