"""AI 分析师：拿着用户画像逐条深读，输出结构化分析并做个性化加权评分。

评分模型：final = 0.55·个性化(维度加权) + 0.25·行业重要性 + 0.20·来源权威度
分级：≥75 🔴必读  ≥60 🟠关注  ≥45 🔵扫一眼  <45 ⚪归档
"""
import re
import threading

from app.config import settings
from app.db import fts_upsert, session_scope
from app.llm.client import LlmBadOutput, LlmError, chat_json
from app.log import log_event, now_iso
from app.models import Analysis, Entity, Item, ItemEntity, Lens, Profile, Source

CATEGORIES = ["政策发布", "实施细则", "资金申报", "人才政策", "监管动态",
              "企业动态", "融资并购", "学术前沿", "产业数据", "其他"]
_AUTHORITY = {1: 100, 2: 88, 3: 65}
# 采集 tick、补分析 tick、晨报任务和手动 API 会同时触发补分析；不互斥时两个线程会把同一批条目各分析一遍
# （llm_usage 里有 71 对重复调用）。uvicorn 单 worker（见 AGENTS.md），进程内锁即可。
_batch_lock = threading.Lock()
_MAX_TRANSPORT_FAILS = 3  # 连续几条传输失败就收工，别让一轮在服务端排队时挨个耗满总时限


def source_authority(tier: int) -> int:
    return _AUTHORITY.get(tier, 50)


def tier_for(score: float) -> str:
    if score >= 75:
        return "red"
    if score >= 60:
        return "orange"
    if score >= 45:
        return "blue"
    return "gray"


def compute_final(lens_scores: list[dict], lenses: dict[str, "Lens"],
                  importance: int, authority: int) -> float:
    weighted, wsum = 0.0, 0.0
    for ls in lens_scores:
        lens = lenses.get(ls.get("lens_id"))
        if lens is None or not lens.enabled:
            continue
        weighted += float(ls.get("score") or 0) * lens.weight
        wsum += lens.weight
    personal = weighted / wsum if wsum > 0 else 0.0
    return round(0.55 * personal + 0.25 * float(importance) + 0.20 * float(authority), 1)


