"""首启种子与旧数据导入（幂等）。"""
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db import fts_upsert, session_scope
from app.log import log_event, now_iso
from app.models import Analysis, Item, Lens, Profile, Source
from app.textutil import simhash64, uid_for

LENS_SEEDS = [
    ("az_career", "AZ北京·亦庄机会", 0.30,
     "AstraZeneca（阿斯利康）中国动向、北京亦庄/经开区生物医药园区政策与配套、外企在华研发投入与岗位信号。"),
    ("trustpathbot", "TrustPathBot 市场", 0.25,
     "AI 可信/合规/监管科技的需求信号、医药行业数字化合规要求、AI 治理与算法备案政策落地、可解释性与审计要求。"),
    ("talent_funding", "人才与资金", 0.20,
     "人才计划（海聚工程、雏鹰计划等）、科研基金/课题申报窗口、园区补贴与租金减免，尤其是有明确截止日期的申报机会。"),
    ("settle_decision", "定居决策", 0.15,
     "宏观政策环境与外企营商环境变化、生物医药/AI 行业景气度、北京落户与国际人才生活配套（住房/教育/医疗）政策。"),
    ("industry", "AI4S 行业大盘", 0.10,
     "AI for Science 与 AI 制药行业动态：大模型进展、算力政策、融资并购、头部公司（晶泰科技、英矽智能、深势科技、百图生科等）。"),
]

PROFILE_NARRATIVE = (
    "我是 Oliver，AI/ML 方向从业者，长期关注 AI for Science 与 AI 制药。当前正在评估三个现实决策：\n"
    "① AstraZeneca 北京（亦庄）的职业机会——关注 AZ 中国研发布局、亦庄/经开区生物医药生态；\n"
    "② 自研产品 TrustPathBot（AI 可信/合规方向）在大陆市场的定位与时机；\n"
    "③ 英国 vs 中国大陆的定居选择——关注人才政策、行业景气度与外企环境。\n"
    "偏好：政策原文优先于媒体转述；重视有明确申报窗口/截止日期的机会；对亦庄和北京市级信号敏感度最高。"
)

PROFILE_KEYWORDS = [
    "AI制药", "AI for Science", "人工智能", "生物医药", "创新药", "大模型", "医药",
    "亦庄", "经开区", "BioPark", "阿斯利康", "AstraZeneca", "药物研发",
    "人才计划", "海聚", "申报", "算力", "合规", "监管", "算法备案",
    "晶泰", "英矽", "深势", "百图生科", "融资", "临床试验", "药监",
]

_LEGACY_LENS_MAP = {  # v0.1 五维(0-5) → v2 lens(0-100)
    "az_beijing": "az_career",
    "trustpathbot": "trustpathbot",
    "talent_program": "talent_funding",
    "funding_opportunity": "talent_funding",
}


def _tier_for(score: float) -> str:
    if score >= 75:
        return "red"
    if score >= 60:
        return "orange"
    if score >= 45:
        return "blue"
    return "gray"


def seed_lenses_profile(db: Session) -> None:
    for pos, (lid, name, weight, desc) in enumerate(LENS_SEEDS):
        if db.get(Lens, lid) is None:
            db.add(Lens(id=lid, name=name, weight=weight, description=desc, enabled=True, position=pos))
    if db.get(Profile, 1) is None:
        db.add(Profile(id=1, narrative=PROFILE_NARRATIVE, keywords=PROFILE_KEYWORDS, updated_at=now_iso()))


def import_legacy(db: Session) -> int:
    """把 v0.1 intel_entries 导入 items+analyses（按 URL 去重，幂等）。"""
    if not inspect(db.get_bind()).has_table("intel_entries"):
        return 0
    if db.get(Source, "legacy") is None:
        db.add(Source(id="legacy", name="v0.1 手工导入", tier=2, kind="manual",
                      enabled=False, health="disabled", note="历史数据来源"))
    rows = db.execute(text("SELECT * FROM intel_entries")).mappings().all()
    imported = 0
    for r in rows:
        uid = uid_for(r["source_url"] or f"legacy://{r['id']}")
        if db.query(Item.id).filter(Item.uid == uid).first():
            continue
        item = Item(
            uid=uid, source_id="legacy", url=r["source_url"] or "",
            title=r["title"] or "", published_at=r["date_published"] or "",
            fetched_at=now_iso(), excerpt=r["original_excerpt"] or "",
            content=r["original_excerpt"] or "", status="analyzed",
            simhash=str(simhash64(r["title"] or "")),
        )
        db.add(item)
        db.flush()
        overall = int(r["relevance_score_overall"] or 0) * 20
        lens_scores = []
        for old_key, lens_id in _LEGACY_LENS_MAP.items():
            val = int(r[_legacy_col(old_key)] or 0) * 20
            existing = next((s for s in lens_scores if s["lens_id"] == lens_id), None)
            if existing:
                existing["score"] = max(existing["score"], val)
            else:
                lens_scores.append({"lens_id": lens_id, "score": val,
                                    "reason": (r["relevance_reasoning"] or "")[:200]})
        db.add(Analysis(
            item_id=item.id, summary=r["ai_interpretation"] or "", category=r["category"] or "其他",
            importance=overall, final_score=float(overall), tier=_tier_for(overall),
            lens_scores=lens_scores, action_hint=r["recommended_action"] or "",
            policy_family=r["policy_family"] or "", policy_stage=r["policy_stage"] or "",
            entities=[], model="legacy-import", analyzed_at=now_iso(),
        ))
        fts_upsert(db, item.id, item.title, r["ai_interpretation"] or "", item.content)
        imported += 1
    return imported


def _legacy_col(key: str) -> str:
    return {
        "az_beijing": "relevance_score_az",
        "trustpathbot": "relevance_score_trustpathbot",
        "talent_program": "relevance_score_talent",
        "funding_opportunity": "relevance_score_funding",
    }[key]


def run_seeds() -> None:
    with session_scope() as db:
        seed_lenses_profile(db)
        n = import_legacy(db)
    if n:
        log_event("seeds.legacy_imported", count=n)
