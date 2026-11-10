"""本地演示 / UI 测试夹具。只写数据库，不调用 DeepSeek。

用法（调度关闭、独立库）::

    AIDRUG_DB_PATH=/tmp/aidrug-demo.db AIDRUG_SCHEDULER_ENABLED=false \\
        python3 scripts/seed_fixture.py
"""
from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("AIDRUG_SCHEDULER_ENABLED", "false")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-fixture-not-used")


def main() -> None:
    from app.db import fts_upsert, migrate, session_scope
    from app.ingest.registry import sync_sources
    from app.log import now_iso
    from app.models import Analysis, Brief, Entity, Feedback, Item, ItemEntity
    from app.seeds import run_seeds
    from app.textutil import beijing_now, beijing_today

    migrate()
    run_seeds()
    with session_scope() as db:
        sync_sources(db)
        if db.query(Item.id).filter(Item.uid.like("fixture-%")).first():
            print("fixture already present")
            return

        today = beijing_today()
        yday = (beijing_now() - timedelta(days=1)).strftime("%Y-%m-%d")
        soon = (beijing_now() + timedelta(days=2)).strftime("%Y-%m-%d")
        later = (beijing_now() + timedelta(days=11)).strftime("%Y-%m-%d")
        fetched = now_iso()

        rows = [
            dict(n=1, src="kfqgw_zwgk", title="北京经开区发布人工智能制药专项申报指南",
                 pub=today, cat="资金申报", score=88, tier="red", deadline=soon,
                 summary="亦庄针对 AI 制药与药物安全性评价单列专项，明确材料清单与截止日，和北京小组当前要找的合作入口直接相关。",
                 hint="今天把截止日放进日历，并对照你们正在谈的本地合作方看是否够格联合申报。",
                 signal="强", family="经开区 AI 制药专项", stage="申报窗口",
                 lenses=[("az_career", 86, "亦庄专项，和北京小组的合作叙事同向"),
                         ("talent_funding", 90, "有明确截止日的申报窗口"),
                         ("china_partnership", 72, "鼓励本地企业联合申报")],
                 entities=[("北京经济技术开发区", "park"), ("阿斯利康", "company")]),
            dict(n=2, src="most_tztg", title="科技部征求人工智能赋能科学研究专项意见",
                 pub=today, cat="政策发布", score=81, tier="red", deadline=later,
                 summary="面向 AI for Science 的国家级专项进入征求意见，点名药物研发与生命科学大模型，意见截止日已写明。",
                 hint="意见稿阶段适合内部记一笔，不必现在对外表态。",
                 signal="强", family="AI for Science 专项", stage="征求意见",
                 lenses=[("industry", 84, "国家级 AI4S 专项"), ("az_career", 70, "药物研发被点名")],
                 entities=[("科技部", "agency")]),
            dict(n=3, src="bydrug", title="阿斯利康传与国内病理 AI 公司探讨联合实验室",
                 pub=yday, cat="企业动态", score=79, tier="red", deadline=None,
                 summary="媒体称阿斯利康中国在接触计算病理团队，讨论联合实验室而非单纯采购。尚无官方确认。",
                 hint="先在内部核对是否已有对接人，避免对外重复开口。",
                 signal="中", family="", stage="",
                 lenses=[("az_career", 92, "直接关系北京分支怎么定位"),
                         ("china_partnership", 80, "中国病理 AI 合作信号")],
                 entities=[("阿斯利康", "company"), ("迪英加科技", "company")]),
            dict(n=4, src="bjkw_zcwj", title="北京市科委发布算法备案与医疗人工智能合规指引",
                 pub=yday, cat="政策发布", score=74, tier="orange", deadline=later,
                 summary="市级指引把医疗 AI 的算法备案、数据出境和可解释性写进同一份操作说明，TrustPathBot 能对上的条款不少。",
                 hint="抽一页对照 TrustPathBot 现在的合规叙事，看缺口在备案还是审计。",
                 signal="中", family="", stage="",
                 lenses=[("trustpathbot", 88, "算法备案与审计要求落地"), ("settle_decision", 60, "北京合规环境更明确")],
                 entities=[("北京市科委", "agency")]),
            dict(n=5, src="vbdata", title="晶泰科技披露机器人实验室新订单，单季服务收入转正",
                 pub=yday, cat="企业动态", score=66, tier="orange", deadline=None,
                 summary="晶泰把 AI+CRO 的订单和盈利说清楚了：按项目收费，而不是靠自研管线。行业大盘的一个锚点。",
                 hint="当行业参照，不必行动。",
                 signal="中", family="", stage="",
                 lenses=[("industry", 78, "AI+CRO 商业模式被验证")],
                 entities=[("晶泰科技", "company")]),
            dict(n=6, src="govcn_library", title="国务院印发关于深化医药卫生体制改革的重点任务",
                 pub=today, cat="政策发布", score=63, tier="orange", deadline=None,
                 summary="国办文件强调创新药审评与真实世界数据，没有新的申报窗口，但给外企在华研发定了调。",
                 hint="扫一遍目录即可，和亦庄申报不是同一件事。",
                 signal="中", family="医药卫生体制改革", stage="发布",
                 lenses=[("settle_decision", 64, "外企营商环境的年度基调"), ("az_career", 58, "创新药审评节奏")],
                 entities=[("国家药监局", "agency")]),
            dict(n=7, src="beijing_zc", title="北京国际人才住房与子女入学配套办法公开征求意见",
                 pub=yday, cat="人才政策", score=61, tier="orange", deadline=later,
                 summary="面向在京外籍与海归人才的住房、入学条款进入征求意见，和定居选择有关，和研发工作无关。",
                 hint="定居决策用，标成跟进即可。",
                 signal="弱", family="", stage="",
                 lenses=[("settle_decision", 82, "北京生活配套"), ("talent_funding", 55, "人才政策")],
                 entities=[("北京市科委", "agency")]),
            dict(n=8, src="ncsti_jkq", title="亦庄生物医药园发布下一季度园区活动日历",
                 pub=today, cat="企业动态", score=52, tier="blue", deadline=None,
                 summary="园区路演与开放日安排，没有政策增量，偶尔能碰到合作方。",
                 hint="不用专门读。",
                 signal="弱", family="", stage="",
                 lenses=[("china_partnership", 48, "线下能见到本地公司")],
                 entities=[("北京经济技术开发区", "park")]),
            dict(n=9, src="iivd", title="一家 IVD 媒体转载：病理 AI 切片竞赛结果公示",
                 pub=yday, cat="企业动态", score=40, tier="gray", deadline=None,
                 summary="赛事结果转载，参赛方与你的管线工作没有交集。",
                 hint="", signal="弱", family="", stage="",
                 lenses=[("industry", 30, "行业噪音")],
                 entities=[]),
            dict(n=10, src="bjkw_zcjd", title="市科委解读海聚工程本年度申报口径",
                 pub=today, cat="人才政策", score=77, tier="red", deadline=soon,
                 summary="海聚工程今年的申报口径收窄到有雇主担保的创新岗位，截止日与经开区专项同一周。",
                 hint="如果团队里有人要办人才项目，这周内确认雇主材料。",
                 signal="强", family="海聚工程", stage="申报窗口",
                 lenses=[("talent_funding", 91, "本年度申报口径"), ("settle_decision", 70, "落户路径")],
                 entities=[("北京市科委", "agency")]),
        ]

        ids = {}
        for r in rows:
            it = Item(uid=f"fixture-{r['n']}", source_id=r["src"],
                      url=f"https://example.com/fixture/{r['n']}", title=r["title"],
                      published_at=r["pub"], fetched_at=fetched,
                      excerpt=r["summary"][:80],
                      content=r["summary"] + "\n\n这是夹具正文，用于本地阅读，不代表真实公文。",
                      status="analyzed")
            db.add(it)
            db.flush()
            db.add(Analysis(
                item_id=it.id, summary=r["summary"], category=r["cat"], event_type=r["cat"],
                importance=int(r["score"]), final_score=r["score"], tier=r["tier"],
                lens_scores=[{"lens_id": i, "score": s, "reason": why} for i, s, why in r["lenses"]],
                action_hint=r["hint"], deadline=r["deadline"], signal=r["signal"],
                policy_family=r["family"], policy_stage=r["stage"],
                entities=[{"name": n, "kind": k} for n, k in r["entities"]],
                model="fixture", analyzed_at=fetched,
            ))
            fts_upsert(db, it.id, it.title, r["summary"], it.content)
            ids[r["n"]] = it.id
            for name, _kind in r["entities"]:
                ent = db.query(Entity).filter(Entity.name == name).one_or_none()
                if ent is not None:
                    db.add(ItemEntity(item_id=it.id, entity_id=ent.id))

        db.add(Feedback(item_id=ids[3], action="star"))
        db.add(Feedback(item_id=ids[7], action="follow_up"))
        db.add(Feedback(item_id=ids[1], action="read"))

        az = db.query(Entity).filter(Entity.name == "阿斯利康").one()
        az.watch = True

        content = f"""# {today[5:7]}月{today[8:10]}日 · 三分钟

先看两件和你这周有关的事：亦庄专项和海聚工程都在 {soon} 截止；阿斯利康的联合实验室还只是传闻。

## 必读
- 经开区把 AI 制药单列成专项，材料清单已经公开。[#{ids[1]}]
- 海聚工程今年要雇主担保，和专项同一周截止。[#{ids[10]}]
- 阿斯利康接触国内病理 AI 公司的说法尚未被官方确认。[#{ids[3]}]

## 值得扫一眼
- 科技部 AI for Science 专项在征求意见，药物研发被点名。[#{ids[2]}]
- 市级算法备案指引对得上 TrustPathBot 的合规叙事。[#{ids[4]}]
- 晶泰把 AI+CRO 的服务收入说清楚了，当行业锚点即可。[#{ids[5]}]

## 今天可以不动
园区活动日历和 IVD 竞赛转载没有新的决策信息。
"""
        db.add(Brief(date=today, content_md=content.strip(), model="fixture",
                     meta={"item_ids": list(ids.values())}, created_at=fetched))
        prev = (beijing_now() - timedelta(days=1)).strftime("%Y-%m-%d")
        db.add(Brief(date=prev, content_md="# 昨日晨报\n\n没有新的必读。晶泰订单是行业参照。",
                     model="fixture", meta={}, created_at=fetched))
        print(f"seeded {len(ids)} items, brief {today}")


if __name__ == "__main__":
    main()
