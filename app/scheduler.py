"""进程内调度（APScheduler，Asia/Shanghai）。

约束：uvicorn 必须单 worker（多 worker 会重复调度）——见 AGENTS.md。
每源实际频率由 sources.yml 的 schedule_minutes 控制；这里的 ingest tick
只是"检查谁到期了"。
"""
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.log import log_event

_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


def _ingest_tick():
    from app.ingest.pipeline import run_all
    from app.llm.analyst import analyze_pending
    try:
        results = run_all(only_due=True)
        if any(r.get("new") for r in results):
            analyze_pending()
    except Exception as e:
        log_event("scheduler.ingest_error", error=f"{type(e).__name__}: {e}")


def _analyze_tick():
    from app.llm.analyst import analyze_pending
    try:
        analyze_pending()
    except Exception as e:
        log_event("scheduler.analyze_error", error=f"{type(e).__name__}: {e}")


def _brief_job():
    from app.llm.analyst import analyze_pending
    from app.llm.briefing import generate_brief
    try:
        analyze_pending()  # 出报前把存量分析完
        generate_brief(force=False)
    except Exception as e:
        log_event("scheduler.brief_error", error=f"{type(e).__name__}: {e}")


def _evolve_job():
    from app.llm.evolver import run_evolution
    try:
        run_evolution()
    except Exception as e:
        log_event("scheduler.evolve_error", error=f"{type(e).__name__}: {e}")


def start_scheduler() -> None:
    global _scheduler
    with _lock:
        if _scheduler is not None:
            return
        sch = BackgroundScheduler(timezone=settings.tz)
        sch.add_job(_ingest_tick, IntervalTrigger(minutes=30, jitter=90),
                    id="ingest", name="采集到期源", max_instances=1, coalesce=True)
        sch.add_job(_analyze_tick, IntervalTrigger(minutes=10),
                    id="analyze", name="补分析", max_instances=1, coalesce=True)
        sch.add_job(_brief_job, CronTrigger(hour=settings.brief_hour, minute=settings.brief_minute),
                    id="brief", name="每日晨报", max_instances=1, coalesce=True)
        sch.add_job(_evolve_job, CronTrigger(day_of_week="sun", hour=21, minute=0),
                    id="evolve", name="每周进化", max_instances=1, coalesce=True)
        sch.start()
        _scheduler = sch
        log_event("scheduler.started", jobs=[j.id for j in sch.get_jobs()], tz=settings.tz)


def stop_scheduler() -> None:
    global _scheduler
    with _lock:
        if _scheduler is not None:
            _scheduler.shutdown(wait=False)
            _scheduler = None


def job_overview() -> list[dict]:
    if _scheduler is None:
        return []
    return [{"id": j.id, "name": j.name,
             "next_run": j.next_run_time.isoformat() if j.next_run_time else None}
            for j in _scheduler.get_jobs()]
