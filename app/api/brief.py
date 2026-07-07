"""晨报 API。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm.briefing import generate_brief
from app.models import Brief

router = APIRouter(tags=["brief"])


def _brief_dict(b: Brief) -> dict:
    return {"id": b.id, "date": b.date, "content_md": b.content_md,
            "model": b.model, "meta": b.meta or {}, "created_at": b.created_at}


@router.get("/brief/today")
def brief_today(db: Session = Depends(get_db)):
    b = db.query(Brief).order_by(Brief.date.desc()).first()
    if b is None:
        return {"brief": None}
    return {"brief": _brief_dict(b)}


@router.get("/briefs")
def brief_list(limit: int = 14, db: Session = Depends(get_db)):
    rows = db.query(Brief).order_by(Brief.date.desc()).limit(min(limit, 60)).all()
    return {"briefs": [_brief_dict(b) for b in rows]}


@router.get("/briefs/{date}")
def brief_by_date(date: str, db: Session = Depends(get_db)):
    b = db.query(Brief).filter(Brief.date == date).first()
    if b is None:
        raise HTTPException(404, "该日期无晨报")
    return {"brief": _brief_dict(b)}


@router.post("/brief/generate")
def brief_generate():
    """手动（重新）生成今日晨报。同步执行，pro 模型一般 <30s。"""
    return generate_brief(force=True)
