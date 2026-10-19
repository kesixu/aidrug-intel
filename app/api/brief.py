"""晨报 API。"""
import threading

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm.briefing import generate_brief
from app.log import log_event, now_iso
from app.models import Brief

router = APIRouter(tags=["brief"])

# 手动生成在后台跑、前端轮询状态：开思考约 30s，服务端排队时更久，同步执行会撞 nginx 60s 变成 504
_gen = {"running": False, "started_at": None, "finished_at": None, "result": None, "error": None}
_gen_lock = threading.Lock()


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


def _generate_in_background() -> None:
    result = error = None
    try:
        result = generate_brief(force=True)
    except Exception as e:  # 后台任务的异常没人接，必须落进状态
        error = f"{type(e).__name__}: {e}"
        log_event("brief.generate_error", error=error)
    finally:
        _gen.update(running=False, finished_at=now_iso(), result=result, error=error)


@router.post("/brief/generate")
def brief_generate(background: BackgroundTasks):
    """手动（重新）生成今日晨报：立即返回，进度看 /brief/generate/status。已在生成时不重复启动。"""
    with _gen_lock:
        if not _gen["running"]:
            _gen.update(running=True, started_at=now_iso(), finished_at=None, result=None, error=None)
            background.add_task(_generate_in_background)
        return dict(_gen)


@router.get("/brief/generate/status")
def brief_generate_status():
    return dict(_gen)
