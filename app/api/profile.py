"""画像 / 决策维度 / 实体关注 API。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.common import item_dict, source_map
from app.db import get_db
from app.log import log_event, now_iso
from app.models import Analysis, Entity, Item, ItemEntity, Lens, Profile

router = APIRouter(tags=["profile"])


@router.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    p = db.get(Profile, 1)
    lenses = db.query(Lens).order_by(Lens.position).all()
    return {
        "narrative": p.narrative if p else "",
        "keywords": p.keywords if p else [],
        "updated_at": p.updated_at if p else "",
        "lenses": [{"id": l.id, "name": l.name, "description": l.description,
                    "weight": l.weight, "enabled": l.enabled} for l in lenses],
    }


class ProfileIn(BaseModel):
    narrative: str | None = None
    keywords: list[str] | None = None


@router.put("/profile")
def put_profile(body: ProfileIn, db: Session = Depends(get_db)):
    p = db.get(Profile, 1)
    if p is None:
        raise HTTPException(500, "画像未初始化")
    if body.narrative is not None:
        if not body.narrative.strip():
            raise HTTPException(400, "画像不能为空")
        p.narrative = body.narrative.strip()[:3000]
    if body.keywords is not None:
        p.keywords = [k.strip() for k in body.keywords if k.strip()][:80]
    p.updated_at = now_iso()
    db.commit()
    log_event("profile.updated")
    return {"ok": True}


class LensIn(BaseModel):
    id: str
    weight: float = Field(ge=0.0, le=1.0)
    enabled: bool = True
    description: str | None = None


@router.put("/lenses")
def put_lenses(body: list[LensIn], db: Session = Depends(get_db)):
    for l_in in body:
        lens = db.get(Lens, l_in.id)
        if lens is None:
            raise HTTPException(404, f"维度 {l_in.id} 不存在")
        lens.weight = round(l_in.weight, 2)
        lens.enabled = l_in.enabled
        if l_in.description is not None:
            lens.description = l_in.description[:500]
    db.commit()
    log_event("lenses.updated", count=len(body))
    return {"ok": True}


@router.get("/entities")
def list_entities(watch: bool | None = None, q: str | None = None,
                  db: Session = Depends(get_db)):
    query = db.query(Entity)
    if watch is not None:
        query = query.filter(Entity.watch.is_(watch))
    if q:
        query = query.filter(Entity.name.contains(q))
    rows = query.order_by(Entity.watch.desc(), Entity.id).limit(200).all()
    counts = dict(db.query(ItemEntity.entity_id, func.count())
                  .group_by(ItemEntity.entity_id).all())
    return {"entities": [{"id": e.id, "name": e.name, "kind": e.kind, "watch": e.watch,
                          "aliases": e.aliases or [], "item_count": counts.get(e.id, 0)}
                         for e in rows]}


class EntityIn(BaseModel):
    name: str
    kind: str = "other"
    aliases: list[str] = []


@router.post("/entities")
def create_entity(body: EntityIn, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "名称不能为空")
    row = db.query(Entity).filter(Entity.name == name).first()
    if row is None:
        row = Entity(name=name, kind=body.kind, aliases=body.aliases, watch=True)
        db.add(row)
        db.commit()
    else:
        row.watch = True
        db.commit()
    return {"id": row.id, "name": row.name}


class WatchIn(BaseModel):
    watch: bool


@router.post("/entities/{entity_id}/watch")
def watch_entity(entity_id: int, body: WatchIn, db: Session = Depends(get_db)):
    e = db.get(Entity, entity_id)
    if e is None:
        raise HTTPException(404, "实体不存在")
    e.watch = body.watch
    db.commit()
    return {"ok": True, "watch": e.watch}


@router.get("/entities/{entity_id}/timeline")
def entity_timeline(entity_id: int, limit: int = 30, db: Session = Depends(get_db)):
    e = db.get(Entity, entity_id)
    if e is None:
        raise HTTPException(404, "实体不存在")
    rows = (db.query(Item, Analysis)
            .join(ItemEntity, ItemEntity.item_id == Item.id)
            .outerjoin(Analysis, Analysis.item_id == Item.id)
            .filter(ItemEntity.entity_id == entity_id, Item.cluster_of.is_(None))
            .order_by(Item.published_at.desc(), Item.id.desc()).limit(min(limit, 100)).all())
    smap = source_map(db)
    return {"entity": {"id": e.id, "name": e.name, "kind": e.kind, "watch": e.watch},
            "items": [item_dict(it, an, smap.get(it.source_id)) for it, an in rows]}
