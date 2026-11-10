"""首启种子与旧数据导入（幂等）。"""
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db import fts_upsert, session_scope
from app.log import log_event, now_iso
from app.models import Analysis, Entity, Item, Lens, Profile, Source
from app.textutil import simhash64, uid_for

LENS_SEEDS = [
    # v3 重构（2026-09-17）：Oliver 已入职阿斯利康 CPSS→PDS 北京分支，
    # 决策焦点从「拿到机会」转为「在岗做出差异 + 中国合作落地」。
    # 注意：az_career 的 **id 保持不变**（legacy 映射与前端印章语义依赖它），只改名称/权重/描述。
    ("az_career", "AZ CPSS·北京分支", 0.30,
     "阿斯利康 CPSS（临床药理与安全科学）/PDS 与北京亦庄研发中心动向；非临床毒理病理 AI、"
     "AI-Pathology、药物安全性评估加速；NAMs（新方法论）/器官芯片/替代动物实验相关监管与企业动态；"
     "AZ 内部与中国的合作信号（BD、产业基金、高校、医院、联合实验室）。"),
    ("china_partnership", "中国合作生态", 0.20,
     "中国 AI 病理公司（医策科技、迪英加、商汤善萃等）、类器官与器官芯片企业（大橡科技、耀速科技、"
     "伯桢生物等）、毒理病理 CRO（益诺思、昭衍等）；以及准备 license-out 的创新药企及其对"
     "「早期资产安全性数据包」的需求；人类遗传资源与数据出境合规政策变化。"),
    ("industry", "AI4S 行业大盘", 0.15,
     "AI for Science 与 AI 制药行业动态：大模型进展、算力政策、融资并购、头部公司"
     "（晶泰科技、英矽智能、深势科技、百图生科等）。"),
    ("trustpathbot", "TrustPathBot 市场", 0.15,
     "AI 可信/合规/监管科技的需求信号、医药行业数字化合规要求、AI 治理与算法备案政策落地、"
     "可解释性与审计要求。"),
    ("talent_funding", "人才与资金", 0.10,
     "人才计划（海聚工程、雏鹰计划等）、科研基金/课题申报窗口、园区补贴与租金减免，"
     "尤其是有明确截止日期的申报机会。"),
    ("settle_decision", "定居决策", 0.10,
     "宏观政策环境与外企营商环境变化、生物医药/AI 行业景气度、"
     "北京落户与国际人才生活配套（住房/教育/医疗）政策。"),
]

PROFILE_NARRATIVE = (
    "我是 Oliver，计算病理方向的 AI/ML 从业者，已入职阿斯利康北京亦庄全球研发中心，"
    "在 CPSS（临床药理与安全科学）下的 Predictive Data Science 分支做 AI-Pathology，"
    "北京小组共 4 人，向剑桥的经理汇报。\n"
    "我当前的核心任务有三条：\n"
    "① 用「临床前病理数据 + 多模态 AI」支持多条药物管线，并把药物安全性评估这个拖慢研发的环节加速；\n"
    "② 对接中国本地高校与创业公司，找到值得做、能向上汇报的合作项目（团队不熟悉中国的合作方式，需要我来 build connection）；\n"
    "③ 在团队定位尚未完全定死的窗口期，先定义问题、建立自己的不可替代位置。\n"
    "我同时仍在观察另外两条线：自研产品 TrustPathBot（AI 可信/合规方向）在大陆市场的定位与时机；"
    "以及英国 vs 中国大陆的长期定居选择。\n"
    "偏好：政策原文优先于媒体转述；重视有明确申报窗口/截止日期的机会；"
    "对亦庄、北京市级信号，以及 AI 病理/器官芯片/药物安全性监管信号敏感度最高；"
    "关注阿斯利康自身的合作动向（BD、基金、高校、联合实验室）——那是我做中国合作的入口。"
)

_PROFILE_NARRATIVE_V2 = (
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
    # v3 新增（2026-09-17）
    "CPSS", "临床药理", "安全性评价", "毒理病理", "病理", "计算病理", "多模态",
    "数字病理", "器官芯片", "类器官", "微生理系统", "NAMs", "替代动物实验",
    "license out", "对外授权", "人类遗传资源", "数据出境",
]

