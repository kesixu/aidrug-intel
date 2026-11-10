"""源停滞巡检 —— 补齐"静默停摆"告警缺口 (2026-10-06)

背景：本轮审计发现 aidrug 会在源静默停摆时完全无声。
现场证据：2026-10-02 ~ 10-06 连续 5 天晨报 model='none'（零候选条目），
而系统状态一切正常（source ok=9, down=0），没有任何告警。根因是
_is_due 日粒度导致 120 分钟周期的源一天只抓一次，加上没有"源太久没成功"
的巡检。日粒度已修，这里补第二道防线。

本模块只读；判定结果通过 log_event 输出，供 cron/看板消费。
"""
import json
import sys
from datetime import datetime, timedelta, timezone

from app.db import session_scope
from app.log import log_event
from app.models import Item, Source

# 源"最后一次成功抓取"超过 期望周期 × 该倍数，判为停滞
STALE_MULTIPLIER = 4
# 绝对下限：即使周期很短，也不早于这个时间报警，避免抖动误报
STALE_FLOOR_HOURS = 6


def _parse(ts: str):
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def inspect(stale_days_for_nothing_new: int = 7) -> dict:
    """返回 {stale: [...], silent: [...], ok: [...]}。

    stale  —— 源太久没有成功抓取（抓取层问题：改版、被墙、证书）
    silent —— 源抓取正常但长期零新增（内容层问题：真的没新闻，或解析器静默失配）
    """
    now = datetime.now(timezone.utc)
    stale, silent, ok = [], [], []

    with session_scope() as db:
        srcs = db.query(Source).filter(Source.enabled.is_(True)).all()
        for s in srcs:
            cfg = s.config or {}
            expect_min = int(cfg.get("schedule_minutes", 240))
            threshold = max(timedelta(minutes=expect_min * STALE_MULTIPLIER),
                            timedelta(hours=STALE_FLOOR_HOURS))
            last_ok = _parse(s.last_success_at)

            if last_ok is None or (now - last_ok) > threshold:
                stale.append({
                    "id": s.id, "name": s.name, "health": s.health,
                    "last_success_at": s.last_success_at,
                    "expect_minutes": expect_min,
                    "hours_since": round((now - last_ok).total_seconds() / 3600, 1) if last_ok else None,
                    "consecutive_failures": s.consecutive_failures,
                })
                continue

            # 抓取正常 → 看内容层是否有新增
            since = (now - timedelta(days=stale_days_for_nothing_new)).strftime("%Y-%m-%dT%H:%M:%SZ")
            n = (db.query(Item).filter(Item.source_id == s.id,
                                       Item.fetched_at >= since).count())
            if n == 0:
                silent.append({"id": s.id, "name": s.name, "tier": s.tier,
                               "days_without_new": stale_days_for_nothing_new})
            else:
                ok.append({"id": s.id, "new_items": n})

    return {"stale": stale, "silent": silent, "ok": ok,
            "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}


def main() -> int:
    rep = inspect()
    log_event("source.patrol",
              stale=len(rep["stale"]), silent=len(rep["silent"]), ok=len(rep["ok"]))
    for s in rep["stale"]:
        log_event("source.stale", **s)
    for s in rep["silent"]:
        log_event("source.silent", **s)

    print(json.dumps(rep, ensure_ascii=False, indent=2))
    # 有停滞源 → 非零退出，便于 cron 告警。静默源只提示不算失败（可能真的没新闻）
    return 1 if rep["stale"] else 0


if __name__ == "__main__":
    sys.exit(main())
