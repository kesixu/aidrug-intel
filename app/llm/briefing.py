"""每日晨报：v4-pro 把 24h 高分条目综合成 3 分钟可读完的简报。"""
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db import session_scope
from app.llm.client import LlmError, chat_text
from app.log import log_event, now_iso
from app.models import Analysis, Brief, Item, Lens, Profile
from app.textutil import beijing_today

BRIEF_ITEM_POOL = 25


def _collect(db) -> tuple[list, list]:
    """晨报素材：近36h新分析条目（分数降序）+ 未过期的临期提醒。"""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = (db.query(Item, Analysis).join(Analysis, Analysis.item_id == Item.id)
            .filter(Item.fetched_at >= cutoff, Item.cluster_of.is_(None),
                    Analysis.tier.in_(["red", "orange", "blue"]))
            .order_by(Analysis.final_score.desc()).limit(BRIEF_ITEM_POOL).all())
    today = beijing_today()
    horizon = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
    deadlines = (db.query(Item, Analysis).join(Analysis, Analysis.item_id == Item.id)
                 .filter(Analysis.deadline.isnot(None), Analysis.deadline >= today,
                         Analysis.deadline <= horizon)
                 .order_by(Analysis.deadline.asc()).limit(10).all())
    return rows, deadlines


def _fallback_md(date: str, n_new: int) -> str:
    return (f"# 见微晨报 · {date}\n\n今日无达到关注阈值的新情报"
            f"（新入库 {n_new} 条，均为低相关）。系统持续监控中。\n")


def _low_signal_md(date: str, n_new: int, n_candidates: int) -> str:
    """有候选条目但全部未达阈值——必须与"完全无新条目"区分开。

    原缺陷：两种情况共用 _fallback_md，导致连续多日 model='none' 的空晨报
    （现场：2026-10-02 ~ 10-06 连续 5 天）无人察觉。
    """
    return (f"# 见微晨报 · {date}\n\n"
            f"今日新入库 {n_new} 条，其中 {n_candidates} 条进入候选池，"
            f"但均未达到关注阈值。无值得单独提示的进展。\n\n"
            f"> 若连续多日如此，请检查采集源是否停摆或门控关键词是否过窄。\n")


def generate_brief(force: bool = False) -> dict:
    date = beijing_today()
    with session_scope() as db:
        existing = db.query(Brief).filter(Brief.date == date).first()
        if existing and not force:
            return {"date": date, "created": False, "id": existing.id}

        rows, deadlines = _collect(db)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M:%SZ")
        n_new = db.query(Item).filter(Item.fetched_at >= cutoff).count()

        if not rows:
            # 区分两种空态：候选池为空 vs 候选池非空但全被阈值挡掉
            n_cand = (db.query(Item, Analysis).join(Analysis, Analysis.item_id == Item.id)
                      .filter(Item.fetched_at >= cutoff, Item.cluster_of.is_(None),
                              Analysis.tier.in_(["red", "orange", "blue"])).count())
            if n_cand:
                content = _low_signal_md(date, n_new, n_cand)
                model = "low-signal"
            else:
                content = _fallback_md(date, n_new)
                model = "none"
            meta = {"item_ids": [], "deadlines": [], "n_new": n_new, "candidates": n_cand}
            log_event("brief.low_signal" if n_cand else "brief.empty",
                      date=date, n_new=n_new, candidates=n_cand)
        else:
            profile = db.get(Profile, 1)
            lens_names = {l.id: l.name for l in db.query(Lens).all()}
            lines = []
            for it, an in rows:
                top = sorted(an.lens_scores or [], key=lambda s: -s["score"])[:2]
                lens_txt = "；".join(f"{lens_names.get(s['lens_id'], s['lens_id'])}{s['score']}分:{s['reason']}"
                                    for s in top if s["score"] >= 40)
                lines.append(f"[#{it.id}] ({an.tier}/{an.final_score}) {it.published_at}《{it.title}》"
                             f"——{an.summary} {('｜' + lens_txt) if lens_txt else ''}"
                             f"{('｜行动:' + an.action_hint) if an.action_hint else ''}")
            dl_lines = [f"[#{it.id}] {an.deadline} 截止：{it.title}" for it, an in deadlines]
            system = f"""你是「见微」，用户的私人情报分析师。基于给定素材写今天（{date}）的晨报，Markdown 格式，让用户 3 分钟读完就知道"今天有什么、跟我有什么关系、要做什么"。

# 用户画像
{profile.narrative}

# 硬性要求
- 结构：先一行"总览"（≤40字），然后「## 🔴 今日必读」（1-3条，每条给两行：一行讲清事实，一行讲"对你意味着什么/建议动作"）、「## 📋 政策雷达」和「## 🏢 企业与市场」（各≤4条，每条一行）、「## ⏰ 临期提醒」（若有）、「## 🔬 弱信号」（0-2条，值得留意的苗头）。
- 引用条目一律用 [#数字] 格式（数字=条目id，已在素材中给出），放在相应句子末尾。
- 无内容的板块直接省略。不要编造素材之外的信息。语气冷静专业，不用感叹号。
- 全文 ≤600 字。标题用「# 见微晨报 · {date}」。"""
            user = "【素材条目】\n" + "\n".join(lines) + ("\n\n【临期截止】\n" + "\n".join(dl_lines) if dl_lines else "")
            try:
                content = chat_text([{"role": "system", "content": system},
                                     {"role": "user", "content": user}],
                                    model=settings.deepseek_model_pro, purpose="brief",
                                    temperature=0.4, max_tokens=1600)
                model = settings.deepseek_model_pro
            except LlmError as e:
                # 兜底清单改为真实条目（标题+链接），不再贴未声明的 [#id] 伪引用
                content = (_fallback_md(date, n_new)
                           + f"\n> 晨报生成失败（{e}），以下为高分条目清单：\n\n"
                           + "\n".join(f"- {it.published_at}《{it.title}》{it.url}" for it, _an in rows[:8]))
                model = "fallback"
            meta = {"item_ids": [it.id for it, _ in rows],
                    "deadlines": [{"item_id": it.id, "date": an.deadline, "title": it.title}
                                  for it, an in deadlines],
                    "n_new": n_new}

        if existing:
            existing.content_md, existing.model, existing.meta, existing.created_at = content, model, meta, now_iso()
            bid = existing.id
        else:
            b = Brief(date=date, content_md=content, model=model, meta=meta)
            db.add(b)
            db.flush()
            bid = b.id
        log_event("brief.generated", date=date, model=model, items=len(meta["item_ids"]))
        return {"date": date, "created": True, "id": bid}
