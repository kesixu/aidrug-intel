"""情报流 / 条目详情 / 反馈 / 检索 / 政策脉络。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.common import feedback_state, item_dict, source_map
from app.db import fts_search, get_db
from app.log import log_event
from app.models import Analysis, Feedback, Item, ItemEntity

router = APIRouter(tags=["feed"])

FEEDBACK_ACTIONS = {"useful", "irrelevant", "star", "unstar", "follow_up", "unfollow", "read", "open_url"}


def _starred_ids(db: Session) -> set[int]:
    ids: set[int] = set()
    for f in db.query(Feedback).filter(Feedback.action.in_(["star", "unstar"])).order_by(Feedback.id):
        if f.action == "star":
            ids.add(f.item_id)
        else:
            ids.discard(f.item_id)
    return ids


def _followed_ids(db: Session) -> set[int]:
    ids: set[int] = set()
    for f in db.query(Feedback).filter(Feedback.action.in_(["follow_up", "unfollow"])).order_by(Feedback.id):
        if f.action == "follow_up":
            ids.add(f.item_id)
        else:
            ids.discard(f.item_id)
    return ids


@router.get("/feed")
def get_feed(
    tier: str | None = Query(None, pattern="^(red|orange|blue|gray)$"),
    category: str | None = None,
    entity_id: int | None = None,
    q: str | None = None,
    collection: str | None = Query(None, pattern="^(starred|followed|deadline)$"),
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = (db.query(Item, Analysis)
             .outerjoin(Analysis, Analysis.item_id == Item.id)
             .filter(Item.status.in_(["new", "analyzed"]), Item.cluster_of.is_(None)))
    if tier:
        query = query.filter(Analysis.tier == tier)
    if category:
        query = query.filter(Analysis.category == category)
    if entity_id:
        query = query.join(ItemEntity, ItemEntity.item_id == Item.id).filter(ItemEntity.entity_id == entity_id)
    if q:
        hit_ids = [i for i, _ in fts_search(db, q, limit=200)]
        if not hit_ids:
            return {"items": [], "next_cursor": None}
        query = query.filter(Item.id.in_(hit_ids))
    if collection == "starred":
        query = query.filter(Item.id.in_(_starred_ids(db) or {-1}))
    elif collection == "followed":
        query = query.filter(Item.id.in_(_followed_ids(db) or {-1}))
    elif collection == "deadline":
        query = query.filter(Analysis.deadline.isnot(None))

    if cursor:
        try:
            c_pub, c_id = cursor.rsplit("~", 1)
            query = query.filter(
                (Item.published_at < c_pub)
                | ((Item.published_at == c_pub) & (Item.id < int(c_id))))
        except ValueError:
            raise HTTPException(400, "cursor 格式错误")

    rows = query.order_by(Item.published_at.desc(), Item.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    smap = source_map(db)
    states = feedback_state(db, [it.id for it, _ in rows])
    items = [item_dict(it, an, smap.get(it.source_id), states[it.id]) for it, an in rows]
    next_cursor = f"{rows[-1][0].published_at}~{rows[-1][0].id}" if has_more and rows else None
    return {"items": items, "next_cursor": next_cursor}


@router.get("/items/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(404, "条目不存在")
    analysis = db.get(Analysis, item_id)
    smap = source_map(db)
    state = feedback_state(db, [item_id])[item_id]
    d = item_dict(item, analysis, smap.get(item.source_id), state, with_content=True)
    # 关联条目：同政策脉络优先，其次同实体
    related = []
    if analysis and analysis.policy_family:
        related = (db.query(Item, Analysis).join(Analysis, Analysis.item_id == Item.id)
                   .filter(Analysis.policy_family == analysis.policy_family, Item.id != item_id)
                   .order_by(Item.published_at.desc()).limit(5).all())
    if not related:
        ent_ids = [e.entity_id for e in db.query(ItemEntity).filter(ItemEntity.item_id == item_id)]
        if ent_ids:
            related = (db.query(Item, Analysis).join(Analysis, Analysis.item_id == Item.id)
                       .join(ItemEntity, ItemEntity.item_id == Item.id)
                       .filter(ItemEntity.entity_id.in_(ent_ids), Item.id != item_id,
                               Item.cluster_of.is_(None))
                       .order_by(Item.published_at.desc()).limit(5).all())
    seen: set[int] = set()
    d["related"] = []
    for it, an in related:
        if it.id not in seen:
            seen.add(it.id)
            d["related"].append({"id": it.id, "title": it.title, "published_at": it.published_at,
                                 "tier": an.tier if an else "gray"})
    return d


class FeedbackIn(BaseModel):
    action: str


@router.post("/items/{item_id}/feedback")
def post_feedback(item_id: int, body: FeedbackIn, db: Session = Depends(get_db)):
    if body.action not in FEEDBACK_ACTIONS:
        raise HTTPException(400, f"action 必须是 {sorted(FEEDBACK_ACTIONS)}")
    if db.get(Item, item_id) is None:
        raise HTTPException(404, "条目不存在")
    db.add(Feedback(item_id=item_id, action=body.action))
    db.commit()
    log_event("feedback", item=item_id, action=body.action)
    return {"ok": True, "state": feedback_state(db, [item_id])[item_id]}


@router.get("/search")
def search(q: str = Query(..., min_length=1), limit: int = Query(30, ge=1, le=100),
           db: Session = Depends(get_db)):
    hits = fts_search(db, q, limit=limit)
    if not hits:
        return {"items": []}
    order = {iid: rank for rank, (iid, _) in enumerate(hits)}
    rows = (db.query(Item, Analysis).outerjoin(Analysis, Analysis.item_id == Item.id)
            .filter(Item.id.in_(list(order)), Item.cluster_of.is_(None)).all())
    rows.sort(key=lambda r: order.get(r[0].id, 999))
    smap = source_map(db)
    states = feedback_state(db, [it.id for it, _ in rows])
    return {"items": [item_dict(it, an, smap.get(it.source_id), states[it.id]) for it, an in rows]}


@router.get("/policies/lineages")
def lineages(db: Session = Depends(get_db)):
    rows = (db.query(Item, Analysis).join(Analysis, Analysis.item_id == Item.id)
            .filter(Analysis.policy_family != "").order_by(Item.published_at.asc()).all())
    fams: dict[str, dict] = {}
    for it, an in rows:
        f = fams.setdefault(an.policy_family, {"name": an.policy_family, "stages": [], "entries": []})
        f["entries"].append({"id": it.id, "title": it.title, "date": it.published_at,
                             "stage": an.policy_stage, "tier": an.tier})
        if an.policy_stage and an.policy_stage not in f["stages"]:
            f["stages"].append(an.policy_stage)
    out = sorted(fams.values(), key=lambda f: f["entries"][-1]["date"], reverse=True)
    return {"data": out}