ENTITY_SEEDS = [  # (name, kind, aliases)
    ("阿斯利康", "company", ["AstraZeneca", "AZ", "阿斯利康中国"]),
    ("北京经济技术开发区", "park", ["亦庄", "北京亦庄", "经开区", "亦庄经开区", "北京经开区", "BDA"]),
    ("晶泰科技", "company", ["XtalPi", "晶泰"]),
    ("英矽智能", "company", ["Insilico Medicine", "英矽"]),
    ("深势科技", "company", ["DP Technology", "深势"]),
    ("百图生科", "company", ["BioMap"]),
    ("北京市科委", "agency", ["北京市科学技术委员会", "市科委", "中关村管委会"]),
    ("国家药监局", "agency", ["NMPA", "药监局"]),
    ("科技部", "agency", ["MOST", "科学技术部"]),
    # v3 新增（2026-09-17）：中国合作生态的目标对象
    ("医策科技", "company", ["杭州医策", "灵眸"]),
    ("迪英加科技", "company", ["迪英加", "DeepPathAI", "DiPath"]),
    ("商汤善萃医疗", "company", ["商汤善萃"]),
    ("大橡科技", "company", ["大橡"]),
    ("耀速科技", "company", ["Xellar Biosystems", "Xellar", "3D-Wet-AI"]),
    ("伯桢生物", "company", ["伯桢"]),
    ("和铂医药", "company", ["Harbour BioMed", "Harbour Mice"]),
    ("石药集团", "company", ["石药", "CSPC"]),
    ("上海瑞金医院", "hospital", ["瑞金医院", "RuiPath"]),
    ("清华大学", "university", ["清华", "Tsinghua"]),
    ("北京大学", "university", ["北大", "PKU", "北京大学肿瘤医院"]),
    ("复旦大学", "university", ["复旦", "Fudan"]),
    ("四川大学华西医院", "hospital", ["华西医院", "华西"]),
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
    """幂等种子。

    v3（2026-09-17）起，已存在的 lens 会被**按 seeds 重新校准**（名称/权重/描述/顺序），
    因为 LENS_SEEDS 是 Oliver 自己的决策维度配置，不是 AI 自动生成的画像。
    但 **profile 的编辑权仍归 Oliver**：关键词只做增补（不删），
    narrative 仅当它仍等于上一次的种子原文时才替换（即 Oliver 没手改过）。
    """
    refreshed = []
    for pos, (lid, name, weight, desc) in enumerate(LENS_SEEDS):
        lens = db.get(Lens, lid)
        if lens is None:
            db.add(Lens(id=lid, name=name, weight=weight, description=desc,
                        enabled=True, position=pos))
            continue
        if (lens.name, round(lens.weight, 2), lens.description, lens.position) != \
                (name, round(weight, 2), desc, pos):
            lens.name, lens.weight, lens.description, lens.position = name, weight, desc, pos
            refreshed.append(lid)

    profile = db.get(Profile, 1)
    if profile is None:
        db.add(Profile(id=1, narrative=PROFILE_NARRATIVE, keywords=PROFILE_KEYWORDS,
                       updated_at=now_iso()))
    else:
        merged = list(dict.fromkeys(list(profile.keywords or []) + PROFILE_KEYWORDS))
        if merged != (profile.keywords or []):
            profile.keywords = merged
            refreshed.append("profile.keywords")
        if (profile.narrative or "").strip() == _PROFILE_NARRATIVE_V2.strip():
            profile.narrative = PROFILE_NARRATIVE
            profile.updated_at = now_iso()
            refreshed.append("profile.narrative")

    for name, kind, aliases in ENTITY_SEEDS:
        if db.query(Entity.id).filter(Entity.name == name).first() is None:
            db.add(Entity(name=name, kind=kind, aliases=aliases, watch=True))

    if refreshed:
        log_event("seeds.lens_refresh", changed=refreshed)



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
