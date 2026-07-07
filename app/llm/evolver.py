"""每周自进化：复盘反馈与内容分布 → 生成报告 + 可采纳的调整建议。

原则：建议只入 pending 队列，用户在「我的→进化日志」一键采纳/拒绝，绝不静默改画像。
"""
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.db import session_scope
from app.llm.client import LlmBadOutput, LlmError, chat_json
from app.log import log_event, now_iso
from app.models import (Analysis, Entity, EvolutionRun, Feedback, Item, Lens,
                        Profile, Suggestion)

LOOKBACK_DAYS = 14
SUGGESTION_KINDS = {"keyword_add", "keyword_remove", "weight", "entity_watch", "narrative_append"}


def _gather(db: Session) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fb_rows = (db.query(Feedback, Item, Analysis)
               .join(Item, Item.id == Feedback.item_id)
               .outerjoin(Analysis, Analysis.item_id == Item.id)
               .filter(Feedback.created_at >= cutoff,
                       Feedback.action.in_(["useful", "irrelevant", "star", "follow_up"]))
               .order_by(Feedback.id.desc()).limit(120).all())
    fb_lines = [f"- [{fb.action}] ({an.tier if an else '?'} {an.final_score if an else '?'}) "
                f"{an.category if an else '未分析'}《{it.title[:40]}》"
                for fb, it, an in fb_rows]
    tier_dist = Counter(t for (t,) in db.query(Analysis.tier)
                        .join(Item, Item.id == Analysis.item_id)
                        .filter(Item.fetched_at >= cutoff).all())
    cat_dist = Counter(c for (c,) in db.query(Analysis.category)
                       .join(Item, Item.id == Analysis.item_id)
                       .filter(Item.fetched_at >= cutoff).all())
    profile = db.get(Profile, 1)
    lenses = db.query(Lens).order_by(Lens.position).all()
    watched = [e.name for e in db.query(Entity).filter(Entity.watch.is_(True)).all()]
    return {
        "fb_lines": fb_lines,
        "tier_dist": dict(tier_dist),
        "cat_dist": dict(cat_dist.most_common(10)),
        "narrative": profile.narrative if profile else "",
        "keywords": profile.keywords if profile else [],
        "lenses": [{"id": l.id, "name": l.name, "weight": l.weight, "enabled": l.enabled} for l in lenses],
        "watched": watched,
    }


def run_evolution() -> dict:
    with session_scope() as db:
        g = _gather(db)
    system = f"""你是「见微」情报系统的自进化模块。基于用户过去两周的反馈行为和内容分布，评估当前配置是否需要微调。

# 当前配置
画像：{g['narrative']}
门控关键词：{g['keywords']}
决策维度权重：{g['lenses']}
关注实体：{g['watched']}

# 输出
只输出一个 JSON 对象：
- report_md: Markdown 复盘报告（≤300字）：本期信号质量如何、反馈说明了什么倾向、为什么给出这些建议（若无反馈，基于内容分布评估门控与维度覆盖是否合理）
- suggestions: 数组，0-5 条，每条 {{"kind": "...", "payload": {{...}}, "reason": "一句话"}}
  - kind=keyword_add，payload={{"keyword": "..."}}：门控漏掉了用户关心的主题时
  - kind=keyword_remove，payload={{"keyword": "..."}}：某关键词持续引入无关条目时
  - kind=weight，payload={{"lens_id": "...", "weight": 0.05-0.5}}：反馈显示某维度权重明显失衡时
  - kind=entity_watch，payload={{"name": "...", "kind": "company|agency|park|program"}}：反复出现且用户关注的新实体
  - kind=narrative_append，payload={{"text": "..."}}：画像缺失的重要偏好（≤50字）

保守原则：证据不足就少建议或不建议，宁缺毋滥。"""
    user = ("【近两周反馈】\n" + ("\n".join(g["fb_lines"]) if g["fb_lines"] else "（无显式反馈）")
            + f"\n\n【分级分布】{g['tier_dist']}\n【分类分布】{g['cat_dist']}")
    try:
        raw = chat_json([{"role": "system", "content": system}, {"role": "user", "content": user}],
                        model=settings.deepseek_model_pro, purpose="evolve",
                        temperature=0.3, max_tokens=1800)
    except (LlmError, LlmBadOutput) as e:
        with session_scope() as db:
            db.add(EvolutionRun(report_md=f"进化任务失败：{e}", status="failed"))
        return {"ok": False, "error": str(e)}

    report = str(raw.get("report_md") or "")[:4000]
    sugs = []
    for s in (raw.get("suggestions") or [])[:5]:
        if s.get("kind") in SUGGESTION_KINDS and isinstance(s.get("payload"), dict):
            sugs.append(s)
    with session_scope() as db:
        run = EvolutionRun(report_md=report, status="ok")
        db.add(run)
        db.flush()
        for s in sugs:
            db.add(Suggestion(run_id=run.id, kind=s["kind"], payload=s["payload"],
                              reason=str(s.get("reason") or "")[:300]))
        rid = run.id
    log_event("evolve.done", run=rid, suggestions=len(sugs))
    return {"ok": True, "run_id": rid, "suggestions": len(sugs)}


def apply_suggestion(db: Session, sug: Suggestion) -> str:
    """采纳建议 → 实际改配置。返回人话描述。"""
    p = sug.payload or {}
    profile = db.get(Profile, 1)
    if sug.kind == "keyword_add":
        kw = str(p.get("keyword") or "").strip()
        if kw and kw not in (profile.keywords or []):
            profile.keywords = (profile.keywords or []) + [kw]
            profile.updated_at = now_iso()
        return f"已添加门控关键词「{kw}」"
    if sug.kind == "keyword_remove":
        kw = str(p.get("keyword") or "").strip()
        profile.keywords = [k for k in (profile.keywords or []) if k != kw]
        profile.updated_at = now_iso()
        return f"已移除门控关键词「{kw}」"
    if sug.kind == "weight":
        lens = db.get(Lens, str(p.get("lens_id") or ""))
        if lens is None:
            return "维度不存在，未生效"
        w = float(p.get("weight") or lens.weight)
        lens.weight = max(0.05, min(0.5, round(w, 2)))
        return f"已把「{lens.name}」权重调整为 {lens.weight}"
    if sug.kind == "entity_watch":
        name = str(p.get("name") or "").strip()
        if not name:
            return "实体名为空，未生效"
        row = db.query(Entity).filter(Entity.name == name).first()
        if row is None:
            row = Entity(name=name, kind=str(p.get("kind") or "other"))
            db.add(row)
        row.watch = True
        return f"已关注实体「{name}」"
    if sug.kind == "narrative_append":
        text = str(p.get("text") or "").strip()[:100]
        if text:
            profile.narrative = f"{profile.narrative}\n{text}"
            profile.updated_at = now_iso()
        return "已追加画像描述"
    return "未知建议类型"