def build_messages(item: Item, source: Source | None, profile: Profile,
                   lenses: list[Lens]) -> list[dict]:
    lens_lines = "\n".join(
        f"- {l.id} «{l.name}»：{l.description}" for l in lenses if l.enabled
    )
    system = f"""你是「见微」，用户的私人情报分析师，专注中国大陆 AI for Science / 生物医药领域的政策与产业情报。你的职责：读一条情报，判断它对用户意味着什么。

# 用户画像
{profile.narrative}

# 决策维度（逐一打分 0-100：0-19 无关，20-49 背景相关，50-74 直接相关，75-100 重大影响）
{lens_lines}

# 输出
只输出一个 JSON 对象，字段如下（全部必填）：
- summary: 中文摘要，恰好两句话：第一句说清发生了什么，第二句给关键细节（金额/日期/适用对象）
- category: 严格从这些值中选一个：{" | ".join(CATEGORIES)}
- event_type: 2-6 字事件类型，如 征求意见、资金申报、园区签约、产品发布、临床进展
- importance: 0-100 整数，对中国 AI4S/生物医药行业的客观重要性（与用户无关的客观判断）
- lens_scores: 数组，每个决策维度一项 {{"lens_id": "...", "score": 0-100, "reason": "一句话理由"}}
- entities: 数组，最多 8 个 {{"name": "规范名称", "kind": "company|agency|park|program|person|other"}}
- action_hint: 用户应该做的具体动作一句话（如"7月20日前提交XX申报"），没有则空字符串
- deadline: 文中明确的申报/征求意见/报名截止日期，格式 YYYY-MM-DD，没有则 null
- signal: "强"|"中"|"弱" —— 该信息作为决策信号的确定性
- policy_family: 若属于可追踪的政策脉络给出简短家族名（如"北京AI赋能科研2026"），否则空字符串
- policy_stage: 征求意见|发布|解读|配套细则|申报窗口|结果公示 之一，非政策类为空字符串

注意：媒体源可能夸大，打分要保守；政府原文的申报类信息重点抽取时间窗口。"""

    src_name = source.name if source else item.source_id
    src_tier = source.tier if source else 3
    user = (f"【标题】{item.title}\n"
            f"【来源】{src_name}（Tier {src_tier}）\n"
            f"【发布日期】{item.published_at}\n"
            f"【正文】\n{(item.content or item.excerpt or '（无正文，仅标题）')[:settings.content_max_chars]}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _link_entities(db, item_id: int, raw_entities: list) -> None:
    seen_ids = set()
    for ent in (raw_entities or [])[:8]:
        if not isinstance(ent, dict):
            continue
        name = str(ent.get("name") or "").strip()
        if not name or len(name) > 60:
            continue
        row = db.query(Entity).filter(Entity.name == name).first()
        if row is None:
            for cand in db.query(Entity).all():
                if name in (cand.aliases or []):
                    row = cand
                    break
        if row is None:
            row = Entity(name=name, kind=ent.get("kind") or "other")
            db.add(row)
            db.flush()
        if row.id not in seen_ids:
            db.merge(ItemEntity(item_id=item_id, entity_id=row.id))
            seen_ids.add(row.id)


def _clamp100(v) -> int:
    try:
        return max(0, min(100, int(float(v or 0))))
    except (TypeError, ValueError):
        return 0


def _normalize(raw: dict, lenses: list[Lens]) -> dict:
    """把模型输出钳制到合法范围，缺失维度补 0 分。字段类型不对也只降级、不抛异常（否则整批分析中断）。"""
    out = dict(raw)
    out["summary"] = str(raw.get("summary") or "")[:600]
    out["category"] = raw.get("category") if raw.get("category") in CATEGORIES else "其他"
    out["importance"] = _clamp100(raw.get("importance"))
    known = {l.id for l in lenses}
    scores, got = [], set()
    raw_scores = raw.get("lens_scores")
    for ls in raw_scores if isinstance(raw_scores, list) else []:
        if not isinstance(ls, dict):
            continue
        lid = ls.get("lens_id")
        if lid in known and lid not in got:
            scores.append({"lens_id": lid,
                           "score": _clamp100(ls.get("score")),
                           "reason": str(ls.get("reason") or "")[:200]})
            got.add(lid)
    for lid in known - got:
        scores.append({"lens_id": lid, "score": 0, "reason": ""})
    out["lens_scores"] = scores
    out["signal"] = raw.get("signal") if raw.get("signal") in ("强", "中", "弱") else "中"
    dl = raw.get("deadline")
    out["deadline"] = dl if isinstance(dl, str) and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", dl) else None
    for k in ("event_type", "action_hint", "policy_family", "policy_stage"):
        out[k] = str(raw.get(k) or "")[:200]
    ents = raw.get("entities")
    out["entities"] = [e for e in ents if isinstance(e, dict)][:8] if isinstance(ents, list) else []
    return out


def _analyze_one(item_id: int) -> str:
    """分析单条（独立事务）。返回 ok / skip / transport（保持 new，下轮重试）/ bad（已标 failed）。"""
    with session_scope() as db:
        item = db.get(Item, item_id)
        if item is None or item.status != "new":
            return "skip"
        if item.cluster_of is not None:  # 同事件重复条目不重复分析
            item.status = "analyzed"
            return "ok"
        profile = db.get(Profile, 1)
        lenses = db.query(Lens).order_by(Lens.position).all()
        source = db.get(Source, item.source_id)
        messages = build_messages(item, source, profile, lenses)
        raw = None
        for attempt in (1, 2):  # 坏输出多是偶发（空 JSON、未转义引号、截断），先当场重试一次再判死
            try:
                raw = chat_json(messages, model=settings.deepseek_model_flash, purpose="analyze")
                break
            except LlmError:
                return "transport"
            except LlmBadOutput as e:
                log_event("analyst.bad_output", item=item_id, attempt=attempt, error=str(e)[:200])
        if raw is None:
            item.status = "failed"
            return "bad"
        a = _normalize(raw, lenses)
        authority = source_authority(source.tier if source else 3)
        final = compute_final(a["lens_scores"], {l.id: l for l in lenses}, a["importance"], authority)
        db.merge(Analysis(
            item_id=item.id, summary=a["summary"], category=a["category"],
            event_type=a["event_type"], importance=a["importance"],
            final_score=final, tier=tier_for(final), lens_scores=a["lens_scores"],
            action_hint=a["action_hint"], deadline=a["deadline"], signal=a["signal"],
            policy_family=a["policy_family"], policy_stage=a["policy_stage"],
            entities=a.get("entities") or [], model=settings.deepseek_model_flash,
            analyzed_at=now_iso(),
        ))
        _link_entities(db, item.id, a.get("entities"))
        item.status = "analyzed"
        fts_upsert(db, item.id, item.title, a["summary"], item.content or "")
        return "ok"


def analyze_item(item_id: int) -> bool:
    """分析单条。返回是否成功。"""
    return _analyze_one(item_id) == "ok"


def analyze_pending(limit: int | None = None, wait: float = 0) -> dict:
    """批量补分析（新→旧）。同一时刻只跑一批：已有批次在跑时 wait=0 直接跳过，wait>0 最多等这么多秒。"""
    if not (_batch_lock.acquire(timeout=wait) if wait > 0 else _batch_lock.acquire(blocking=False)):
        log_event("analyst.batch_skipped", reason="busy")
        return {"requested": 0, "ok": 0, "failed": 0, "busy": True}
    try:
        limit = limit or settings.analyze_batch_limit
        with session_scope() as db:
            ids = [i for (i,) in db.query(Item.id).filter(Item.status == "new")
                   .order_by(Item.id.desc()).limit(limit).all()]
        ok = failed = streak = 0
        for iid in ids:
            res = _analyze_one(iid)
            if res == "ok":
                ok += 1
            else:
                failed += 1
            streak = streak + 1 if res == "transport" else 0
            if streak >= _MAX_TRANSPORT_FAILS:
                log_event("analyst.batch_aborted", reason="transport", after=ok + failed)
                break
        if ids:
            log_event("analyst.batch_done", requested=len(ids), ok=ok, failed=failed)
        return {"requested": len(ids), "ok": ok, "failed": failed}
    finally:
        _batch_lock.release()


def analyst_busy() -> bool:
    return _batch_lock.locked()


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(analyze_pending(), ensure_ascii=False))
