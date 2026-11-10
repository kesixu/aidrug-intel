"""API 共用序列化与反馈状态推导。"""
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import Analysis, Feedback, Item, Source


def feedback_state(db: Session, item_ids: list[int]) -> dict[int, dict]:
    """按时间回放反馈事件推导每条的用户状态。"""
    state: dict[int, dict] = defaultdict(lambda: {"starred": False, "followed": False,
                                                  "read": False, "voted": ""})
    if not item_ids:
        return state
    rows = (db.query(Feedback).filter(Feedback.item_id.in_(item_ids))
            .order_by(Feedback.id).all())
    for f in rows:
        s = state[f.item_id]
        if f.action == "star":
            s["starred"] = True
        elif f.action == "unstar":
            s["starred"] = False
        elif f.action == "follow_up":
            s["followed"] = True
        elif f.action == "unfollow":
            s["followed"] = False
        elif f.action == "read":
            s["read"] = True
        elif f.action in ("useful", "irrelevant"):
            s["voted"] = f.action
    return state


def source_map(db: Session) -> dict[str, Source]:
    return {s.id: s for s in db.query(Source).all()}


def item_dict(item: Item, analysis: Analysis | None, src: Source | None,
              state: dict | None = None, with_content: bool = False) -> dict:
    d = {
        "id": item.id,
        "title": item.title,
        "url": item.url,
        "source": {"id": item.source_id,
                   "name": src.name if src else item.source_id,
                   "tier": src.tier if src else 3},
        "published_at": item.published_at,
        "fetched_at": item.fetched_at,
        "status": item.status,
        "analysis": None,
    }
    if analysis is not None:
        d["analysis"] = {
            "summary": analysis.summary,
            "category": analysis.category,
            "event_type": analysis.event_type,
            "importance": analysis.importance,
            "final_score": analysis.final_score,
            "tier": analysis.tier,
            "lens_scores": analysis.lens_scores or [],
            "action_hint": analysis.action_hint,
            "deadline": analysis.deadline,
            "signal": analysis.signal,
            "policy_family": analysis.policy_family,
            "policy_stage": analysis.policy_stage,
            "entities": analysis.entities or [],
        }
    if state is not None:
        d["user"] = state
    if with_content:
        d["excerpt"] = item.excerpt
        d["content_preview"] = (item.content or "")[:1500]
    return d
